"""Ingest: fetch docs -> trafilatura -> chunks (256 tokens, overlap 50).

Sources: llms-full.txt / llms.txt (list of markdown links) or direct URL.
"""

import re
import time

import httpx
import trafilatura

CHUNK_TOKENS = 256
OVERLAP_TOKENS = 50


def fetch_text(url: str, timeout: int = 20) -> str | None:
    try:
        r = httpx.get(url, timeout=timeout, follow_redirects=True,
                      headers={"User-Agent": "memo/1.0"})
        if r.status_code != 200:
            return None
        if "text/html" in r.headers.get("content-type", "") or r.text.strip().startswith("<"):
            return trafilatura.extract(r.text, include_comments=False) or ""
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
    """Split by paragraphs into ~max_tokens (~4 chars/token), overlap paragraphs."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks, cur, cur_tokens = [], [], 0
    for p in paras:
        # hard-cut a single oversized paragraph (e.g. minified README)
        while len(p) > max_tokens * 4:
            cut = p[: max_tokens * 4]
            p = p[max_tokens * 4:]
            if cur:
                chunks.append("\n\n".join(cur))
                cur, cur_tokens = [], 0
            chunks.append(cut)
        pt = max(1, len(p) // 4)
        if cur and cur_tokens + pt > max_tokens:
            chunks.append("\n\n".join(cur))
            # overlap: keep tail paragraphs up to overlap budget
            tail, tt = [], 0
            for q in reversed(cur):
                if tt + max(1, len(q) // 4) > overlap:
                    break
                tail.insert(0, q)
                tt += max(1, len(q) // 4)
            cur, cur_tokens = tail, tt
        cur.append(p)
        cur_tokens += pt
    if cur:
        chunks.append("\n\n".join(cur))
    return chunks or [text]


def ingest_docs(url: str) -> list[dict]:
    """Fetch one page -> [{path, title, text}]."""
    text = fetch_text(url)
    if not text:
        return []
    chunks = chunk_text(text)
    title = re.sub(r"^#+\s*", "", text.splitlines()[0])[:80] if text.splitlines() else url
    return [{"path": url, "title": title, "text": c} for c in chunks]


def ingest_lib(docs_url: str) -> list[dict]:
    """docs_url + /llms-full.txt -> try llms-full, else llms, else single page.
    ponytail: serial fetch, global time budget ~60s (40 pages x 20s would hang)."""
    base = docs_url.rstrip("/")
    deadline = time.monotonic() + 60
    for candidate in (f"{base}/llms-full.txt", f"{base}/llms.txt"):
        text = fetch_text(candidate)
        if not text:
            continue
        pages = parse_llms(text)
        if not pages:
            return ingest_docs(candidate)
        out = []
        for p in pages:
            if time.monotonic() > deadline:
                break
            chunks = ingest_docs(p["url"])
            for c in chunks:
                c["path"] = f"{p['title']} ({p['url']})"
            out.extend(chunks)
            if len(out) > 300:  # cap chunks per library
                break
        return out
    return ingest_docs(base)


def _demo() -> None:
    llms = parse_llms("- [Flask](https://flask.palletsprojects.com/)\n- [API](https://flask.palletsprojects.com/api/)")
    assert len(llms) == 2, "parse_llms gagal"
    chunks = chunk_text("\n\n".join(f"Para {i} " + "B." * 400 for i in range(20)))
    assert len(chunks) >= 2, f"chunk_text gagal: {len(chunks)} chunk"
    print(f"SELFCHECK ingest: PASS (parse {len(llms)} link, {len(chunks)} chunk dari 4000 char)")


if __name__ == "__main__":
    _demo()
