# MASTER PLAN MEMO MCP v3 — PENUTUPAN TOTAL GAP (Update Ronde 11)

Tanggal: 2026-08-04 (revisi). Dibangun dari: swarm 4 sub-agent paralel (audit kode
`src/memo/*`, audit runtime `docs.db`, riset web best-practices 2025-26, riset
referensi Context7 asli) + verifikasi silang antar temuan.

Semua klaim bertag `[VERIFIED]` (file:line / URL / data DB) / `[INFERRED]` / `[ASUMSI]`.

---

## 0. STATUS TERVERIFIKASI (Ronde 11) — KOREKSI terhadap ronde 10

| Klaim di R10 | Fakta swarm R11 | Status |
|---|---|---|
| `_maybe_refresh` return dibuang (server.py:212) | SALAH — return dipakai (server.py:265-268, fix I5) | klaim basi |
| oversize >12.000 char dibuang | SALAH — trim memotong (store.py:264-275) + split paragraf (ingest.py:160-185) | klaim basi |
| crawler query-aware "hanya halaman cocok query" | SETENGAH BENAR — prio() hanya memprioritaskan (ingest.py:239-248); pembatas nyata: cap chunk 200 (server.py:327), probe serial, deadline budget | mekanisme beda |
| etag mati semua | SETENGAH BENAR — etag sumber versi mati (registry.py:83 selalu `""`), `docs_etag` hidup dgn If-None-Match (registry.py:87-107) | parsial |
| lock id mentah / cache resolve per-query | SALAH — lock canonical (server.py:68-77, I3), cache by name (registry.py:434-441, I4) | klaim basi |
| astro content collections (B) | FIXED (R10) | ✅ |
| tailwind versions (B) | FIXED (R10) | ✅ |

**Gap B1–B5 SEMUA MASIH OPEN di R11.** Skor terakhir (R5): hit@5 39% (7/18) vs
Context7 44%; target 40% belum tercapai `[VERIFIED — bench/report-R5.md]`.

Fakta runtime DB `[VERIFIED — audit DB]`:
- 22 libs, **2862 chunks, `chunks_vec` hanya 81 baris (astro saja)** — 5/6 lib B vektor 0
- fastapi 200 chunk / 8 path (tanpa `/reference/dependencies`); react 87 / 8 (tanpa
  `/reference/react/*`); duckdb 200 / 27 (11 pasangan duplikat `.html`, unik cuma 16)
- astro 81 / 10 path tersebar 4 locale (en/hi/zh-cn/zh-tw) — pasangan konten sama
- `chunks.ver` kosong kecuali astro=7.1.6 & tailwindcss=4.3.3; `libs.etag` kosong 21/22;
  `full=0` utk astro/docker/prisma/pydantic → re-ingest tiap call
- FTS5: MATCH `"useEffect"` = 0, `"window_functions"` = 0 di semua lib; `"Depends"` hanya
  fastapi 2 → korpus memang tidak memuat topik target (coverage, bukan ranking)
- `queries.json` duckdb#12 (`docs/sql/query_syntax`) & react#10 (`/reference/react/useState`)
  path-nya TIDAK ada di DB → mustahil hit
- tailwindcss: 200 chunk termasuk `feeds/atom.xml`, `/showcase`, `/plus/ui-blocks` (noise)

---

## 1. AKAR PENYEBAB TERBUKTI (file:line) — kenapa coverage gagal

**B1–B3 = coverage, bukan ranking (konfirmasi R10, tapi mekanisme dikoreksi):**

1. **Cap chunk 200 tercapai sebelum halaman target** `[VERIFIED]` — server.py:327 cap
   200; fastapi & duckdb PERSIS 200 chunk di DB. Halaman dalam (window_functions,
   reference/dependencies, useEffect) tidak pernah sempat.
2. **Probe serial menghabiskan budget** `[VERIFIED]` — ingest.py:303-329 probe
   llms-full(6s)+llms(6s)+sitemap(5s) berurutan; fastapi (llms 404) & duckdb kehilangan
   10-18s dari budget ~28s sebelum crawl dimulai.
3. **full=0 saat complete=False → re-crawl restart dari nol** `[VERIFIED]` —
   server.py:319-340: chunks>0 tapi deadline habis → full=0 → get_docs berikutnya
   re-crawl; existing dihormati tapi **state BFS tidak dipersist** → halaman prioritas
   di-fetch ulang, halaman dalam tidak pernah tercapai.
