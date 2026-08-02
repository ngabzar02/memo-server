"""MCP server: resolve-library-id, get-docs, versions — Context7 API clone.

Usage: memo  (stdio MCP server, registered via uv tool install)
"""

import json
import logging
import sqlite3
import sys
import threading
from typing import Any

from fastmcp import FastMCP

from memo import ingest, registry, store

log = logging.getLogger("memo")
mcp = FastMCP("memo")

# ingest+embed tidak thread-safe (fastembed first-load race -> crash paralel);
# cache hit sub-ms jadi antrian lock pendek. ponytail: lock global, per-lib
# lock kalau throughput nyata butuh.
_INGEST_LOCK = threading.Lock()


def _embeddings():
    """Lazy singleton: model load ~0.7s (cache panas), RAM ~240MB."""
    if not hasattr(_embeddings, "model"):
        from fastembed import TextEmbedding

        _embeddings.model = TextEmbedding("BAAI/bge-small-en-v1.5")
    return _embeddings.model


@mcp.tool()
def resolve_library_id(library_name: str, query: str = "") -> list[dict[str, Any]]:
    """Resolve a library name (e.g. 'flask', 'nextjs') to candidate library IDs
    with trust scores and latest version. query is optional context to disambiguate."""
    return registry.resolve(library_name, query)


@mcp.tool()
def get_docs(library_id: str, query: str, version: str | None = None) -> list[dict[str, Any]]:
    """Get relevant documentation chunks for a library and query.
    Cache hit: sub-ms. Cache miss: fetch+ingest+index once (~5-60s first time)."""
    with _INGEST_LOCK:  # cold ingest/embed serial: crash paralel = fatal
        return _get_docs(library_id, query, version)


def _get_docs(library_id: str, query: str, version: str | None = None) -> list[dict[str, Any]]:
    conn = store.connect()
    lib = store.get_lib(conn, library_id)
    if not lib:
        cands = registry.resolve(library_id, query)
        if not cands:
            return []
        lib = cands[0]
        lib["versions"] = json.dumps([lib["latest_ver"]] if lib.get("latest_ver") else [])
        store.upsert_lib(conn, lib)
    ver = version or lib.get("latest_ver") or ""
    vec = _embeddings().embed([query])
    query_vec = [float(x) for x in list(vec)[0]]  # numpy float32 -> float, utk json.dumps
    hits = store.search(conn, library_id, query, k=10, query_vec=query_vec)
    stale = not version and len(store.get_versions(conn, library_id)) <= 1
    if (not hits or stale) and (not version and _docs_changed(conn, library_id)):
        # stale trap: docs_url alias berubah (fastapi README -> /reference/deps);
        # lib versi<=1 (indikasi DB lama/README dangkal) -> cek ulang tiap call
        lib = store.get_lib(conn, library_id)  # di-drop oleh _docs_changed
        if not lib:
            cands = registry.resolve(library_id)
            if not cands:
                return []
            lib = cands[0]
            lib["versions"] = json.dumps([lib["latest_ver"]] if lib.get("latest_ver") else [])
            store.upsert_lib(conn, lib)
        chunks = ingest.ingest_lib(lib.get("docs_url") or f"https://{lib.get('repo','')}")
        if not chunks:
            return []
        chunks = chunks[:200]  # cap: 200 embed ~2 menit di ARM; cukup utk top docs
        embs = []
        for i in range(0, len(chunks), 64):  # batch embed: spike RAM kecil
            embs.extend(_embeddings().embed([c["text"] for c in chunks[i:i+64]]))
        store.add_chunks(conn, library_id, ver, chunks,
                         [[float(x) for x in e] for e in embs])
        hits = store.search(conn, library_id, query, k=10, query_vec=query_vec)
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
                get_docs(c["id"], "overview usage documentation")
            except Exception as e:  # noqa: BLE001 — satu library gagal, lanjut
                print(f"warmup: {name} -> GAGAL: {str(e)[:120]}", file=sys.stderr)
                continue
            conn = store.connect()
            n = conn.execute("SELECT COUNT(*) FROM chunks WHERE lib_id=?", (c["id"],)).fetchone()[0]
            print(f"warmup: {name} -> {c['id']} ({n} chunk terindeks)")
        return
    logging.basicConfig(level=logging.WARNING)
    mcp.run()


if __name__ == "__main__":
    main()
