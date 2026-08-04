# FIX_PLAN_R9 — Eksekusi MASTER PLAN v2 (REPORT.md, 2026-08-04)

Acuan: REPORT.md (MASTER PLAN v2: G1-G12, I1-I29, D1-D20, roadmap 5 fase) +
riset swarm 3 sub-agent (audit kode pasca-r8, audit runtime docs.db, riset
feasibility sitemap/conditional-GET/reranker/embed/sqlite-vec).

## Temuan kunci keadaan aktual (verifikasi swarm, post-r8)

- **I1 KRITIS**: `chunks_vec` = 0 baris di prod; jalur MCP FTS-only by design
  (server.py:264). Embed nyata di ARM: **622ms/chunk @540 token** → 30s budget
  hanya muat ~45 chunk. D1 sinkron tidak realistis → **embed asinkron**.
- **I2 KRITIS**: `_embeddings`/`_get_reranker` lazy tanpa lock → load 2×.
- **I3 KRITIS**: lock pakai ID mentah user; **tailwind & tailwindcss duplikat
  full=1 di DB** (docs_url sama). Lock key canonical + dedupe libs by docs_url.
- **I4 KRITIS**: cache resolve keyed (name,query) → hot path re-resolve.
- **I6**: etag '' 22/22 — `docs_etag()` (A9) tidak pernah jalan (daemon lama
  masih hidup, kode r8 belum pernah dieksekusi di prod!). Setelah daemon
  restart, A9 hidup; version_etag versi-npm tetap backlog (API versi tanpa
  etag reliabel).
- **I7**: `_extract`/`page()` tanpa try/except → HTML aneh bisa crash get_docs.
- **I9**: `_recrawl` tulis recrawl_at SEBELUM crawl → gagal tetap bakar cooldown.
- **I10/I13**: llms branch ignore `existing`, path `"title (url)"` (konvensi ganda).
- **I11**: deadline antar-halaman, 1 fetch lambat (20s) makan budget.
- **I12**: tanpa indeks chunks(lib_id), user_version=0.
- **I14**: `versions_of` 5 ekosistem SERIAL (hingga ~30s di bawah lock).
- **I15**: SSRF ringan (docs_url dari npm/pypi → bisa localhost).
- **I16**: `_stars_of` tanpa cache; rate-limit anon → stars 0 senyap.
- **I20**: query-miss tanpa reason (docker/react top:[] tanpa event reason).
- **I24**: `get_versions` json.loads tanpa try.
- **I26**: docs.db.bak 1.8MB + docs.db.cache 37MB; `_fetch_cache` tanpa try.
- **Astro**: docs.astro.build punya sitemap-index.xml → sitemap-0.xml (URL
  docs lengkap) — fallback D6 layak; react.dev TIDAK punya sitemap (llms.txt
  sudah jalur benar); fastapi punya sitemap.xml.
- **D9**: bge-reranker-v2-m3 int8 571MB, **2.2s/pair di ARM** vs MiniLM
  50-150ms → upgrade hanya utk CI/offline, **MiniLM tetap di jalur MCP**.
- **D7**: chunking aktual 256/50 (overlap vestigial) → target 512.
- **Ronde 9**: skor "resolve A+ / relevance B− (4/8: fastapi, duckdb, react,
  astro)" TIDAK terdokumentasi di bench/rounds/ (tak ada report-R9.md);
  query bermasalah: fastapi→reference/dependencies, duckdb→window functions,
  react→useEffect hooks, astro→content collections (ingest_empty).

## Status eksekusi (2026-08-04)

SELESAI & teruji: R9-1 s/d R9-19 (56 pytest passed, 1 deselected; selfcheck
store/ingest/registry PASS). Daemon 4041 lama dimatikan (kode r8+ r9 belum
pernah jalan di prod — restart opencode memuat kode baru). Artefak
docs.db.bak & docs.db.cache dihapus (I26).

Catatan verifikasi lanjutan (setelah daemon restart): etag 22/22 akan terisi
probe pertama `_maybe_refresh`; `chunks_vec` terisi bertahap via `_embed_async`
(setiap ingest baru, ~2 chunk/s di ARM); lib duplikat tailwind/tailwindcss
terkunci satu lock + merger docs_url (ingest berikutnya lewat satu id);
astro re-crawl pertama akan lewat jalur sitemap (docs.astro.build
sitemap-index.xml) alih-alih ingest_empty.

