# Architecture Update — memo (as-built v2)

- **Versi**: 2.0 · **Tanggal**: 2026-08-03 · **Status**: ACTIVE
- **Peran**: Arsitektur REAL setelah semua fix R4 (commit `4c8ed4d`). Menggantikan deskripsi
  lama di `bench/research/memo-internals.md` §1-§2 (masih berlaku sebagai riwayat).
- **Tag**: `[V]` = diverifikasi dari source · `[A]` = asumsi.

---

## 1. Topologi

```
┌─ client (opencode/Claude/Cursor) ───────────────────────────────┐
│  MCP stdio: /root/.local/bin/mcp-start-memo (bridge, ~1 s boot)  │
└──────────────────────────┬──────────────────────────────────────┘
                           │ JSON-RPC per line + Mcp-Session-Id
┌──────────────────────────▼──────────────────────────────────────┐
│ daemon HTTP 127.0.0.1:4041  (memo --transport http)              │
│ fastmcp server: resolve_library_id · get_docs · versions         │
└──┬───────────────────────────────────────────────────────────────┘
   │ single SQLite file
┌──▼──────────────────────────────────────────────────────────────┐
│ ~/.local/share/memo/docs.db  (WAL) [V: store.py:20,30]          │
│ libs · chunks · chunks_fts (FTS5) · chunks_vec (vec0, 384-dim)  │
└─────────────────────────────────────────────────────────────────┘
```

**Kenapa bridge+daemon, bukan stdio murni**: cold start stdio 30-50 s > timeout opencode
30 s [V: mcp-start-memo:2-6]. Daemon boot sekali (mcp-boot.sh idempoten), bridge hanya proxy
ringan. RAM ketat: daemon tunggal vs proses per call.

## 2. Komponen (5 modul, ukuran aktual)

| Modul | Baris | Tanggung jawab |
|---|---|---|
| `server.py` | 444 | orkestrasi MCP: tools, pipeline get_docs 11 langkah, CLI (--warmup/--build-cache/--fetch-cache), daemon HTTP |
| `store.py` | 221 | SQLite + FTS5 + vec0, hybrid search (RRF), trim_to_tokens |
| `ingest.py` | 310 | fetch → trafilatura → chunk → crawl BFS; filter domain/bahasa |
| `registry.py` | 481 | resolve nama → kandidat lib (alias curated, npm/PyPI/crates/Go/RubyGems/GitHub) |
| `rerank.py` | 66 | cross-encoder ONNX qint8 tanpa torch/transformers |

Data: `aliases.json` (65 entri curated trust 95) · `builtins.json` (35 Node + ~50 Python stdlib) ·
`cache-libs.txt` (66 lib pre-built) [V: count aktual 2026-08-03].

## 3. Pipeline get_docs (11 langkah, server.py:137-201)

1. Lock per-library (threading.Lock — paralel antar lib, serial per lib) [V: server.py:47-49]
2. Load lib dari DB; `_docs_changed()` cek docs_url (TTL 1 jam, tanpa gate github.com) [V: server.py:145-150,204-223]
3. `_maybe_refresh()` cek versi terbaru (TTL: trust>5 = 1 hari, lain 7 hari; chunk lama DIPERTAHANKAN) [V: server.py:226-251]
4. Lib baru → `registry.resolve()` (paralel, deadline) → upsert
5. Embed query bge-small-en-v1.5 (lazy singleton, threads=2) [V: server.py:52-60]
6. `store.search()`: FTS5 BM25 (AND→OR) + vec0 (k=20) → RRF k=60 [V: store.py:128-161]
7. Chunk kurang / ingest parsial (`full=0`) → `ingest.ingest_lib()` deadline 30 s [V: server.py:134]
8. Di jalur MCP dengan budget: FTS-only (tanpa embed chunk) [V: server.py:189-191]
9. `_rerank()` cross-encoder top-10; gagal load → fallback hybrid [V: server.py:66-93]
10. `trim_to_tokens()` cap 3.000 token ≈ 12.000 char; chunk oversize di-skip (continue) [V: store.py:186-194]
11. Log JSONL ke `bench/activity.log` (basis benchmark; skor valid dari client, bukan log) [V: server.py:24-34]

## 4. Model data & penyimpanan

- 4 tabel + WAL [V: store.py:35-66]: `libs` (id, name, repo, docs_url, trust, latest_ver, versions,
  full, etag, last_check) · `chunks` (id, lib_id, ver, path, title, text, fetched_at) ·
  `chunks_fts` (fts5: lib_id UNINDEXED, text) · `chunks_vec` (vec0: embedding float[384], lib_id).
- `add_chunks`: UPSERT per path — hapus chunks+fts+vec lama untuk path itu sekali di awal [V: store.py:92-123].
- Backup: `docs.db.bak` (fetch-cache), `docs.db.pre-cache` (sebelum unduh cache baru) [V: server.py:316-388].
- Ukuran aktual: DB 55 MB (72 lib, 18.087 chunk, 6.642 vektor; 25 lib FTS-only) [V: pengukuran 2026-08-03].

## 5. Concurrency

| Aspek | Kebijakan | Lokasi |
|---|---|---|
| Per-library ingest | lock serial per lib; paralel antar lib | server.py:47-49 |
| Embed query | lazy singleton, threads=2, batch 8 (89 ms/chunk ARM) | server.py:52-60 |
| Rerank | onnxruntime CPU threads=2, lazy load | rerank.py:40-50 |
| BFS crawl | 4 fetch paralel, iterative deepening, cap 200 | ingest.py:154-222 |
| Fallback | rerank/embed gagal → FTS5-only hybrid (tidak crash) | server.py:70-77 |

## 6. Transport & topologi daemon (matriks boot)

| Jalur | Boot | Catatan |
|---|---|---|
| stdio langsung | 30-50 s | melewati timeout opencode 30 s [V] |
| bridge (mcp-start-memo) | < 1 s | self-heal: boot daemon bila mati, tunggu ≤ 180 s |
| daemon HTTP | 60-90 s cold (import berat) | di-boot sekali per reboot oleh mcp-boot.sh |

## 7. Batas & kompensasi (jujur)

- **Embedding coverage**: jalur MCP ber-budget tidak meng-embed chunk baru (FTS-only);
  vektor penuh hanya saat warmup/CI. 25 lib saat ini FTS-only → retrieval setengah hybrid.
  Upgrade: warmup pasca-ingest di jalur background, atau batch embed di `get_docs` kedua.
- **Skala**: SQLite tunggal realistis untuk ~200-500 lib; 33k library tidak realistis [V: report-context7 §3 #5].
- **Overlap**: `OVERLAP_TOKENS=50` dideklarasikan tapi tidak dipakai dalam chunking [V: ingest.py:13,69]
  — status: konstanta mati; harus diimplementasi ATAU dihapus (lihat logic-update §8).
- **Deps pyproject tidak lengkap**: onnxruntime/numpy/tokenizers/packaging dipakai tapi tidak
  terdaftar [V: pyproject.toml:6-12 vs penggunaan source] — harus ditambah (infrastructure-update §5).

## 8. Arsitektur masa depan (target, [A])

- Background refresh terpisah dari jalur request (thread/jadwal) — hilangkan cek per-request ~1-2 s.
- Pin versi `lib@1.2.3` → kolom `libs.versions` sudah ada, tanpa tabel baru.
- Enrichment ringan di CI (prepend deskripsi/README ke chunk) — tanpa LLM di jalur runtime.
- Opsional: health endpoint MCP (ping sudah ada via bridge; tambah metrik).