4. **Re-crawl full=1 dibatasi query-miss 1×/jam** `[VERIFIED]` — server.py:346-347;
   selain itu hanya docs_url berubah yang memicu (server.py:263,397).
5. **react: llms.txt ADA** (react.dev/llms.txt, daftar `/reference/*.md` +
   `/learn/*.md`) `[VERIFIED — web]` tapi korpus react tidak memuat useEffect →
   jalur llms tidak pernah dipakai efektif utk react (ingest pertama sebelum fix
   I10/I13, tanpa re-crawl penuh). duckdb.org juga punya llms.txt; fastapi 404
   (fallback sitemap/BFS wajib) `[VERIFIED — web]`.

**B4–B5 = duplikat & stale rows:**
- `norm_path` strip `.html`/trailing slash ADA (ingest.py:28-35, dipakai di jalur
  ingest) **tapi normalisasi LOCALE TIDAK ADA**; `store.search` TIDAK dedupe path
  ter-norm (store.py:171-234) `[VERIFIED]`
- `add_chunks` (store.py:123-156) hanya UPSERT path yang dikunjungi — baris lama
  (.html, /hi/, locale lain) **tidak pernah di-prune** → 114 chunk .html duckdb &
  pasangan en/hi astro mengendap permanen `[VERIFIED]`
- FTS5 rusak sinkron? tidak — FTS sinkron dgn chunks; masalahnya isi korpus itu sendiri.

**Lapis retrieval:**
- **Vector search nyaris mati**: `_embed_async` (server.py:185-199) gagal hanya di-log,
  thread daemon mati saat restart → 5/6 lib FTS-only (81/2862 vec) `[VERIFIED]`.
- has_vec dicek SEBELUM ingest (server.py:296-301) → call pertama selalu FTS-only.
- Anti-injection: TIDAK ADA implementasi `[VERIFIED — grep src/]`.
- Golden set formal: TIDAK ADA (hanya 22 query bench manual) `[VERIFIED — bench/]`.
- Content-hash/simhash near-duplicate: TIDAK ADA `[VERIFIED]`; If-None-Match hanya di
  `docs_etag` HEAD llms.txt (registry.py:96-100).

---

## 2. RENCANA PERBAIKAN v3 — EMPAT LAPISAN (wajib berurutan, verify tiap lapis)

> Prinsip tetap: fix akar di fungsi bersama, bukan per-query. Koreksi model:
> **bge-reranker-v2-m3 / bge-m3 / Qwen3-Embedding TIDAK didukung fastembed**
> `[VERIFIED — web]` — rekomendasi R10 dibatalkan; pakai yang benar-benar ada
> (L4-3).

### Lapisan 1 — Coverage penuh (B1–B3)

**L1-1. Discovery 3-tier: `llms.txt` → `sitemap.xml` → BFS terkendali.**
- Jika llms.txt ada → fetch SEMUA URL di dalamnya (prioritas penuh, bukan campur BFS);
  llms-full.txt bila ada → satu file → chunk page-level.
- Jika 404 → sitemap.xml → daftar URL; query HANYA memboboti urutan fetch
  (prio() sudah ada), bukan membatasi jumlah.
- BFS hanya fallback; hormati robots.txt; budget 300-500 halaman/lib.
- react/duckdb ter-cover via llms; fastapi wajib sitemap+BFS.

**L1-2. Cap chunk dinaikkan & per-tier, bukan global 200.**
- Cap = f(sumber): llms penuh selalu; sitemap ≥ 400; BFS 300-500. Cap saat ini
  (server.py:327) terbukti memotong di tengah — jadikan parameter per-lib di DB.

**L1-3. Probe paralel (L1-2 lama).** llms-full+llms+sitemap-index+sitemap di-fetch
konkuren (thread/async), timeout per-probe pendek — jangan 10-18s serial sebelum crawl.

**L1-4. Persist state BFS** per lib (tabel `crawl_state`: seen/queue/visited_at).
Re-crawl LANJUT dari posisi terakhir, tidak mulai dari 0 (kunci B1-B3 lintas call).

**L1-5. Re-crawl progresif saat coverage belum penuh.** Hapus batas query-miss 1×/jam
untuk lib `full=0`: izinkan lanjut BFS sampai `is_full` sejati (≥ min halaman, bukan
min chunk 3). `full=1` hanya saat coverage penuh (L1-5 R10 tetap).