## Daftar fix ronde ini (prioritas, fase 1+2 MASTER PLAN)

| # | Item | Perubahan |
|---|---|---|
| R9-1 | D1/I1 | Embed asinkron: MCP path embed chunk ≤40 sync; >40 background thread (daemon) + add_chunks dgn vec. Hybrid best-effort (FTS tetap hidup saat vec belum siap). |
| R9-2 | D3/I2 | Singleton `threading.Lock` utk `_embeddings()` & `_get_reranker()`. |
| R9-3 | D2/I3 | Lock key canonical: `_lock_key(name)` = docs_url utk alias/builtin (instan), else nama mentah. Dedupe libs by docs_url di `_get_docs` (tailwind↔tailwindcss merger). |
| R9-4 | D4/I4 | Cache resolve network by `name` saja; builtin/alias instan tetap; A4 boost query diterapkan per-call di atas cache. |
| R9-5 | I5 | `_maybe_refresh` return dipakai: versi berubah → full=0 (re-ingest, chunks lama tetap). |
| R9-6 | I7 | try/except di `_extract` (trafilatura) & `_crawl.page`. |
| R9-7 | I9 | `recrawl_at` ditulis HANYA setelah crawl/chunks diterima (bukan di `_recrawl`). |
| R9-8 | I10/I13 | llms branch hormati `existing` (norm_path); `c["path"]` = URL ternormalisasi (satu konvensi). |
| R9-9 | I11 | Deadline per-fetch: timeout tiap halaman = sisa budget (min 2s). |
| R9-10 | D6 | Sitemap fallback di `ingest_lib`: llms-full → llms → **sitemap** → gh_raw → crawl → single. Parse sitemap-index & urlset, hormati existing+deadline. Astro ter-cover (docs.astro.build). |
| R9-11 | I14 | `versions_of` paralel (ThreadPool 5 sumber). |
| R9-12 | I15 | SSRF guard di `fetch_text` (choke point): blok localhost/private/loopback/metadata/.local. |
| R9-13 | I16 | `_stars_of` cache TTL 24h; 403/429 → sentinel (jangan 0 senyap berulang). |
| R9-14 | I12 | `CREATE INDEX chunks(lib_id)` + `PRAGMA user_version` (migration list sederhana). |
| R9-15 | I20 | Event `query_miss` saat hits kosong (full=1), count chunk hasil ingest. |
| R9-16 | I24 | `get_versions` json.loads try/except. |
| R9-17 | D7 | CHUNK_TOKENS 256→512 (overlap vestigial, biarkan); update test cap. |
| R9-18 | I26 | `_fetch_cache` exception-safe (try/finally rollback); hapus artefak docs.db.bak & docs.db.cache. |
| R9-19 | I19 | Test baru: SSRF, `_recrawl` (cooldown/post-crawl), llms-respect-existing, sitemap parse, lock canonical, resolve cache by name, embed async (mock). |
| R9-20 | — | Update FIX_PLAN status + verifikasi pytest/selfcheck; catat langkah restart daemon. |

## Backlog (dicatat, TIDAK dieksekusi ronde ini)

- D9/D10: bge-reranker-v2-m3 & Qwen3/bge-m3 — model baru RAM besar + 2.2s/pair
  di ARM; syarat: golden set utk ukur lift (fase 3). MiniLM & bge-small tetap.
- D13 trust 2-dimensi (benchmarkScore LLM-jury), D17 golden set 100-500 query,
  D20 anti-injection, D18 refactor CLI argparse + struktur file (I18),
  D15 FK/single-writer (I17), D12 guidance per-kondisi versi.
- I6 version_etag vs API versi (docs_etag A9 sudah menutup perubahan docs).
- Dokumen ronde 9: tulis report-R9.md dari bench/activity.log (data sudah ada).
- Cleanup DB: tailwind 135 chunk PNG biner tetap di docs.db (code fix A11
  mencegah baru); hapus via re-ingest atau DELETE manual.

## Verifikasi (wajib)

```bash
cd /root/.local/share/memo
.venv/bin/python -m memo.store && .venv/bin/python -m memo.ingest && .venv/bin/python -m memo.registry
.venv/bin/pytest tests/ -q -m "not network"
# lalu: pkill -f "memo --transport http" (daemon lama) + restart opencode
```
