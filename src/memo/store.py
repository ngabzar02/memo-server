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


def norm_path(p: str) -> str:
    """R10/L2-1: bentuk kanonik utk dedupe/compare — strip locale default en
    (/en/x ≡ /x), ekstensi .html, dan slash di ujung."""
    p = p.strip()
    p = re.sub(r"^/?en(?=$|/)", "", p, count=1)
    p = p.rstrip("/")
    if p.endswith(".html"):
        p = p[:-5]
    return p


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
    try:  # migrasi: A2 re-crawl — kapan lib terakhir di-re-crawl (cooldown 1 jam)
        conn.execute("ALTER TABLE libs ADD COLUMN recrawl_at TEXT DEFAULT ''")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # kolom sudah ada
    try:  # migrasi: R10 — cap chunk per lib (override default per-tier)
        conn.execute("ALTER TABLE libs ADD COLUMN cap INTEGER DEFAULT 0")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # kolom sudah ada
    conn.execute(
        """CREATE TABLE IF NOT EXISTS crawl_state (
            lib_id TEXT PRIMARY KEY, docs_url TEXT, seen TEXT, queue TEXT,
            updated_at TEXT)"""
    )
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
    conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_lib ON chunks(lib_id)")
    _migrate(conn)
    conn.commit()


# I15/D15: migrasi ber-version — PRAGMA user_version (0 = sebelum framework ini).
# Tambah entry baru utk skema berubah; jangan ubah entry lama.
_MIGRATIONS: dict[int, str] = {}


def _migrate(conn: sqlite3.Connection) -> None:
    ver = conn.execute("PRAGMA user_version").fetchone()[0]
    while ver in _MIGRATIONS:
        for stmt in _MIGRATIONS[ver].split(";"):
            if stmt.strip():
                conn.execute(stmt)
        ver += 1
        conn.execute(f"PRAGMA user_version={ver}")
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
    conn.execute("DELETE FROM crawl_state WHERE lib_id=?", (lib_id,))
    conn.commit()


def prune_chunks(conn: sqlite3.Connection, lib_id: str, keep_paths: set[str]) -> None:
    """R10/L2-2: hapus chunk lib yg path-nya tidak ada di set ter-norm (stale:
    versi lama, halaman .html ganda, locale non-en yg tersapu deny-path)."""
    rows = conn.execute("SELECT id, path FROM chunks WHERE lib_id=?", (lib_id,)).fetchall()
    norm = {p: norm_path(p) for p in keep_paths}
    for cid, path in rows:
        if norm_path(path) not in norm.values():
            conn.execute("DELETE FROM chunks_fts WHERE rowid=?", (cid,))
            conn.execute("DELETE FROM chunks_vec WHERE rowid=?", (cid,))
            conn.execute("DELETE FROM chunks WHERE id=?", (cid,))
    conn.commit()


def get_crawl_state(conn: sqlite3.Connection, lib_id: str, docs_url: str) -> tuple[set[str], list[str]] | None:
    """R10/L1-4: state BFS/progress persisten. None jika belum ada atau
    docs_url berubah (sumber baru -> mulai dari awal)."""
    r = conn.execute(
        "SELECT seen, queue FROM crawl_state WHERE lib_id=? AND docs_url=?",
        (lib_id, docs_url),
    ).fetchone()
    if not r:
        return None
    return set(json.loads(r[0])), json.loads(r[1])


def save_crawl_state(conn: sqlite3.Connection, lib_id: str, docs_url: str, seen: set[str], queue: list[str]) -> None:
    conn.execute(
        "INSERT INTO crawl_state (lib_id, docs_url, seen, queue, updated_at) "
        "VALUES (?,?,?,?,datetime('now')) "
        "ON CONFLICT(lib_id) DO UPDATE SET docs_url=excluded.docs_url, "
        "seen=excluded.seen, queue=excluded.queue, updated_at=excluded.updated_at",
        (lib_id, docs_url, json.dumps(sorted(seen)), json.dumps(queue)),
    )
    conn.commit()


def clear_crawl_state(conn: sqlite3.Connection, lib_id: str) -> None:
    conn.execute("DELETE FROM crawl_state WHERE lib_id=?", (lib_id,))
    conn.commit()


