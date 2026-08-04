"""test_store — hybrid retrieval (FTS5 + vec RRF), UPSERT per path, trim budget.

API diverifikasi dari src/memo/store.py:
- trim_to_tokens(chunks, max_tokens=3000) store.py:186 (SAB-1: skip oversize,
  jangan buang sisa)
- search(conn, lib_id, query, k=5, query_vec=None) store.py:128 (RRF k=60)
- add_chunks(conn, lib_id, ver, chunks, embeddings=None) store.py:92 (UPSERT
  per path; embeddings[i]=None -> FTS-only, vec lama path itu dihapus)
"""

import json

import memo.store as store

Z = [0.0] * 384          # 384-dim, norm 0 (tidak dipakai utk MATCH)
P = [1.0] + [0.0] * 383   # cosine +1 terhadap query vector [1,0,...]
M = [0.5] + [0.0] * 383   # cosine +0.5: moderat, lolos threshold FP-3 (>=50% top-1)
N = [-1.0] + [0.0] * 383  # cosine -1


def _lib(conn, lib_id="flask", name="Flask", docs_url="https://flask.palletsprojects.com"):
    store.upsert_lib(conn, {"id": lib_id, "name": name, "repo": "pallets/flask",
                            "docs_url": docs_url, "trust": 95.0,
                            "latest_ver": "3.1.0",
                            "versions": json.dumps(["3.1.0", "2.3.0"])})


def test_trim_truncates_oversize_not_drop(tmp_db):
    """A6: chunk 20k char DIPOTONG ke budget (12k char), isi awal dipertahankan
    — dulu dibuang seluruhnya (SAB-1 skip)."""
    out = store.trim_to_tokens(
        [{"text": "x" * 20000}, {"text": "ok"}], max_tokens=3000)
    assert len(out) == 1 and len(out[0]["text"]) == 12000
    assert out[0]["text"].startswith("x")


def test_trim_budget_respected(tmp_db):
    """Budget 3000 token (~12000 char): akumulasi sampai habis, lalu berhenti."""
    big = {"text": "a" * 7000}   # 7000 <= 12000 -> masuk, sisa 5000
    mid = {"text": "b" * 6000}   # 6000 > 5000 -> dipotong ke 5000, budget habis
    small = {"text": "c" * 100}
    out = store.trim_to_tokens([big, mid, small], max_tokens=3000)
    assert [len(c["text"]) for c in out] == [7000, 5000]


def test_search_rrf_orders_by_fusion(tmp_db):
    """RRF: chunk yang relevan di FTS DAN vec menang atas yang hanya di vec."""
    _lib(tmp_db)
    chunks = [
        {"path": "intro.md", "title": "Intro",
         "text": "Flask is a micro web framework for Python."},
        {"path": "api.md", "title": "API",
         "text": "Flask route decorator registers view functions."},
    ]
    store.add_chunks(tmp_db, "flask", "3.1.0", chunks, [P, M])
    hits = store.search(tmp_db, "flask", "flask framework", k=2, query_vec=P)
    assert [h["path"] for h in hits] == ["intro.md", "api.md"]
    assert hits[0]["title"] == "Intro"


def test_search_or_fallback_when_and_empty(tmp_db):
    """AND kosong -> OR fallback (recall; tanpa vec sama sekali)."""
    _lib(tmp_db)
    store.add_chunks(tmp_db, "flask", "3.1.0", [
        {"path": "intro.md", "title": "Intro",
         "text": "Flask is a micro web framework for Python."},
        {"path": "api.md", "title": "API",
         "text": "Flask route decorator registers view functions."},
    ])
    hits = store.search(tmp_db, "flask", "framework route", k=2)
    assert {h["path"] for h in hits} == {"intro.md", "api.md"}


def test_search_unknown_lib_empty(tmp_db):
    _lib(tmp_db, "flask")
    assert store.search(tmp_db, "nope", "flask", k=5) == []


