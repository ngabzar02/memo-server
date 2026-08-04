# MASTER PLAN MEMO MCP v2 — Menuju "Sempurna" (Versus Context7)

Tanggal: 2026-08-04. Disusun dari: benchmark 9 ronde + 3 riset paralel sub-agent (swarm):
1. Riset mendalam Context7 (source npm @upstash/context7-mcp@3.2.5, SDK, docs, blog upstash)
2. Best practices RAG-docs 2025-2026 (chunking, hybrid, embedding, rerank, llms.txt, freshness, MCP, evaluasi)
3. Audit teknis kode memo (server/registry/store/ingest/rerank, DB live, tests)

Semua klaim bertag `[VERIFIED]` (bukti file:line atau URL) / `[INFERRED]` / `[ASUMSI]`.

---

## 0. RANGKUMAN EKSEKUTIF

Memo saat ini: MCP lokal, 3 tools, FTS+vec hybrid (TAPI vektor KOSONG di prod → FTS murni),
rerank ONNX, crawl on-demand, guidance message. Skor ronde 9: resolve A+, anti-hal A+,
stability A+, **relevance B−** (4/8 lib bermasalah: fastapi, duckdb, react, astro).

**Temuan paling fatal (audit kode):** `chunks_vec` = **0 baris** di docs.db produksi
(server.py:227 embed tiap request sia-sia) — fitur "hybrid RRF" yang di-klaim tidak pernah
berfungsi di jalur MCP server. Ini artinya sebagian besar skor benchmark selama ini berasal
dari FTS+rerank saja.

Context7 asli hanya punya **2 tools** (resolve-library-id, query-docs), server-side rerank
memangkas konteks 65% (9.7k→3.3k token), trustScore berbasis organisasi, benchmarkScore
LLM-jury, version pinning, refresh adaptif popularity-based, anti-injection pipeline.
Backend parsing/crawling/vector mereka private — memo bisa menang di transparansi, offline,
dan tanpa rate limit.

Target v2: menjadi MCP docs-RAG lokal TERBAIK dengan standar setara context7: retrieval
yang benar-benar hybrid (vec aktif), freshness adaptif, version-aware, evaluasi berkelanjutan.

---

## 1. GAP ANALYSIS — Memo vs Context7 (detail)

### 1.1 Gap permukaan (benchmark & dokumentasi)

| # | Gap | Memo (sekarang) | Context7 (asli) | Sumber |
|---|---|---|---|---|
| G1 | Jumlah tools | 3 (resolve, versions, get_docs) | 2 (resolve-library-id, query-docs) | [VERIFIED] npm mcp@3.2.5 |
| G2 | `query` di resolve | opsional, hampir tak berpengaruh | wajib, untuk ranking relevansi | [VERIFIED] |
| G3 | Library ID | slug bebas (`fastapi`) | `/owner/repo` global unik | [VERIFIED] |
| G4 | Version pinning | `version` param label saja (tidak filter) | `/owner/repo@1.2.3` benar-benar memilih versi docs | [VERIFIED] |
| G5 | Output | JSON `{id,path,title,text,section_title,tokens,score}` | teks + rerank server-side, server yang putuskan jumlah docs | [VERIFIED] |
| G6 | Trust | log10(stars/downloads)+llms.txt+penalti fork | trustScore 0-10 org-based + benchmarkScore 0-100 (LLM jury) + Verified badge | [VERIFIED] |
| G7 | Freshness | etag mati total (etag='' di 21 libs), re-crawl 7 hari kaku | refresh adaptif berbasis popularity + threshold; GitHub Action per push | [VERIFIED] audit + blog |
| G8 | Self-healing | guidance ada (fake lib, SPA) | guidance + pesan per error (404/429/401) + prompt auth | [VERIFIED] |
| G9 | Anti-injection | tidak ada | pipeline LLM classifier 2 tahap untuk docs & Skills.md | [VERIFIED] |
| G10 | Cakupan lib | ~49 alias + resolve ad-hoc | ribuan, community-contributed, verified | [VERIFIED] |
| G11 | Evaluasi | tidak ada benchmark formal (hanya ronde manual) | benchmarkScore otomatis tiap parse, jury LLM | [VERIFIED] |
| G12 | Latensi | cold 5-60s (fetch+ingest on-demand) | hosted, API cepat | [VERIFIED] |

### 1.2 Gap internal memo (dari audit kode) — yang TIDAK terlihat dari benchmark

