"""MCP server: resolve-library-id, get-docs, versions — Context7 API clone.

Usage: memo  (stdio MCP server, registered via uv tool install)
"""

import json
import logging
import sqlite3
import sys
import threading
import time
from typing import Any

from fastmcp import FastMCP

from memo import ingest, registry, store

log = logging.getLogger("memo")
mcp = FastMCP("memo")

# ingest embed+sqlite thread-safe (ORT concurrent run TERUJI 6-thread aman);
# lock per-library hanya mencegah 2 ingest lib sama bersamaan.
_lib_locks: dict[str, threading.Lock] = {}
_lib_locks_guard = threading.Lock()


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
    return registry.resolve(library_name, query)


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
_REQUEST_BUDGET = 20.0


def _get_docs(library_id: str, query: str, version: str | None = None,
              deadline: float | None = None) -> list[dict[str, Any]]:
    conn = store.connect()
    lib = store.get_lib(conn, library_id)
    chunk_count = conn.execute(
        "SELECT COUNT(*) FROM chunks WHERE lib_id=?", (library_id,)
    ).fetchone()[0]
    if lib and not version and "github.com" in (lib.get("docs_url") or ""):
        # trap hanya utk docs_url yg masih README GitHub (fastapi/requests dulu
        # bocor ke sini); docs_url resmi (numpy.org dll) jarang pindah -> skip
        # resolve 14s per call. resolve dicache TTL di registry.
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
            conn.execute("UPDATE libs SET full=? WHERE id=?", (1 if complete else 0, library_id))
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
            conn.execute("UPDATE libs SET full=? WHERE id=?", (1 if complete else 0, library_id))
            conn.commit()
        hits = store.search(conn, library_id, query, k=10, query_vec=query_vec)
    hits = _rerank(query, hits)
    return store.trim_to_tokens(hits)


def _docs_changed(conn: sqlite3.Connection, library_id: str) -> bool:
    """True jika docs_url resolve != DB -> drop lib (minta re-ingest). Network: cek tipis."""
    lib = store.get_lib(conn, library_id)
    if not lib:
        return False
    cands = registry.resolve(library_id)
    if not cands:
        return False
    new_url = cands[0].get("docs_url") or f"https://{cands[0].get('repo', '')}"
    old_url = lib.get("docs_url") or f"https://{lib.get('repo', '')}"
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
        old = lib.get("latest_ver")
        conn.execute("UPDATE libs SET latest_ver=?, versions=? WHERE id=?",
                     (latest, json.dumps(vs or []), lib["id"]))
        if old:
            conn.execute("DELETE FROM chunks WHERE lib_id=? AND ver=?", (lib["id"], old))
        conn.commit()
        return True
    return False


@mcp.tool()
def versions(library_id: str) -> list[str]:
    """List known versions for a library (history dari npm/PyPI bila tersedia)."""
    conn = store.connect()
    vs = store.get_versions(conn, library_id)
    if not vs or len(vs) <= 1:  # DB lama/alias tanpa riwayat -> resolve segar
        cands = registry.resolve(library_id)
        if cands:
            vs = json.loads(cands[0].get("versions") or "[]")
            if len(vs) <= 1:  # alias/builtin tak bawa versi -> tanya npm/PyPI
                vs = registry.versions_of(library_id)
            if vs:
                cands[0]["versions"] = json.dumps(vs)
                store.upsert_lib(conn, cands[0])
    return vs


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
    _embeddings()  # preload model: hindari race lazy-load di request pertama
    mcp.run()


if __name__ == "__main__":
    main()