Verify L1: 3 query B1-B3 memunculkan path benar; FTS spot-check `window_functions`>0,
`useEffect`>0; fastapi `reference/dependencies` masuk.

### Lapisan 2 — Dedupe & kebersihan korpus (B4–B5)

**L2-1. `norm_path` + strip locale.** Pilih satu locale default (en); buang prefix
`/en/` `/hi/` `/ja/` `/zh-*/` dst utk dedupe + filter non-default saat ingest.

**L2-2. `chunks.path` disimpan TER-NORM** (bukan raw), + **prune stale rows**: setelah
re-ingest lib, `DELETE` chunk lib tsb yang path-nya tidak dikunjungi call itu
(bersihkan 114 `.html` duckdb, 31 `/hi/` astro, 4 locale).

**L2-3. Dedupe di retrieval** (store.search): group path ter-norm, ambil score
tertinggi per group sebelum trim budget. Berlaku seketika, tanpa tunggu re-ingest.

**L2-4. Deny-path noise**: `feeds/`, `/showcase`, `/plus/`, `*.xml` non-sitemap —
daftar deny umum + per-lib, di `_path_allowed` (ingest.py:15-25).

Verify L2: duckdb 0 pasangan `.html`; astro 1 locale; unit test locale baru
(saat ini 0 test locale `[VERIFIED — grep tests/]`).

### Lapisan 3 — Freshness & kebenaran versi (L2 R10)

**L3-1. ETag/Last-Modified disimpan per docs source** + If-None-Match; 304 → skip
fetch, naikkan interval. Bila server tak beri validator → **content hash (simhash
64-bit, Hamming ≤3 = near-dup)** — tidak ada sama sekali saat ini.

**L3-2. Interval adaptif per popularitas**: threshold umur (hari) dari stars/downloads
(cache `_stars_of` sudah ada, jangan hit GitHub per call). `recrawl_at` post-crawl
(sudah I9). Ganti `full=0` yang re-ingest tiap call.

**L3-3. `chunks.ver` diisi saat re-crawl** + verify soft-filter versi (A7) benar
dengan data ber-version.

Verify L3: `libs.etag` terisi >0; 304 tercatat; lib berubah → re-crawl; lib statis →
skip.

### Lapisan 4 — Retrieval & kualitas (ceiling)

**L4-1. Embed DIJAMIN selesai**: ganti thread daemon → non-daemon + join saat
shutdown + retry; backfill vec semua chunk lama (CLI `--warmup --force` / build-cache).
Target: `chunks_vec > 0` utk SEMUA lib (81/2862 → penuh).

**L4-2. Jujur soal hybrid**: selama lib belum vec, BM25 murni (jangan janji hybrid);
has_vec dicek SETELAH ingest call pertama, bukan sebelum (pindah posisi cek
server.py:296-301), atau jalankan embed sinkron untuk lib itu saat ingest pertama.

**L4-3. Model**: tetap `bge-small-en-v1.5` (ada di fastembed, 67MB int8, cocok ARM).
Rerank opsional: `jina-reranker-v2-base-multilingual` (1.11GB, ADA di fastembed)
sebagai upgrade dari ms-marco-MiniLM — **ukur lift dulu (L4-4), jangan ganti buta.**
Jangan install model yang tidak didukung fastembed.

**L4-4. Evaluasi formal**: golden set 30-60 Q&A (WAJIB: B1-B3, query miss R5),
metrik **set-based hit@5/recall@k** (bukan nDCG saja — LLM konsumsi set, bukan list
`[VERIFIED — web]`), baseline BM25-only vs hybrid vs rerank; skrip `bench/eval.py`;
skor tercatat tiap rilis (regression test B1-B3).

