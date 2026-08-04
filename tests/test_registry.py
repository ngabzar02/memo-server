"""test_registry — trust engine (log10 + penalti fork/README), alias/builtin
offline, merge versi (Bug 6), filter sampah (SAB-5).

API diverifikasi dari src/memo/registry.py:
- _alias(name) registry.py:26 (curated, tanpa network)
- _builtin(name, query) registry.py:34 (stdlib, tanpa network)
- _trust_final(c, name) registry.py:355 (mutasi c["trust"]; _stars_of dan
  _has_llms di-monkeypatch agar offline & deterministik)
- _resolve(name, query) registry.py:399 (paralel 6 sumber; dedupe/merge)
- resolve(name, query) registry.py:375 (TTL-cache wrapper)
"""

import json

import memo.registry as registry


def _resolve_no_network(monkeypatch, junk=None):
    """Matikan semua sumber network; opsional 1 sumber mengembalikan junk."""
    monkeypatch.setattr(registry, "_dir_entry", lambda name: junk)
    monkeypatch.setattr(registry, "_npm", lambda name: junk)
    monkeypatch.setattr(registry, "_pypi", lambda name: junk)
    monkeypatch.setattr(registry, "_crates", lambda name: junk)
    monkeypatch.setattr(registry, "_rubygems", lambda name: junk)
    monkeypatch.setattr(registry, "_gh_search", lambda name, query="": None)
    monkeypatch.setattr(registry, "_stars_of", lambda repo: 0.0)
    monkeypatch.setattr(registry, "_has_llms", lambda docs_url: False)


def test_alias_offline():
    a = registry._alias("nextjs")
    assert a["repo"] == "vercel/next.js"
    assert a["docs_url"] == "https://nextjs.org/docs"
    assert a["trust"] == 95.0
    assert registry._alias("zzzzzz") is None
    assert registry._alias("NextJS") is not None  # case-insensitive


def test_alias_requests_docs_root():
    """P1-06: alias requests nunjuk root docs (korpus penuh via crawl), bukan
    halaman /user/advanced yang menghasilkan korpus 1 chunk."""
    a = registry._alias("requests")
    assert a["docs_url"] == "https://requests.readthedocs.io/en/latest/"
    assert not a["docs_url"].rstrip("/").endswith("/advanced")


def test_alias_docs_url_current_for_moved_sites():
    """P1-08: docs anthropic/openai pindah domain — docs.anthropic.com &
    platform.openai.com mengarahkan llms.txt ke platform.claude.com /
    developers.openai.com; alias lama bikin korpus 0 chunk (netloc beda)."""
    assert registry._alias("anthropic")["docs_url"] == "https://platform.claude.com/docs"
    assert registry._alias("openai")["docs_url"] == "https://developers.openai.com/api/docs"


def test_builtin_offline():
    b = registry._builtin("os", "python import os list files")
    assert b["id"] == "py:os"
    assert b["trust"] == 98.0
    n = registry._builtin("events")
    assert n["id"] == "node:events"


def test_resolve_alias_no_network(monkeypatch):
    """resolve() shortcut alias curated (trust > 90) tanpa network sama sekali."""
    monkeypatch.setattr(registry, "_dir_entry", lambda name: (_ for _ in ()).throw(AssertionError("network dipanggil")))
    monkeypatch.setattr(registry, "_npm", lambda name: (_ for _ in ()).throw(AssertionError("network dipanggil")))
    monkeypatch.setattr(registry, "versions_of", lambda name: [])  # A3: dipanggil utk enrich alias
    out = registry.resolve("nextjs")
    assert out[0]["repo"] == "vercel/next.js"
    assert out[0]["trust"] == 95.0
    assert len(out) == 1


def test_norm_cand_id_always_str():
    """ID kandidat WAJIB string — sumber network (GitHub dsb.) bisa kirim int;
    MCP schema get_docs menolak library_id non-str (bench crash vue id=8857)."""
    c = registry._norm_cand({"id": 8857, "repo": "a/b", "trust": 10.0}, "vue")
    assert c["id"] == "8857"
    assert isinstance(c["id"], str)


def test_trust_formula_log10(monkeypatch):
    """trust = max(base, log10(stars)) + 2 llms + penalti fork/README."""
    monkeypatch.setattr(registry, "_stars_of", lambda repo: 1000.0)
    monkeypatch.setattr(registry, "_has_llms", lambda docs: False)

    c = {"trust": 0.0, "repo": "pallets/flask", "docs_url": ""}
    registry._trust_final(c, "flask")
    assert c["trust"] == 3.0  # log10(1000)

    c = {"trust": 0.0, "repo": "someone/not-flask", "docs_url": ""}  # fork: basename != name
    registry._trust_final(c, "flask")
    assert c["trust"] == 1.0  # 3.0 - 2.0 penalti fork

    c = {"trust": 0.0, "repo": "pallets/flask", "docs_url": "https://github.com/pallets/flask"}
    registry._trust_final(c, "flask")
    assert c["trust"] == 2.0  # -1.0 penalti README github


def test_trust_formula_llms_bonus(monkeypatch):
    monkeypatch.setattr(registry, "_stars_of", lambda repo: 100.0)
    monkeypatch.setattr(registry, "_has_llms", lambda docs: True)
    c = {"trust": 0.0, "repo": "pallets/flask", "docs_url": "https://flask.palletsprojects.com"}
    registry._trust_final(c, "flask")
    assert c["trust"] == 4.0  # 2.0 (log10 100) + 2.0 (llms)


