# AUDIT MEMO MCP — Ronde 1–7 + Analisis Source

Tanggal: 2026-08-04. Sesi audit read-only (tanpa perubahan kode).
Sumber: benchmark 7 ronde (12 lib real + 2 fake) + pembacaan `src/memo/*.py`, `aliases.json`, `docs.db`, `bench/activity.log`.

## A. BUG & KEKURANGAN

### A1. Ingest gagal diam-diam → `full=1` tapi 0 chunk (astro) [KRITIS]
- Gejala: `get_docs(astro, ...)` → `[]` terus-menerus; DB `libs` astro = `0 chunks, full=1`.
- Akar: `ingest_lib()` untuk docs JS-heavy (astro.build anti-bot/SPA) → crawler dapat 0 halaman → `( [], True )`; `server.py:174` menulis `full=1` karena `complete=True`, padahal chunk 0. `is_full()` di ingest.py:28 sudah ada tapi **tidak dipakai di server.py** — cuma dipakai selfcheck.
- Dampak: lib rusak permanen — `_get_docs` lihat `full=1` → skip re-ingest → semua query lib itu kosong selamanya, tanpa log (log activity hanya ditulis di akhir `_get_docs`, tidak di return dini `[]`).

### A2. `get_docs` tidak pernah re-crawl lib yang ter-index sempit [TINGGI]
- Gejala: requests hanya punya halaman `/user/advanced/`; react 87 chunk tanpa `useEffect`; tailwind 2 chunk; duckdb window-functions meleset.
- Akar: begitu `chunks > 0` dan `full=1`, ingest tidak pernah diulang kecuali docs_url berubah. Query "session timeout retries" dulu kosong karena halaman timeout (`/user/quickstart`) tidak ter-crawl — halaman hanya dipilih berdasarkan kata kunci query SAAT ingest pertama.
- Dampak: jawaban bergantung pada query pertama yang kebetulan di-ingest (cold-start bias), bukan cakupan dokumen.

### A3. `versions` di resolve tidak konsisten dengan tool `versions` [SEDANG]
- Gejala: `resolve_library_id(fastapi)` → `versions:"[]"`, tapi `versions("fastapi")` → 20 versi benar. Sebaliknya `resolve(requests)`/`resolve(react)` → versions TERISI. Inconsistent.
- Akar: `_resolve` (registry.py:409) return early untuk alias trust>90 **tanpa versi** (alias di aliases.json tidak punya `versions`), sedangkan requests/react kebetulan terisi via merge dari sumber lain — alias punya `versions` kosong karena entry manual tidak menyimpan riwayat.

### A4. Parameter `query` pada resolve hampir tidak berfungsi [SEDANG]
- `query` hanya dipakai di `_builtin` (pilih python vs node) dan `_gh_search` (hint bahasa). Untuk semua library non-builtin, query tidak mengubah ranking sama sekali. Kontras dengan context7 yang `query` adalah **parameter wajib** untuk ranking relevansi.

### A5. Anti-FP trust<1.0 terlalu agresif [SEDANG]
- registry.py:466 membuang semua entri `trust < 1.0`. Konsekuensi: express (repo kosong, trust 95 via alias — OK) tapi library kecil/baru tanpa stars & tanpa llms.txt → `trust 0.x` → hilang dari hasil. Ronde 7: `express` repo `""` (alias tanpa repo di aliases.json:49) — info repo hilang dari output.

### A6. `trim_to_tokens` + chunk oversize di-skip [RENDAH]
- store.py:199: chunk > 12.000 char **dibuang** dari hasil, bukan dipotong. Untuk halaman reference raksasa (fastapi/parameters), 1 halaman = 1 chunk raksasa → bisa hilang seluruhnya meski relevan. `_split_oversize` ada di ingest tapi hasilnya tetap satu chunk besar per section.

### A7. Version param `get_docs(version=...)` hanya label [RENDAH]
- server.py:143 `ver` dipakai sebagai label `ver` di tabel `chunks`, **tidak pernah sebagai filter query**. `get_docs(lib, q, version="5.0")` mengembalikan chunk versi apa pun yang ada. context7 adalah version-specific (nextjs@15.0) — ini gap besar secara filosofi.

### A8. Duplikasi path `.html` vs tanpa ekstensi [RENDAH]
- duckdb: `data/parquet/overview` DAN `data/parquet/overview.html` dua-duanya ter-crawl → hasil penuh duplikat (ronde 7: 8/10 hasil duplikat pasangan). Dedupe `existing` per path tidak menormalkan ekstensi.

