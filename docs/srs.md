# SRS — memo v2: Spesifikasi Requirement (FR/NFR/data/interface)

- **Versi**: 2.0 · **Tanggal**: 2026-08-03 · **Status**: ACTIVE
- **Menggantikan**: `docs/archive/SRS-v1.md`
- **Tag**: `[V]` = terverifikasi dari source `file:baris` · `[A]` = asumsi · `[BARU]` = belum di kode.
- Metrik & gate: kutip `docs/quality-gates.md`. Konstanta & algoritma: kutip `docs/logic-update.md`.

---

## 1. Pendahuluan & Definisi

- *library*: entitas id unik + docs_url di `libs` [V: store.py:37-52].
- *chunk*: potongan docs 256 token, satuan retrieval di `chunks` [V: store.py:54-57].
- *full*: flag korpus dianggap lengkap; `is_full = complete AND n_chunks ≥ 3` [V: ingest.py:28-31].
- *hit@5*: fragment target query muncul di path 5 chunk teratas jawaban client [V: report-R4.md:4-5].
- *false positive*: output yang terlihat valid padahal salah (library fiktif / chunk tak relevan / hasil kosong tak ditandai).

## 2. Deskripsi Sistem

Arsitektur as-built: `docs/architecture-update.md` (topologi, 5 modul, pipeline 11 langkah,
concurrency, transport). Ringkas: fastmcp server (stdio + daemon HTTP :4041 + bridge),
satu SQLite WAL (4 tabel), pipeline resolve→ingest→hybrid search→rerank→trim.

## 3. Requirement Fungsional

### FR-1 Resolve nama → library (MUST)
- 9 sumber berurutan; 6 network paralel; trust = log10(downloads/stars) + 2.0 llms − 2.0 fork − 1.0 README [V: logic-update §1].
- Acceptance: alias curated tanpa network; dengan network `latest_ver`/`versions` terisi [FIXED: server.py:104-113];
  input sampah (`zzzzzz`, `""`, typo) → respons eksplisit "library not found", **bukan** entri karangan `[BARU: FP-1]`.

### FR-2 Ingest docs (MUST)
- 5 level sumber; chunk 256 heading-aware; hard-split para raksasa cap 4× [V: logic-update §2-3].
- Acceptance: para > 1.024 token selalu terpecah (uji sabotase Bug 2) [V: report-R4.md:157];
  crawler hanya simpan path domain allowlist + bahasa EN [FIXED: ingest.py:18-25,218];
  **daftar llms.txt juga difilter** `[BARU: FP-5, residual Bug 4]`;
  `full=1` hanya bila korpus memadai [FIXED: ingest.py:28-31; keputusan threshold: ADR-008].

### FR-3 Retrieval hybrid + rerank (MUST)
- FTS5 BM25 (AND→OR) + vec0 k=20 → RRF k=60 → rerank ONNX top-10 → trim 3.000 token [V: logic-update §4-5].
- Acceptance: chunk oversize di-skip bukan memutus kiriman [FIXED: store.py:191];
  client selalu menerima konten atau pesan eksplisit, tidak pernah `[]` diam-diam [FIXED + FP-2];
  threshold relevansi relatif (buang < 50% skor top-1) `[BARU: FP-3]`;
  fallback rerank/embed tidak senyap — log warning `[BARU: FP-4]`.

### FR-4 Refresh docs & versi (MUST + `[BARU]` background)
- `_docs_changed` TTL 1 jam tanpa gate github [FIXED: server.py:145-150]; versi baru TTL 1/7 hari, chunk lama dipertahankan [V: server.py:226-251].
- `[BARU]` cek docs_changed/versi pindah ke thread background (lepas request path) — tujuan median < 2 s.

### FR-5 Pin versi `@version` `[BARU]` (SHOULD)
- Terima `library_id@1.2.3`: versi valid (tolak prerelease) → docs versi tsb; default latest.
- Acceptance: `get_docs("lib@1.2.3")` mengembalikan chunk versi tsb; versi tak valid → error jelas.

