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
| `test_store.py` | trim_to_tokens (SAB-1), search RRF (FTS+vec fusion, OR fallback), threshold relevansi 50% top-1 (SAB-7), add_chunks UPSERT per path, budget 3000 token |
| `test_ingest.py` | chunk_text (heading-aware, hard-split SAB-2), `_path_allowed` domain+bahasa (SAB-4), filter llms non-EN (SAB-9), `_looks_404`, is_full |
| `test_registry.py` | trust formula (log10, fork/README penalti, llms bonus), alias/builtin offline, merge versi (Bug 6), filter sampah (SAB-5) |
| `test_server.py` | docs_changed TTL + drop (SAB-3), resolve metadata versi dari DB, query kosong (SAB-6), fallback rerank (SAB-8) |

`tests/fixtures/`: `404.html` (halaman 404-palsu ber-status-200) dan `llms.txt`
(berisi link EN + non-EN).

## Xfail backlog (fitur belum ada — strict)

Test di bawah ini menuliskan perilaku yang DIHARAPKAN untuk item backlog
(`docs/planning.md`); selama backlog belum dikerjakan mereka xfail strict.
Saat item selesai, hapus marker xfail dan biarkan test lulus.

**Tidak ada xfail aktif** (per 2026-08-04): SAB-1..SAB-9 semuanya FIXED dengan pytest.

Aturan: **0 failure** di CI; xfail dihitung xfailed, bukan failed.
