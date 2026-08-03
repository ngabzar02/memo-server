# memo — Internals Research (agent R)

Tanggal: 2026-08-03. Sumber: kode aktual di `/root/.local/share/memo` (commit saat ini).
Semua klaim bertag `file:baris`. Maks 50 fakta.

## 1. Ringkasan

memo = MCP server lokal (clone Context7): resolve nama library → ingest docs →
SQLite FTS5+vec0 → hybrid BM25+vector → cross-encoder rerank → trim token →
stdio/HTTP. Satu file DB `~/.local/share/memo/docs.db`, 5 modul Python + 2 JSON
data, CI GitHub Actions membangun index pre-built 66 lib (~16 MB) sebagai
release asset.

## 2. Per-file

### 2.1 pyproject.toml
- (a) Manifest paket: `memo` v1.0.0, entry `memo = "memo.server:main"` (pyproject.toml:15).
- (b) Deps: fastmcp>=2.0, httpx>=0.27, trafilatura>=1.8, sqlite-vec==0.1.9, fastembed>=0.4 (pyproject.toml:6-12). Build: hatchling, wheel `src/memo` (pyproject.toml:18-22).
- Catatan: `tokenizers` (rerank.py:10), `onnxruntime`+`numpy` (rerank.py:41-42), `packaging` (registry.py:101) TIDAK di pyproject — lazy import, harus sudah terpasang.

### 2.2 README.md
- (a) Dokumentasi: quickstart uv + fetch-cache, register opencode/Claude/Cursor (README.md:43-89).
- (b) Klaim arsitektur: resolve chain 5 lapis (README.md:99), chunk 256 token/50 overlap (README.md:100), BM25 selalu + bge-small-en-v1.5 bila ada vec (README.md:101).
- (c) Data di `~/.local/share/memo/docs.db` (README.md:110); benchmark 20 query vs Context7 masih "TBD" di tabel (README.md:117-138) — status belum terbit walau bench/report.md ada (lihat §8).

### 2.3 src/memo/server.py (444 baris) — orkestrasi MCP
- (a) `main()`: mode CLI (`--warmup`, `--build-cache`, `--fetch-cache`) atau `mcp.run()` stdio/http (server.py:391-431).
- (b) Komponen:
  - `get_docs` (server.py:122-127): tool MCP utama; lock per-lib (paralel antar lib, serial per lib), deadline `time.monotonic() + 30s`.
  - `_get_docs` (server.py:137-201): pipeline lengkap — DB check → docs_changed → refresh versi → embed query → search → ingest bila miss → re-search → rerank → trim.
  - `_docs_changed` (server.py:204-223): cek docs_url resolve vs DB tiap 1 jam (TTL `_DOCS_CHANGED_TTL=3600`, server.py:44); berubah → `drop_lib`.
  - `_maybe_refresh` (server.py:226-251): freshness versi, TTL 1d (trust>5) / 7d; versi baru → update, chunks LAMA dibiarkan (server.py:246-248, DELETE terbukti merugikan).
  - `_embeddings` (server.py:52-60): lazy singleton `TextEmbedding("BAAI/bge-small-en-v1.5", threads=2)`.
  - `_get_reranker`/`_rerank` (server.py:66-93): lazy ONNX cross-encoder; gagal load → off (fallback hybrid); top-10 rerank, doc dipotong 1000 char (server.py:86).
  - `_build_cache` (server.py:284-310): ingest semua `cache-libs.txt` (CI); lib di aliases.json di-upsert dulu tanpa resolve network (server.py:298-300).
  - `_fetch_cache` (server.py:316-388): unduh `memo-cache.db.gz` dari GitHub release → backup → `PRAGMA integrity_check` → rollback bila korup → catat `cache.version`.
  - `_log_activity` (server.py:28-34): JSONL ke `bench/activity.log` (basis benchmark, server.py:23-25).
- (c) Deps: fastmcp, memo.ingest/registry/store, fastembed (lazy), sqlite3, threading.