### FR-6 Cache pipeline CI (MUST)
- `--build-cache` (66 lib, embed penuh batch 8) → release asset gzip `cache-$sha`;
  `--fetch-cache` dengan integrity_check + rollback korup [V: server.py:316-388].
- Acceptance: DB korup → rollback + exit non-zero; setelah fetch-cache → offline penuh.

### FR-7 Transport (MUST)
- stdio default; HTTP daemon :4041 localhost-only; bridge self-heal ≤ 180 s; session header dipertahankan [V: architecture-update §6].
- Acceptance: daemon mati → bridge reboot otomatis; `Mcp-Session-Id` tidak hilang antar request.

## 4. Requirement Non-Fungsional

| Kategori | Requirement | Sumber |
|---|---|---|
| Performance | median get_docs < 2 s (baseline 2.93 s); budget 30 s; cold ≤ 20 s | quality-gates.md |
| RAM | daemon < 500 MB RSS setelah warm; DB ~55 MB + WAL + backup | [V: pengukuran 2026-08-03] |
| Storage | satu file SQLite + `.bak`/`.pre-cache` | [V: server.py:316-388] |
| Portability | ARM OK; gagal ekstensi → fallback FTS5-only (dengan log) | [V: server.py:70-77] |
| Offline | penuh setelah fetch-cache | [V] |
| Reliability | WAL; UPSERT per path (delete-sekali); integrity_check + rollback | [V: store.py:92-123, server.py:316-388] |
| Security | localhost-only; token GitHub hanya env; tanpa secret di DB/log; **output tool = untrusted input — sanitasi** (OWASP MCP) `[BARU]` | [V: OWASP cheat sheet] |
| Maintainability | selfcheck `_demo` per modul; **pytest mini (≥6 uji sabotase)** `[BARU]`; konstanta satu-tempat `[BARU]` | [V: report-R4.md:154-159] |
| Observability | log JSONL (activity.log); **warning saat fallback** `[BARU: FP-4]`; log ke stderr bukan stdout (spec MCP) | [V: spec MCP transport] |

## 5. Interface

- MCP tools: `get_docs(library_id, query, version=None)` · `resolve_library_id(name, query="")` · `versions(library_id)`.
- CLI: `--warmup`, `--build-cache`, `--fetch-cache`, `--transport http --port`.
- Registrasi opencode: bridge `mcp-start-memo` → opencode.json (sudah aktif).
- Logging: `_log_activity` JSONL; skor bench dari client, bukan log [V: report-R4.md:5,20].

## 6. Data

4 tabel + WAL [V: architecture-update §4]. `[BARU]` FR-5 memakai `libs.versions`/`latest_ver` —
tanpa tabel baru. `[BARU]` FR-7/FP-5: tidak butuh schema baru.

## 7. Aturan Implementasi

- YAGNI: jangan kejar OpenAPI/Notion/Confluence, skala 33k, plugin ekosistem, REST, distributed cache [V: report-context7 §3].
- Ponytail: stdlib dulu; solusi paling sederhana yang benar; uji sabotase di tiap fix.
- Single source: konstanta satu-tempat (gap saat ini: cap 200/200/300 chunk — logic-update §8);
  deps pyproject lengkap (onnxruntime, numpy, tokenizers, packaging) — infrastructure-update §5.
- Anti-false-positive adalah requirement kelas MUST (FP-1..FP-5 logic-update §7).

## 8. Traceability FR → Modul

| FR | Modul |
|---|---|
| FR-1 | registry.py, server.py |
| FR-2 | ingest.py, server.py |
| FR-3 | store.py, rerank.py |
| FR-4 | server.py (background: baru) |
| FR-5 | registry.py, server.py, store.py |
| FR-6 | server.py, .github/workflows/cache.yml, tools/fetch-cache.sh |
| FR-7 | server.py, mcp-boot.sh, mcp-start-memo |