def test_add_chunks_upsert_per_path(tmp_db):
    """UPSERT per path: re-add path sama menghapus versi lama (chunks + fts +
    vec) SEKALI di awal, chunk path lain yang tak disentuh tetap utuh."""
    store.add_chunks(tmp_db, "flask", "1.0", [
        {"path": "a.md", "title": "A", "text": "v1"},
        {"path": "b.md", "title": "B", "text": "keep"},
    ], [P, P])
    store.add_chunks(tmp_db, "flask", "2.0", [{"path": "a.md", "title": "A", "text": "v2"}])
    rows = tmp_db.execute("SELECT path, text FROM chunks ORDER BY path").fetchall()
    assert rows == [("a.md", "v2"), ("b.md", "keep")]
    n_vec = tmp_db.execute("SELECT COUNT(*) FROM chunks_vec WHERE lib_id='flask'").fetchone()[0]
    assert n_vec == 1  # vec lama a.md dihapus, vec b.md dipertahankan
    assert store.search(tmp_db, "flask", "keep", k=5)[0]["path"] == "b.md"


def test_add_chunks_embeddings_none_fts_only(tmp_db):
    """embeddings=None -> chunk tersimpan + searchable via FTS, tanpa row vec."""
    store.add_chunks(tmp_db, "flask", "1.0", [
        {"path": "a.md", "title": "A", "text": "unique term here"},
    ])
    assert tmp_db.execute("SELECT COUNT(*) FROM chunks_vec WHERE lib_id='flask'").fetchone()[0] == 0
    assert store.search(tmp_db, "flask", "unique", k=5)[0]["path"] == "a.md"


def test_search_drops_irrelevant_below_relative_threshold(tmp_db):
    """SAB-7 (FP-3): chunk dengan skor < 50% top-1 dibuang. Sekarang search
    mengembalikan chunk tidak relevan (vec cosine -1) selama ada di top-k."""
    _lib(tmp_db)
    store.add_chunks(tmp_db, "flask", "3.1.0", [
        {"path": "relevant.md", "title": "R", "text": "alpha framework docs"},
        {"path": "junk.md", "title": "J", "text": "alpha completely unrelated"},
    ], [P, N])
    hits = store.search(tmp_db, "flask", "alpha", k=5, query_vec=P)
    assert [h["path"] for h in hits] == ["relevant.md"]


def test_search_output_meta_fields(tmp_db):
    """B: chunk output punya section_title (heading pertama), tokens (len/4),
    score (RRF) — metadata utk agent memilih & menghitung budget."""
    _lib(tmp_db)
    store.add_chunks(tmp_db, "flask", "3.1.0", [
        {"path": "intro.md", "title": "Intro",
         "text": "# Welcome\n\nFlask is a micro web framework for Python."},
    ])
    hit = store.search(tmp_db, "flask", "framework", k=5)[0]
    assert hit["section_title"] == "Welcome"
    assert hit["tokens"] == len(hit["text"]) // 4
    assert isinstance(hit["score"], float)


def test_add_chunks_variants_dedupe_html(tmp_db):
    """A8: add_chunks menghapus versi path-variants — '/x.html' lama diberihkan
    saat '/x' di-re-add (dan sebaliknya), tidak jadi duplikat."""
    store.add_chunks(tmp_db, "flask", "1.0", [{"path": "overview.html", "title": "Ov", "text": "v1"}])
    store.add_chunks(tmp_db, "flask", "1.0", [{"path": "overview", "title": "Ov", "text": "v2"}])
    rows = tmp_db.execute("SELECT path, text FROM chunks ORDER BY path").fetchall()
    assert rows == [("overview", "v2")]


def test_search_version_soft_and_prefers(tmp_db):
    """A7: version=... memprioritaskan chunk ber-label cocok, tetap menyertakan
    ver='' (di-ingest sbg latest saat itu); ver lain di-exclude."""
    _lib(tmp_db)
    store.add_chunks(tmp_db, "flask", "3.1.0", [
        {"path": "new.md", "title": "New", "text": "flask route for 3.1"},
    ])
    store.add_chunks(tmp_db, "flask", "2.3.0", [
        {"path": "old.md", "title": "Old", "text": "flask deprecated route"},
    ])
    store.add_chunks(tmp_db, "flask", "", [
        {"path": "base.md", "title": "Base", "text": "flask general route"},
    ])
    hits = store.search(tmp_db, "flask", "flask route", k=5, version="3.1.0")
    assert hits[0]["path"] == "new.md"   # ver cocok di atas
    assert {h["path"] for h in hits} == {"new.md", "base.md"}  # '' tetap ikut


