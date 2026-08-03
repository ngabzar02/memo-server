# PLAN — memo: Implementasi & Roadmap

Tanggal: 2026-08-03 · Penulis: O (Orchestrator, peran O-asisten planning)
Sumber wajib: `bench/report-context7-vs-memo.md` (§3 gap analysis),
`bench/report-R4.md`, `bench/swarm.md`, `bench/research/memo-internals.md`, `bench/state.md`.
Tag: [VERIFIED] = angka/klaim dari sumber · [ASUMSI] = estimasi, bukan dari sumber.

## 1. Ringkasan

Arah: **parity fungsional Context7 dengan fokus kualitas retrieval** — bukan mengejar
fitur SaaS. Basline nyata: docs hit@5 **28% (5/18)** vs target **≥40%**, resolve 22/22,
6/22 query kosong di client (Bug 1), latency median 2.93s [VERIFIED: report-R4 §1].
Pendekatan: **swarm multi-agent** per iterasi (O→B→R‖F‖T→RV→O) sesuai `bench/swarm.md`,
tiap iterasi diverifikasi satu ronde bench 22 query (metode BRUTAL, skor dari client —
log terbukti tidak 1:1). Urutan prioritas dari gap analysis §3: tutup gap kualitas
retrieval (#6) dulu, baru gap fungsional (#1, #2, #4); jangan #3/#5 (YAGNI single-user).
Potensi tertutup bila semua fix R4 jalan: 17–20/22 hit@5 (~77–91%) [VERIFIED: report-R4 §7].

Catatan state: `bench/state.md` mencatat state `BUILDING` dengan skor lama 21% (3/14, round
R2 dari log) [VERIFIED: state.md] — skor R4 (28%, dari client) lebih valid sebagai baseline;
R5 (P1-01) wajib membangun baseline baru yang konsisten sebelum tuning dimulai.

## 1a. Prinsip eksekusi

1. Satu iterasi = satu siklus swarm penuh; tidak pernah memulai round baru tanpa RV.
2. Bench hanya valid pasca **restart daemon :4041** dan skor diambil dari client MCP
   (mcp_sim.py), bukan `activity.log`.
3. Fitur (P2) dilarang sebelum gate M1; tuning dilarang sebelum fix 6 bug (R5).
4. Setiap fix membawa uji sabotase yang membuktikan deteksi bekerja [VERIFIED: swarm.md, R4 §6].

## 2. Backlog terprioritas

### P1 — Kualitas retrieval (gate ke fitur; isi konkret gap #6)

| ID | Item | Tipe | Prioritas | Modul | Est. dampak |
|---|---|---|---|---|---|
| P1-01 | Re-bench R5: daemon restart + 22 query BRUTAL, skor dari client | bench | P1 | bench/ | baseline client valid (skor R0–R2 palsu) [VERIFIED: R4 §1] |
| P1-02 | Fix Bug 1: `trim_to_tokens` break→continue | fix | P1 | store.py:186-194 | +3–4 hit (click, sqlalchemy, polars, anthropic, openai) → ~44% ≥40%; effort 5 menit [VERIFIED: R4 §5.1] |
| P1-03 | Fix Bug 2: hard-split paragraph raksasa (>~1024 token) | fix | P1 | ingest.py:72-82 | hilangkan chunk 15–285k char (polars/anthropic/openai); prasyarat kualitas P1-02 [VERIFIED: R4 §3] |
| P1-04 | Fix Bug 3: invalidasi docs_url tanpa gate `github.com` | fix | P1 | server.py:127-132 | bereskan fastmcp (glama.ai→gofastmcp.com), pydantic (8 chunk python.org) [VERIFIED: R4 §3] |
| P1-05 | Fix Bug 4: allowlist domain + filter bahasa crawler | fix | P1 | ingest.py | bereskan nextjs (101 chunk web.dev/MDN), django (200 chunk 10 bahasa) [VERIFIED: R4 §3] |
| P1-06 | Fix Bug 5: flag `full` berbasis kualitas (≥5 halaman) | fix | P1 | server.py:161/176 | bereskan korpus tipis: requests (1 chunk), sqlite-vec (wasm.html) [VERIFIED: R4 §3] |
| P1-07 | Fix alias requests: docs_url root + llms.txt (bukan halaman `/user/advanced`) | fix | P1 | aliases.json | korpus requests penuh; fragment `user/advanced` [VERIFIED: R4 §7] |
| P1-08 | Fix Bug 6: isi `latest_ver`/`versions` di `resolve_library_id` | fix | P1 | server.py:91-100 | metadata versi di jawaban MCP (kini kosong di 22/22) [VERIFIED: R4 §3] |
| P1-09 | Tuning retrieval: RRF k (20/40/60/100), pool FTS/vec, top-N rerank | tuning | P1 | store.py:128-161 | naikkan peringkat hit@5; A/B via replay 22 query [ASUMSI: rentang param] |
| P1-10 | A/B chunking 5 lib terburuk (anthropic, polars, openai, requests, sqlite-vec): 256/50 vs 128/32, 384/64 + batas hard-split | tuning | P1 | ingest.py | ukur kontribusi chunking terhadap miss 72% [ASUMSI: varian param] |

### P2 — Parity fungsional (gap #1, #2, #4, skala)

| ID | Item | Tipe | Prioritas | Modul | Est. dampak |
|---|---|---|---|---|---|
| P2-01 | Pin versi per-library (`/owner/repo@version`) di resolve + get_docs | feature | P2 | registry.py, server.py | reproduktifitas; gap fungsional #2 [VERIFIED: report §3] |
| P2-02 | Refresh terjadwal background (lepas dari request path) | feature | P2 | server.py:204-251 | turunkan latency (median 2.93s / mean 9.7s; Context7 lazy 3.3s) [VERIFIED: report §3 #4] |
| P2-03 | Skala cache-libs 66 → 200+ lib (CI build-cache + fetch-cache) | feature | P2 | cache-libs.txt, cache.yml | tutup sebagian gap skala (66 vs 33k; 33k tidak realistis lokal) [VERIFIED: report §0/§3 #5] |
| P2-04 | Enrichment ringan di CI: prepend deskripsi + contoh README ke chunk (build-cache saja, tanpa LLM) | feature | P2 | ingest.py, cache.yml | chunk lebih kontekstual; versi murah gap #1 [I: report §3 #1] |

### P3 — Kedewasaan (gap kualitas #7 + dokumen)

| ID | Item | Tipe | Prioritas | Modul | Est. dampak |
|---|---|---|---|---|---|
| P3-01 | pytest mini: 6 uji sabotase R4 (trim, chunk raksasa, docs_url change, domain allowlist, full flag, resolve metadata) | testing | P3 | tests/ | regresi otomatis; ganti bench manual [VERIFIED: R4 §6, report §3 #7] |
| P3-02 | CI smoke bench: jalankan score.py atas release asset cache | feature | P3 | .github/workflows | deteksi regresi hit@5 tiap build cache [ASUMSI] |
| P3-03 | README: terbitkan tabel bench (R5+) menggantikan "TBD" | docs | P3 | README.md:117-138 | gap dokumen stale [VERIFIED: memo-internals §8] |

### TIDAK dikerjakan (YAGNI single-user, alasan 1 baris)

- **REST publik**: pemakaian lokal lewat MCP sudah cukup; gap kecil [VERIFIED: report §1 API publik].
- **Plugin ekosistem (CLI/SDK/i18n)**: tidak ada konsumen selain user tunggal [VERIFIED: report §3 ekosistem].
- **OpenAPI/Notion/Confluence source**: kurang relevan utk docs library umum [VERIFIED: report §3 #3].
- **LLM-rerank penuh**: mahal & butuh API key; cross-encoder ONNX lokal sudah rerank server-side, dan Context7 sendiri pernah turun -15pp [VERIFIED: report §1/§4].

## 3. Rencana iterasi swarm (tiap iterasi = 1 round, verifikasi bench R5 22 query)

```
user: bench done → O state=ROUND-ACTIVE → B (skor+misl) → R‖F‖T → O prioritas → F → RV → O state=IDLE → restart daemon → BRUTAL
```

- **R5 — Fix 6 bug R4** (P1-02..P1-08 + P1-01) · spawn: **F** (implement semua fix + uji sabotase R4 §6), **T** standby, **B** (bench setelah **daemon restart** — kode baru tidak aktif di daemon yang sedang jalan), **RV** (audit fix + setujui). Target: hit@5 ≥40% (dari 28%); potensi 77–91% bila semua fix efektif [VERIFIED: R4 §7]. Gate **M1**.
- **R6 — Tuning retrieval + chunking A/B** (P1-09 ‖ P1-10) · spawn: **T** ‖ **F** paralel (independen: param store vs chunking), **R** (riset fragment benar utk sisa miss → `bench/research/R6.md`), **RV**. Verifikasi: replay 22 query, hit@5 ≥ nilai R5 (tanpa regresi).
- **R7 — Warmup per-lib sisa miss** (kondisional, hanya jika R6 belum ≥40%) · spawn: **R** (riset struktur docs resmi per lib), **F** (warmup spesifik checklist R4 §7: flask quickstart, pandas groupby, vue essentials, react useState), **RV**. Stop jika **3 round tanpa +5pt** → tulis batas di state.md [VERIFIED: swarm.md].
- **R8 — Pin versi + refresh background** (P2-01, P2-02) · spawn: **F**, **RV**. Verifikasi: selfcheck + bench regresi (hit@5 tidak turun >5pt, latency median ≤3.3s Context7).
- **R9 — Skala cache 200+ + enrichment CI** (P2-03, P2-04) · spawn: **F**, **RV**. Verifikasi: fetch-cache integrity PASS + spot-check 10 lib baru non-empty.
- **R10 — Kedewasaan** (P3-01..P3-03) · spawn: **F**, **RV**. Verifikasi: pytest PASS + CI smoke hijau + bench regresi ringan + semua gate P3.

## 4. Milestone & urutan

- **M1 — Parity kualitas retrieval** (R5–R7): exit criteria = docs hit@5 **≥40%** (dari 28%), resolve **22/22**, **0 query kosong** (dari 6/22), 6 uji sabotase PASS, skor dihitung dari client (bukan log).
- **M2 — Parity fungsional** (R8–R9): exit criteria = `@version` berfungsi + selfcheck PASS; refresh background aktif tanpa menaikkan latency median di atas **3.3s**; cache-libs **≥200** dengan fetch-cache integrity PASS; enrichment CI hidup dengan hit@5 **tidak turun >5pt**; hit@5 tetap ≥40%.
- **M3 — Kedewasaan** (R10): exit criteria = pytest mini PASS (≥6 uji sabotase), CI smoke bench hijau 2 run berturut-turut [ASUMSI], README tabel bench terbit, `verify.sh` PASS [contextclone], no secrets di commit.

## 5. Timeline realistis (per iterasi/sesi — user ponsel, sesi singkat)

| Iterasi | Isi | Effort | Sesi |
|---|---|---|---|
| R5 | fix 6 bug + re-bench | M (P1-02 = S [VERIFIED: 5 menit]; sisanya [ASUMSI]) | 2–3 |
| R6 | tuning + chunking A/B | M [ASUMSI] | 1–2 |
| R7 | warmup per-lib (kondisional) | M [ASUMSI] | 1–2 |
| R8 | pin versi + refresh background | L [ASUMSI] | 2–3 |
| R9 | skala 200+ + enrichment CI | L [ASUMSI] | 2–3 |
| R10 | pytest + CI smoke + README | S [ASUMSI] | 1 |

S: ≤1 sesi · M: 1–3 sesi · L: 3+ sesi. Estimasi effort di luar P1-02 = [ASUMSI] (tidak ada sumber).

## 6. Definisi Selesai per iterasi

1. Bench PASS: hit@5 ≥ nilai iterasi sebelumnya (dan ≥40% mulai R5), resolve 22/22, 0 query kosong — skor dari client, bukan `activity.log`.
2. Selfcheck `_demo` modul tersentuh PASS + uji sabotase relevan PASS [VERIFIED: R4 §6]; `verify.sh` PASS bila dikerjakan dalam konteks contextclone.
3. `git push origin main` (aturan user 2026-08-03) — setiap update selesai langsung push.
4. No secrets: credential GitHub hanya `[REDACTED: ~/.git-credentials]`; tidak pernah masuk file/commit/output.
5. RV setujui round (tanpa itu, O tidak memulai round berikutnya) [VERIFIED: swarm.md].

## 7. Regresi & risiko

- **A/B harus replay 22 query yang sama** (bench/queries.json + fragment) — membandingkan skor antar round hanya valid pada kueri identik [VERIFIED: R4 §1].
- **Daemon HTTP :4041 tidak reload kode** — WAJIB restart daemon (mcp-boot.sh / mcp-start-memo self-heal) sebelum tiap bench pasca-fix; bridge stdio hanya proxy.
- **OOM saat ingest besar**: ingest on-demand budget 30s + cap 200 chunk; lib raksasa (anthropic 285k char/para) berisiko — hard-split (P1-03) mengurangi beban; build-cache CI tetap di cloud [VERIFIED: memo-internals §3].
- **django/nextjs kontaminasi bahasa & domain** — re-warmup menambah, bukan mengganti (regresi R3→R4 django 5→10 bahasa) [VERIFIED: R4 §4]; drop korpus dulu sebelum re-ingest.
- **Latency ekor panjang** (nextjs 33s, openai 34s, prisma 31s) saat cold cache — target cap 20s; resume parsial (`full=0`) belum terbukti selesai [VERIFIED: R4 §4].
- **Skor stagnan**: stop criterion swarm = 3 round tanpa +5pt → hentikan, tulis batas [VERIFIED: swarm.md].

## 8. Backlog jauh (sengaja ditunda)

- **Enrichment LLM penuh** (gap #1 versi asli Context7) — mahal + butuh API key; enrichment ringan CI (P2-04) sebagai pengganti sampai hit@5 ≥40% stabil.
- **Skala 33k library** — tidak realistis di SQLite/RAM lokal (16MB utk 66 lib); mitigasi tetap resolve dinamis + ingest on-demand [VERIFIED: report §3 #5].
- **REST publik + plugin ekosistem** — YAGNI single-user; buka kembali bila ada konsumen kedua.
- **Distributed cache (Redis)** — tak diperlukan single-user [VERIFIED: report §1].
- **OpenAPI/Notion/Confluence** — gap source ingestion yang tidak relevan utk docs library umum.