def test_merge_versions_across_sources(monkeypatch):
    """Bug 6 regression: entry bare npm (tanpa repo/docs) dibuang tapi
    latest_ver-nya di-merge ke kandidat pypi dengan id sama."""
    _resolve_no_network(monkeypatch)
    monkeypatch.setattr(registry, "_npm", lambda name: {
        "repo": "", "latest_ver": "8.5.1", "docs_url": "", "trust": 1.0,
        "versions": ["8.5.1"]})
    monkeypatch.setattr(registry, "_pypi", lambda name: {
        "repo": "egoist/tsup", "latest_ver": "", "docs_url": "",
        "trust": 2.0, "versions": ["7.0.0", "8.5.1"]})
    out = registry._resolve("tsup")
    assert len(out) == 1
    assert out[0]["latest_ver"] == "8.5.1"
    assert json.loads(out[0]["versions"]) == ["7.0.0", "8.5.1"]


def test_dedupe_merge_missing_fields(monkeypatch):
    """Dedupe by repo: kandidat kedua mengisi field kosong kandidat pertama."""
    _resolve_no_network(monkeypatch)
    monkeypatch.setattr(registry, "_npm", lambda name: {
        "repo": "pallets/box", "latest_ver": "", "docs_url": "https://example.com",
        "trust": 5.0, "versions": []})
    monkeypatch.setattr(registry, "_pypi", lambda name: {
        "repo": "pallets/box", "latest_ver": "", "docs_url": "",
        "trust": 0.0, "versions": ["1.0", "2.0"]})
    out = registry._resolve("box")
    assert len(out) == 1
    assert json.loads(out[0]["versions"]) == ["1.0", "2.0"]  # pypi mengisi versi


def test_resolve_garbage_name_not_found(monkeypatch):
    """SAB-5 (FP-1): nama sampah -> 'library not found', bukan entri trust 0.
    Sekarang resolve mengembalikan kandidat junk (trust 0) selama ada repo/docs."""
    _resolve_no_network(monkeypatch)
    monkeypatch.setattr(registry, "_dir_entry", lambda name: {"docs_url": "https://zzz.example.com/"})
    assert registry.resolve("zzzzzz") == []


def test_alias_versions_enriched_from_ecosystem(monkeypatch):
    """A3: alias curated tanpa versions (aliases.json) di-isi riwayat versi dari
    ekosistem; latest_ver junk (npm 0.0.3) dikoreksi ke vs[0]."""
    monkeypatch.setattr(registry, "versions_of",
                        lambda name: ["15.4.0", "15.3.0", "15.2.0"])
    c = registry.resolve("nextjs")[0]
    assert json.loads(c["versions"])[:1] == ["15.4.0"]
    assert c["latest_ver"] == "15.4.0"


def test_resolve_query_boost(monkeypatch):
    """A4: query memengaruhi ranking — kandidat yg repo/docs_url-nya memuat
    kata kunci query naik +0.5 (sebelumnya query diabaikan utk non-builtin)."""
    _resolve_no_network(monkeypatch)
    monkeypatch.setattr(registry, "_enrich", lambda cands, name: None)  # trust statis
    monkeypatch.setattr(registry, "_dir_entry", lambda name: {
        "repo": "fastapi/fastapi-extra", "docs_url": "https://fastapi.tiangolo.com",
        "trust": 1.0, "latest_ver": "", "versions": []})
    monkeypatch.setattr(registry, "_pypi", lambda name: {
        "repo": "other/helper", "docs_url": "https://example.com",
        "trust": 1.2, "latest_ver": "", "versions": []})
    out = registry.resolve("webx", query="tiangolo framework")
    by_repo = {c["repo"]: c["trust"] for c in out}
    assert by_repo["fastapi/fastapi-extra"] == 1.5   # +0.5 boost (docs_url memuat tiangolo)
    assert by_repo["other/helper"] == 1.2            # tak kena boost


def test_resolve_cache_by_name_query_boost_per_call(monkeypatch):
    """I4: cache network by NAME saja (query keluar dari key) — resolve 2 query
    berbeda utk nama sama hanya 1x network; boost A4 diterapkan per-call di
    atas cache copy (tidak menumpuk antar query)."""
    _resolve_no_network(monkeypatch)
    monkeypatch.setattr(registry, "_enrich", lambda cands, name: None)
    monkeypatch.setattr(registry, "_dir_entry", lambda name: {
        "repo": "fastapi/fastapi-extra", "docs_url": "https://fastapi.tiangolo.com",
        "trust": 1.0, "latest_ver": "", "versions": []})
    monkeypatch.setattr(registry, "_pypi", lambda name: {
        "repo": "other/helper", "docs_url": "https://example.com",
        "trust": 1.2, "latest_ver": "", "versions": []})
    calls = []
    orig = registry._resolve
    monkeypatch.setattr(registry, "_resolve",
                        lambda *a, **k: calls.append(1) or orig(*a, **k))
    out1 = registry.resolve("webx", query="tiangolo framework")
    assert {c["repo"]: c["trust"] for c in out1}["fastapi/fastapi-extra"] == 1.5
    out2 = registry.resolve("webx", query="helper tool")
    assert calls == [1], "resolve network dipanggil ulang utk query berbeda (I4)"
    by = {c["repo"]: c["trust"] for c in out2}
    assert by["fastapi/fastapi-extra"] == 1.0  # boost query1 tidak membeku di cache
    assert by["other/helper"] == 1.7           # boost query2 utk call ini saja
