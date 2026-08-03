"""Registry: resolve library name -> {id, repo, docs_url, trust, latest_ver, versions}.

Resolve chain (blueprint):
1. directory.llmstxt.cloud (global catalog) -> docs_url
2. npm/PyPI JSON API -> repo + latest version
3. GitHub search API (token from search-mcp config) -> repo fallback
Trust = log(downloads npm + stars GitHub) — metadata quality, Context7 trustScore-like.
"""

import json
import math
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

_GH_CFG = Path.home() / ".config" / "search-mcp" / "config.json"

_BUILTINS = json.loads((Path(__file__).parent / "builtins.json").read_text())
_ALIASES = json.loads((Path(__file__).parent / "aliases.json").read_text())


def _alias(name: str) -> dict | None:
    """Alias manual (nama ambigu: httpx, go, nextjs, dotenv, react...) — trust 95."""
    a = _ALIASES.get(name.lower())
    if not a:
        return None
    return {"id": _clean_id(name), "name": name, **a}


def _builtin(name: str, query: str = "") -> dict | None:
    """Node/Python stdlib: trust tinggi, docs_url langsung per modul.
    id override "node:fs"/"py:os" agar tidak tabrakan nama antar-bahasa."""
    base = name.split(":", 1)[-1] if ":" in name else name
    node = base in _BUILTINS["node"]
    py = base in _BUILTINS["python"]
    if not (node or py):
        return None
    prefer_py = "python" in query.lower() or "import " in query.lower()
    if node and (not py or not prefer_py):
        return {"id": f"node:{base}", "repo": "nodejs/node",
                "docs_url": f"https://nodejs.org/docs/latest/api/{_BUILTINS['node'][base]}",
                "trust": 99.0, "latest_ver": ""}
    if py:
        return {"id": f"py:{base}", "repo": "python/cpython",
                "docs_url": f"https://docs.python.org/3/library/{_BUILTINS['python'][base]}",
                "trust": 98.0, "latest_ver": ""}
    return {"id": f"node:{base}", "repo": "nodejs/node",
            "docs_url": f"https://nodejs.org/docs/latest/api/{_BUILTINS['node'][base]}",
            "trust": 99.0, "latest_ver": ""}


def _read_gh_token() -> str:
    try:
        return json.loads(_GH_CFG.read_text()).get("github_token", "")
    except Exception:
        return ""


GH_TOKEN = (os.environ.get("GITHUB_TOKEN")           # GitHub Actions runner
            or os.environ.get("SEARCH_MCP_GITHUB_TOKEN")
            or _read_gh_token())


def _gh_headers() -> dict:
    return {"Authorization": f"Bearer {GH_TOKEN}"} if GH_TOKEN else {}


def _clean_id(name: str) -> str:
    return re.sub(r"[^a-z0-9-]", "-", name.lower()).strip("-")


def version_etag(name: str, old_etag: str = "") -> tuple[str, str, list[str]]:
    """Cek versi terbaru + riwayat dgn conditional GET (ETag 304 = tidak berubah).
    Returns (latest_ver, etag_baru, versions). TTL dipegang server via last_check.
    Pilih sumber versi TERBANYAK (versions_of): npm 'flask' (1 versi kuno) kalah
    dari PyPI flask resmi (100+) — mencegah versi npm-junk menimpa versi asli."""
    vs = versions_of(name)
    if vs:
        return vs[0], "", vs[:20]
    return "", old_etag, []


def _dir_entry(name: str) -> dict | None:
    """directory.llmstxt.cloud: GET /{name}/llms.txt -> docs_url."""
    try:
        r = httpx.get(f"https://directory.llmstxt.cloud/{_clean_id(name)}/llms.txt",
                      timeout=3, follow_redirects=True)
        if r.status_code == 200 and len(r.text) > 100:
            return {"docs_url": str(r.url).removesuffix("llms.txt")}
    except httpx.HTTPError:
        pass
    return None


