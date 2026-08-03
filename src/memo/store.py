"""SQLite store: hybrid retrieval (FTS5 BM25 + sqlite-vec cosine) + cache.

Schema:
- libs: library metadata from registry
- chunks: raw text to return
- chunks_fts: FTS5 index over chunks (BM25)
- chunks_vec: vec0 embedding index, integer rowid -> chunk rowid (vec0 requires integer PK)

Hybrid rank fusion: normalize BM25 score and cosine similarity to [0,1], sum.
"""

import json
import os
import re
import sqlite3
from pathlib import Path

import sqlite_vec

DEFAULT_DB = str(Path.home() / ".local" / "share" / "memo" / "docs.db")
MAX_TOKENS = 3000  # cap context sent to model


def connect(db_path: str | None = None) -> sqlite3.Connection:
    path = Path(db_path or DEFAULT_DB)
    path.parent.mkdir(parents=True, exist_ok=True)  # fresh install / CI: dir belum ada
    conn = sqlite3.connect(path, timeout=30)  # anti SQLITE_BUSY saat tulis paralel
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.execute("PRAGMA journal_mode=WAL")
    init(conn)  # idempotent
    return conn


def init(conn: sqlite3.Connection) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS libs (
            id TEXT PRIMARY KEY, name TEXT, repo TEXT, docs_url TEXT,
            trust REAL, latest_ver TEXT, versions TEXT
        )"""
    )
    try:  # migrasi: kolom full (1 = ingest lengkap, 0 = parsial/deadline tercapai)
        conn.execute("ALTER TABLE libs ADD COLUMN full INTEGER DEFAULT 1")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # kolom sudah ada
    try:  # migrasi: freshness (ETag + kapan dicek)
        conn.execute("ALTER TABLE libs ADD COLUMN etag TEXT DEFAULT ''")
        conn.execute("ALTER TABLE libs ADD COLUMN last_check TEXT DEFAULT ''")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # kolom sudah ada
    conn.execute(
        """CREATE TABLE IF NOT EXISTS chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT, lib_id TEXT, ver TEXT,
            path TEXT, title TEXT, text TEXT, fetched_at TEXT)"""
    )
    conn.execute(
        """CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
            lib_id UNINDEXED, text)"""
    )
    conn.execute(
        """CREATE VIRTUAL TABLE IF NOT EXISTS chunks_vec USING vec0(
            embedding float[384], lib_id text)"""
    )
    conn.commit()


# --- write ----------------------------------------------------------------

def upsert_lib(conn: sqlite3.Connection, lib: dict) -> None:
    conn.execute(
        "INSERT INTO libs (id, name, repo, docs_url, trust, latest_ver, versions) "
        "VALUES (:id,:name,:repo,:docs_url,:trust,:latest_ver,:versions) "
        "ON CONFLICT(id) DO UPDATE SET name=excluded.name, repo=excluded.repo, "
        "docs_url=excluded.docs_url, trust=excluded.trust, "
        "latest_ver=excluded.latest_ver, versions=excluded.versions",
        lib,
    )
    conn.commit()


def drop_lib(conn: sqlite3.Connection, lib_id: str) -> None:
    """Hapus lib + chunk (warmup --force: re-ingest segar)."""
    conn.execute("DELETE FROM chunks WHERE lib_id=?", (lib_id,))
    conn.execute("DELETE FROM chunks_fts WHERE lib_id=?", (lib_id,))
    conn.execute("DELETE FROM chunks_vec WHERE lib_id=?", (lib_id,))
    conn.execute("DELETE FROM libs WHERE id=?", (lib_id,))
    conn.commit()


def add_chunks(conn: sqlite3.Connection, lib_id: str, ver: str, chunks: list[dict], embeddings: list[list[float] | None] | None = None) -> None:
    """chunks: [{path, title, text}]; embeddings aligned with chunks (384-dim).
    UPSERT per path: partial re-ingest (deadline) menambah, tidak menghapus
    chunk lama yang di-skip (existing). embeddings[i]=None -> FTS-only (chunk
    tetap tersimpan + searchable; vec lama utk path itu dihapus, chunk lain
    yang tak disentuh mempertahankan vec-nya)."""
    assert embeddings is None or len(chunks) == len(embeddings), "chunks/embeddings length mismatch"
    paths = {c["path"] for c in chunks}
    for path in paths:  # hapus versi lama sekali di awal — bukan per chunk,
        for (oid,) in conn.execute(  # kalau per chunk: 1 file llms (100+ chunk
            "SELECT id FROM chunks WHERE lib_id=? AND path=?", (lib_id, path)  # per path) saling menghapus
        ).fetchall():
            conn.execute("DELETE FROM chunks_fts WHERE rowid=?", (oid,))
            conn.execute("DELETE FROM chunks_vec WHERE rowid=?", (oid,))
            conn.execute("DELETE FROM chunks WHERE id=?", (oid,))
    for i, ch in enumerate(chunks):
        cur = conn.execute(
            "INSERT INTO chunks (lib_id, ver, path, title, text, fetched_at) "
            "VALUES (?,?,?,?,?,datetime('now'))",
            (lib_id, ver, ch["path"], ch["title"], ch["text"]),
        )
        cid = cur.lastrowid
        conn.execute(
            "INSERT INTO chunks_fts (rowid, lib_id, text) VALUES (?,?,?)",
            (cid, lib_id, ch["text"]),
        )
        if embeddings and embeddings[i] is not None:
            conn.execute(
                "INSERT INTO chunks_vec (rowid, lib_id, embedding) VALUES (?,?,?)",
                (cid, lib_id, json.dumps(embeddings[i])),
            )
    conn.commit()


# --- read -----------------------------------------------------------------

def search(conn: sqlite3.Connection, lib_id: str, query: str, k: int = 5, query_vec: list[float] | None = None) -> list[dict]:
    """Hybrid: FTS5 BM25 + vector via RRF (reciprocal rank fusion, k=60).
    AND dulu utk presisi; OR fallback utk recall (benchmark: numpy 0 hasil
    pd AND — banyak docs pakai istilah berbeda utk konsep sama)."""
    fts_terms = re.findall(r"[A-Za-z0-9_]+", query)
    if not fts_terms:
        fts_and = fts_or = ""
    else:
        quoted = " ".join(f'"{t}"' for t in fts_terms)
        fts_and, fts_or = quoted, " OR ".join(f'"{t}"' for t in fts_terms)
    ranked = []  # ordered rowids: union FTS(and->or) + vec, di-RRF
    if fts_and:
        ranked.extend(_fts_ranks(conn, lib_id, fts_and))
    if query_vec is not None:
        ranked.extend(r[0] for r in conn.execute(
            "SELECT rowid FROM chunks_vec WHERE lib_id=? AND embedding MATCH ? AND k=?",
            (lib_id, json.dumps(query_vec), 20),
        ).fetchall())
    if not ranked:
        if fts_or and fts_or != fts_and:
            ranked = _fts_ranks(conn, lib_id, fts_or)  # OR: recall terakhir
        if not ranked:
            return []
    fused: dict[int, float] = {}
    for cid in ranked:
        fused[cid] = fused.get(cid, 0.0) + 1.0 / (60 + len(fused))  # RRF: rank urut
    top = [cid for cid, _ in sorted(fused.items(), key=lambda kv: kv[1], reverse=True)[:k]]
    rows = conn.execute(
        f"SELECT id, path, title, text FROM chunks WHERE id IN ({','.join('?'*len(top))})",
        top,
    ).fetchall()
    byid = {r[0]: r for r in rows}
    return [{"id": cid, "path": byid[cid][1], "title": byid[cid][2], "text": byid[cid][3]}
            for cid in top if cid in byid]


def _fts_ranks(conn: sqlite3.Connection, lib_id: str, fts_query: str, limit: int = 20) -> list[int]:
    """Rowid ordered by BM25 (best first)."""
    return [r[0] for r in conn.execute(
        "SELECT rowid FROM chunks_fts WHERE lib_id=? AND chunks_fts MATCH ? ORDER BY rank LIMIT ?",
        (lib_id, fts_query, limit),
    ).fetchall()]


def get_lib(conn: sqlite3.Connection, lib_id: str) -> dict | None:
    r = conn.execute("SELECT * FROM libs WHERE id=?", (lib_id,)).fetchone()
    if not r:
        return None
    cols = ["id", "name", "repo", "docs_url", "trust", "latest_ver", "versions",
            "full", "etag", "last_check"]
    return dict(zip(cols, r))


def get_versions(conn: sqlite3.Connection, lib_id: str) -> list[str]:
    r = conn.execute("SELECT versions FROM libs WHERE id=?", (lib_id,)).fetchone()
    return json.loads(r[0]) if r and r[0] else []


def trim_to_tokens(chunks: list[dict], max_tokens: int = MAX_TOKENS) -> list[dict]:
    """Cap returned chunks ~4 chars/token rough estimate."""
    budget, out = max_tokens * 4, []
    for c in chunks:
        if len(c["text"]) > budget:
            break
        out.append(c)
        budget -= len(c["text"])
    return out


# --- self-check -----------------------------------------------------------

def _demo() -> None:
    conn = connect(":memory:")
    init(conn)
    upsert_lib(conn, {"id": "flask", "name": "Flask", "repo": "pallets/flask", "docs_url": "",
                      "trust": 10.0, "latest_ver": "3.1.0", "versions": json.dumps(["3.1.0", "2.3.0"])})
    chunks = [
        {"path": "intro.md", "title": "Intro", "text": "Flask is a micro web framework for Python. It is based on Werkzeug."},
        {"path": "api.md", "title": "API", "text": "Flask has a route decorator to register view functions."},
        {"path": "db.md", "title": "DB", "text": "SQLAlchemy is commonly used with Flask for databases."},
    ]
    emb = [[1.0, 0, 0] + [0.0] * 381] * 3  # fake 384-dim
    add_chunks(conn, "flask", "3.1.0", chunks, emb)
    hits = search(conn, "flask", "framework", k=2)
    assert hits and hits[0]["title"] == "Intro", f"BM25 hybrid failed: {hits}"
    assert trim_to_tokens([{"text": "x" * 20000}]) == [], "trim failed"
    assert get_versions(conn, "flask") == ["3.1.0", "2.3.0"]
    hits2 = search(conn, "flask", "flask.route (decorator)", k=2)  # FTS5 escaping
    assert hits2, f"FTS5 escaping failed: {hits2}"
    print(f"SELFCHECK store: PASS ({len(hits)} hits, top={hits[0]['title']})")


if __name__ == "__main__":
    _demo()
