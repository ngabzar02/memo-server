<!-- SUPERSEDED 2026-08-03 by docs/SRS.md (canonical v2). Riwayat: boleh dikutip, jangan di-update. -->

# SRS — memo: MCP Server Dokumentasi Library Lokal

- Versi: 1.0 · Tanggal: 2026-08-03 · Penulis: BE (developer/docs)
- Sumber: `bench/research/memo-internals.md` (arsitektur aktual, tag `file:baris`),
  `bench/report-context7-vs-memo.md` (gap analysis), `bench/report-R4.md` (bug),
  `bench/research/context7.md` (parity Context7).
- Tag: `[BARU]` = belum ada di kode, dari gap analysis §3 laporan perbandingan.

## 1. Pendahuluan

**Tujuan**: spesifikasi untuk `memo`, MCP server lokal peniru Context7: resolve nama
library → ingest docs → hybrid search → rerank → kembalikan konteks ke LLM. Gratis
total, unlimited, offline-capable. Target kualitas: docs hit@5 ≥ 40% (bench R4: 28%,
report-R4.md:15).

**Ruang lingkup**: 5 modul Python + SQLite + CI cache + bridge daemon. Di luar
lingkup (YAGNI): enrich LLM, OpenAPI/Notion/Confluence, skala 33k library,
ekosistem plugin (report-context7-vs-memo.md:91).

**Definisi**:
- *library*: entitas dengan ID unik + docs_url, disimpan di tabel `libs` (store.py:37).
- *chunk*: potongan teks docs 256 token hasil chunking, satuan retrieval di `chunks` (store.py:54).
- *full*: flag korpus dianggap lengkap; `is_full` = chunk ≥ 3 (ingest.py:28-31).
- *hit@5*: fragment target query muncul di path salah satu dari 5 chunk teratas jawaban client MCP (report-R4.md:4-5).

## 2. Deskripsi sistem

Arsitektur aktual (memo-internals.md §1, §2): satu file DB `~/.local/share/memo/docs.db`,
5 modul Python:
- `server.py` (444 baris) — orkestrasi MCP: tools, pipeline `get_docs` 11 langkah, CLI, daemon HTTP (server.py:122-431).
- `store.py` (221) — SQLite WAL + hybrid retrieval (store.py:24-194).
- `ingest.py` (310) — fetch → extract (trafilatura) → chunk → crawl (ingest.py:46-263).
- `registry.py` (481) — resolve nama → kandidat lib (registry.py:26-384).
- `rerank.py` (66) — cross-encoder ONNX tanpa torch (rerank.py:52-66).

Data pendukung: `aliases.json` (~65 entri curated), `builtins.json` (35 Node + 40+
Python stdlib), `cache-libs.txt` (66 lib pre-built). CI GitHub Actions membangun
`docs.db` (~16 MB) sebagai release asset; daemon :4041 + bridge stdio self-heal
untuk opencode (memo-internals.md §5, §8).

## 3. Requirement fungsional

### FR-1 Resolve nama → library (MUST)
- Deskripsi: 9 sumber berurutan — `_alias` curated trust 95 (final tanpa network,
  registry.py:407-408) → `_builtin` node:/py: (registry.py:34-53) → llmstxt.cloud →
  npm → crates.io → Go proxy → PyPI → RubyGems → GitHub search (butuh token);
  6 sumber network paralel (registry.py:375-384). Trust final: `log10(downloads/stars)`
  + 2.0 llms.txt − 2.0 fork − 1.0 README (registry.py:355-366). Cache hasil 1 jam
  (registry.py:313); cache llms 24 jam (registry.py:321-338).