def _stable_versions(all_versions: list[str], max_n: int = 20) -> list[str]:
    """Filter stable (tolak rc/a/b/dev/post + yanked), urut semver desc."""
    from packaging.version import Version
    stable = []
    for v in all_versions:
        try:
            pv = Version(v)
        except Exception:  # noqa: BLE001
            continue
        if pv.is_prerelease or pv.is_devrelease or pv.is_postrelease:
            continue
        stable.append(v)
    stable.sort(key=lambda v: Version(v), reverse=True)
    return stable[:max_n]


def _npm(name: str) -> dict | None:
    try:
        # dist-tags endpoint kecil (~55B) utk latest; metadata penuh utk history
        r = httpx.get(f"https://registry.npmjs.org/-/package/{name}/dist-tags", timeout=6)
        if r.status_code != 200:
            return None
        latest = r.json().get("latest", "")
        r = httpx.get(f"https://registry.npmjs.org/{name}", timeout=8,
                      headers={"Accept": "application/vnd.npm.install-v1+json"})
        if r.status_code != 200:
            return None
        d = r.json()
        repo = ""
        for key in ("repository", "homepage"):
            v = d.get(key)
            if isinstance(v, dict):
                repo = v.get("url", "")
            elif isinstance(v, str):
                repo = v
            if repo:
                break
        m = re.search(r"github.com[/:]([\w.-]+/[\w.-]+)", repo)
        repo = m.group(1).removesuffix(".git") if m else ""
        docs = d.get("homepage") or ""
        dl = 0
        try:
            dl = httpx.get(f"https://api.npmjs.org/downloads/point/last-month/{name}",
                           timeout=6).json().get("downloads", 0)
        except (httpx.HTTPError, ValueError):
            pass
        versions = _stable_versions(list(d.get("versions", {}).keys()))
        return {"repo": repo, "latest_ver": latest,
                "trust": math.log10(max(dl, 1)),  # downloads bulanan npm gratis
                "docs_url": docs, "versions": versions}
    except (httpx.HTTPError, ValueError):
        return None


def _crates(name: str) -> dict | None:
    """crates.io: max_version + yanked flag per versi (anon, tanpa ETag)."""
    try:
        r = httpx.get(f"https://crates.io/api/v1/crates/{name}", timeout=6)
        if r.status_code != 200:
            return None
        d = r.json()
        crate = d.get("crate", {})
        vs = []
        for v in d.get("versions", []):
            if not v.get("yanked"):
                vs.append(v.get("num", ""))
        return {"repo": "", "latest_ver": crate.get("max_version", ""),
                "trust": 0.0, "docs_url": "",
                "versions": _stable_versions(vs)}
    except (httpx.HTTPError, ValueError, KeyError):
        return None


def _go(name: str) -> dict | None:
    """Go module proxy: @latest (retracted sudah dikecualikan) + @v/list."""
    try:
        r = httpx.get(f"https://proxy.golang.org/{name}/@latest", timeout=6)
        if r.status_code != 200:
            return None
        latest = r.json().get("Version", "")
        r = httpx.get(f"https://proxy.golang.org/{name}/@v/list", timeout=6)
        vs = r.text.split() if r.status_code == 200 else []
        return {"repo": "", "latest_ver": latest, "trust": 0.0,
                "docs_url": "", "versions": _stable_versions(vs)}
    except (httpx.HTTPError, ValueError):
        return None


def _rubygems(name: str) -> dict | None:
    """RubyGems: version + yanked + documentation_uri (ETag 304 didukung)."""
    try:
        r = httpx.get(f"https://rubygems.org/api/v1/gems/{name}.json", timeout=6)
        if r.status_code != 200:
            return None
        d = r.json()
        r = httpx.get(f"https://rubygems.org/api/v1/versions/{name}.json", timeout=6)
        vs = []
        if r.status_code == 200:
            for v in r.json():
                if not v.get("yanked") and not v.get("prerelease"):
                    vs.append(v.get("number", ""))
        return {"repo": "", "latest_ver": d.get("version", ""),
                "trust": 0.0, "docs_url": d.get("documentation_uri", ""),
                "versions": _stable_versions(vs)}
    except (httpx.HTTPError, ValueError, KeyError):
        return None


