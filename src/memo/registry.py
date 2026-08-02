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


def _dir_entry(name: str) -> dict | None:
    """directory.llmstxt.cloud: GET /{name}/llms.txt -> docs_url."""
    try:
        r = httpx.get(f"https://directory.llmstxt.cloud/{_clean_id(name)}/llms.txt",
                      timeout=10, follow_redirects=True)
        if r.status_code == 200 and len(r.text) > 100:
            return {"docs_url": str(r.url).removesuffix("llms.txt")}
    except httpx.HTTPError:
        pass
    return None


def _npm(name: str) -> dict | None:
    try:
        r = httpx.get(f"https://registry.npmjs.org/{name}", timeout=10)
        if r.status_code != 200:
            return None
        d = r.json()
        latest = d.get("dist-tags", {}).get("latest", "")
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
                           timeout=8).json().get("downloads", 0)
        except (httpx.HTTPError, ValueError):
            pass
        versions = list(d.get("versions", {}).keys())[-20:]  # history, terakhir dulu
        return {"repo": repo, "latest_ver": latest,
                "trust": math.log10(max(dl, 1)),  # downloads bulanan npm gratis
                "docs_url": docs, "versions": versions}
    except (httpx.HTTPError, ValueError):
        return None


def _pypi(name: str) -> dict | None:
    try:
        r = httpx.get(f"https://pypi.org/pypi/{name}/json", timeout=10)
        if r.status_code != 200:
            return None
        d = r.json()["info"]
        urls = d.get("project_urls") or {}
        repo = urls.get("Source", "") or d.get("home_page", "") or ""
        m = re.search(r"github.com[/:]([\w.-]+/[\w.-]+)", repo)
        return {"repo": m.group(1) if m else "", "latest_ver": d.get("version", ""),
                "trust": 0.0,  # PyPI JSON API tanpa download count; trust dari GitHub/npm
                "docs_url": "",
                "versions": list(d.get("releases", {}).keys())[-20:]}
    except (httpx.HTTPError, ValueError, KeyError):
        return None


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


def _norm_url(docs_url: str) -> str:
    return docs_url.rstrip("/")


def resolve(name: str, query: str = "") -> list[dict]:
    """Return candidates [{id, name, repo, docs_url, trust, latest_ver, versions}]."""
    cands = []
    for label, fn in (("alias", lambda: _alias(name)),
                      ("builtin", lambda: _builtin(name, query)),
                      ("llmstxt", lambda: _dir_entry(name)),
                      ("npm", lambda: _npm(name)),
                      ("pypi", lambda: _pypi(name)),
                      ("github", lambda: _gh_search(name, query))):
        hit = fn()
        if not hit:
            continue
        cands.append({
            "id": hit.get("id") or _clean_id(name),
            "name": name,
            "repo": hit.get("repo", ""),
            "docs_url": _norm_url(hit.get("docs_url", "")),
            "trust": float(hit.get("trust", 0.0)),
            "latest_ver": hit.get("latest_ver", ""),
            "versions": json.dumps(hit.get("versions") or ([hit["latest_ver"]] if hit.get("latest_ver") else [])),
        })
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
                if (not cur.get(k)) or (k == "versions" and cur.get(k) in ("[]", "")) and v:
                    cur[k] = v
            continue
        seen[key] = len(out)
        out.append(c)
    # buang noise: entri tanpa repo & docs_url (PyPI bare: tak bisa dipakai
    # get_docs) — info versinya sudah ter-merge via dedupe di atas
    return [c for c in out if c["repo"] or c["docs_url"]]


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
