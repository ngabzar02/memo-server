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
    conn = _server_conn(monkeypatch, tmp_path)
    store.upsert_lib(conn, {"id": "fastmcp", "name": "fastmcp", "repo": "",
                            "docs_url": "https://glama.ai/", "trust": 95.0,
                            "latest_ver": "", "versions": "[]"})
    store.add_chunks(conn, "fastmcp", "", [{"path": "x.md", "title": "X", "text": "old docs"}])
    monkeypatch.setattr(server.registry, "resolve",
                        lambda *a, **k: [{"docs_url": "https://gofastmcp.com/", "repo": ""}])
    assert server._docs_changed(conn, "fastmcp") is True
    assert store.get_lib(conn, "fastmcp") is None  # drop_lib: chunk + lib hilang
    n = conn.execute("SELECT COUNT(*) FROM chunks WHERE lib_id='fastmcp'").fetchone()[0]
    assert n == 0


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


# --- SAB-6: query kosong (xfail backlog P0-03) ------------------------------

@pytest.mark.xfail(strict=True, reason="backlog: P0-03")
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
    monkeypatch.setattr(server, "_rerank", lambda q, hits, top_n=10: hits)
    assert server.get_docs("flask", "") == []


# --- SAB-8: fallback rerank (xfail backlog P0-04) ---------------------------

@pytest.mark.xfail(strict=True, reason="backlog: P0-04")
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


# --- network path (skip default, jalan manual) ------------------------------

@pytest.mark.network
def test_get_docs_live_smoke(monkeypatch, tmp_path):
    """Smoke live (bukan di CI): get_docs untuk lib alias dengan network.
    Jalankan: pytest -m network."""
    conn = _server_conn(monkeypatch, tmp_path)
    monkeypatch.setattr(server, "_embeddings", lambda: _FakeEmbed(P))
    out = server.get_docs("flask", "routing")
    assert out  # chunks non-kosong bila network hidup