def _path_variants(p: str) -> set[str]:
    """A8: semua bentuk path yg merujuk halaman sama (/x, /x/, /x.html)."""
    base = p.rstrip("/")
    if base.endswith(".html"):
        base = base[:-5]
    return {p, base, base + ".html", base + "/"}


def add_chunks(conn: sqlite3.Connection, lib_id: str, ver: str, chunks: list[dict], embeddings: list[list[float] | None] | None = None) -> None:
    """chunks: [{path, title, text}]; embeddings aligned with chunks (384-dim).
    UPSERT per path: partial re-ingest (deadline) menambah, tidak menghapus
    chunk lama yang di-skip (existing). embeddings[i]=None -> FTS-only (chunk
    tetap tersimpan + searchable; vec lama utk path itu dihapus, chunk lain
    yang tak disentuh mempertahankan vec-nya)."""
    assert embeddings is None or len(chunks) == len(embeddings), "chunks/embeddings length mismatch"
    vpaths = set()  # A8: hapus versi lama + path-variants (.html/slash) sekali
    for ch in chunks:  # di awal — bukan per chunk,
        vpaths |= _path_variants(ch["path"])  # kalau per chunk: 1 file llms (100+ chunk
    for path in vpaths:  # per path) saling menghapus
        for (oid,) in conn.execute(
            "SELECT id FROM chunks WHERE lib_id=? AND path=?", (lib_id, path)
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

def _section_title(text: str) -> str:
    """B: heading pertama (H1-H4) sbg section_title — chunk_text menyimpan
    heading sbg breadcrumb di baris pertama tiap section."""
    for ln in text.splitlines()[:3]:
        m = re.match(r"^#{1,4}\s+(.*)$", ln)
        if m:
            return m.group(1).strip()[:80]
    return ""


def search(conn: sqlite3.Connection, lib_id: str, query: str, k: int = 5, query_vec: list[float] | None = None, rrf_k: int = 60, version: str = "") -> list[dict]:
    """Hybrid: FTS5 BM25 + vector via RRF (reciprocal rank fusion, rrf_k=60).
    AND dulu utk presisi; OR fallback utk recall (benchmark: numpy 0 hasil
    pd AND — banyak docs pakai istilah berbeda utk konsep sama).
    A7: version=... soft filter — chunk ber-label ver==version diutamakan di
    atas (dan chunk ver='' tetap ikut), tidak pernah membuang semua hasil.
    B: output + section_title/tokens/score (score RRF utk rank relatif)."""
    fts_terms = re.findall(r"[A-Za-z0-9_]+", query)
    if not fts_terms:
        fts_and = fts_or = ""
    else:
        quoted = " ".join(f'"{t}"' for t in fts_terms)
        fts_and, fts_or = quoted, " OR ".join(f'"{t}"' for t in fts_terms)
    ranked = []  # ordered rowids: union FTS(and->or) + vec, di-RRF
    vec_drop: set[int] = set()
    if fts_and:
        ranked.extend(_fts_ranks(conn, lib_id, fts_and))
    if query_vec is not None:
        vec_hits = conn.execute(
            "SELECT rowid, distance FROM chunks_vec WHERE lib_id=? AND embedding MATCH ? AND k=?",
            (lib_id, json.dumps(query_vec), 20),
        ).fetchall()
        if vec_hits:
            # FP-3/SAB-7: anti-FP — hit dengan cos < 50% cos top-1 dibuang.
            # cos = 1 - distance (embedding ternormalisasi); top-1 selalu lolos.
            top_cos = 1.0 - vec_hits[0][1]
            vec_drop = {r[0] for r in vec_hits if 1.0 - r[1] < 0.5 * top_cos}
            ranked.extend(r[0] for r in vec_hits)
    if not ranked:
        if fts_or and fts_or != fts_and:
            ranked = _fts_ranks(conn, lib_id, fts_or)  # OR: recall terakhir
        if not ranked:
            return []
    fused: dict[int, float] = {}
    for cid in ranked:  # RRF: ditebak 1/(rrf_k+rank); doc yg ada di FTS & vec dihitung 2x
        fused[cid] = fused.get(cid, 0.0) + 1.0 / (rrf_k + len(fused))
    if vec_drop:
        fused = {cid: s for cid, s in fused.items() if cid not in vec_drop}
    limit = k * 3 if version else k  # A7: ambil lebih utk compensasi filter
    top = [cid for cid, _ in sorted(fused.items(), key=lambda kv: kv[1], reverse=True)[:limit]]
    if not top:
        return []
    sql = f"SELECT id, path, title, text, ver FROM chunks WHERE id IN ({','.join('?'*len(top))})"
    params: list = list(top)
    if version:  # soft: ver==version ATAU ver kosong (di-ingest sbg latest saat itu)
        sql += " AND (? = '' OR ver = ? OR ver = '')"
        params += [version, version]
    rows = conn.execute(sql, params).fetchall()
    byid = {r[0]: r for r in rows}
    out = []
    for cid in top:
        r = byid.get(cid)
        if not r:
            continue
        text = r[3]
        out.append({"id": cid, "path": r[1], "title": r[2], "text": text,
                    "section_title": _section_title(text),
                    "tokens": len(text) // 4, "score": round(fused[cid], 4),
                    "_ver": r[4]})
    if version:
        out.sort(key=lambda h: h["_ver"] != version)  # ver cocok paling atas
    for h in out:
        h.pop("_ver", None)
    # R10/L2-3: dedupe retrieval — satu halaman per path ter-norm (lokal /en/
    # dan .html hilang), skor tertinggi menang (out sudah urut skor turun).
    best: dict[str, float] = {}
    unique = []
    for h in out:
        pk = norm_path(h["path"])
        if pk not in best:
            best[pk] = h["score"]
            unique.append(h)
    return unique[:k]


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
            "full", "etag", "last_check", "recrawl_at", "cap"]
    return dict(zip(cols, r))