| # | Severity | Temuan | Bukti |
|---|---|---|---|
| I1 | KRITIS | `chunks_vec` = 0 baris di prod → "hybrid" = FTS murni; embed query tiap request sia-sia (~90ms) | server.py:227, store.py:170-180 |
| I2 | KRITIS | Lazy singleton `_embeddings`/`_reranker` tanpa lock → 2 request konkuren load model 2× (RAM ~480MB) | server.py:100-128 |
| I3 | KRITIS | Lock per-lib dipakai ID mentah user (bukan hasil resolve): `next` vs `nextjs`, `go` vs `golang` → lock beda untuk docs sama → double ingest + duplikat korpus (DB: baris tailwind DAN tailwindcss dua-duanya full=1) | server.py:63-65,178 |
| I4 | KRITIS | `_resolve` cache keyed `(name, query)` → tiap kombinasi query unik = resolve 6-sumber network penuh (~2-3s) di hot path; memori tak terbatas | registry.py:401-407, server.py:216 |
| I5 | TINGGI | `_maybe_refresh` return value dibuang (server.py:212) — versi baru terdeteksi tapi chunks lama tetap disajikan tanpa penanda | server.py:212 |
| I6 | TINGGI | ETag conditional-GET mati: `version_etag` tidak pernah pakai `old_etag`, selalu return etag="" | registry.py:76-84 |
| I7 | TINGGI | `_extract` & `page()` tanpa try/except → HTML aneh dari web → exception propagasi → SELURUH get_docs gagal (bukan fallback) | ingest.py:58-72, 200-211 |
| I8 | SEDANG | Gagal ingest = silent; re-crawl existing 0 halaman baru tidak ter-log | ingest.py:86-87 |
| I9 | SEDANG | `_recrawl` tulis `recrawl_at` SEBELUM crawl → crawl gagal tetap bakar cooldown | server.py:86-88 |
| I10 | SEDANG | llms branch ignore `existing` → re-fetch SEMUA halaman; `c["path"]=f"{title} ({url})"` → title sama → chunk menimpa | ingest.py:281-294 |
| I11 | SEDANG | Deadline antar-halaman bukan per-fetch; 1 halaman lambat makan 20s | ingest.py:285-287 |
| I12 | SEDANG | Tidak ada migration framework/FK/indeks `chunks(lib_id)` → full scan di 50k chunk | store.py:42-70 |
| I13 | SEDANG | Dua konvensi path (URL vs "title (url)") → dedupe tidak konsisten | ingest.py:290 |
| I14 | SEDANG | `versions_of` panggil 5 ekosistem SERIAL di dalam `_maybe_refresh` (di bawah lock per-lib) → bisa makan ~30s network, meledakkan budget | registry.py:261-269, server.py:336 |
| I15 | SEDANG | SSRF ringan: docs_url dari npm/PyPI/directory bisa ke localhost; `ingest_docs` fetch URL apa pun | registry.py:161,239; ingest.py:302 |
| I16 | SEDANG | `_stars_of` tanpa cache + rate limit GitHub anon 60/jam → setelah ~10 resolve semua stars=0, trust turun diam-diam | registry.py:364-375 |
| I17 | SEDANG | Koneksi sqlite baru per request tanpa close eksplisit; 2 penulis (server+warmup) WAL → SQLITE_BUSY >30s | store.py:24-32 |
| I18 | SEDANG | CLI rapuh (`--transport` di akhir argv → IndexError); server.py 546 baris multi-tanggung jawab | server.py:525-527 |
| I19 | SEDANG | Test gap: tidak ada test _recrawl/_maybe_refresh/_crawl/rollback/migrasi/concurrency; network path tak pernah jalan di CI | test_server.py:186 |
| I20 | SEDANG | Activity log 4 event saja; tidak ada log chunk hasil ingest, fetch gagal, latency embed/rerank, query-miss | bench |
| I21 | RENDAH | Duplikat path `.html` vs non-.html (duckdb 8/10 hasil duplikat pasangan) | bench ronde 7-8 |
| I22 | RENDAH | Chunk >12.000 char DIBUANG (store.py:199) — halaman reference besar hilang padahal relevan (menjelaskan G5-fastapi) | store.py:199 |
| I23 | RENDAH | `get_lib` SELECT * + 11 kolom hardcoded → mismatch diam-diam saat schema berubah | store.py:227-233 |
| I24 | RENDAH | `json.loads` tanpa try di get_versions → versions korup = crash | store.py:236-238 |
| I25 | RENDAH | `_docs_changed_cache` race benign (worst case resolve ganda) | server.py:59 |
| I26 | RENDAH | Dead code/artefak: docs.db.bak 1.8MB + docs.db.cache 37MB; `_fetch_cache` rollback bisa kehilangan tulis terakhir | server.py:473-485 |
| I27 | INFO | Semua cache in-process hilang saat restart → cold start re-resolve penuh | registry.py |
| I28 | INFO | `_log_activity` swallow OSError → disk penuh = observability buta | server.py:33-34 |
| I29 | INFO | Fallback rerank silent: model gagal → FTS-only tanpa kabar (sudah ada log "fallback-rerank" — [VERIFIED] server.py:124-126) | server.py:124-126 |

