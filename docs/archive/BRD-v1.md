<!-- SUPERSEDED 2026-08-03 by docs/BRD.md (canonical v2). Riwayat: boleh dikutip, jangan di-update. -->

# BRD — memo: MCP Server Dokumentasi Library Lokal

- **Versi**: 1.0 · **Tanggal**: 2026-08-03 · **Penulis**: BE (Developer)
- **Sumber utama**: `bench/report-R4.md`, `bench/report-context7-vs-memo.md`, `bench/research/context7.md`, `README.md`, `bench/state.md`
- **Tag**: `[ASUMSI]` = tidak ada di sumber, perlu verifikasi; sumber angka ditulis inline `(path:baris)`.

---

## 1. Ringkasan Eksekutif

memo adalah MCP server lokal peniru Context7 yang memberi agen coding dokumentasi
library versi terbaru — gratis total, unlimited, offline, dan privat (`README.md:3-8`).
Dibuat karena Context7 adalah SaaS komersial Upstash: backend parsing & crawling-nya
private/black-box, free tier hanya 1.000 call/bulan lalu diblokir, dan Pro $10/seat/bulan
(`bench/research/context7.md:9-11,49`); sementara perangkat target (ponsel) RAM ketat dan
membutuhkan kerja offline tanpa biaya. Status sekarang: BUILDING — ronde benchmark R4
mencapai resolve 100% (22/22), docs hit@5 28% (5/18), latency median 2.93s, dengan 6 bug
terverifikasi yang jika diperbaiki berpotensi membawa hit@5 ke ~77–91%
(`bench/report-R4.md:14-17,51,185`).

## 2. Latar Belakang & Masalah

1. **Context7 mahal dan dibatasi**: Free 1.000 call/bln, Pro $10/seat/bln, private repo
   parsing $25/1M token (`bench/research/context7.md:49`).
2. **Black box**: backend parsing, crawling, chunking, embedding model TIDAK publik —
   hanya MCP server/CLI/SDK yang open source (`bench/research/context7.md:11,34`).
3. **Kebutuhan offline/unlimited**: perangkat pengguna (Android, ARM, RAM ketat) tidak
   cocok streaming ke cloud; memo harus bekerja penuh setelah satu kali unduh index
   (~16 MB) (`README.md:30-33`).
4. **Kualitas tidak dijamin siapa pun**: Context7 punya kasus nyata skor turun -15pp
   (73.8→59%) di uji komunitas ZKOSS (`bench/research/context7.md:67`) — "yang mahal
   pun bisa gagal", jadi kualitas harus diukur sendiri, bukan diasumsikan.

## 3. Visi & Tujuan

**Visi**: parity fungsional dengan Context7 untuk penggunaan single-user di perangkat
lokal — tanpa biaya, tanpa limit, tanpa kebocoran query ke server pihak ketiga.

**Tujuan terukur** (dari `bench/state.md:6` dan keputusan bench):
- T1. Kualitas retrieval menembus target: docs hit@5 ≥ 40% (baseline R4: 28%).
- T2. Resolve library id tetap andal: ≥ 95% (baseline R4: 100%).
- T3. Latency turun: median < 2s (baseline R4: 2.93s) — target ditetapkan tim,
  belum ada di sumber proyek `[ASUMSI: arahan user 2026-08-03]`.
- T4. Semua 6 bug R4 ter-fix dengan uji sabotase, bukan sekadar "berjalan".

## 4. Stakeholder

| Peran | Keterangan |
|---|---|
| **Pemakai** | User tunggal di ponsel/perangkat ARM; agen coding (opencode) sebagai konsumen MCP |
| **Pengelola** | Swarm agent CC-SYS (O orchestrator, R scout, BE developer, RV reviewer) di `/root/contextclone` |
| **Penyedia konten** | CI GitHub Actions membangun index pre-built 66 lib (`bench/report-context7-vs-memo.md:62`) |
| **Pembanding** | Context7 (Upstash) — tolok ukur fitur & kualitas, bukan pesaing bisnis |

## 5. Ruang Lingkup

**IN SCOPE**
- Fix 6 bug R4: trim-to-tokens (BUG1), hard-split paragraph raksasa (BUG2), invalidasi
  docs_url berubah (BUG3), filter domain & bahasa crawler (BUG4), kualitas flag `full`
  + warmup korpus (BUG5), metadata versi di resolve (BUG6) (`bench/report-R4.md:55-133`).
- Re-run benchmark R5 dengan skor dari client MCP (bukan log) via `mcp_sim.py`
  (`bench/report-R4.md:5,152`).
- Perbaikan kualitas korpus per-lib (warmup path fragment target) (`bench/report-R4.md:161-184`).
- Registrasi MCP di opencode.json + push GitHub setelah tiap update (aturan user 2026-08-03).

**OUT OF SCOPE** (jujur, dari `bench/report-context7-vs-memo.md:71-76,88-91`)
- Enrichment LLM penuh per snippet — hanya setelah hit@5 ≥ 40% tercapai.
- Pin versi per-library (`/owner/repo@version`).
- Refresh lazy terjadwal (cek per-request dipertahankan dulu).
- OpenAPI/Notion/Confluence sebagai sumber ingest.
- Skala ke 33.000+ library (tidak realistis di SQLite + RAM lokal).
- Plugin ekosistem (Claude/Codex/Cursor/Copilot), CLI, SDK, REST publik — YAGNI single-user.

## 6. Requirement Prioritas (dari gap analysis §3, `bench/report-context7-vs-memo.md:69-91`)