### 2.4 src/memo/store.py (221 baris) — SQLite + hybrid retrieval
- (a) `connect()`: buka DB + load sqlite-vec extension + `PRAGMA journal_mode=WAL` + init idempotent (store.py:24-32).
- (b) Komponen: `init` schema (store.py:35-66), `upsert_lib` (71-80), `drop_lib` (83-89), `add_chunks` UPSERT per path (92-123), `search` hybrid RRF (128-161), `_fts_ranks` BM25 (164-169), `get_lib`/`get_versions` (172-183), `trim_to_tokens` (186-194), `_demo` selfcheck (199-217).
- (c) Deps: sqlite3 stdlib, sqlite_vec.

### 2.5 src/memo/ingest.py (310 baris) — fetch → extract → chunk
- (a) `ingest_lib()`: pipeline llms-full.txt → llms.txt → README GitHub → crawl BFS → single page (ingest.py:225-263).
- (b) Komponen: `fetch_text` (46-56, trafilatura utk HTML), `parse_llms` (59-66), `chunk_text` heading-aware (69-110, 256 token/50 overlap), `_split_oversize` (113-126), `_crawl` BFS 4-thread dengan prioritas keyword query (154-222), `_gh_raw` (139-151), `_path_allowed` filter domain+bahasa (18-25), `_looks_404` (284-289), `is_full` (28-31).
- (c) Deps: httpx, trafilatura (lazy, ingest.py:41), stdlib re/urllib.

### 2.6 src/memo/registry.py (481 baris) — resolusi nama → kandidat
- (a) `resolve()`: 6 sumber network paralel, TTL cache 1 jam (registry.py:375-384, `_CACHE_TTL=3600` di 313).
- (b) Komponen: `_alias` (26-31, trust 95), `_builtin` (34-53, id `node:`/`py:`), `_npm` (115-150, trust=log10 downloads), `_pypi` (207-225), `_crates` (153-169), `_go` (172-184), `_rubygems` (187-204), `_gh_search` (258-300), `_trust_final` fusion trust (355-366), `version_etag` (76-84), `versions_of` (228-246, pilih sumber versi terbanyak).
- (c) Deps: httpx, packaging (lazy), JSON file aliases/builtins (registry.py:22-23), ThreadPoolExecutor.

### 2.7 src/memo/rerank.py (66 baris) — cross-encoder ONNX
- (a) `CrossReranker.rerank()`: encode (query,doc) pairs → logit relevansi (rerank.py:52-66).
- (b) Model `temsa/ms-marco-MiniLM-L-6-v2-onnx-cpu-qint8` (~25MB), MAX_LEN 512, download dari HF ke `~/.cache/memo/reranker` (rerank.py:12-15, 22-34).
- (c) Deps: tokenizers (BertWordPieceTokenizer), numpy, onnxruntime — tanpa torch/transformers (sengaja, rerank.py:4).

### 2.8 Data files
- `aliases.json` (292 baris): ~65 entri `{repo, docs_url, trust: 95.0, latest_ver: ""}` — contoh: angular, axios, bs4, django, dotenv, fastapi, fastmcp (aliases.json:2-40).
- `builtins.json` (34 baris): 35 modul Node (`node:fs → fs.md`) + 40+ Python stdlib (`py:json → json.html`) → docs_url nodejs.org/docs/latest/api/... & docs.python.org/3/library/... (builtins.json:1-30; dipakai registry.py:38-53).
- `cache-libs.txt` (74 baris): 66 lib untuk pre-built cache — 20 query benchmark + alias populer + builtin stdlib (cache-libs.txt:1-74).

### 2.9 tools/fetch-cache.sh
- Unduh `releases/latest/download/docs.db` via curl, verifikasi sqlite (count libs+chunks > 0), backup lama → mv (fetch-cache.sh:6-29).

### 2.10 bench/ (protokol swarm)
- `state.md`: state live `BUILDING`, skor terakhir resolve 94% (33/35), docs hit@5 21% (3/14), target 40% (state.md:3-6).
- `swarm.md`: siklus multi-agent O→B→R‖F‖T→RV→O; peran + output wajib tiap agent; kriteria selesai hit@5 ≥ 40% atau 3 round tanpa +5pt (swarm.md:17-53).