def _pypi(name: str) -> dict | None:
    try:
        r = httpx.get(f"https://pypi.org/pypi/{name}/json", timeout=6)
        if r.status_code != 200:
            return None
        d = r.json()  # releases ada di top-level, bukan di "info"
        info = d["info"]
        urls = info.get("project_urls") or {}
        # Documentation > Source/homepage: docs resmi langsung, hemat dir_entry
        docs = urls.get("Documentation") or urls.get("Documentation, ") or ""
        repo = next((urls[k] for k in ("Source", "Source Code", "Repository",
                                       "Homepage") if urls.get(k)), "")
        m = re.search(r"github.com[/:]([\w.-]+/[\w.-]+)", repo)
        return {"repo": m.group(1) if m else "", "latest_ver": info.get("version", ""),
                "trust": 0.0,  # PyPI JSON API tanpa download count; trust dari GitHub/npm
                "docs_url": docs,
                "versions": _stable_versions(list(d.get("releases", {}).keys()))}
    except (httpx.HTTPError, ValueError, KeyError):
        return None


def versions_of(name: str) -> list[str]:
    """Riwayat versi dari SEMUA ekosistem (npm/PyPI/crates/Go/RubyGems).
    Pilih sumber dgn versi TERBANYAK: npm 'fastapi' (8 versi kuno) kalah dari
    PyPI fastapi resmi (100+); npm express (207) menang atas pypi express.
    Cache TTL sama dgn resolve (1 jam): alias path memanggil ini per request."""
    key = f"vo|{name}"
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < _CACHE_TTL:
        return hit[1]
    best: list[str] = []
    for fn in (_npm, _pypi, _crates, _go, _rubygems):
        try:
            hit = fn(name)
            if hit and hit.get("versions") and len(hit["versions"]) > len(best):
                best = hit["versions"]
        except Exception:  # noqa: BLE001
            continue
    _cache[key] = (time.monotonic(), best)
    return best


def _norm(s: str) -> str:
    """Normalize repo basename for fuzzy match: lower, strip [._-]."""
    return re.sub(r"[._\-]+", "", s.lower())


_LANGS = {"python", "javascript", "typescript", "go", "rust", "java",
          "kotlin", "swift", "ruby", "php", "c", "c++", "dart"}


def _gh_search(name: str, query: str = "") -> dict | None:
    if not GH_TOKEN:
        return None
    # namespaced/builtin (node:events, @scope/pkg) punya repo ambigu → jangan fallback
    if ":" in name or "/" in name:
        return None
    lang = ""
    for w in re.findall(r"[A-Za-z+#]+", query.lower()):
        if w in _LANGS:
            lang = w
            break
    qual = f" language:{lang}" if lang else ""
    queries = [f"{name} in:name{qual}", f"{name}{qual}"]

    def pick(items: list) -> dict | None:
        if not items:
            return None
        want = _norm(name)
        for it in items:
            if _norm(it["name"]) == want:
                return {"repo": it["full_name"], "latest_ver": "",
                        "docs_url": it.get("html_url", ""),
                        "trust": math.log10(max(it.get("stargazers_count", 0), 1))}
        return {"repo": items[0]["full_name"], "latest_ver": "",
                "docs_url": items[0].get("html_url", ""),
                "trust": math.log10(max(items[0].get("stargazers_count", 0), 1))}

    try:
        first = None
        for q in queries:
            r = httpx.get("https://api.github.com/search/repositories",
                          params={"q": q, "sort": "stars", "per_page": 10},
                          headers=_gh_headers(), timeout=10)
            if r.status_code != 200:
                return None
            items = r.json().get("items", [])
            hit = pick(items)
            first = first or hit
            if hit and _norm(hit["repo"].split("/")[-1]) == _norm(name):
                return hit
        return first
    except (httpx.HTTPError, ValueError, KeyError):
        return None


