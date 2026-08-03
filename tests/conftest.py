"""Fixtures bersama: DB sqlite temp per test + reset cache global.

Semua test memakai sqlite temp (tmp_path), tidak pernah menyentuh
~/.local/share/memo/docs.db asli.
"""

import pytest

import memo.registry as registry
import memo.server as server


@pytest.fixture(autouse=True)
def _reset_global_caches():
    """Cache in-memory global bisa bocor antar test (registry TTL 1 jam,
    docs_changed TTL 1 jam, reranker singleton). Bersihkan tiap test."""
    registry._cache.clear()
    registry._LLMS_CACHE.clear()
    server._docs_changed_cache.clear()
    server._reranker = None
    yield
    registry._cache.clear()
    registry._LLMS_CACHE.clear()
    server._docs_changed_cache.clear()


@pytest.fixture
def tmp_db(tmp_path):
    """Koneksi sqlite temp ber-schema lengkap (store.init)."""
    import memo.store as store
    conn = store.connect(str(tmp_path / "test.db"))
    yield conn
    conn.close()
