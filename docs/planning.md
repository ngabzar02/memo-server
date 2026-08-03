# Planning — memo v2: roadmap implementasi & iterasi

- **Versi**: 2.0 · **Tanggal**: 2026-08-03 · **Status**: ACTIVE
- **Menggantikan**: `docs/archive/PLAN-v1.md`
- **Tag**: `[V]` = terverifikasi · `[A]` = asumsi effort/estimasi. Metrik → quality-gates.md.

---

## 1. Ringkasan arah

Tujuan: hit@5 28% → ≥ 60%, 0 false positive, median < 2 s, paritas fungsional Context7
(pin versi, refresh background, skala cache), dan kedewasaan (pytest, CI smoke, README jujur).
Urutan prioritas: **P0 (validasi & anti-palsu) → P1 (kualitas) → P2 (paritas) → P3 (kedewasaan)**.
6 bug R4 sudah fix; dua residual parsial: jalur llms belum difilter (B4), threshold `full`
& alias requests (B5) [V: verifikasi source 2026-08-03].

## 2. Prinsip eksekusi

1. Satu iterasi = satu siklus swarm penuh (O→B‖R‖F‖T→RV→O); tanpa RV tidak mulai round baru [V: swarm.md].
2. Bench valid hanya pasca **restart daemon :4041**; skor dari client MCP, bukan activity.log [V: report-R4.md:5,20].
3. Fitur (P2) dilarang sebelum gate G1; tuning dilarang sebelum D0 baseline valid.
4. Tiap fix membawa uji sabotase — bukan sekadar "berjalan" [V: report-R4.md:154-159].
5. Promosi target memakai data, tidak membandingkan round berbeda dengan query beda [V: report-R4.md:114].

## 3. Backlog terprioritas

### P0 — Validasi & anti-false-positive (gate ke semua)

| ID | Item | Tipe | Modul | Bukti target |
|---|---|---|---|---|
| P0-01 ✅ | Bench R5 baseline: restart daemon + 22 query, skor client | bench | bench/, server.py | report-R5 (2026-08-03, CI) |
| P0-02 ✅ | FP-1: resolve tolak trust < threshold tanpa download/stars → "not found" | fix | registry.py | uji `zzzzzz` → PASS (2026-08-04) |
| P0-03 ✅ | FP-2: get_docs query kosong/omong kosong → respon eksplisit (bukan 10 chunk acak) | fix | server.py | uji `""` → PASS (2026-08-04) |
| P0-04 ✅ | FP-4: fallback rerank/embed → log warning + metrik | fix | server.py | uji sabotase → PASS (2026-08-04) |

### P1 — Kualitas retrieval (gate G1/G2)

| ID | Item | Tipe | Modul | Est. dampak |
|---|---|---|---|---|
| P1-01 ✅ | FP-3: threshold skor relatif (< 50% top-1 buang) + rerank wajib | tuning/fix | store.py, rerank.py | uji SAB-7 → PASS (2026-08-04) |
| P1-02 ✅ | FP-5: filter `_path_allowed`/`_LANG_RE` ke daftar llms.txt | fix | ingest.py | uji SAB-9 → PASS (2026-08-04) |
| P1-03 ✅ | Tuning RRF k (20/40/60/100), pool FTS/vec, top-N rerank | tuning | store.py | A/B replay → k tidak signifikan; k=60 dipertahankan (ADR-016, `bench/tuning/rrf-k.md`); replay ulang pasca korpus lengkap |
| P1-04 | Chunking A/B: 256/50 (overlap aktual) vs 128/32, 384/64 | tuning | ingest.py | akar miss 72% |
| P1-05 | Warmup 17 lib checklist R4 (flask quickstart, pandas groupby, vue essentials, react useState, dsb) | warmup | ingestion | fragment hit (blocker korpus P1-03) |
| P1-06 ✅ | Alias requests: docs_url root + llms.txt (bukan halaman `/user/advanced`) | fix | aliases.json | warmup --force → 200 chunk (2026-08-04); `test_alias_requests_docs_root` |

### P2 — Paritas fungsional (gate G3)

| ID | Item | Tipe |
|---|---|---|
| P2-01 | Pin versi `lib@1.2.3` (tolak prerelease) | feature |
| P2-02 | Refresh background (docs_changed/versi lepas request path) | feature |
| P2-03 | cache-libs 66 → 200+ (build-cache + fetch-cache) | feature |
| P2-04 | Enrichment ringan CI: prepend deskripsi+README ke chunk (tanpa LLM runtime) | feature |