### 1.3 Akar masalah yang paling berdampak (untuk benchmark)

Fastapi/duckdb/react gagal di get_docs bukan karena ranking jelek, tapi karena **halaman yang
dibutuhkan tidak pernah masuk korpus** (re-crawl tidak pernah jalan saat cakupan sempit,
`full=1` dicek dulu, etag mati, llms branch fetch ulang tanpa arah). Astro gagal karena
crawler tidak pernah menangkap SPA (tidak ada fallback sitemap/headless).

---

## 2. IDE & DESAIN TARGET — memo v2 "Sempurna"

### 2.1 Arsitektur target

```
┌─ MCP tools (4, bukan 3) ─────────────────────────────┐
│ resolve_library_id(library_name, query?)             │
│ get_docs(library_id, query, version?)                │   ← versi benar-benar memfilter
│ versions(library_id)                                 │
│ refresh(library_id) [opsional, eksplisit]            │   ← pisahkan update dari search
└──────────────────────────────────────────────────────┘
        │  FastMCP + lock per-id-ter-resolve + backpressure
┌───────▼───────────────┐   ┌──────────────────────────────┐
│ ingest engine         │   │ retrieval engine             │
│ • llms.txt > .md pages│   │ FTS5 bm25() ─┐                │
│   > sitemap > crawl   │   │ vec (sqlite-vec)─┤ RRF k=60  │
│ • page-level chunking │   │       (harus AKTIF)           │
│ • 512 tok + overlap 15│   │ rerank bge-reranker-v2-m3     │
│ • conditional GET+hash│   │ dedupe (path-normalized)      │
│ • anti-SPA fallback   │   │ trim 3000 tok (potong, bukan │
│ • SSRF guard          │   │  skip)                        │
└───────────────────────┘   └──────────────────────────────┘
        │ persist                        │
┌───────▼───────────────────────────────▼──────────────────┐
│ SQLite: schema migrasi PRAGMA user_version; FK; indeks;   │
│ per-lib: etag, content-hash, fetched_at, version, full,   │
│ last_check, popularity; WAL; single writer + timeout      │
└──────────────────────────────────────────────────────────┘
```

### 2.2 Keputusan desain (dengan alasan + sumber)

**D1. Aktifkan vektor (I1).** Embedding untuk SEMUA chunk, termasuk jalur ingest lokal
(bukan hanya build-cache). Ini prasyarat "hybrid" yang jujur. `[INFERRED]` — dari audit
store.py; benchmark harus ulang setelah ini karena skor lama FTS-only.

**D2. Idempotent lock key.** Lock dihitung dari id SETELAH resolve (canonical), bukan ID
mentah user. `next`/`nextjs` → lock sama. `[VERIFIED]` I3.

**D3. Lazy-load dengan lock (thread-safe singleton).** `_embeddings` & `_reranker` pakai
`threading.Lock` sekali. `[VERIFIED]` I2.

**D4. Resolve cache memisahkan (name) dari (query).** Cache hasil `_resolve(name)` per name
(6-sumber) TTL ~24-48 jam; `query` hanya untuk rerank/order hasil lokal, TIDAK memicu
network baru. `[VERIFIED]` I4 + G2.

**D5. Freshness adaptif (ganti I5/I6/I7).** `[VERIFIED]` riset:
- Conditional GET: `If-None-Match` + `If-Modified-Since` bersamaan; 304 = skip.
- Validator lemah → **content hash** (simhash 64-bit, Hamming ≤3 bit near-duplicate,
  strip boilerplate dulu).
- Re-crawl interval adaptif: perpendek saat berubah, multiplicative backoff saat statis;
  popularity-based threshold (popular lib = lebih sering dicek).
- `recrawl_at` baru di-set SETELAH crawl sukses (I9).
- `_maybe_refresh`: hasil dipakai — update `latest_ver` + tandai chunks lama, jangan buang
  return value (I5).

