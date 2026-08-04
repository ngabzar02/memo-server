"""test_server — docs_changed TTL + drop (SAB-3), resolve metadata versi (Bug 6),
query kosong (SAB-6 xfail), fallback rerank metrik (SAB-8 xfail).

API diverifikasi dari src/memo/server.py:
- _docs_changed(conn, library_id) server.py:204 (TTL _DOCS_CHANGED_TTL=3600,
  drop_lib saat docs_url resolve != DB)
- resolve_library_id(library_name, query) server.py:97 (isi versi dari DB)
- get_docs(library_id, query, version=None) server.py:122
- _get_reranker() server.py:66 / _rerank(query, hits) server.py:80
"""

import json
import time

import pytest

import memo.registry as registry
import memo.server as server
import memo.store as store

P = [1.0] + [0.0] * 383
N = [-1.0] + [0.0] * 383


class _FakeEmbed:
    """Pengganti fastembed tanpa model: kembalikan vektor tetap (offline)."""

    def __init__(self, vec):
        self._vec = vec

    def embed(self, texts):
        return [self._vec]


def _server_conn(monkeypatch, tmp_path):
    """Server memakai store.connect() -> temp DB, tanpa menyentuh docs.db asli."""
    conn = store.connect(str(tmp_path / "srv.db"))
    monkeypatch.setattr(server.store, "connect", lambda: conn)
    monkeypatch.setattr(server, "_log_activity", lambda e: None)
    return conn


# --- SAB-3: docs_changed ---------------------------------------------------

def test_docs_changed_drops_lib_on_url_change(monkeypatch, tmp_path):
    """docs_url berubah -> lib TIDAK di-drop (data loss dulu: re-ingest budget
    gagal -> 0 chunk permanen). URL di-update + full=0, chunk lama tetap ada."""
    conn = _server_conn(monkeypatch, tmp_path)
    store.upsert_lib(conn, {"id": "fastmcp", "name": "fastmcp", "repo": "",
                            "docs_url": "https://glama.ai/", "trust": 95.0,
                            "latest_ver": "", "versions": "[]"})
    store.add_chunks(conn, "fastmcp", "", [{"path": "x.md", "title": "X", "text": "old docs"}])
    monkeypatch.setattr(server.registry, "resolve",
                        lambda *a, **k: [{"docs_url": "https://gofastmcp.com/", "repo": ""}])
    assert server._docs_changed(conn, "fastmcp") is True
    lib = store.get_lib(conn, "fastmcp")
    assert lib is not None  # dulu drop_lib: lib hilang -> 0 chunk
    assert lib["docs_url"] == "https://gofastmcp.com/"  # URL baru terpasang
    assert lib["full"] == 0  # trigger re-ingest bertahap
    n = conn.execute("SELECT COUNT(*) FROM chunks WHERE lib_id='fastmcp'").fetchone()[0]
    assert n == 1  # chunk lama dipertahankan sampai diganti (anti data loss)


def test_docs_changed_false_when_url_same(monkeypatch, tmp_path):
    conn = _server_conn(monkeypatch, tmp_path)
    store.upsert_lib(conn, {"id": "flask", "name": "Flask", "repo": "pallets/flask",
                            "docs_url": "https://flask.palletsprojects.com",
                            "trust": 95.0, "latest_ver": "", "versions": "[]"})
    monkeypatch.setattr(server.registry, "resolve",
                        lambda *a, **k: [{"docs_url": "https://flask.palletsprojects.com", "repo": ""}])
    assert server._docs_changed(conn, "flask") is False
    assert store.get_lib(conn, "flask") is not None


def test_docs_changed_ttl_skips_resolve(monkeypatch, tmp_path):
    conn = _server_conn(monkeypatch, tmp_path)
    store.upsert_lib(conn, {"id": "xlib", "name": "X", "repo": "",
                            "docs_url": "https://a.example.com", "trust": 95.0,
                            "latest_ver": "", "versions": "[]"})
    server._docs_changed_cache["xlib"] = time.monotonic()  # fresh dalam TTL 1 jam
    calls = []
    monkeypatch.setattr(server.registry, "resolve",
                        lambda *a, **k: calls.append(1) or [{"docs_url": "https://b.example.com/"}])
    assert server._docs_changed(conn, "xlib") is False
    assert calls == []  # TTL cache: resolve (network) tidak dipanggil
    assert store.get_lib(conn, "xlib") is not None


# --- resolve_library_id: metadata versi dari DB (Bug 6, FIXED) -------------

def test_resolve_merges_versions_from_db(monkeypatch, tmp_path):
    conn = _server_conn(monkeypatch, tmp_path)
    store.upsert_lib(conn, {"id": "flask", "name": "Flask", "repo": "pallets/flask",
                            "docs_url": "https://flask.palletsprojects.com",
                            "trust": 95.0, "latest_ver": "3.1.0",
                            "versions": json.dumps(["3.1.0", "2.3.0"])})
    monkeypatch.setattr(server.registry, "resolve", lambda name, query="": [{
        "id": "flask", "name": "flask", "repo": "pallets/flask",
        "docs_url": "", "trust": 95.0, "latest_ver": "", "versions": "[]"}])
    out = server.resolve_library_id("flask")
    assert out[0]["latest_ver"] == "3.1.0"
    assert json.loads(out[0]["versions"]) == ["3.1.0", "2.3.0"]


