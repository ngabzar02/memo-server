"""Ingest: fetch docs -> trafilatura -> chunks (256 tokens, overlap 50).

Sources: llms-full.txt / llms.txt (list of markdown links) or direct URL.
"""

import re
import time

import httpx

CHUNK_TOKENS = 256
OVERLAP_TOKENS = 50

_trafilatura = None


def _extract(text: str) -> str:
    """Lazy import trafilatura (~1s) — server start harus cepat utk MCP
    handshake 30s (ARM contention saat 2 server start bersamaan)."""
    global _trafilatura
    if _trafilatura is None:
        import trafilatura
        _trafilatura = trafilatura
    return _trafilatura.extract(text, include_comments=False) or ""


def fetch_text(url: str, timeout: int = 20) -> str | None:
    try:
        r = httpx.get(url, timeout=timeout, follow_redirects=True,
                      headers={"User-Agent": "memo/1.0"})
        if r.status_code != 200:
            return None
        if "text/html" in r.headers.get("content-type", "") or r.text.strip().startswith("<"):
            return _extract(r.text)
        return r.text  # plain text (llms.txt / llms-full.txt)
    except httpx.HTTPError:
        return None


def parse_llms(text: str) -> list[dict]:
    """Parse llms.txt: markdown links -> [{url, title}]."""
    out = []
    for line in text.splitlines():
        m = re.match(r"^\s*[-*\d.]*\s*\[([^\]]+)\]\((\S+)\)", line)
        if m and m.group(2).startswith("http"):
            out.append({"url": m.group(2), "title": m.group(1)})
    return out