def _norm_url(docs_url: str | None) -> str:
    return (docs_url or "").rstrip("/")


def _is_gh_url(u: str) -> bool:
    """True utk github page/README raw — docs_url ini TIDAK dipakai utk crawl."""
    return u.startswith(("https://github.com/", "http://github.com/",
                         "https://raw.githubusercontent.com/"))


_CACHE_TTL = 3600  # 1 jam: resolve mahal (6 sumber jaringan); hit ~0ms
_cache: dict[str, tuple[float, list[dict]]] = {}

# --- trust engine ----------------------------------------------------------
# skor akhir = skor sumber (npm downloads / stars GH / alias curated) +
#              +2.0 llms.txt hadir (AI-ready) + penalti fork/README:
#              -2.0 repo != nama dicari (fork), -1.0 docs_url = github README.

_LLMS_CACHE: dict[str, tuple[float, bool]] = {}


def _has_llms(docs_url: str) -> bool:
    """HEAD {docs}/llms.txt (timeout 3s, cache TTL 24h) — sinyal AI-ready."""
    if not docs_url:
        return False
    hit = _LLMS_CACHE.get(docs_url)
    if hit and time.monotonic() - hit[0] < 86400:
        return hit[1]
    try:
        r = httpx.get(f"{docs_url.rstrip('/')}/llms.txt", timeout=3,
                      follow_redirects=True)
        ok = r.status_code == 200 and len(r.text) > 50
    except httpx.HTTPError:
        ok = False
    _LLMS_CACHE[docs_url] = (time.monotonic(), ok)
    return ok


def _stars_of(repo: str) -> float:
    """Stars GitHub via API repo (anon, rate limit 60/h). 0 bila gagal."""
    if not repo:
        return 0.0
    try:
        r = httpx.get(f"https://api.github.com/repos/{repo}", timeout=4,
                      headers=_gh_headers())
        if r.status_code == 200:
            return float(r.json().get("stargazers_count", 0))
    except httpx.HTTPError:
        pass
    return 0.0


def _trust_final(c: dict, name: str) -> None:
    """Fusion skor sumber + sinyal kualitas. Mutasi c['trust']."""
    base = float(c.get("trust", 0.0))
    repo = c.get("repo", "")
    docs = c.get("docs_url", "")
    stars = _stars_of(repo)
    llms = _has_llms(docs)
    # log10 downloads/stars -> skor 0-7; stars > downloads (lebih terspesialisasi)
    base = max(base, math.log10(max(stars, 1)))
    fork_penalty = -2.0 if repo and _norm(repo.split("/")[-1]) != _norm(name) else 0.0
    readme_penalty = -1.0 if "github.com" in docs else 0.0
    c["trust"] = max(0.0, round(base + (2.0 if llms else 0.0) + fork_penalty + readme_penalty, 2))


def _enrich(cands: list[dict], name: str) -> None:
    """Trust final utk semua kandidat: stars+llms paralel (network murah)."""
    with ThreadPoolExecutor(max_workers=4) as ex:
        list(ex.map(lambda c: _trust_final(c, name), cands))


def resolve(name: str, query: str = "") -> list[dict]:
    """Return candidates [{id, name, repo, docs_url, trust, latest_ver, versions}].
    TTL-cache per name: resolve penuh = 6 panggilan jaringan ~14s di ARM."""
    key = f"{name}|{query}"
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < _CACHE_TTL:
        return hit[1]
    out = _resolve(name, query)
    _cache[key] = (time.monotonic(), out)
    return out


def _norm_cand(hit: dict, name: str) -> dict:
    return {
        "id": hit.get("id") or _clean_id(name),
        "name": name,
        "repo": hit.get("repo", ""),
        "docs_url": _norm_url(hit.get("docs_url", "")),
        "trust": float(hit.get("trust", 0.0)),
        "latest_ver": hit.get("latest_ver", ""),
        "versions": json.dumps(hit.get("versions") or ([hit["latest_ver"]] if hit.get("latest_ver") else [])),
    }