# --- I3: lock key canonical + dedupe libs by docs_url -----------------------

def test_lock_key_canonical_for_alias_same_docs():
    """I3: tailwind & tailwindcss (alias, docs_url sama) -> key lock SAMA —
    dua request berbeda nama tidak double-ingest ke docs_url sama."""
    assert server._lock_key("tailwind") == server._lock_key("tailwindcss")
    assert server._lock_key("flask") == server._lock_key("flask")  # deterministik


def test_lock_key_namespaced_builtin_distinct():
    assert server._lock_key("py:os") != server._lock_key("node:os")


def test_get_docs_merges_lib_by_docs_url(monkeypatch, tmp_path):
    """I3: resolve('tailwindcss') dgn docs_url yg sudah dipakai 'tailwind' ->
    merger ke id existing; tidak ada baris duplikat, chunk existing yang
    melayani."""
    conn = _server_conn(monkeypatch, tmp_path)
    store.upsert_lib(conn, {"id": "tailwind", "name": "Tailwind", "repo": "tailwindlabs/tailwindcss",
                            "docs_url": "https://tailwindcss.com/docs", "trust": 95.0,
                            "latest_ver": "4.0.0", "versions": "[]"})
    store.add_chunks(conn, "tailwind", "4.0.0",
                     [{"path": "colors", "title": "Colors", "text": "the colors utility class applies"}])
    monkeypatch.setattr(server.registry, "resolve", lambda name, query="": [{
        "id": "tailwindcss", "name": "tailwindcss", "repo": "tailwindlabs/tailwindcss",
        "docs_url": "https://tailwindcss.com/docs", "trust": 95.0,
        "latest_ver": "4.0.0", "versions": "[]"}])
    monkeypatch.setattr(server, "_embeddings", lambda: _FakeEmbed(P))
    monkeypatch.setattr(server.registry, "version_etag", lambda *a, **k: ("", "", []))
    monkeypatch.setattr(server.registry, "docs_etag", lambda *a, **k: None)
    monkeypatch.setattr(server, "_rerank", lambda q, hits, top_n=10: hits)
    out = server.get_docs("tailwindcss", "colors")
    assert out, "chunk tailwind harusnya melayani query"
    assert store.get_lib(conn, "tailwindcss") is None, "tidak boleh ada baris duplikat"
    assert store.get_lib(conn, "tailwind") is not None


# --- I5 + I9: freshness & cooldown ------------------------------------------

def test_maybe_refresh_version_change_sets_full_0(monkeypatch, tmp_path):
    """I5: versi baru -> latest_ver terpasang DAN full=0 (trigger re-ingest
    call berikutnya); return True dipakai _get_docs utk baca ulang lib."""
    conn = _server_conn(monkeypatch, tmp_path)
    store.upsert_lib(conn, {"id": "flask", "name": "Flask", "repo": "",
                            "docs_url": "", "trust": 95.0, "latest_ver": "3.0.0",
                            "versions": "[]"})
    monkeypatch.setattr(server.registry, "version_etag",
                        lambda *a, **k: ("3.1.0", "", ["3.1.0"]))
    lib = store.get_lib(conn, "flask")
    assert server._maybe_refresh(conn, lib) is True
    lib2 = store.get_lib(conn, "flask")
    assert lib2["latest_ver"] == "3.1.0"
    assert lib2["full"] == 0


def test_recrawl_writes_cooldown_only_after_mark(monkeypatch, tmp_path):
    """I9: _recrawl hanya periksa; recrawl_at ditulis _mark_recrawled SETELAH
    crawl selesai — cooldown 1 jam mulai berlaku dari keberhasilan, bukan dari
    permulaan (dulu gagal di tengah tetap bakar cooldown)."""
    conn = _server_conn(monkeypatch, tmp_path)
    store.upsert_lib(conn, {"id": "flask", "name": "Flask", "repo": "",
                            "docs_url": "", "trust": 95.0, "latest_ver": "",
                            "versions": "[]"})
    store.add_chunks(conn, "flask", "", [{"path": "a.md", "title": "A", "text": "x"}])
    conn.execute("UPDATE chunks SET fetched_at='2026-01-01 00:00:00' WHERE lib_id='flask'")
    assert server._recrawl(conn, "flask") is True  # konten tua & belum di-mark -> boleh
    row = conn.execute("SELECT recrawl_at FROM libs WHERE id='flask'").fetchone()[0]
    assert row == "", "I9: _recrawl tidak boleh menulis recrawl_at"
    server._mark_recrawled(conn, "flask")
    assert server._recrawl(conn, "flask") is False      # cooldown aktif
    assert server._recrawl(conn, "flask", force=True) is False  # cooldown menang


# --- SAB-6: query kosong (xfail backlog P0-03) ------------------------------