**D6. Ingest sumber bertingkat.** `[INFERRED]` dari riset llms.txt:
1. `llms-full.txt` (satu file, coverage penuh) → 2. `llms.txt` (daftar .md pages, fetch
   per page, skip `existing`) → 3. `sitemap.xml` (untuk SPA/astro: astro.build pasti punya
   sitemap) → 4. crawl BFS terbatas. llms branch harus hormati `existing` (I10).
- Anti-SPA fallback: jika HTML kosong setelah ekstraksi → coba `?output=1` /
  `?raw=1` / sitemap / headless (puppeteer-core optional, [ASUMSI] berat — jadikan opsional).

**D7. Chunking page-level, 512 token + overlap 15%.** `[VERIFIED]` riset: page-level menang
e2e (0.648), sweet spot 256-1024, overlap 10-20% (15% terbaik NVIDIA). Ganti 256/50 saat
ini → 512/75. Normalisasi path sebelum dedupe: strip `.html`, trailing `/` (I21).

**D8. Jangan buang oversize — potong.** `_split_oversize` dipakai untuk chunk >12k char
sebelum dikirim (I22). `[INFERRED]`.

**D9. Rerank lebih kuat.** Naik dari ms-marco-MiniLM-L6 (baseline lama) ke
**bge-reranker-v2-m3** (568M, Apache-2.0, multilingual, pilihan open self-host terbaik
menurut riset). Fallback chain: bge → MiniLM → no-rerank (log). Tetap ONNX quantized 8-bit
dan evaluasi lift-nya. `[VERIFIED]` riset reranker.

**D10. Embedding upgrade bertahap.** Saat ini bge-small (240MB resident). Target:
**Qwen3-Embedding-0.6B/4B** (instruction-aware, MRL, 32K ctx, No.1 MTEB multilingual) ATAU
**bge-m3** (dense+sparse+multi, 8K ctx). Aturan: context-length model > ukuran chunk (model
512-token memotong chunk 1000 token diam-diam — mxbai warning). 0.6B 4-bit ≈ 5GB RAM
[ASUMSI]-cek; ukur dulu vs gain, tetap bisa pakai bge-small bila resource kecil.
`[VERIFIED]` riset.

**D11. Versi sungguhan (G4).** `version` jadi filter nyata di query `search()` (kolom `ver`
sudah ada). Untuk docs multi-versi di path (numpy `vX.Y`): resolve versi → pilih path.
Version analyzer sederhana: deteksi `latest/`, `vX.Y/`, `stable/` di URL.
`[INFERRED]` — meniru context7.

**D12. Guidance diperkaya (G8).** Pesan per kondisi: lib tak dikenal (exist), SPA/gagal
fetch, versi tidak ada, rate limit, network error, versi docs lebih baru dari index
("docs updated recently, refresh() or try again"). `[VERIFIED]` pattern context7.

**D13. Trust 2-dimensi (G6).** `trust` (log10 stars/downloads, cache _stars_of dengan TTL +
pakai data per-source sekaligus untuk hemat rate limit — I16) + `benchmark_score` opsional
(LLM-jury sekali per lib, disimpan di DB). Keduanya ekspos di resolve output.
`[INFERRED]` — model context7 yang disederhanakan.

**D14. SSRF guard (I15).** Whitelist skema http(s), blok localhost/private IP/loopback/
metadata IP (169.254.169.254); validasi host di `ingest_docs` dan `fetch_text`; max size
resource (mis. 5MB). `[VERIFIED]` I15.

**D15. DB hardening (I12/I17/I23/I24).** `PRAGMA user_version` + migration list;
`CREATE INDEX chunks(lib_id)`; FTS `lib_id` jadi indexed (content='' dengan external content
atau setidaknya trigram); FK libs→chunks; satu koneksi writer + timeout; `get_lib` jangan
SELECT *; `get_versions` try/except. `[VERIFIED]` audit.

**D16. Observability penuh (I20/I28).** Activity log tambah: chunks hasil ingest, fetch
gagal per URL, latency embed/rerank/query, query-miss (0 hit + alasan), versions check.
Rotasi log. Jangan swallow OSError.

**D17. Evaluasi berkelanjutan (G11).** `bench/` golden set 100-500 query (nDCG@10 manual +
LLM-as-judge council) di-commit; jalankan tiap rilis; bandingkan skor antar versi.
`[VERIFIED]` riset eval.

