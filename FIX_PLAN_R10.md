# FIX_PLAN_R10 — Eksekusi MASTER PLAN v3 (REPORT.md ronde 11)

Acuan: REPORT.md (MASTER PLAN v3: 4 lapisan L1-L4, B1-B5, DoD v3) + riset swarm
3 sub-agent (audit kode post-r9, audit runtime docs.db, riset web feasibility)
+ verifikasi web manual (react/duckdb/fastapi llms & sitemap).

## Fakta terverifikasi (swarm R10, bukan hanya REPORT)

**Kode** (semua klaim R11 terkonfirmasi dgn file:line aktual):
- Cap 200 server.py:327 memotong sebelum halaman target; probe serial
  llms-full(6s)+llms(6s)+sitemap(5s) = 10-18s dari budget ~28s (ingest.py:303-329)
- TIDAK ada tabel crawl_state; `_crawl` reset seen/queue tiap call (ingest.py:250)
- has_vec dicek SEBELUM ingest (server.py:296-301) → call pertama & search ke-2
  (server.py:342) selalu FTS-only; `_embed_async` daemon=True tanpa retry
- Tidak ada: anti-injection, simhash/near-dup, golden set (bench = 22 query,
  tanpa eval.py), deny-path (feeds//showcase//plus/), locale strip di norm_path,
  dedupe retrieval, prune stale rows, cap per-tier
- `_path_allowed` SUDAH filter locale en (ingest.py:18-25) — tapi norm_path
  belum strip /en/ → dedupe en/x vs /x gagal; is_full min_chunks=3; ver sudah
  diisi latest_ver (server.py:293) — klaim R11 "ver kosong" BASI (313 chunk
  ber-ver: astro/docker/poetry/tailwindcss/uv)

**Runtime DB** (docs.db, 22 libs / 2862 chunks / 81 vec):
- chunks_vec = 81 baris, 100% astro — 21/22 lib vec 0 ✓ klaim R11
- fastapi 200/8 path, 0 "dependencies"; duckdb 200/27 path, 11 pasangan .html
  (114 chunk .html), 0 window_functions; react 87/8, 0 useEffect
- astro 81/10 path, 4 locale (en/hi/zh-cn/zh-tw, konten pasangan sama);
  tailwindcss 34 chunk noise (feeds 11, showcase 2, plus 21)
- full=0: astro/docker/prisma/pydantic; etag kosong 21/22

**Web** ([VERIFIED]):
- react.dev/llms.txt 14.3KB, **177 link** (50 learn, 48 reference/react, 39
  react-dom); berisi `/learn/synchronizing-with-effects.md` (= target alt B3);
  llms-full.txt **404**
- fastapi.tiangolo.com/sitemap.xml flat 151 loc, berisi
  `/tutorial/dependencies/` (target B1 ✓); robots.txt tanpa larangan
- duckdb.org: llms.txt ADA (12 link tipis), sitemap.xml 3175 loc dgn
  `/docs/lts/sql/query_syntax/...` (mengandung substring "docs/sql/query_syntax"
  = target B2 ✓); llms tipis → WAJIB union sitemap
- jina-reranker-v2-base-multilingual ADA di fastembed (1.11GB) tapi
  license **CC-BY-NC-4.0** → TIDAK dipakai; bge-m3/Qwen3/bge-reranker-v2-m3
  TIDAK ada di fastembed (terkonfirmasi dari source qdrant/fastembed)
- simhash: manual 64-bit (~30 baris, zero-dep) lebih cocok daripada paket
- robots.txt fastapi/react = allow-all → parsing robots dilewati (catatan ADR)

## Daftar fix ronde ini (L1 + L2 + L4-1/2/5/6)

| # | Item | Perubahan |
|---|---|---|
| R10-1 | L1-3 | **Probe paralel**: llms-full+llms+sitemap-index+sitemap di-fetch konkuren, timeout 4s (hemat 10-18s/call) |
| R10-2 | L1-1 | **Discovery union**: llms-full → llms (SEMUA URL) + sitemap union (halaman sitemap yg tak ada di llms) → sitemap saja → gh_raw → crawl → single. Query hanya memboboti urutan (prio), bukan membatasi. Fastapi ter-cover (151 loc), duckdb union (12+3175), react (177) |
| R10-3 | L1-2 | **Cap per-tier** (bukan 200 global): llms 300, sitemap 400, BFS 300; kolom `libs.cap` (migrasi user_version=1) utk override per-lib; server.py:327 cap hard 200 dihapus |
| R10-4 | L1-4 | **Persist BFS/progress**: tabel `crawl_state(lib_id, docs_url, seen, queue, updated_at)`; seen (semua sumber) & queue (BFS) disimpan saat deadline habis, dilanjutkan call berikutnya, dibersihkan saat complete; di-skip jika docs_url berubah |
| R10-5 | L1-5 | Re-crawl progresif: utk lib full=0 tiap call lanjut (existing+seen), sampai complete sejati → full=1 |
| R10-6 | L2-1 | **norm_path strip locale default en** (`/en/x` ≡ `/x`); unit test locale baru |
| R10-7 | L2-2 | chunks.path disimpan TER-NORM (sudah sebagian via r9, dilengkapi) + **prune stale rows** saat complete: `store.prune_chunks(keep=visited)` (bersihkan 114 .html duckdb, 62 astro non-en) |
| R10-8 | L2-3 | **Dedupe retrieval**: store.search group by path ter-norm, keep skor tertinggi per group sebelum trim |
| R10-9 | L2-4 | **Deny-path noise**: feeds/, /showcase, /plus/, blog/ (duckdb /20xx/), *.xml non-sitemap di `_path_allowed` |
| R10-10 | L4-1 | **Embed dijamin**: `_embed_async` + retry 1×; lazy backfill per lib saat get_docs (lib punya chunk, vec=0 → embed semua chunk di background setelah response) — target `chunks_vec > 0` semua lib |
| R10-11 | L4-2 | **Jujur hybrid**: has_vec dicek ulang SETELAH ingest (search ke-2 dgn query_vec bila vec baru tersedia) |
| R10-12 | L4-5 | **Anti-injection**: regex scan saat fetch_text ("ignore previous instructions", "</system>", dll) → drop chunk |
| R10-13 | L4-6 | **Guidance query jelek**: query < 3 char / generik ("docs","api","usage") → guidance saran query spesifik |
| R10-14 | — | Test: locale strip, deny-path, prune, dedupe search, crawl_state persist, probe order, union llms+sitemap, anti-injection, guidance, backfill mock, cap per-tier |
| R10-15 | — | Verifikasi B1-B3 path: react synchronizing-with-effects ✓, fastapi tutorial/dependencies ✓, duckdb docs/lts/sql/query_syntax ✓ (web-verified) — re-ingest live di verifikasi akhir |

## Backlog (TIDAK dieksekusi ronde ini, catat utk ronde berikutnya)

- L3-1..L3-3: etag per docs source + simhash 64-bit near-dup + interval adaptif
  + ver verify (etag docs_etag hidup, ver sudah terisi — sisa simhash + interval)
- L4-3: jina-reranker-v2 TIDAK dipakai (license CC-BY-NC-4.0) — MiniLM tetap;
  alternatif komersial-safe perlu riset
- L4-4: golden set 30-60 Q&A + bench/eval.py + skor per rilis (fase terakhir)
- Parse robots.txt (fastapi/react allow-all → tidak mendesak; ADR dicatat)
- Cleanup DB: baris lama non-en/.html tersapu otomatis oleh prune saat
  re-ingest lib terkait; docker/prisma/pydantic full=0 → re-ingest progresif

## Verifikasi wajib

```bash
cd /root/.local/share/memo
.venv/bin/python -m memo.store && .venv/bin/python -m memo.ingest && .venv/bin/python -m memo.registry
.venv/bin/pytest tests/ -q -m "not network"
# live (opsional): ingest_lib("https://fastapi.tiangolo.com", deadline=25) → cek
#   path tutorial/dependencies muncul; react → synchronizing-with-effects;
#   duckdb → query_syntax (cap 400, butuh beberapa call progresif)
```