def _resolve(name: str, query: str = "") -> list[dict]:
    """6 sumber network dijalankan PARALEL (ThreadPool): resolve 12.5s -> ~2-3s.
    alias/builtin instan -> langsung saja; sisanya paralel."""
    cands = []
    for fn in (lambda: _alias(name), lambda: _builtin(name, query)):
        hit = fn()
        if hit:
            cands.append(hit)
            if "trust" in hit and float(hit.get("trust", 0)) > 90:
                return [_norm_cand(hit, name)]  # alias/builtin curated: final, tanpa network
    with ThreadPoolExecutor(max_workers=6) as ex:
        futures = {ex.submit(fn): label for label, fn in (
            ("llmstxt", lambda: _dir_entry(name)),
            ("npm", lambda: _npm(name)),
            ("pypi", lambda: _pypi(name)),
            ("crates", lambda: _crates(name)),
            ("rubygems", lambda: _rubygems(name)),
            ("github", lambda: _gh_search(name, query)))}
        for f, label in futures.items():
            try:
                hit = f.result()
            except Exception:  # noqa: BLE001 — satu sumber gagal, lanjut
                continue
            if not hit:
                continue
            cands.append(_norm_cand(hit, name))
    # dedupe by repo/docs_url: keep highest trust, merge non-empty fields
    seen, out = {}, []
    for c in sorted(cands, key=lambda c: -c["trust"]):
        key = c["repo"] or c["docs_url"]
        if not key:
            out.append(c)
            continue
        if key in seen:
            cur = out[seen[key]]
            for k, v in c.items():  # merge missing info (e.g. latest_ver from PyPI)
                if not v:
                    continue
                if k == "docs_url":
                    # docs resmi (bukan github page) MENANG atas github README
                    if not cur.get(k) or (_is_gh_url(cur[k]) and not _is_gh_url(v)):
                        cur[k] = v
                elif (not cur.get(k)) or (k == "versions" and cur.get(k) in ("[]", "")):
                    cur[k] = v
            continue
        seen[key] = len(out)
        out.append(c)
    # buang noise: entri tanpa repo & docs_url (PyPI/npm bare: tak bisa dipakai
    # get_docs) — info versinya di-merge dulu ke kandidat lain dgn id sama
    # (npm tsup: repo/docs kosong padahal latest_ver 8.5.1 -> Bug 6)
    kept = [c for c in out if c["repo"] or c["docs_url"]]
    for c in out:
        if c["repo"] or c["docs_url"]:
            continue
        for k in kept:
            if k["id"] == c["id"]:
                if not k.get("latest_ver"):
                    k["latest_ver"] = c.get("latest_ver", "")
                if k.get("versions") in ("[]", ""):
                    k["versions"] = c.get("versions") or "[]"
    out = kept
    _enrich(out, name)  # trust final: stars + llms.txt + penalti fork/README
    out.sort(key=lambda c: -c["trust"])
    return out


def _demo() -> None:
    r = resolve("flask")
    assert r, "resolve flask kosong"
    top = r[0]
    fs = resolve("node:events")[0]
    assert fs["id"] == "node:events" and fs["trust"] > 50, f"builtin node gagal: {fs}"
    os_py = resolve("os", "python import os list files")[0]
    assert os_py["id"] == "py:os", f"prefer python gagal: {os_py}"
    httpx = resolve("httpx")[0]
    assert httpx["repo"] == "encode/httpx", f"alias httpx gagal: {httpx}"
    assert resolve("nextjs")[0]["repo"] == "vercel/next.js", "alias nextjs gagal"
    print(f"SELFCHECK registry: PASS ({len(r)} kandidat, top={top['name']} "
          f"trust={top['trust']:.2f} ver={top['latest_ver']} repo={top['repo']})")


if __name__ == "__main__":
    _demo()