**L4-5. Anti-injection mini** (L3-5 R10): regex scan saat ingest ("ignore previous
instructions", role-switch, `</system>` dsb.) → tandai/buang chunk.

**L4-6. Guidance query jelek** (pola Context7): query < N char / generik ("docs",
"api") → guidance saran query spesifik, bukan hasil diam-diam jelek.

---

## 3. URUTAN EKSEKUSI & VERIFIKASI

| # | Langkah | Verify dengan |
|---|---|---|
| 1 | L1-1 + L1-3: discovery 3-tier + probe paralel (fastapi, duckdb, react) | 3 query B1-B3 muncul path benar; FTS `useEffect`/`window_functions` > 0 |
| 2 | L1-2 + L1-4: cap per-tier + persist BFS state | re-crawl lanjut bukan restart; fastapi `reference/dependencies` masuk |
| 3 | L1-5: re-crawl progresif sampai coverage penuh | `full=1` hanya saat ≥ min halaman; `full=0` lib lanjut BFS tiap call |
| 4 | L2-1..L2-3: norm+locale, path ter-norm, prune stale, dedupe retrieval | duckdb 0 `.html` ganda; astro 1 locale; unit test locale |
| 5 | L2-4: deny-path noise | tailwind tanpa atom.xml/showcase |
| 6 | L3-1..L3-3: etag + simhash + interval adaptif + ver | `libs.etag` > 0; 304 log; `chunks.ver` terisi |
| 7 | L4-1 + L4-2: embed dijamin + backfill | `chunks_vec > 0` semua lib; BM25 murni jujur selama belum vec |
| 8 | L4-4: golden set + eval.py | skor baseline BM25 vs hybrid tercatat; B1-B3 di set |
| 9 | L4-3 (opsional): jina-reranker v2 | lift terukur di eval, tanpa regresi latency |
| 10 | L4-5 + L4-6: anti-injection + guidance query | docs jahat di-buang/ditandai; query pendek → guidance |

---

## 4. DEFINITION OF DONE v3 (semua wajib)

- [ ] B1: `get_docs(fastapi, "Depends OAuth2")` → `/reference/dependencies/` atau `/tutorial/security/` keluar
- [ ] B2: `get_docs(duckdb, "window functions RANK OVER")` → `/sql/window_functions` keluar
- [ ] B3: `get_docs(react, "useEffect")` → `/reference/react/useEffect` / `/learn/synchronizing-with-effects` keluar
- [ ] B4/B5: 0 duplikat locale/.html di semua hasil; path ter-norm di DB
- [ ] `chunks_vec > 0` untuk semua lib; tidak ada lib FTS-only diam-diam (log/guidance jika gagal)
- [ ] `libs.etag` terisi; 304 skip bekerja; simhash fallback ada
- [ ] `chunks.ver` terisi; version filter memfilter sungguhan
- [ ] Golden set + eval.py: skor tercatat, tidak turun antar rilis
- [ ] Tidak ada silent failure: semua kegagalan fetch/ingest/embed tercatat di activity.log
- [ ] Tests: unit suite hijau (termasuk locale dedupe, prune, anti-injection, cap per-tier)
- [ ] Benchmark ronde final: resolve 100%, hit@5 ≥ 40% (≥ Context7 44%), 0 kosong

---

## 5. RISIKO & KEPUTUSAN SAAT EKSEKUSI

1. **Waktu ingest naik**: llms+sitemap penuh (300-500 halaman/lib) = menit per lib.
   Putuskan: background + guidance "sedang meng-index" (rekomendasi) vs sinkron.
2. **RAM**: jina-reranker-v2 1.1GB hanya jika target device sanggup; default MiniLM
   (0.08GB). Jangan pakai model non-fastembed.
3. **react jalur llms**: react.dev/llms.txt berisi `.md` — chunk page-level dari
   llms-full bila ada; cek ukuran dulu (bisa besar).
4. **fastapi tanpa llms**: sitemap.xml + BFS — verifikasi sitemap berisi
   `/reference/dependencies/`.
5. **Dedupe locale default "en"**: halaman yang HANYA ada di locale non-en akan hilang
   — catat sebagai keputusan (ADR) bila itu yang dipilih.
6. **Jangan tiru Context7**: auth/dashboard, `context7.json` per-library, generateDocs
   dari source — itu biaya ekosistem cloud, bukan perilaku retrieval.
7. **Tiru Context7**: fase resolve→query (sudah), ID kanonik + pin versi
   (`/owner/repo@v`, parsial: A7 soft filter), refresh by age+popularity (L3-2),
   snippet dgn provenance (B: section_title/tokens/score sudah ada), guidance utk
   query jelek (L4-6).
8. **SQLite cukup**: sampai ~100k chunk sqlite-vec brute-force memadai; LanceDB hanya
   jika melewati itu.