**P1 — tutup gap kualitas #6 (retrieval)** — paling berdampak, sudah fix R4, tunggu bench R5:
- P1.1 `trim_to_tokens`: `break` → `continue` (chunk oversize dilewati, sisanya terkirim) — 5 menit, potensi +3–4 hit.
- P1.2 `chunk_text`: hard-split paragraph > batas (hilangkan chunk 15–285k char).
- P1.3 Crawler: allowlist domain + filter bahasa (bereskan nextjs/django).
- P1.4 Invalidasi docs_url tanpa gate `github.com` → drop_lib + re-ingest (fastmcp/pydantic).
- P1.5 Kualitas `full` flag: warmup root docs_url + llms.txt; `full` hanya jika korpus cukup.
- P1.6 Metadata versi di `resolve_library_id` (latest_ver/versions).
- P1.7 Warmup per-lib sesuai checklist 17 lib MISS/KOSONG (`bench/report-R4.md:161-184`).

**P2 — setelah P1 terbukti**: enrichment LLM (#1), pin versi (#2), refresh terjadwal (#4).

**P3 — JANGAN dikejar**: OpenAPI/Notion/Confluence (#3), skala 33k (#5), ekosistem plugin
— semua YAGNI untuk single-user.

## 7. Metrik Sukses

| Metrik | Baseline (R4) | Target | Sumber |
|---|---|---|---|
| Resolve hit | 100% (22/22) | ≥ 95% | `bench/report-R4.md:14` |
| Docs hit@5 | 28% (5/18) | ≥ 40% | `bench/report-R4.md:15`, target `bench/state.md:6` |
| Docs hit@1 | 22% (4/18) | ikut naik (tidak ada target resmi) | `bench/report-R4.md:16` |
| Latency median | 2.93s | < 2s `[ASUMSI: arahan user]` | `bench/report-R4.md:17` |
| Query kosong (client) | 6/22 | 0 | `bench/report-R4.md:19` |
| Skor diambil dari | log (tidak valid R0–R2) | client MCP (`mcp_sim.py`) | `bench/report-R4.md:5,20` |

Referensi pembanding: Context7 latency median 3.3s & hit@5 28% pada R0
(`bench/report-R4.md:14-17`) — target 40% berarti memo harus melampaui Context7.

## 8. Constraints

- **RAM**: perangkat ponsel dengan memori terbatas (~1.3 GB available
  `[ASUMSI: arahan user, tidak ada di sumber proyek]`); DB index hanya ~16 MB
  (`bench/report-context7-vs-memo.md:33`), reranker ONNX ~25 MB (`:34`).
- **Platform**: ARM (Raspberry Pi / Android-ish), Python 3.10+ (`README.md:33,41`).
- **CI**: GitHub Actions ubuntu-latest, build-cache timeout 360m (`bench/report-context7-vs-memo.md:62`).
- **Proses**: push `git push origin main` wajib setelah SETIAP update selesai
  (aturan user 2026-08-03, tercatat di AGENTS.md CC-SYS).
- **Keamanan**: tanpa secret di kode, memory, atau report; credential GitHub hanya di
  `~/.git-credentials` (mode 600), tidak pernah disalin (`AGENTS.md CC-SYS`).

## 9. Risiko & Mitigasi

| Risiko | Dampak | Mitigasi |
|---|---|---|
| OOM saat embed/ingest di device RAM ketat | crash, DB korup | Pre-built cache dari CI menggantikan warmup lokal (`bench/state.md:3`); fetch-cache verifikasi sqlite sebelum dipakai |
| CI timeout build-cache (360m) | release asset basi | Batasi 66 lib; prioritas lib benchmark; `full=0` mekanisme parsial (`bench/report-R4.md:139`) |
| Latency ekor panjang cold cache (nextjs 33.1s, openai 34.1s) | pengalaman buruk | Pre-built cache menghilangkan ingest on-demand; target cap 20s (`bench/report-R4.md:139`) |
| Target 40% tidak bergerak (R3→R4 stagnan) | proyek jalan di tempat | Fokus kualitas korpus (warmup fragment) bukan fitur baru (`bench/report-context7-vs-memo.md:100-101`) |
| Regresi tanpa pytest | bug balik diam-diam | Selfcheck `_demo` per modul + uji sabotase 6 bug (`bench/report-R4.md:154-159`) + skor ulang dari client |
| Skor palsu dari activity.log | keputusan salah | Skor benchmark hanya dari client MCP (`bench/report-R4.md:5,20`) |
| Chunk basi/kontaminasi (BUG3/4) | jawaban salah terus | Invalidasi docs_url + allowlist domain; drop chunk tercemar lalu re-warmup |
| Kehabisan konteks swarm | kontrol kualitas turun | Protokol chunked memory CC-SYS, checkpoint per fase |

## 10. Kriteria Diterima (Definition of Done)

1. **Benchmark**: 22 query nyata di-scoring dari client MCP → resolve ≥ 95%,
   docs hit@5 ≥ 40%, latency median < 2s, 0 query kosong.
2. **6 bug R4** ter-fix dan lulus uji sabotase masing-masing (`bench/report-R4.md:154-159`).
3. **REPORT.md** (rondes + final) diterbitkan; setiap klaim bertag verifikasi.
4. **memo terdaftar di opencode.json dan berfungsi** lewat daemon :4041 + bridge stdio.
5. **Push**: semua update terdorong ke `origin main`.
6. Klaim kuantitatif di luar sumber ditandai `[ASUMSI]` — tidak ada angka mengambang.
