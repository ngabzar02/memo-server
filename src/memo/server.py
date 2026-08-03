"""MCP server: resolve-library-id, get-docs, versions — Context7 API clone.

Usage: memo  (stdio MCP server, registered via uv tool install)
"""

import json
import logging
import os
import sqlite3
import sys
import threading
import time
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

from memo import ingest, registry, store

log = logging.getLogger("memo")
mcp = FastMCP("memo")

# activity log JSONL: dasar pemantauan benchmark via MCP langsung (BRUTAL.md).
_ACTIVITY = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "..", "..", "bench", "activity.log")


def _log_activity(entry: dict[str, Any]) -> None:
    """Append JSONL; gagal (permission/disk) tidak menggagalkan request."""
    try:
        with open(_ACTIVITY, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass

# ingest embed+sqlite thread-safe (ORT concurrent run TERUJI 6-thread aman);
# lock per-library hanya mencegah 2 ingest lib sama bersamaan.
_lib_locks: dict[str, threading.Lock] = {}
_lib_locks_guard = threading.Lock()

# Bug 3: hasil cek _docs_changed per lib, TTL 1 jam — hindari resolve (network)
# di tiap get_docs untuk lib yang docs_url-nya tidak berubah.
_docs_changed_cache: dict[str, float] = {}
_DOCS_CHANGED_TTL = 3600.0


def _lock_for(lib_id: str) -> threading.Lock:
    with _lib_locks_guard:
        return _lib_locks.setdefault(lib_id, threading.Lock())


def _embeddings():
    """Lazy singleton: model load ~0.7s (cache panas), RAM ~240MB."""
    if not hasattr(_embeddings, "model"):
        from fastembed import TextEmbedding

        # threads=2 + batch 8 = 89ms/chunk di ARM (vs 798ms default: thread
        # contention ORT). batch >8 diminishing; threads>2 contention.
        _embeddings.model = TextEmbedding("BAAI/bge-small-en-v1.5", threads=2)
    return _embeddings.model


_reranker = None


def _get_reranker():
    """Cross-encoder reranker (lazy, model qint8 ~25MB). top-10 rerank ~0.3-0.8s
    di ARM — default ON; gagal load (offline/hilang) -> fallback hybrid saja."""
    global _reranker
    if _reranker is None:
        try:
            from memo.rerank import CrossReranker
            _reranker = CrossReranker(threads=2)
        except Exception as e:  # noqa: BLE001
            log.warning("reranker off: %s", str(e)[:100])
            # FP-4 [P0-04]: fallback tidak senyap — catat metrik di activity log.
            _log_activity({"t": time.time(), "tool": "get_docs", "event": "fallback",
                           "kind": "rerank", "detail": str(e)[:100]})
            _reranker = False
    return _reranker or None


def _rerank(query: str, hits: list[dict[str, Any]], top_n: int = 10) -> list[dict[str, Any]]:
    """Skor ulang top-N hits dgn cross-encoder (query,doc) -> urut ulang.
    Fast path: <2 hits atau reranker off -> tanpa perubahan."""
    r = _get_reranker()
    if not r or len(hits) < 2:
        return hits
    pairs = [(query, h["text"][:1000]) for h in hits[:top_n]]
    try:
        scores = list(r.rerank(pairs))
        scored = sorted(zip(scores, hits[:top_n]), key=lambda s: -s[0])
        return [h for _, h in scored] + hits[top_n:]
    except Exception as e:  # noqa: BLE001
        log.warning("rerank failed: %s", str(e)[:100])
        return hits


@mcp.tool()
def resolve_library_id(library_name: str, query: str = "") -> list[dict[str, Any]]:
    """Resolve a library name (e.g. 'flask', 'nextjs') to candidate library IDs
    with trust scores and latest version. query is optional context to disambiguate."""
    t0 = time.monotonic()
    out = registry.resolve(library_name, query)
    # Bug 6: cands bisa kehilangan versi (npm bare dibuang di dedupe registry);
    # isi dari DB (hasil ingest sebelumnya) — tanpa network tambahan.
    conn = store.connect()
    for c in out:
        if c.get("latest_ver") and c.get("versions") not in ("[]", ""):
            continue
        db = store.get_lib(conn, c["id"])
        if db and db.get("latest_ver"):
            if not c.get("latest_ver"):
                c["latest_ver"] = db["latest_ver"]
            if c.get("versions") in ("[]", ""):
                c["versions"] = db.get("versions") or json.dumps([db["latest_ver"]])
    _log_activity({"t": time.time(), "tool": "resolve", "name": library_name,
                   "q": query, "ms": round((time.monotonic() - t0) * 1000),
                   "top": [{"id": c["id"], "trust": round(c["trust"], 1),
                            "docs": c.get("docs_url", "")[:60]} for c in out[:3]]})
    return out


@mcp.tool()
def get_docs(library_id: str, query: str, version: str | None = None) -> list[dict[str, Any]]:
    """Get relevant documentation chunks for a library and query.
    Cache hit: sub-ms. Cache miss: fetch+ingest+index once (~5-60s first time)."""
    with _lock_for(library_id):  # paralel antar lib; serial utk lib sama
        return _get_docs(library_id, query, version,
                         deadline=time.monotonic() + _REQUEST_BUDGET)

# batas waktu request MCP: client timeout ~30s lalu disconnect -> proses keluar.
# deadline 20s (bufer utk embed + resolve) menjamin request selesai sebelum
# timeout; sisa ingest dilanjutkan di call berikutnya (flag full=0 -> lanjut).
# Daemon+bridge: bridge timeout 120s, opencode request timeout tak diketahui ->
# 30s moderat; ingest dalam per call (iterative deepening). Embed FTS-only.
_REQUEST_BUDGET = 30.0


def _get_docs(library_id: str, query: str, version: str | None = None,
              deadline: float | None = None) -> list[dict[str, Any]]:
    t0 = time.monotonic()
    # FP-2 [P0-03]: query kosong/whitespace -> respon eksplisit [], BUKAN 10
    # chunk acak dari vec search (anti-false-positive).
    if not query or not query.strip():
        _log_activity({"t": time.time(), "tool": "get_docs", "lib": library_id,
                       "q": query, "ver": version or "", "ms": 0,
                       "reason": "empty_query", "top": []})
        return []
    conn = store.connect()
    lib = store.get_lib(conn, library_id)
    chunk_count = conn.execute(
        "SELECT COUNT(*) FROM chunks WHERE lib_id=?", (library_id,)
    ).fetchone()[0]
    if lib and not version:
        # docs_url berubah (lib pindah domain: fastmcp glama.ai -> gofastmcp.com)
        # -> drop chunks basi. _docs_changed cache TTL 1 jam -> resolve (network)
        # tidak dipanggil per request; registry.resolve juga TTL-cache sendiri.
        if _docs_changed(conn, library_id):
            lib = store.get_lib(conn, library_id)  # di-drop -> None
    if lib and not version:
        _maybe_refresh(conn, lib)  # freshness: versi baru -> drop chunks (re-ingest)
    has_chunks = lib is not None and chunk_count > 0
    full = (lib or {}).get("full", 1)
    if not lib:
        cands = registry.resolve(library_id, query)
        if not cands:
            return []
        lib = cands[0]
        lib["versions"] = json.dumps([lib["latest_ver"]] if lib.get("latest_ver") else [])
        store.upsert_lib(conn, lib)
        has_chunks = False
    ver = version or lib.get("latest_ver") or ""
    vec = _embeddings().embed([query])
    query_vec = [float(x) for x in list(vec)[0]]  # numpy float32 -> float, utk json.dumps
    hits = store.search(conn, library_id, query, k=10, query_vec=query_vec)
    if not has_chunks or (not version and not full):
        # lib baru / ingest parsial (deadline tercapai sebelumnya): fetch+index
        # lanjutan. hits kosong pd lib lengkap TIDAK memicu re-ingest.
        crawl_deadline = deadline - 2 if deadline else None  # FTS instan: sisakan utk index+search
        existing = {r[0] for r in conn.execute(
            "SELECT path FROM chunks WHERE lib_id=?", (library_id,))}
        chunks, complete = ingest.ingest_lib(
            lib.get("docs_url") or f"https://{lib.get('repo','')}",
            deadline=crawl_deadline, existing=existing, query=query)
        if not chunks:
            if not has_chunks:
                return []
            conn.execute("UPDATE libs SET full=? WHERE id=?", (1 if ingest.is_full(complete, len(chunks)) else 0, library_id))
            conn.commit()
        else:
            chunks = chunks[:200]  # cap: 200 embed ~3 menit di ARM; cukup utk top docs
            if deadline is None:
                # warmup/CI (tanpa budget): embed penuh utk release cache
                embs: list[list[float] | None] = []
                for i in range(0, len(chunks), 8):  # batch 8: optimal ORT ARM
                    embs.extend([[float(x) for x in e] for e in _embeddings().embed([c["text"] for c in chunks[i:i+8]])])
                store.add_chunks(conn, library_id, ver, chunks, embs)
            else:
                # MCP path: FTS-only. Embed chunk 256 token ~1-2s/chunk di ARM
                # (bge-small quantized) > budget 20s. Vec penuh dari pre-built
                # CI; hits tetap relevan via BM25+RRF (teruji broadcasting).
                store.add_chunks(conn, library_id, ver, chunks)
            conn.execute("UPDATE libs SET full=? WHERE id=?", (1 if ingest.is_full(complete, len(chunks)) else 0, library_id))
            conn.commit()
        hits = store.search(conn, library_id, query, k=10, query_vec=query_vec)
    hits = _rerank(query, hits)
    _log_activity({"t": time.time(), "tool": "get_docs", "lib": library_id,
                   "q": query, "ver": ver, "ms": round((time.monotonic() - t0) * 1000),
                   "top": [h["path"] for h in hits[:5]]})
    return store.trim_to_tokens(hits)


def _docs_changed(conn: sqlite3.Connection, library_id: str) -> bool:
    """True jika docs_url resolve != DB -> drop lib (minta re-ingest). Network:
    registry.resolve TTL-cache 1 jam; hasil per-lib di-cache in-memory di sini
    (TTL 1 jam) agar lib dgn resolve cache-miss tidak menunggu network."""
    lib = store.get_lib(conn, library_id)
    if not lib:
        return False
    now = time.monotonic()
    if now - _docs_changed_cache.get(library_id, -float("inf")) < _DOCS_CHANGED_TTL:
        return False
    cands = registry.resolve(library_id)
    if not cands:
        return False
    new_url = cands[0].get("docs_url") or f"https://{cands[0].get('repo', '')}"
    old_url = lib.get("docs_url") or f"https://{lib.get('repo', '')}"
    _docs_changed_cache[library_id] = now
    if new_url != old_url:
        store.drop_lib(conn, library_id)
        return True
    return False


def _maybe_refresh(conn: sqlite3.Connection, lib: dict) -> bool:
    """Freshness: cek versi terbaru periodik (TTL by popularitas: trust>5 = 1d,
    lain 7d). Versi berubah -> update + drop chunks (re-ingest saat dipakai).
    Returns True bila lib di-drop (perlu re-ingest)."""
    last = lib.get("last_check") or ""
    ttl = 86400 if float(lib.get("trust", 0)) > 5 else 604800
    if last:
        from datetime import datetime
        try:
            age = (datetime.utcnow() - datetime.fromisoformat(last)).total_seconds()
            if age < ttl:
                return False
        except ValueError:
            pass
    latest, _, vs = registry.version_etag(lib["id"], lib.get("etag", ""))
    conn.execute("UPDATE libs SET last_check=datetime('now') WHERE id=?", (lib["id"],))
    conn.commit()
    if latest and latest != lib.get("latest_ver"):
        conn.execute("UPDATE libs SET latest_ver=?, versions=? WHERE id=?",
                     (latest, json.dumps(vs or []), lib["id"]))
        # chunks versi lama DIBIARKAN (tetap relevan; re-ingest berikutnya
        # mengganti per-path). DELETE dulu terbukti merugikan: re-ingest
        # gagal deadline 20s -> lib jadi 0 chunk.
        conn.commit()
        return True
    return False


@mcp.tool()
def versions(library_id: str) -> list[str]:
    """List known versions for a library (history dari npm/PyPI bila tersedia)."""
    conn = store.connect()
    cands = registry.resolve(library_id)
    if cands:
        vs = json.loads(cands[0].get("versions") or "[]")
        if len(vs) > 1:  # merge pypi/npm sukses -> langsung pakai
            return vs
    vs = registry.versions_of(library_id)  # alias/curated: fetch ekosistem resmi
    if vs:
        if cands:
            cands[0]["versions"] = json.dumps(vs)
            store.upsert_lib(conn, cands[0])
        return vs
    return store.get_versions(conn, library_id)  # offline: DB (mungkin stale)


def _cache_libs() -> list[str]:
    """Daftar lib pre-build cache dari cache-libs.txt.
    Cari di CWD (CI: repo root) lalu di repo root saat dev; bukan site-packages."""
    here = Path(__file__).resolve()
    for base in (Path.cwd(), here.parents[2], here.parents[1]):
        f = base / "cache-libs.txt"
        if f.exists():
            return [l.strip() for l in f.read_text().splitlines()
                    if l.strip() and not l.startswith("#")]
    return []


def _build_cache(limit: int | None = None) -> None:
    """`--build-cache`: ingest semua lib cache-libs.txt -> docs.db siap upload.
    Dipakai di GitHub Actions (x86, RAM besar); jalankan dari repo root.
    Lib yang ada di aliases.json di-upsert dulu utk memotong resolve network."""
    try:
        aliases = json.loads((Path(__file__).resolve().parent / "aliases.json").read_text())
    except OSError:
        aliases = {}
    libs = _cache_libs()[:limit] if limit else _cache_libs()
    ok, fail = 0, []
    t0 = time.monotonic()
    conn = store.connect()
    for name in libs:
        a = aliases.get(name)
        if a:  # docs_url sudah pasti: skip resolve network
            store.upsert_lib(conn, {"id": name, "name": name, "repo": "", "trust": a.get("trust", 95),
                                    "docs_url": a["docs_url"], "latest_ver": "", "versions": "[]"})
        try:
            _get_docs(name, "overview usage documentation")
            ok += 1
            print(f"cache: {name} OK", flush=True)
        except Exception as e:  # noqa: BLE001 — satu lib gagal, lanjut
            fail.append((name, str(e)[:80]))
            print(f"cache: {name} FAIL {str(e)[:80]}", flush=True)
    print(f"cache: selesai {ok}/{len(libs)} dalam {round(time.monotonic() - t0)}s", flush=True)
    if fail:
        print(f"cache: GAGAL: {[n for n, _ in fail]}", flush=True)


_CACHE_REPO = os.environ.get("MEMO_CACHE_REPO", "ngabzar02/memo-server")


def _fetch_cache(force: bool = False, dry_run: bool = False) -> int:
    """`--fetch-cache`: unduh pre-built docs.db dari GitHub release terbaru.
    Asset: memo-cache.db.gz. Backup DB lama -> verifikasi integrity -> ganti.
    Versi terpakai dicatat di <docs.db dir>/cache.version (skip bila sama)."""
    import gzip
    import shutil
    import urllib.request

    api = f"https://api.github.com/repos/{_CACHE_REPO}/releases?per_page=1"
    try:
        with urllib.request.urlopen(urllib.request.Request(
                api, headers={"User-Agent": "memo"}), timeout=30) as r:
            releases = json.load(r)
    except Exception as e:  # noqa: BLE001
        print(f"cache: gagal cek release: {str(e)[:100]}", file=sys.stderr)
        return 1
    if not releases:
        print("cache: tidak ada release", file=sys.stderr)
        return 1
    ver = releases[0]["tag_name"]
    asset = next((a for a in releases[0].get("assets", [])
                  if a["name"] == "memo-cache.db.gz"), None)
    if not asset:
        # release terbaru bisa saja tanpa asset (tag manual); cari release
        # sebelumnya yang punya asset (max 10)
        page = f"https://api.github.com/repos/{_CACHE_REPO}/releases?per_page=10"
        try:
            with urllib.request.urlopen(urllib.request.Request(
                    page, headers={"User-Agent": "memo"}), timeout=30) as r:
                releases = json.load(r)
        except Exception:  # noqa: BLE001
            releases = []
        for rel in releases:
            a = next((x for x in rel.get("assets", [])
                      if x["name"] == "memo-cache.db.gz"), None)
            if a:
                ver, asset = rel["tag_name"], a
                break
    if not asset:
        print("cache: tidak ada release dengan asset memo-cache.db.gz", file=sys.stderr)
        return 1
    ver_file = Path(store.DEFAULT_DB).parent / "cache.version"
    cur = ver_file.read_text().strip() if ver_file.exists() else ""
    if not force and cur == ver:
        print(f"cache: sudah terbaru ({ver})")
        return 0
    if dry_run:
        print(f"cache: dry-run: {ver} ({asset['size']} B) -> {store.DEFAULT_DB}")
        return 0
    print(f"cache: unduh {ver} ({asset['size']} B)...")
    tmp = Path(store.DEFAULT_DB + ".gz")
    with urllib.request.urlopen(urllib.request.Request(
            asset["browser_download_url"], headers={"User-Agent": "memo"}), timeout=900) as r, \
            open(tmp, "wb") as f:
        shutil.copyfileobj(r, f)
    bak = Path(store.DEFAULT_DB + ".pre-cache")
    if Path(store.DEFAULT_DB).exists():
        shutil.move(store.DEFAULT_DB, bak)
    with gzip.open(tmp, "rb") as gz, open(store.DEFAULT_DB, "wb") as f:
        shutil.copyfileobj(gz, f)
    tmp.unlink(missing_ok=True)
    check = sqlite3.connect(store.DEFAULT_DB, timeout=30)
    ok = check.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    check.close()
    if not ok:
        shutil.move(bak, store.DEFAULT_DB)  # rollback
        print("cache: file korup, rollback ke DB lama", file=sys.stderr)
        return 1
    Path(store.DEFAULT_DB + "-wal").unlink(missing_ok=True)
    Path(store.DEFAULT_DB + "-shm").unlink(missing_ok=True)
    ver_file.write_text(ver)
    print(f"cache: OK — {ver} aktif. Restart daemon (mcp-boot.sh) agar dipakai.")
    return 0


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "--warmup":
        # Pre-ingest: cold fetch di MCP request > 30s timeout client, jadi
        # panaskan cache dari shell dulu: `memo --warmup flask node:fs`
        emb = _embeddings()
        force = "--force" in sys.argv[2:]
        for name in sys.argv[2:]:
            if name == "--force":
                continue
            cands = registry.resolve(name)
            if not cands:
                print(f"warmup: {name} -> tidak ditemukan", file=sys.stderr)
                continue
            c = cands[0]
            if force:
                store.drop_lib(store.connect(), c["id"])
            try:
                _get_docs(c["id"], "overview usage documentation")  # tanpa budget: CLI
            except Exception as e:  # noqa: BLE001 — satu library gagal, lanjut
                print(f"warmup: {name} -> GAGAL: {str(e)[:120]}", file=sys.stderr)
                continue
            conn = store.connect()
            n = conn.execute("SELECT COUNT(*) FROM chunks WHERE lib_id=?", (c["id"],)).fetchone()[0]
            print(f"warmup: {name} -> {c['id']} ({n} chunk terindeks)")
        return
    logging.basicConfig(level=logging.WARNING)
    argv = sys.argv[1:]
    if "--build-cache" in argv:
        _build_cache(limit=_flag_int(argv, "--limit"))
        return
    if "--fetch-cache" in argv:
        raise SystemExit(_fetch_cache(force="--force" in argv, dry_run="--dry-run" in argv))
    if "--transport" in argv:
        transport = argv[argv.index("--transport") + 1]
    else:
        transport = "stdio"
    if transport == "http":
        port = int(argv[argv.index("--port") + 1]) if "--port" in argv else 4041
        mcp.run(transport="http", host="127.0.0.1", port=port)
    else:
        mcp.run()


if __name__ == "__main__":
    main()


def _flag_int(argv: list[str], flag: str) -> int | None:
    if flag in argv:
        try:
            return int(argv[argv.index(flag) + 1])
        except (IndexError, ValueError):
            return None
    return None