- Acceptance: `resolve_library_id` tanpa network mengembalikan alias terpasang,
  dan dengan network mengembalikan `latest_ver`/`versions` terisi (bug R4 #6, report-R4.md:129-133).

### FR-2 Ingest docs (MUST)
- Deskripsi: 5 level sumber — llms-full.txt → llms.txt → README GitHub → crawl BFS →
  single page (ingest.py:225-263). Filter `_path_allowed` domain+bahasa (ingest.py:18-25)
  dan `_looks_404` (ingest.py:284-289). Chunking 256 token/overlap 50 heading-aware
  H1-H4 (ingest.py:69-110); oversize di-hard-split (ingest.py:113-126); cap ~4×
  max_tokens (ingest.py:12-13). Budget 30s: crawl diberi deadline−2s (server.py:134,170);
  BFS 4-thread prioritas keyword query (ingest.py:154-222). Cap 200 chunk (server.py:182).
  Ingest parsial → `full=0` → dilanjut call berikutnya (server.py:179,194).
- Acceptance: para raksasa selalu dipecah ≤ hard-cap (sabotase Bug 2, report-R4.md:157);
  crawler hanya menyimpan path dalam domain allowlist + bahasa EN (Bug 4); `full=1`
  hanya bila korpus ≥ 5 halaman (Bug 5, report-R4.md:127).

### FR-3 Retrieval hybrid + rerank (MUST)
- Deskripsi: FTS5 BM25 (AND dulu, OR fallback, limit 20) + cosine vec0 (k=20 top),
  fusion RRF k=60 (store.py:129-153, 164-169). Rerank ONNX `ms-marco-MiniLM-L-6-v2`
  qint8 ~25 MB CPU threads=2, top-10, MAX_LEN 512, doc dipotong 1000 char; gagal load →
  fallback hybrid (server.py:66-93; rerank.py:12-14,40-50). Trim output 3000 token
  ~4 char/token (server.py:201; store.py:186-194). Query di-embed dengan
  bge-small-en-v1.5 384-dim threads=2 (server.py:52-60, 164-165).
- Acceptance: chunk oversize di-skip bukan memutus kiriman (Bug 1: `break`→`continue`,
  report-R4.md:77); client MCP menerima hasil non-empty saat log mencatat hasil;
  hit@5 ≥ 40% (report-context7-vs-memo.md:79).

### FR-4 Refresh docs & versi (MUST; refresh terjadwal [BARU] SHOULD)
- Deskripsi: `_docs_changed` cek docs_url resolve vs DB, TTL 1 jam; berubah →
  `drop_lib` + re-ingest; TANPA gate `github.com` (server.py:44, 204-223; Bug 3,
  report-R4.md:99-110). `_maybe_refresh` versi baru TTL 1 hari (trust>5)/7 hari; update
  versi, chunk LAMA dibiarkan — DELETE terbukti merugikan (server.py:226-251, 246-248).
  `[BARU]` refresh terjadwal background: Context7 refresh lazy async tanpa menunda
  respons (context7.md:20); memo cek per-request (overhead ~1-2 s, penyumbang latency
  median 2.93s) — pindahkan ke thread/jadwal background, hasil dipakai request berikutnya
  (report-context7-vs-memo.md:28,75).
- Acceptance: `[BARU]` cek docs_changed/versi tidak menambah latensi jalur `get_docs`;
  docs_url berubah → chunk lama di-drop walau URL bukan github.com (Bug 3).

### FR-5 Pin versi per-library `@version` [BARU] (SHOULD)
- Deskripsi: Context7 mendukung libraryId `/owner/repo@version` (context7.md:29);
  memo hanya latest. `[BARU]` terima `library_id@version`: versi valid (tolak prerelease,
  registry.py:99-112) → ingest docs versi tsb → simpan di `libs.versions`; default tetap
  latest. `versions_of` pilih ekosistem versi terbanyak (registry.py:228-246).
  Dampak reproduktifitas (report-context7-vs-memo.md:73).
- Acceptance: `get_docs("lib@1.2.3")` mengembalikan chunk docs versi 1.2.3; `lib` tanpa
  versi tetap latest; versi tak valid → error MCP jelas.

### FR-6 Cache pipeline CI (MUST)
- Deskripsi: `memo --build-cache` ingest semua `cache-libs.txt` (66 lib), lib di
  aliases.json di-upsert tanpa resolve network, embed PENUH batch 8, deadline None
  (server.py:284-310, 183-188). CI `cache.yml`: ubuntu-latest × py3.11 → build-cache →
  gzip → release asset tag `cache-$sha` (cache.yml:10-28). `memo --fetch-cache`: cek
  release API → download → backup → `PRAGMA integrity_check` → rollback bila korup →
  catat `cache.version` (server.py:316-388); varian shell `tools/fetch-cache.sh`
  verifikasi count libs+chunks>0 (fetch-cache.sh:6-29).
- Acceptance: DB korup saat fetch-cache → rollback ke backup + exit non-zero;
  setelah fetch-cache sukses, memo berfungsi offline penuh tanpa jaringan.

### FR-7 Transport stdio/HTTP/bridge (MUST)
- Deskripsi: stdio default `mcp.run()` (server.py:426-431); HTTP daemon `--transport
  http --port 4041` host 127.0.0.1 (server.py:427-429), di-boot `mcp-boot.sh` idempoten
  via ping JSON-RPC (mcp-boot.sh:1-24). Bridge `mcp-start-memo`: proxy tiap line JSON-RPC
  ke `http://127.0.0.1:4041/mcp`, pertahankan `Mcp-Session-Id`, timeout 120 s,
  self-heal boot daemon tunggu ≤180 s (mcp-start-memo:1-70). Alasan: stdio boot 30-50 s
  > timeout opencode 30 s → daemon sekali + bridge ~1 s (mcp-start-memo:2-6).
- Acceptance: daemon mati → bridge reboot otomatis ≤180 s tanpa intervensi; session
  header dipertahankan antar request.

## 4. Requirement non-fungsional

- **Performance (MUST)**: latency median `get_docs` < 2 s (R4: 2.93 s, target turunkan;
  report-R4.md:17); budget per request 30 s hard deadline (server.py:134); boot bridge
  ~1 s setelah daemon hidup (mcp-start-memo:2-6).
- **RAM (MUST)**: DB ~16 MB single file (memo-internals.md:11); reranker ~25 MB dimuat
  lazy hanya saat dipakai (server.py:66-93); embedding lazy singleton threads=2
  (server.py:52-60).
- **Storage (MUST)**: satu file DB ~16 MB + backup `docs.db.bak`/`docs.db.pre-cache`
  (fetch-cache.sh:27; server.py:371-373).
- **Portability ARM (SHOULD)**: sqlite-vec/fastembed/onnxruntime berisiko di ARM;
  fallback FTS5-only bila ekstensi gagal load — build from source sebagai opsi
  (AGENTS.md builder rules).
- **Offline (MUST)**: offline penuh setelah `fetch-cache` (report-context7-vs-memo.md:44).
- **Reliability (MUST)**: `journal_mode=WAL` (store.py:30); add_chunks UPSERT per path,
  hapus FTS+vec lama dulu (store.py:99-106); integrity_check + rollback korup
  (server.py:316-388).
- **Security (MUST)**: tanpa auth, localhost only 127.0.0.1 (server.py:427-429);
  token GitHub hanya env untuk `_gh_search`; secret TIDAK PERNAH ditulis ke DB/log/
  memory (secret law, AGENTS.md).
- **Maintainability (MUST)**: selfcheck `_demo` per modul (store.py:199-217,
  registry.py:465-477, ingest.py:292-306). `[BARU]` pytest mini: suite kecil 6 uji
  sabotase bug R4 (report-R4.md:154-159) agar regresi terdeteksi otomatis di CI
  (report-context7-vs-memo.md:80, 46).

## 5. Kebutuhan antarmuka

- **MCP tools** (fastmcp): `get_docs(library_id, query)` — lock per-lib, deadline 30s
  (server.py:122-127); `resolve_library_id(name)` (server.py:91-100);
  `versions(library_id)` (memo-internals.md §6).
- **CLI**: `memo --warmup`, `memo --build-cache`, `memo --fetch-cache` (server.py:391-431).
- **Registrasi opencode**: bridge `mcp-start-memo` (stdio) terdaftar di opencode.json
  dan berfungsi (DoD, AGENTS.md).
- **Logging**: `_log_activity` JSONL ke `bench/activity.log` sebagai basis benchmark
  (server.py:28-34); catatan: skor valid harus dari client MCP, bukan log (report-R4.md:5).

## 6. Requirement data

Empat tabel (store.py:35-66) + WAL (store.py:30):
- `libs`: id PK, name, repo, docs_url, trust, latest_ver, versions, full, etag, last_check (store.py:37-52).
- `chunks`: id PK autoincrement, lib_id, ver, path, title, text, fetched_at (store.py:54-57).
- `chunks_fts`: fts5(lib_id UNINDEXED, text) (store.py:59-61).
- `chunks_vec`: vec0(embedding float[384], lib_id text) (store.py:63-65).
- `add_chunks` UPSERT per path, hapus FTS+vec lama dulu (store.py:99-106).
- `[BARU]` FR-5 memakai kolom `versions`/`latest_ver` yang sudah ada — tanpa tabel baru.

## 7. Aturan implementasi

- **YAGNI**: jangan kejar OpenAPI/Notion/Confluence (gap #3), skala 33k library (gap #5),
  ekosistem plugin (report-context7-vs-memo.md:91).
- **Ponytail**: solusi paling sederhana yang benar; stdlib dulu; chunk baseline sudah
  terbukti penyebab miss → kualitas retrieval dulu (gap #6), enrich LLM (gap #1) ditunda
  sampai hit@5 ≥ 40% (report-context7-vs-memo.md:89-101).
- **Single source**: konstanta satu tempat — dua cap chunk berbeda (`chunks[:200]`
  server.py:182 vs 300 ingest.py:253) dan deps tak terdokumentasi di pyproject
  (onnxruntime, numpy, tokenizers, packaging) wajib diperbaiki (memo-internals.md §9).

## 8. Traceability FR → modul

| FR | Modul utama |
|---|---|
| FR-1 resolve | registry.py |
| FR-2 ingest | ingest.py, server.py |
| FR-3 retrieval | store.py, rerank.py |
| FR-4 refresh | server.py |
| FR-5 pin versi [BARU] | registry.py, server.py, store.py |
| FR-6 cache | server.py, cache.yml, tools/fetch-cache.sh |
| FR-7 transport | server.py, mcp-boot.sh, mcp-start-memo |
