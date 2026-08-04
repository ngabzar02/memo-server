# FIX_PLAN — Ronde 8 (eksekusi perbaikan REPORT.md)

Tanggal: 2026-08-04. Acuan: `REPORT.md` (audit R1-R7) + hasil deep research swarm
3 sub-agent (kode aktual, runtime/DB, referensi context7 asli). Dokumen ini
adalah acuan kerja; tiap item ditandai `[DONE]` setelah diverifikasi.

## Status aktual (hasil riset swarm, 2026-08-04)

| Item | Status di kode saat ini | Temuan runtime |
|---|---|---|
| A1 | Sebagian: `is_full` sudah dipakai (server.py:189,204) | astro **full=1 & 0 chunk** di DB; flask juga full=1 0 chunk |
| A2 | Masih ada: re-crawl tidak pernah (server.py:177-179) | react 87 chunk / 8 halaman, 0 hit `useEffect` |
| A3 | Sebagian: patch DB di resolve_library_id (server.py:107-116) | aliases.json tanpa `versions`; nextjs latest_ver=0.0.3 (npm junk) |
| A4 | Masih ada: query hanya di `_builtin`/`_gh_search` | — |
| A5 | Masih ada: threshold >= 1.0 (registry.py:466) | express & litestar tanpa `repo` di aliases.json |
| A6 | Sebagian: hulu sudah hard-split 4x (ingest.py:100) | DB 0 chunk oversize; skip masih di trim_to_tokens |
| A7 | Masih ada: ver cuma label (server.py:173) | 99% chunk ver='' |
| A8 | Masih ada: dedupe path mentah (ingest.py:230) | **55% top-5 duplikat**; 11 pasangan .html di duckdb |
| A9 | Masih ada: etag kosong semua lib; version_etag return "" | etag '' utk SEMUA lib |
| A10 | Stabil (by design) | — |
| B | Masih ada: output {id,path,title,text} (store.py:169) | rerank score dibuang |
| C | Masih ada: [] senyap | 26/414 get_docs kosong tanpa pesan |
| **A11 (baru)** | Belum ada filter konten | tailwind **135/200 chunk PNG biner**, httpx 120 chunk .min.css |

Koreksi riset context7: format `{doc_path,doc_title,section_title,tokens,score}`
di REPORT.md TIDAK pernah ada di context7 publik (asli: `codeSnippets`/
`infoSnippets` + `contentTokens`; `query-docs` mengembalikan plain text).
Pesan guidance asli: *"Documentation not found or not finalized..."* —
`search_packages`/`download_package` bukan milik context7 (itu @neuledge/context).
=> memo tetap menambah `section_title`/`tokens`/`score` sebagai EKSTENSI berguna
bagi agent (bukan klaim meniru context7), guidance meniru kalimat context7.

## Prioritas & rencana kerja

1. **[DONE] A1** — server.py `_get_docs`: return dini `[]` saat ingest 0 chunk:
   update `full` via `is_full(complete, 0)` -> 0 + `_log_activity(reason=ingest_empty)`
   + return guidance. Lib baru 0-chunk tidak lagi tersandera full=1.
2. **[DONE] A2** — server.py: kolom `recrawl_at` (migrasi store.py init) +
   `_recrawl(conn, lib, force)`: cooldown 1 jam; force=query-miss (hits 0 pd lib
   full) -> re-crawl dgn query; selain itu usia konten (MAX(fetched_at)) > 7 hari.
   Inkorporasi di `_get_docs`: kondisi ingest bertambah `_recrawl()` age-based;
   setelah search, hits kosong + full + force -> ingest inkremental.
3. **[DONE] A3** — registry.py `_resolve` early-return alias: `versions_of(name)`
   (sudah TTL-cache) di-merge; `latest_ver` dikoreksi bila junk (0.0.3) tak ada
   di daftar versi. Skip utk builtin (node:/py:).
4. **[DONE] A4** — registry.py `_resolve`: keyword boost +0.5 utk kandidat yg
   repo/docs_url/id-nya memuat term query (>3 char), sebelum sort akhir.
5. **[DONE] A5** — registry.py threshold `>= 0.5`; aliases.json tambah `repo`
   utk express (`expressjs/express`) & litestar (`litestar-org/litestar`).
6. **[DONE] A6** — store.py `trim_to_tokens`: potong (truncate) chunk oversize
   ke sisa budget, bukan buang. Update 2 test trim.
7. **[DONE] A7** — store.py `search(..., version="")`: soft filter `ver=? OR
   ver=''` + urut prefer ver==version di atas (tidak pernah kosong).
8. **[DONE] A8** — ingest.py `norm_path()` (strip trailing slash + `.html`)
   dipakai utk seen/existing/path chunk di `_crawl`; server.py existing
   dinormalisasi; store.py `add_chunks` hapus path-variants (base, base.html,
   base/) sekali di awal. Membersihkan duplikat .html lama saat re-ingest.
9. **[DONE] A9** — registry.py `docs_etag()` (HEAD llms.txt fallback docs_url,
   conditional If-None-Match); server.py `_maybe_refresh`: etag berubah ->
   full=0 (re-ingest ringan), baseline pertama hanya simpan etag.
10. **[DONE] B** — store.py search: `section_title` (heading pertama),
    `tokens` (len/4), `score` (RRF); server.py `_rerank` menempel skor
    cross-encoder bila tersedia.
11. **[DONE] C** — server.py `_guidance()`: chunk pseudo {id:"guidance",...}
    saat lib tak terresolve / ingest 0 halaman (bukan query-miss normal).
12. **[DONE] A11** — ingest.py `_textual(content_type)` + dipakai di
    `fetch_text` & `_crawl.page()`: css/js/img/binary ditolak (racun korpus).
13. **[DONE] Test** — update test trim (A6), patch `versions_of` (A3), tambah
    test: A7 version filter, A8 norm_path/variants, A11 _textual, B meta
    fields, A1+C guidance, A4 boost. Jalankan `pytest tests/ -q` + selfcheck
    modul.

## Di luar scope (dicatat, tidak dikerjakan di ronde ini)

- Data sampah tailwind/httpx yang SUDAH ter-ingest tetap di docs.db (135 PNG
  biner); cleanup manual sekali jalan bila perlu:
  `DELETE FROM chunks WHERE path LIKE '%.png' OR path LIKE '%.css'`
  (code fix mencegah masuknya chunk baru; re-crawl tidak menghapus path lama).
- alias `ruff` hilang (resolve [] padahal astral-sh/ruff legit) — kandidat
  entry aliases.json di ronde berikutnya.
- `nextjs.latest_ver=0.0.3` di DB lama ter-copy dari npm junk; fix A3
  mencegahnya ke depan, DB lama diperbaiki saat re-crawl berikutnya.

## Verifikasi (wajib sebelum dianggap DONE)

```bash
cd /root/.local/share/memo
.venv/bin/python -m memo.store && .venv/bin/python -m memo.ingest && .venv/bin/python -m memo.registry
.venv/bin/pytest tests/ -q
```