### A9. `_maybe_refresh` tidak pernah jalan untuk lib tanpa etag [RENDAH]
- `registry.version_etag` mengembalikan `("", old_etag, [])` ketika `versions_of` gagal → `latest` kosong → update tidak terjadi. Ambiguitas: docs bisa berubah tanpa versi berubah (docs update) — tidak ada freshness untuk perubahan non-versioning.

### A10. Concurrency: lock per-library serial, bukan global [INFORMATIF]
- 2 request lib sama → serial (by design); request beda lib → paralel. Ronde 6-7 stabil (24-30 calls no crash) — **sudah teratasi**. `_embeddings()` lazy-load race di-cover preload `main()`.

## B. PERBANDINGAN FORMAT & OUTPUT vs CONTEXT7 (asli, upstash/context7)

| Aspek | memo | context7 (asli) |
|---|---|---|
| Tools | `resolve_library_id`, `versions`, `get_docs` | `resolve-library-id`, `query-docs` (+ `ctx7` CLI) |
| Resolve params | `library_name` + `query` opsional | `libraryName` + **`query` WAJIB** (untuk ranking) |
| Library ID | `fastapi` (slug bebas) | `/vercel/next.js` (path owner/repo, unik global) |
| get_docs param | `library_id`, `query`, `version` opsional | `libraryId` + `query` (version via ID/percakapan) |
| Output chunk | `{id, path, title, text}` | `{doc_path, doc_title, section_title, content, tokens, score}` — full path, section title, token count, BM25 score |
| Version-specific | tidak (versi cuma label) | **ya** (nextjs@15.0) |
| Arsitektur | live fetch + ingest on-demand (5–60s cold) | **hosted index** (API key, OAuth, paket `.db` prebuilt) |
| Trust | log10(stars/downloads) + llms.txt + penalti fork | "trustScore" internal (API private) |
| Self-healing | `[]` diam-diam (astro) | guidance message + `search_packages`/`download_package` |
| Token management | total cap 3000 (trim) | per-chunk `tokens` field untuk agent |

Gap paling mencolok: (1) field output chunk — memo kehilangan `section_title`, `tokens`, `score` yang dipakai agent untuk memilih & menghitung budget; (2) version-awareness; (3) self-healing; (4) `query` yang diabaikan.

## C. CARA PERBAIKI (prioritas, untuk dikerjakan di sesi lain)

1. **A1 (full=0 saat 0 chunk)** — di `_get_docs` server.py, ganti penulisan `full` dengan `ingest.is_full(complete, len(chunks))`; tambahkan `_log_activity` untuk return dini `[]` (observabilitas).
2. **A2 (re-crawl)** — tambah `max_age` per docs_url: jika `chunks > 0 && full=1` tapi `fetched_at` lama (mis. > 7 hari), atau query tidak menghasilkan hit → panggil `ingest_lib` lagi dengan `existing=paths` (incremental). Atau batas chunk per lib dinaikkan + crawl query-aware diulang.
3. **A3 (versi konsisten)** — di `_resolve`, untuk alias tanpa `versions`, jangan return early murni: tambahkan `versions_of(name)` (sudah di-cache TTL) ke `_norm_cand`.
4. **A4 (query dipakai)** — untuk library ter-resolve, gunakan `query` sebagai kata kunci di `_crawl` (sudah ada `terms`), dan/atau pertimbangkan keyword boost di `search()`.
5. **A5** — turunkan threshold ke `trust >= 0.5` + beri sinyal tambahan (punya `docs_url` valid) alih-alih batas keras 1.0.
6. **A6** — ganti skip-oversize menjadi potong via `_split_oversize` sebelum dikirim.
7. **A8** — normalisasi path di `_crawl`: strip `.html` + trailing slash saat dedupe `existing`/`seen`.
8. **Format output (B)** — tambahkan `section_title` (heading pertama dari text), `tokens` (len/4), `score` (dari BM25/RRF — saat ini score tidak diekspos dari `search()`).
9. **Version-specific (A7)** — jadikan `version` parameter filter nyata di `search()` (kolom `ver` sudah ada); untuk lib dengan docs ber-versioning (numpy `vX.Y` di path), pilih path sesuai versi.
10. **Self-healing** — kembalikan pesan guidance (seperti context7 `NO_DOCUMENTATION_FOUND_MESSAGE`) saat `[]` bukan karena lib tidak ada.

Catatan: skor ronde 7 (A−/A) menunjukkan stabil & relevan, tapi A1–A2 adalah silent-failure yang tidak terlihat di skor karena memengaruhi lib tertentu (astro) dan cakupan (bukan crash). Verifikasi semua fix dengan benchmark ulang (ronde 8).