**D18. CLI & struktur (I18).** `main()` pakai argparse ketat; pisahkan file: `server.py`
(MCP only), `cli.py` (warmup/cache), `cache.py` (build-cache fetch). Bersihkan artefak
(docs.db.bak/.cache) (I26).

**D19. Tests (I19).** Tambah unit test: _recrawl, _maybe_refresh, _crawl (mock network),
rollback cache, migrasi schema, concurrency (lazy-singleton, lock alias), SSRF guard.
Network path: pytest.mark.network tetap, tapi sediakan make target. Perbaiki docstring basi.

**D20. Anti-injection (G9).** Skor prompt-injection sederhana pada teks docs (deteksi
"ignore previous instructions"/"system prompt" dalam chunk sebelum embed; buang/tandai).
`[INFERRED]` — versi mini pipeline context7.

---

## 3. ROADMAP FASE — Urutan Eksekusi

### Fase 1 — Fondasi kebenaran retrieval (impact terbesar, skor benchmark)
1. D1: embedding aktif di semua jalur ingest (vec tidak lagi 0) — **prasyarat hybrid**
2. D2: lock key canonical (perbaiki double-ingest tailwind/tailwindcss dulu)
3. D3: singleton lock (model load 1×)
4. D4: cache resolve by name
5. D7: chunking 512/15% + normalisasi path (I21)
6. D8: oversize dipotong, tidak dibuang (I22)
7. Benchmark ulang penuh (ronde 10) → ini baseline baru yang jujur

### Fase 2 — Freshness & coverage (perbaiki fastapi/duckdb/react/astro)
8. D5: conditional GET + content hash + recrawl adaptif (I5/I6/I9)
9. D6: ingest bertingkat llms-full > llms > sitemap > crawl; llms hormati existing (I10);
   astro via sitemap
10. D11: version filter nyata
11. D12: guidance diperkaya
12. Benchmark ulang (ronde 11): fastapi OAuth → `/reference/dependencies/`, duckdb →
    `/sql/window_functions`, react → hooks page, astro → chunk ada

### Fase 3 — Kualitas retrieval (naikkan ceiling)
13. D9: rerank bge-reranker-v2-m3 (ukur lift dulu, golden set)
14. D10: embedding Qwen3/bge-m3 bila resource cukup
15. D13: trust 2-dimensi + cache _stars_of
16. D17: golden set 100-500 query + evaluasi formal
17. D20: anti-injection mini

### Fase 4 — Hardening (stabilitas & keamanan)
18. D14: SSRF guard
19. D15: DB migration + indeks + FK + single writer
20. D16: observability lengkap + rotasi log
21. D18: refactor CLI/struktur file, bersihkan artefak
22. D19: test suite lengkap

### Fase 5 — Polish
23. D20 lanjut: benchmarkScore LLM-jury opsional
24. Pack & docs: README cara pakai, konfigurasi, arsitektur
25. Release v2.0 + benchmark final (ronde 12+)

---

## 4. KRITERIA "SEMBUNYI" / Definition of Done v2

- [ ] `chunks_vec` > 0 di prod, RRF benar-benar hybrid (bukan FTS-only)
- [ ] Benchmark ronde: resolve A+, anti-hal A+, relevance ≥ A− (fastapi/duckdb/react/astro
      semuanya memunculkan halaman yang benar), stability A+ di 30+ calls
- [ ] Version param benar-benar memfilter
- [ ] Tidak ada silent failure: semua kegagalan fetch/ingest/rerank masuk activity.log
- [ ] Tests: unit suite hijau, termasuk concurrency & SSRF
- [ ] Golden set: skor evaluasi tercatat dan tidak turun antar versi
- [ ] verify.sh PASS (sesuai CUI-SYS)

---

## 5. CATATAN JALAN PINTAS YANG DISENGAJA (untuk diputuskan di sesi eksekusi)

- D9/D10 model baru menambah RAM (bge-reranker 568M + Qwen3-embed bisa 1-2GB+).
  Jika target device kecil → tetap bge-small + MiniLM rerank, hanya aktifkan vec.
- Headless browser (astro) opsional & berat; coba sitemap dulu (astro.build punya
  sitemap-index.xml) — kalau cukup, headless tidak perlu.
- LanceDB sebagai pengganti sqlite-vec hanya jika chunk > ~100k (sqlite-vec brute-force
  cukup sampai puluhan ribu vektor) — [VERIFIED] riset.
- `refresh()` tool eksplisit di Fase 1 opsional; bisa juga internal-only (auto-refresh).
