# tests/ — pytest offline (regresi + sabotase)

Suite regresi untuk `src/memo/`: semua test **offline deterministik** (sqlite
temp via `tmp_path`, network dimatikan dengan monkeypatch). Tidak pernah
menyentuh `~/.local/share/memo/docs.db` asli.

## Menjalankan

```bash
pip install -e ".[test]"          # dari repo root
pytest tests/ -m "not network" -q # suite CI (default)
pytest tests/ -q                  # sama, tanpa filter
pytest tests/ -m network          # smoke live (butuh network, tidak di CI)
```

CI (`.github/workflows/test.yml`) menjalankan `pytest tests/ -m "not network"
--junitxml=pytest.xml -rxXs` + selfcheck modul (`python -m memo.store`,
`.ingest`, `.registry`).

## Per file

| File | Yang diuji |
|---|---|
| `test_store.py` | trim_to_tokens (SAB-1), search RRF (FTS+vec fusion, OR fallback), add_chunks UPSERT per path, budget 3000 token |
| `test_ingest.py` | chunk_text (heading-aware, hard-split SAB-2), `_path_allowed` domain+bahasa (SAB-4), `_looks_404`, is_full |
| `test_registry.py` | trust formula (log10, fork/README penalti, llms bonus), alias/builtin offline, merge versi (Bug 6), SAB-5 xfail |
| `test_server.py` | docs_changed TTL + drop (SAB-3), resolve metadata versi dari DB, SAB-6/SAB-8 xfail |

`tests/fixtures/`: `404.html` (halaman 404-palsu ber-status-200) dan `llms.txt`
(berisi link EN + non-EN).

## Xfail backlog (fitur belum ada — strict)

Test di bawah ini menuliskan perilaku yang DIHARAPKAN untuk item backlog
(`docs/planning.md`); selama backlog belum dikerjakan mereka xfail strict.
Saat item selesai, hapus marker xfail dan biarkan test lulus.

| Test | SAB | Backlog |
|---|---|---|
| `test_registry.py::test_resolve_garbage_name_not_found` | SAB-5 (resolve sampah) | P0-02 |
| `test_server.py::test_get_docs_empty_query_explicit_response` | SAB-6 (query kosong) | P0-03 |
| `test_store.py::test_search_drops_irrelevant_below_relative_threshold` | SAB-7 (relevansi < 50% top-1) | P1-01 |
| `test_server.py::test_rerank_fallback_logs_metric` | SAB-8 (fallback rerank) | P0-04 |
| `test_ingest.py::test_llms_filter_skips_non_en_links` | SAB-9 (filter llms non-EN) | P1-02 |

Aturan: **0 failure** di CI; xfail dihitung xfailed, bukan failed.