### 2.11 .github/workflows/cache.yml
- Trigger push ke main (path src/**, cache-libs.txt, aliases.json, builtins.json, pyproject.toml, cache.yml) + workflow_dispatch (cache.yml:2-6).
- Steps: ubuntu-latest × python 3.11 → `pip install .` → `memo --build-cache` (ingest 66 lib + embed penuh) → `gzip -k docs.db` → `mv docs.db.gz memo-cache.db.gz` → release tag `cache-${{ github.sha }}` (cache.yml:10-28).

### 2.12 Bridge scripts (~/.local/bin)
- `mcp-boot.sh`: boot daemon HTTP sekali per reboot — free-search port 4040 (env `SEARCH_MCP_FETCH_STRATEGY=http`), memo port 4041 (`--transport http`); idempoten via ping JSON-RPC (mcp-boot.sh:1-24).
- `mcp-start-memo`: bridge stdio ↔ daemon HTTP 4041. Ping → self-heal (boot daemon bila mati, tunggu ≤180s); forward tiap line stdin sebagai POST ke `/mcp` dgn `Mcp-Session-Id`, timeout 120s; parse SSE `data:` → stdout (mcp-start-memo:1-70).
- `mcp-start-free-search`: sama persis utk port 4040 / free-search-mcp (mcp-start-free-search:1-70).
- Alasan: stdio server 30-50s boot > timeout MCP opencode 30s → daemon sekali + bridge ringan ~1s (mcp-start-memo:2-6, mcp-boot.sh:2-3).

## 3. Alur end-to-end get_docs (verifikasi per langkah)

1. Request MCP → `get_docs(library_id, query)` → lock per-lib, deadline +30s (server.py:122-127).
2. DB check: `get_lib` + COUNT chunks (server.py:140-144).
3. `_docs_changed`: resolve → docs_url beda → `drop_lib` (server.py:145-150, 204-223).
4. `_maybe_refresh`: versi baru → update libs, chunks dibiarkan (server.py:151-152, 226-251).
5. Belum ada lib → `registry.resolve` → `upsert_lib` (server.py:155-162).
6. Embed query: `_embeddings().embed([query])` (server.py:164-165).
7. Search pertama: `store.search(k=10, query_vec=...)` (server.py:166).
8. Miss/parsial (`full=0`) → `ingest.ingest_lib(docs_url, deadline, existing, query)` (server.py:167-175). MCP path: `add_chunks` FTS-only, TANPA embed chunk (server.py:189-193, komentar 190-192) — vec penuh hanya dari pre-built CI / warmup (`deadline is None`, server.py:183-188). Cap 200 chunk (server.py:182).
9. Re-search setelah ingest (server.py:196).
10. `_rerank(query, hits)` — ONNX cross-encoder top-10 (server.py:197, 80-93).
11. `trim_to_tokens` — MAX_TOKENS 3000, ~4 char/token (server.py:201, store.py:186-194).

## 4. Engine details

- Embedding: `BAAI/bge-small-en-v1.5`, 384 dim (server.py:59; store.py:64 `embedding float[384]`), via fastembed/ONNX, threads=2 (server.py:57-59).
- Search hybrid: FTS5 BM25 (AND dulu, OR fallback) + cosine vec0, fusion RRF k=60 (store.py:129-153), vec k=20 hasil top (store.py:142-145), FTS limit 20 (store.py:164-169).
- Rerank: `temsa/ms-marco-MiniLM-L-6-v2-onnx-cpu-qint8`, CPU, threads=2, top-10, MAX_LEN 512 (rerank.py:12-14, 40-50; server.py:73, 86).
- Paralelisme: crawl 4 fetch (ingest.py:188), resolve 6 sumber (registry.py:409), enrich trust 4 (registry.py:371), embed batch 8 (server.py:186-187).
- Budget: `_REQUEST_BUDGET = 30.0` detik, crawl diberi deadline−2s (server.py:134, 170). Ingest parsial → `full=0` → lanjut di call berikutnya (server.py:179, 194).
- Chunking: 256 token, overlap 50, heading-aware H1-H4, cap ~4× max_tokens (ingest.py:12-13, 69-110).

## 5. Transport

- stdio: default `mcp.run()` (server.py:426-431).
- HTTP daemon: `--transport http --port 4041`, host 127.0.0.1 (server.py:427-429), di-boot `mcp-boot.sh` via nohup (mcp-boot.sh:16-20).
- Bridge: opencode mendaftarkan `mcp-start-memo` (stdio), yang men-proxy tiap JSON-RPC line ke `http://127.0.0.1:4041/mcp`, mempertahankan `Mcp-Session-Id`, timeout 120s, self-healing boot daemon (mcp-start-memo:1-70).

## 6. Registry / resolve

- Sumber: aliases.json (curated, trust 95, final tanpa network — registry.py:407-408) → builtins stdlib node/py (registry.py:34-53) → directory.llmstxt.cloud (registry.py:87-96) → npm (registry.py:115-150) → PyPI (207-225) → crates.io (153-169) → Go proxy (172-184) → RubyGems (187-204) → GitHub search (258-300, butuh token).
- Trust final: log10(downloads/stars) + 2.0 llms.txt + penalti fork −2.0 / README −1.0 (registry.py:355-366).
- Cache: `_CACHE_TTL = 3600` (1 jam) per (name,query) (registry.py:313-314, 375-384); `_LLMS_CACHE` 24 jam (registry.py:321-338); `_docs_changed_cache` 1 jam in-memory server (server.py:43-44).
- `versions_of`: pilih ekosistem dgn versi terbanyak (registry.py:228-246); `_stable_versions` tolak prerelease (registry.py:99-112).

## 7. Arsitektur data (SQLite, WAL)

- `libs` (id PK, name, repo, docs_url, trust, latest_ver, versions, full, etag, last_check) — store.py:37-52.
- `chunks` (id PK autoincrement, lib_id, ver, path, title, text, fetched_at) — store.py:54-57.
- `chunks_fts` — fts5(lib_id UNINDEXED, text) — store.py:59-61.
- `chunks_vec` — vec0(embedding float[384], lib_id text) — store.py:63-65.
- WAL: `PRAGMA journal_mode=WAL` (store.py:30); add_chunks UPSERT per path, hapus FTS+vec lama dulu (store.py:99-106).
- Backups: `docs.db.bak` dan `docs.db.pre-cache` dilihat di disk (fetch-cache.sh:27, server.py:371-373).

## 8. Cache pipeline

- `memo --build-cache` (CI): aliases di-upsert tanpa network → `_get_docs` per lib dgn deadline=None → embed PENUH batch 8 (server.py:284-310, 183-188).
- cache.yml: build → `memo-cache.db.gz` release asset tag `cache-$sha` (cache.yml:20-28).
- `memo --fetch-cache`: cek release API, download gz, backup, integrity_check, rollback bila korup, tulis `cache.version` (server.py:316-388). `tools/fetch-cache.sh` = varian shell sederhana (fetch-cache.sh:6-29).
- Gap dokumentasi: README tabel benchmark masih TBD (README.md:117-138) padahal `bench/report.md` & `report-R4.md` sudah ada — README stale.

## 9. Kekurangan terlihat dari kode (jujur)

- Error handling: `fetch_text`/`_fetch_llms` return None → `ingest_docs` diam-diam [] (ingest.py:46-56, 129-136); kegagalan satu lib di build-cache hanya dicetak (server.py:305-310); `_log_activity` swallow OSError (server.py:31-34).
- `chunks[:200]` di server path (server.py:182) vs cap 300 di `ingest_lib` (ingest.py:253) — dua cap berbeda, konsisten-tidaknya tidak dijaga.
- Deps tak terdokumentasi di pyproject (onnxruntime, numpy, tokenizers, packaging) — fresh install bisa gagal di `_get_reranker`/`version_etag`; hanya di-swallow warning (server.py:74-76).
- Testing: hanya selfcheck `_demo` per modul (store.py:199-217, registry.py:465-477, ingest.py:292-306); tidak ada pytest/CI test; regresi bench bergantung activity.log manual.
- `_fetch_cache` gzip timeout 900s fixed (server.py:368); version_etag conditional GET (ETag 304) diimplementasi tapi `vs[0]` path mengembalikan etag `""` (registry.py:76-84) — ETag praktis tak dipakai server (`_maybe_refresh` set `latest != latest_ver` sebagai sinyal, server.py:243).
- Thread-safety: `_embeddings` singleton tanpa lock (server.py:52-60) — aman hanya karena ORT concurrent; komentar mengaku teruji 6-thread (server.py:36-38) tanpa test otomatis.