def get_versions(conn: sqlite3.Connection, lib_id: str) -> list[str]:
    r = conn.execute("SELECT versions FROM libs WHERE id=?", (lib_id,)).fetchone()
    if not r or not r[0]:
        return []
    try:  # I24: json sampah di DB (versi lama) tidak boleh crash versions tool
        return json.loads(r[0])
    except ValueError:
        return []


def trim_to_tokens(chunks: list[dict], max_tokens: int = MAX_TOKENS) -> list[dict]:
    """Cap returned chunks ~4 chars/token rough estimate. A6: chunk oversize
    DIPOTONG ke sisa budget (dulu dibuang seluruhnya), isi awal dipertahankan."""
    budget, out = max_tokens * 4, []
    for c in chunks:
        if budget <= 0:
            break
        if len(c["text"]) > budget:
            c["text"] = c["text"][:budget]
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
    assert trim_to_tokens([{"text": "x" * 20000}, {"text": "ok"}])[0]["text"] == "x" * 12000, "trim truncate failed"
    assert get_versions(conn, "flask") == ["3.1.0", "2.3.0"]
    hits2 = search(conn, "flask", "flask.route (decorator)", k=2)  # FTS5 escaping
    assert hits2, f"FTS5 escaping failed: {hits2}"
    assert norm_path("/en/intro/") == "/intro" and norm_path("en/x.html") == "/x"
    same = [{"path": "en/api.md", "title": "API", "text": "same text"},
            {"path": "/api.md", "title": "API", "text": "same text"}]
    add_chunks(conn, "flask", "3.1.0", same, None)
    dedup = search(conn, "flask", "same text", k=5)
    assert len(dedup) <= 1, f"L2-3 dedupe failed: {dedup}"
    prune_chunks(conn, "flask", {"intro.md"})
    assert all(c["path"] == "intro.md" for c in search(conn, "flask", "Flask", k=10)), "prune failed"
    save_crawl_state(conn, "flask", "https://x", {"a", "b"}, ["c"])
    assert get_crawl_state(conn, "flask", "https://x") == ({"a", "b"}, ["c"])
    assert get_crawl_state(conn, "flask", "https://other") is None, "docs_url change must reset"
    assert get_lib(conn, "flask")["cap"] == 0
    print(f"SELFCHECK store: PASS ({len(hits)} hits, top={hits[0]['title']})")


if __name__ == "__main__":
    _demo()