def test_search_dedupes_norm_path(tmp_db):
    """R10/L2-3: retrieval dedupe — '/en/api.md' & '/api.md' = satu halaman
    (locale en di-strip norm_path), skor tertinggi menang."""
    _lib(tmp_db)
    store.add_chunks(tmp_db, "flask", "3.1.0", [
        {"path": "en/api.md", "title": "A", "text": "unique route thing"},
        {"path": "/api.md", "title": "A", "text": "unique route thing"},
        {"path": "other.md", "title": "O", "text": "different text"},
    ])
    hits = store.search(tmp_db, "flask", "unique route thing", k=5)
    assert len(hits) == 1 and hits[0]["path"] in ("en/api.md", "/api.md")


def test_prune_chunks_removes_stale(tmp_db):
    """R10/L2-2: prune_chunks membuang chunk yg path ter-norm-nya tidak ada
    di keep (stale .html ganda, locale non-en, dll)."""
    _lib(tmp_db)
    store.add_chunks(tmp_db, "flask", "3.1.0", [
        {"path": "/x.html", "title": "X", "text": "stale html twin"},
        {"path": "/de/x", "title": "X", "text": "stale locale"},
        {"path": "/keep", "title": "K", "text": "keep me"},
    ])
    store.prune_chunks(tmp_db, "flask", {"/keep"})
    rows = tmp_db.execute("SELECT path FROM chunks WHERE lib_id='flask'").fetchall()
    assert rows == [("/keep",)]


def test_crawl_state_persist_and_reset(tmp_db):
    """R10/L1-4: crawl_state disimpan & dipulihkan; docs_url berubah -> reset
    (mulai dari awal)."""
    store.save_crawl_state(tmp_db, "flask", "https://x.dev", {"a", "b"}, ["c"])
    assert store.get_crawl_state(tmp_db, "flask", "https://x.dev") == ({"a", "b"}, ["c"])
    assert store.get_crawl_state(tmp_db, "flask", "https://other.dev") is None
    store.clear_crawl_state(tmp_db, "flask")
    assert store.get_crawl_state(tmp_db, "flask", "https://x.dev") is None


def test_simhash_deterministic_and_near_dup(tmp_db):
    """L3-2: simhash 64-bit zero-dep — deterministik, beda 1 kata terdeteksi
    near-dup (<=6 bit), konten beda total jauh; add_chunks menyaring dup."""
    t = ("Flask routing maps HTTP methods to view functions. The route decorator "
         "registers a function for a URL pattern and method. When a request "
         "matches, Flask calls the view with the request context and arguments "
         "extracted from the path. View functions return a response object or "
         "string that Flask converts to an HTTP response. This mechanism powers "
         "everything from simple endpoints to blueprints with prefixes and "
         "subdomains, and is documented across the routing and views chapters. ")
    a = store.simhash64(t)
    assert a == store.simhash64(t) and a != 0
    assert (a ^ store.simhash64(t.replace("HTTP methods", "HTTP verb"))).bit_count() <= 6
    far = store.simhash64("FastAPI path operations, dependency injection, async routes, "
                          "websockets, background tasks, OpenAPI generation, typing driven "
                          "validation, automatic docs, middleware, exception handlers, and "
                          "dependencies compose into testable applications across dozens of "
                          "chapters of guides and recipes with a completely different vocabulary. ")
    assert (a ^ far).bit_count() > 6
    store.add_chunks(tmp_db, "flask", "1.0", [{"path": "a.md", "title": "A", "text": t}])
    store.add_chunks(tmp_db, "flask", "1.0", [{"path": "b.md", "title": "B",
                                               "text": t.replace("HTTP methods", "HTTP verb")}])
    rows = tmp_db.execute("SELECT path FROM chunks WHERE lib_id='flask'").fetchall()
    paths = [r[0] for r in rows]
    assert paths == ["a.md"], f"L3-2 near-dup harus di-skip: {paths}"