def chunk_text(text: str, max_tokens: int = CHUNK_TOKENS, overlap: int = OVERLAP_TOKENS) -> list[str]:
    """Split by sections (heading-aware): tiap section H1-H4 jadi unit sendiri,
    heading ikut sebagai breadcrumb; code block tidak dipotong."""
    lines = text.splitlines()
    sections, cur = [], []
    for ln in lines:
        is_h = re.match(r"^#{1,4} ", ln) is not None
        in_code = [l.startswith("```") for l in cur[::-1]]
        if is_h and not any(in_code):
            if cur:
                sections.append("\n".join(cur))
            cur = [ln]
        else:
            cur.append(ln)
    if cur:
        sections.append("\n".join(cur))
    # split ulang section raksasa (hard cap ~4x max_tokens)
    out = []
    for sec in sections:
        if len(sec) <= max_tokens * 4:
            out.append(sec)
            continue
        para = [p.strip() for p in re.split(r"\n\s*\n", sec) if p.strip()]
        cur2, cur_tok = [], 0
        for p in para:
            pt = max(1, len(p) // 4)
            if cur2 and cur_tok + pt > max_tokens:
                out.append("\n\n".join(cur2))
                cur2, cur_tok = [], 0
            cur2.append(p)
            cur_tok += pt
        if cur2:
            out.append("\n\n".join(cur2))
    return out or [text]


def ingest_docs(url: str) -> list[dict]:
    """Fetch one page -> [{path, title, text}]."""
    text = fetch_text(url)
    if not text:
        return []
    chunks = chunk_text(text)
    title = re.sub(r"^#+\s*", "", text.splitlines()[0])[:80] if text.splitlines() else url
    return [{"path": url, "title": title, "text": c} for c in chunks]


def _gh_raw(docs_url: str) -> list[dict] | None:
    """Halaman GitHub repo -> raw README (halaman JS berat, llms.txt jarang)."""
    m = re.match(r"https?://github\.com/([\w.-]+/[\w.-]+)", docs_url.rstrip("/"))
    if not m:
        return None
    for branch in ("main", "master"):
        for fname in ("README.md", "README.rst", "README.txt"):
            text = fetch_text(f"https://raw.githubusercontent.com/{m.group(1)}/{branch}/{fname}")
            if text:
                chunks = chunk_text(text)
                return [{"path": f"https://raw.githubusercontent.com/{m.group(1)}/{branch}/{fname}",
                         "title": fname, "text": c} for c in chunks]
    return None


def _crawl(start_url: str, deadline: float, existing: set[str] | None = None,
           query: str = "") -> list[dict]:
    """Docs tanpa llms.txt/sitemap (numpy, requests, dll): BFS ber-tingkat dgn
    prioritas tutorial/user/reference + URL yg match kata kunci query (halaman
    yg paling mungkin menjawab diproses duluan), fetch 4 PARALEL. Budget
    deadline + cap 200 chunk. existing: path sudah ter-chunk di DB -> skip."""
    import urllib.parse as up
    from concurrent.futures import ThreadPoolExecutor
    base = start_url.rstrip("/") + "/"  # urljoin butuh dir base (tanpa slash = file)
    terms = [t.lower() for t in re.findall(r"[a-z]+", query.lower()) if len(t) > 3]

    def page(url: str) -> tuple[str | None, str]:
        try:
            r = httpx.get(url, timeout=8, follow_redirects=True,
                          headers={"User-Agent": "memo/1.0"})
        except httpx.HTTPError:
            return None, ""
        if r.status_code != 200:
            return None, ""
        text = _extract(r.text) or ""
        return text, r.text  # text utk chunk, html mentah utk link BFS

    def prio(u: str) -> int:
        # URL yg match query term = -1 (diproses duluan: jawab relevansi cepat)
        ul = u.lower()
        if any(t in ul for t in terms):
            return -1
        if any(s in u for s in ("/basics", "basics.", "/tutorial", "/getting-started", "/user/")):
            return 0
        if any(s in u for s in ("/reference/", "/guide/", "/api/", "/en/latest/")):
            return 1
        return 2

    seen, out, queue = set(), [], [base]
    existing = existing or set()
    with ThreadPoolExecutor(max_workers=4) as ex:
        while queue and time.monotonic() < deadline and len(out) < 200:
            # ambil batch URL prioritas tertinggi, fetch paralel.
            # ponytail: URL existing TETAP di-fetch (link extraction tetap jalan,
            # tiap call mengeksplorasi 1 tingkat baru — iterative deepening);
            # chunk-nya di-skip supaya tidak duplikat path.
            batch, frontier = [], []
            for url in sorted(queue, key=prio):  # prio 0 dulu (ascending)
                if url in seen:
                    continue
                if len(batch) >= 4:
                    break
                batch.append(url)
                seen.add(url)
            queue = [u for u in queue if u not in set(batch)]
            if not batch:
                break
            for url, (text, html) in zip(batch, ex.map(page, batch)):
                if not text:
                    continue
                if url not in existing:
                    title = re.sub(r"^#+\s*", "", text.splitlines()[0])[:80] if text.splitlines() else url
                    for c in chunk_text(text):
                        out.append({"path": url, "title": title, "text": c})
                    if len(out) >= 200:
                        break
                # link internal; relatif ke HALAMAN INI (bukan base) -> path benar
                nxt = []
                for href in re.findall(r'href="([^"#?]+)', html):
                    u = up.urljoin(url, href)
                    if (u.startswith(base) and u not in seen
                            and not any(s in u for s in ("_static", "_sources", "genindex", "search.html", "404", "whatsnew/", "release/"))):
                        nxt.append(u)
                queue.extend(nxt)
    return out


def ingest_lib(docs_url: str, deadline: float | None = None,
               existing: set[str] | None = None, query: str = "") -> tuple[list[dict], bool]:
    """docs_url + /llms-full.txt -> try llms-full, else llms, else single page.
    Returns (chunks, complete). complete=False bila deadline tercapai -> server
    menyimpan parsial dan melanjutkan di call berikutnya.
    ponytail: serial fetch; deadline None = tak terbatas (warmup)."""
    base = docs_url.rstrip("/")
    if deadline is None:
        deadline = time.monotonic() + 60
    for candidate in (f"{base}/llms-full.txt", f"{base}/llms.txt"):
        # probe pendek: llms.txt kecil; 404/slow = langsung ke sumber berikut.
        # deadline absolute: probe yg lama mencuri budget crawl.
        text = fetch_text(candidate, timeout=6)
        if not text or _looks_404(text):
            continue
        pages = parse_llms(text)
        if not pages:
            return ingest_docs(candidate), True
        out = []
        for p in pages:
            if time.monotonic() > deadline:
                return out, False
            chunks = ingest_docs(p["url"])
            for c in chunks:
                c["path"] = f"{p['title']} ({p['url']})"
            out.extend(chunks)
            if len(out) > 300:  # cap chunks per library
                return out, True
        return out, True
    raw = _gh_raw(base)
    if raw is not None:
        return raw, True
    if not base.startswith(("https://github.com/", "http://github.com/")):
        crawled = _crawl(base, deadline, existing, query=query)
        if crawled:
            return crawled, True
    return ingest_docs(base), True


def _looks_404(text: str) -> bool:
    """Sphinx/static docs mengembalikan 404 page dgn status 200: teks pendek
    berisi 'page you're looking for'/'not found'. llms.txt palsu ini meracuni
    korpus (1 chunk sampah, terdeteksi saat debug R2 sqlalchemy)."""
    t = text.lower()
    return len(text) < 2000 and ("page you're looking for" in t or "not found" in t)


def _demo() -> None:
    llms = parse_llms("- [Flask](https://flask.palletsprojects.com/)\n- [API](https://flask.palletsprojects.com/api/)")
    assert len(llms) == 2, "parse_llms gagal"
    chunks = chunk_text("\n\n".join(f"Para {i} " + "B." * 400 for i in range(20)))
    assert len(chunks) >= 2, f"chunk_text gagal: {len(chunks)} chunk"
    print(f"SELFCHECK ingest: PASS (parse {len(llms)} link, {len(chunks)} chunk dari 4000 char)")


if __name__ == "__main__":
    _demo()
