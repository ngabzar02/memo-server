# Tuning RRF k — P1-03 (A/B 20-100, replay offline)

- **Tanggal**: 2026-08-04 · **Status**: SELESAI (temuan: k tidak signifikan; blocker = korpus)
- **Metode**: `bench/replay_rrf.py` — replay 22 query bench langsung ke docs.db
  (search hybrid FTS+vec, embedding fastembed bge-small sama dgn server), hitung
  hit@1/hit@5 dgn aturan norm yang sama seperti `bench/score.py`. Tanpa network,
  tanpa rerank (rerank fallback = identity di env tanpa sentence_transformers).
- **Korpus**: release cache `cache-edc6c37` (200 chunk/lib).

## Hasil (14 query relevan; 4 lib tidak ada di korpus: pydantic, tailwindcss, anthropic, click)

| RRF k | hit@1 | hit@5 | n |
|---|---|---|---|
| 20 | 14% | 14% | 14 |
| 40 | 14% | 14% | 14 |
| 60 | 14% | 14% | 14 |
| 80 | 14% | 14% | 14 |
| 100 | 14% | 14% | 14 |

## Analisis

1. **Semua k identik** — urutan hasil didominasi oleh kesepakatan FTS BM25 + vec;
   pergeseran bobot RRF 20→100 tidak mengubah top-5 untuk kasus ini.
2. **Miss dominan = korpus, bukan ranking**: halaman jawaban tidak ter-index di
   release cache — numpy `basics.broadcasting.html` 0 chunk, flask `/quickstart/`
   0 chunk, pydantic/tailwindcss/anthropic/click tidak ada di cache sama sekali.
   Tuning ranking pada korpus yang jawabannya hilang tidak memberi sinyal.
3. R5 resmi (39%) memakai korpus live-ingest per-query (deadline 30s), bukan
   release cache 200-chunk — karena itu flask/numpy @1 di R5 padahal cache
   sekarang tidak punya halaman itu.

## Keputusan (ADR-016)

- **RRF k = 60 dipertahankan** (default param `store.search(..., rrf_k=60)`).
- Replay ulang WAJIB setelah korpus lengkap: build cache CI berikutnya
  (dgn FP-5 llms filter + alias requests fix) + `memo --fetch-cache`.
- Blocker korpus diikuti di P1-04 (chunking) / P1-05 (warmup checklist) / P2-03
  (cache-libs 66 → 200+).