def test_get_docs_empty_query_explicit_response(monkeypatch, tmp_path):
    """SAB-6 (FP-2): get_docs(lib, '') -> respon eksplisit ([]), BUKAN chunk
    acak. Sekarang query kosong tetap melewati vec search -> chunk acak."""
    conn = _server_conn(monkeypatch, tmp_path)
    store.upsert_lib(conn, {"id": "flask", "name": "Flask", "repo": "pallets/flask",
                            "docs_url": "https://flask.palletsprojects.com",
                            "trust": 95.0, "latest_ver": "3.1.0",
                            "versions": json.dumps(["3.1.0"])})
    store.add_chunks(conn, "flask", "3.1.0",
                     [{"path": "intro.md", "title": "Intro", "text": "alpha"}], [P])
    monkeypatch.setattr(server, "_embeddings", lambda: _FakeEmbed(N))
    monkeypatch.setattr(server.registry, "resolve", lambda *a, **k: [])
    monkeypatch.setattr(server.registry, "version_etag", lambda *a, **k: ("", "", []))
    monkeypatch.setattr(server.registry, "docs_etag", lambda *a, **k: None)
    monkeypatch.setattr(server, "_rerank", lambda q, hits, top_n=10: hits)
    assert server.get_docs("flask", "") == []


# --- A1+C: ingest 0 halaman -> full=0 + guidance (bukan [] senyap) ----------

def test_get_docs_ingest_empty_guidance(monkeypatch, tmp_path):
    """A1+C: lib baru yg ingest-nya 0 halaman (astro: anti-bot/SPA) -> full
    dikoreksi ke 0 (dulu sandera full=1) + respon guidance, BUKAN [] senyap."""
    conn = _server_conn(monkeypatch, tmp_path)
    store.upsert_lib(conn, {"id": "astro", "name": "astro", "repo": "withastro/astro",
                            "docs_url": "https://docs.astro.build",
                            "trust": 95.0, "latest_ver": "7.1.6",
                            "versions": json.dumps(["7.1.6"])})
    monkeypatch.setattr(server, "_embeddings", lambda: _FakeEmbed(P))
    monkeypatch.setattr(server.registry, "resolve", lambda *a, **k: [])
    monkeypatch.setattr(server.registry, "version_etag", lambda *a, **k: ("", "", []))
    monkeypatch.setattr(server.registry, "docs_etag", lambda *a, **k: None)
    monkeypatch.setattr(server, "_rerank", lambda q, hits, top_n=10: hits)
    monkeypatch.setattr(server.ingest, "ingest_lib", lambda *a, **k: ([], True))
    out = server.get_docs("astro", "hooks")
    assert out and out[0]["title"] == "Guidance"
    assert store.get_lib(conn, "astro")["full"] == 0  # re-ingest di call berikutnya


# --- SAB-8: fallback rerank (xfail backlog P0-04) ---------------------------

def test_rerank_fallback_logs_metric(monkeypatch):
    """SAB-8 (FP-4): reranker gagal load -> warning log + METRIK fallback
    dicatat. Sekarang fallback hanya warning, tanpa metrik di activity log."""
    import memo.rerank as rr

    class Boom:
        def __init__(self, *a, **k):
            raise RuntimeError("force fail load")

    monkeypatch.setattr(rr, "CrossReranker", Boom)
    events = []
    monkeypatch.setattr(server, "_log_activity", events.append)
    server._get_reranker()
    server._rerank("some query", [{"text": "a"}, {"text": "b"}])
    assert any("rerank" in json.dumps(e).lower() for e in events), \
        "metrik fallback rerank tidak dicatat di activity log"


def test_pick_cache_release_skips_stale_manual():
    """Release manual `cache-latest` (asset docs.db) muncul lebih dulu di API —
    jangan dipakai; pilih release `memo-cache.db.gz` TERBARU (by created_at)."""
    releases = [
        {"tag_name": "cache-latest", "created_at": "2026-08-03T11:39:47Z",
         "assets": [{"name": "docs.db", "size": 1}]},
        {"tag_name": "cache-edc6c37", "created_at": "2026-08-03T16:38:41Z",
         "assets": [{"name": "memo-cache.db.gz", "size": 2}]},
        {"tag_name": "cache-b961c0f", "created_at": "2026-08-03T21:06:32Z",
         "assets": [{"name": "memo-cache.db.gz", "size": 3}]},
    ]
    ver, asset = server._pick_cache_release(releases)
    assert ver == "cache-b961c0f"
    assert asset["size"] == 3
    assert server._pick_cache_release(
        [{"tag_name": "x", "created_at": "2026-01-01T00:00:00Z", "assets": []}]) is None


# --- network path (skip default, jalan manual) ------------------------------

@pytest.mark.network
def test_get_docs_live_smoke(monkeypatch, tmp_path):
    """Smoke live (bukan di CI): get_docs untuk lib alias dengan network.
    Jalankan: pytest -m network."""
    conn = _server_conn(monkeypatch, tmp_path)
    monkeypatch.setattr(server, "_embeddings", lambda: _FakeEmbed(P))
    out = server.get_docs("flask", "routing")
    assert out  # chunks non-kosong bila network hidup
