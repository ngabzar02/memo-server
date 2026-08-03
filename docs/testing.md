# Testing — memo: strategi uji (selfcheck + sabotase + pytest)

- **Versi**: 2.0 · **Tanggal**: 2026-08-03 · **Status**: ACTIVE
- **Peran**: daftar uji yang WAJIB lulus sebelum round ditutup. Tidak ada "uji asal jalan" —
  setiap uji membuktikan perilaku tertentu, termasuk perilaku salah.

---

## 1. Filosofi

1. **Uji sabotase** = masukkan kondisi buruk → buktikan sistem tidak berperilaku buruk.
   Ini bedanya dengan uji biasa yang hanya mengecek jalur bahagia [V: report-R4.md:154-159].
2. **Skor bench bukan unit test** — bench (22 query, client MCP) mengukur kualitas;
   unit/sabotase mengukur kebenaran perilaku. Keduanya wajib.
3. Selfcheck `_demo` per modul (sudah ada: store.py:212-217, ingest.py:295-305, registry.py:465-477)
   dipertahankan sebagai smoke; pytest mini `[BARU]` menambah regresi CI.

## 2. Uji sabotase (status: sebagian di selfcheck, pytest P3-01)

| ID | Target | Input | Harapan | Bukti sekarang |
|---|---|---|---|---|
| SAB-1 | Bug 1 (trim) | chunk 20.000 char + chunk kecil | ≥1 chunk kecil tetap terkirim | [FIXED] store.py:191,213 selfcheck |
| SAB-2 | Bug 2 (hard-split) | `chunk_text("A." * 100_000)` | max chunk ≤ cap (4×) | [FIXED] ingest.py:85,101,113 |
| SAB-3 | Bug 3 (docs_url berubah) | ganti docs_url registry mock | drop_lib + re-ingest | [FIXED] server.py:145-150 |
| SAB-4 | Bug 4 (domain) | crawler di-list web.dev untuk nextjs | path di luar domain TIDAK disimpan | [FIXED] ingest.py:218,298-301 |
| SAB-5 | FP-1 (resolve sampah) | `resolve_library_id("zzzzzz")` | "library not found", bukan entri trust 0 | [FIXED] registry.py:_resolve (trust < 1.0); `test_resolve_garbage_name_not_found` |
| SAB-6 | FP-2 (query kosong) | `get_docs(lib, "")` | respon eksplisit, bukan 10 chunk acak | [FIXED] server.py:_get_docs (empty → []); `test_get_docs_empty_query_explicit_response` |
| SAB-7 | FP-3 (relevansi) | query vs chunk tak relevan | chunk < 50% skor top-1 dibuang | [FIXED] store.py:139-162 (cos = 1 - distance, threshold relatif); `test_search_drops_irrelevant_below_relative_threshold` |
| SAB-8 | FP-4 (fallback) | force gagal load rerank | warning log + tetap respons | [FIXED] server.py:_get_reranker (metrik fallback); `test_rerank_fallback_logs_metric` |
| SAB-9 | FP-5 (llms filter) | llms.txt berisi link non-EN | path non-EN tidak masuk korpus | [FIXED] ingest.py:66-72 `parse_llms(base_url=...)`; `test_llms_filter_skips_non_en_links` |

## 3. Strategi pytest mini (`tests/`)

- `test_store.py`: trim (SAB-1), search RRF ordering, add_chunks UPSERT (delete-sekali), trim budget.
- `test_ingest.py`: chunk_text (batas, heading, hard-split SAB-2), `_path_allowed` (SAB-4), `_looks_404`, is_full.
- `test_registry.py`: trust formula, alias vs builtin, filter sampah (SAB-5), merge versi.
- `test_server.py`: FP-2 (SAB-6), fallback warning (SAB-8), docs_changed (SAB-3), resolve metadata.
- Gaya: sqlite temp file per test (`tmp_path` fixture) — **tanpa network** di CI (offline deterministik);
  network path diuji via integration terpisah (ditandai `@pytest.mark.network`, skip default).
- Framework: pytest (stdlib + pytest). Bukan unittest — mengikuti ekosistem Python modern, minimal.

## 4. Integrasi CI `[BARU: P3-01/P3-02]`

```
tests.yml (push/PR):
  - pytest tests/ (offline) — gate utama
  - selfcheck: python -m memo.store / .ingest / .registry / .rerank
  - smoke bench (opsional, cache asset): score.py atas release terbaru — gagal = tanda regresi hit@5
```

Gate G3: pytest hijau + smoke bench 2× berturut-turut.

## 5. Data & fixture

- `tests/fixtures/` (minimal): satu contoh HTML 404-palsu, satu llms.txt (EN + non-EN), satu docs_url mock.
- Query golden tetap di `bench/queries.json` (22 query) — bukan duplikasi di tests/.
- `bench/mcp_sim.py` — simulasi client MCP langsung ke daemon (verifikasi delivery nyata) [V: report-R4.md:6].

## 6. Kriteria lulus

- Semua uji sabotase yang statusnya `[BELUM]` → `[FIXED]` + ada di pytest sebelum item backlog ditutup.
- pytest: 0 failure di CI. Selfcheck: 0 failure.
- Round hanya ditutup bila SAB yang relevan PASS + bench PASS (client-scored).