### P3 — Kedewasaan (gate G3/G4)

| ID | Item | Tipe |
|---|---|---|
| P3-01 | pytest mini: ≥6 uji sabotase FP + bug R4 | testing |
| P3-02 | CI smoke bench: score.py atas release asset cache | feature/CI |
| P3-03 | README: tabel bench nyata (ganti "TBD") + perbaikan klaim "65"→66, "sub-ms" | docs |
| P3-04 | Konstanta satu-tempat (cap 200/200/300; OVERLAP dipakai/hapus) | refactor |
| P3-05 | deps pyproject lengkap (onnxruntime, numpy, tokenizers, packaging) | infra |

### TIDAK dikerjakan (YAGNI single-user, alasan 1 baris)

- REST publik — MCP cukup untuk pemakaian lokal.
- Plugin ekosistem/CLI/SDK/i18n — tidak ada konsumen lain.
- OpenAPI/Notion/Confluence — kurang relevan untuk docs library umum.
- Enrich LLM penuh — mahal + butuh API key; enrichment ringan CI (P2-04) pengganti.
- Skala 33.000 library — tidak realistis di SQLite/RAM lokal.
- Distributed cache / multi-user / auth — single-user.

## 4. Iterasi swarm & milestones

| Round | Isi | Gate |
|---|---|---|
| **R5** | P0 fix baseline + FP-1/FP-2/FP-4 | G1 (hit@5 ≥ 40%, 0 kosong, 0 karangan) |
| **R6** | P1-01..P1-04 tuning + FP-3 | G1/G2 lanjut |
| **R7** | P1-05/P1-06 warmup 17 lib | **G2** (hit@5 ≥ 60%) |
| **R8** | P2-01 pin versi + P2-02 refresh background | G3 (parsial) |
| **R9** | P2-03 skala cache 200+ + P2-04 enrichment CI | G3 |
| **R10** | P3-01..P3-05 kedewasaan | G3-G4 |

Potensi yang tercatat R4: bila 6 bug efektif, hit@5 17-20/22 (77-91%) [V: report-R4.md:185] —
target M2 60% berada dalam jangkauan realistis, tapi wajib diverifikasi bench, bukan diasumsikan.

## 5. Timeline realistis (sesi ponsel singkat)

| Round | Effort | Catatan |
|---|---|---|
| R5 | M | baseline + guard; P0-02/P0-03 kecil |
| R6 | M | A/B tuning butuh replay 22 query |
| R7 | M | warmup 17 lib, peka jaringan |
| R8 | L | fitur + background thread |
| R9 | L | build-cache 200+ lib panjang |
| R10 | S-M | pytest + CI + refactor konstanta/deps |

S: ≤1 sesi · M: 1-3 sesi · L: 3+ sesi.

## 6. DoD per iterasi

Lihat quality-gates.md §3. Ringkas: bench PASS client-scored (tanpa regresi vs target) ·
selfcheck + sabotase PASS · push origin main · RV setuju · tanpa secret.

## 7. Regresi & risiko

- A/B wajib replay 22 query identik; skor antar-round valid hanya atas query sama [V: report-R4.md:114].
- Daemon tidak reload kode — restart wajib sebelum bench tiap pasca-fix.
- OOM saat ingest besar: budget 30 s + cap; build-cache di cloud (CI).
- Kontaminasi django/nextjs: re-ingest = add, bukan replace — drop korpus dulu.
- **Stop criterion**: 3 round tanpa +5pt → tulis batas di state.md [V: swarm.md:56-57].
- Skor palsu dari log: skor hanya dari client; aktivitas log hanya pelengkap.

## 8. Backlog jauh (sengaja ditunda)

- Enrichment LLM penuh (gap enrich Context7 asli) — sampai hit@5 ≥ 60% stabil.
- Skala 33k — SQLite tidak realistik; mitigasi: resolve dinamis + ingest on-demand.
- Distributed cache (Redis) — tak perlu single-user.
- REST publik + plugin — buka kembali bila ada konsumen kedua.

[1] Verifikasi: grep source 2026-08-03 — `store.py:191,213` (trim fix), `ingest.py:85,101,113` (hard-split),
`ingest.py:218,298-301` (domain filter path), `server.py:145-150` (docs_changed tanpa gate),
`ingest.py:28` (full ≥3), `server.py:104-113` (resolve isi versi).
