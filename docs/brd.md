# BRD — memo v2: Pengganti Context7 (lokal, akurat, production-grade)

- **Versi**: 2.0 · **Tanggal**: 2026-08-03 · **Status**: ACTIVE
- **Menggantikan**: `docs/archive/BRD-v1.md` (lihat docs/README.md)
- **Tag**: `[V]` = terverifikasi · `[A]` = asumsi. Semua angka metrik → `docs/quality-gates.md` (single source).

---

## 1. Ringkasan Eksekutif

memo adalah MCP server lokal peniru Context7: memberi agen coding dokumentasi library
versi terbaru — gratis, unlimited, offline, privat. Context7 adalah SaaS Upstash: free 1.000
call/bln lalu diblokir (+20 bonus/hari), Pro $10/seat/bln + $10/1.000 calls, backend parsing/
crawling/rerank **private/black-box** [V: riset web 2026-08-03].

Status v2: semua **6 bug R4 sudah di-fix** (trim, hard-split, filter domain, invalidasi docs_url,
full flag, metadata versi) [V: commit 4c8ed4d + verifikasi source]. Tantangan sekarang bukan
"perbaiki yang rusak" tapi **"buktikan produksi dan ungguli Context7"**: baseline hit@5 28%,
target M2 ≥ 60% (2× Context7 pada bench identik [V: quality-gates.md]).

## 2. Latar & Masalah

1. **Context7 dibatasi & mahal**: free tier dipangkas menjadi 1.000 call/bln + rate limit [V: neuledge blog 2026-02-08]; Pro berbayar.
2. **Black box**: backend retriieval/tuning credential di seberang server; tak satu pun metrik
   akurasi retrieval dipublikasikan [V: riset web 2026-08-03].
3. **Kebutuhan perangkat**: ARM, RAM ketat, kerja offline — streaming ke cloud tidak cocok [V: README.md:30-33].
4. **Beberapa kualitas tidak dijamin siapa pun**: Context7 punya kasus skor turun (−15pp
   community ZKOSS) [V: report-context7 §4] — kualitas harus diukur sendiri.
5. **False positive berbahaya**: menjawab dengan library fiktif atau chunk tak relevan lebih
   buruk daripada tidak menjawab — ini batas kualitas produksi.

## 3. Visi, Tujuan, Metrik

**Visi**: memo menjadi pengganti Context7 yang diandalkan — jawaban *benar*, bukan sekadar ada.

| Kode | Tujuan | Baseline | Target | Sumber metrik |
|---|---|---|---|---|
| T1 | Docs hit@5 | 28% | ≥ 60% (M2) | quality-gates.md |
| T2 | Resolve andal tanpa entri karangan | 100% tapi ada kasus sampah | ≥ 95% + 0 karangan | quality-gates.md |
| T3 | 0 query kosong di client | 6/22 | 0 | quality-gates.md |
| T4 | Latency median < 2 s | 2.93 s | < 2 s | quality-gates.md |
| T5 | Jujur (README = angka nyata) | "sub-ms"/"TBD" [X] | tabel bench nyata | quality-gates.md G4 |
| T6 | .laim semantic > Context7 | pembanding 28% | ≥ 60% | quality-gates.md |

## 4. Stakeholder

| Peran | Kepentingan |
|---|---|
| Pemakai (opencode/agent) | jawab benar, cepat, tanpa kosong/palsu |
| Operator (user ARM/RAM ketat) | offline, ringan, gratis |
| Developer (swarm O/B/R/F/T/RV) | kode terukur, metrik jujur |
| Pembanding | Context7 — tolok ukur kualitas |

## 5. Ruang Lingkup

**OUT OF SCOPE** (YAGNI): enrich LLM penuh (hanya enrichment ringan CI), OpenAPI/Notion/
Confluence, skala 33k, REST publik, plugin ekosistem, distributed cache, multi-user/auth.

**IN SCOPE**: bench R5 baseline valid; anti-false-positive hardening (FP-1..FP-5 logic-update §7);
tuning retrieval (RRF k, pool, top-N, chunking A/B); warmup 17 lib checklist R4; paritas fungsional
(pin `@version`, refresh background, cache-libs → 200+); kedewasaan (pytest, CI smoke, README);
konsistensi konstanta (satu-tempat); deps pyproject lengkap.

## 6. Prioritas

| Prioritas | Isi | Alasan |
|---|---|---|
| P0 | Bench R5 valid + anti-kosong/palsu | kepercayaan pada angka; produksi dimulai dari "tidak membohongi" |
| P1 | Tuning + warmup 17 lib | hit@5 40% → 60% |
| P2 | Pin versi + refresh background + skala 200 | parity fungsional |
| P3 | pytest + CI + README jujur | kedewasaan, regresi terdeteksi |

## 7. Constraint

- Platform Linux/ARM, Python ≥ 3.10, RAM target daemon < 500 MB RSS setelah warm.
- Satu SQLite file (WAL); tanpa infra eksternal.
- CI GitHub Actions ubuntu — timeout build-cache 360 m.
- Aturan user: push setiap update; tanpa secret di file/log/commit.
- Sesi pengembangan singkat (ponsel) → tiap iterasi beri hasil terukur.

## 8. Risiko & Mitigasi

| Risiko | Dampak | Mitigasi |
|---|---|---|
| 25/72 lib FTS-only (tanpa vektor) | retrieval berkurang | warmup embed penuh; audit `chunks_vec` count |
| Chunk basi (fastmcp 3.382 chunk) | jawaban lawas | drop_lib + re-ingest saat docs_url berubah (sudah fix) |
| Cold cache 30-40 s | UX buruk | pre-built cache + cap 20 s |
| Skor stagnan >3 round | buang waktu | stop criterion tertulis [V: swarm.md] |
| Regresi tanpa test | bug balik | pytest uji sabotase + CI smoke (P3) |
| Overclaim dokumen | kredibilitas | tiap angka ber-laporan sumber |

## 9. Definition of Done (rilis produksi)

Lihat `docs/quality-gates.md` G1-G4. Ringkas: bench PASS (skor client, ≥ 60% hit@5, 0 kosong,
0 karangan, median < 2 s) · uji sabotase + pytest hijau · CI smoke 2× · README = angka nyata ·
konstanta satu-tempat · deps lengkap · push + RV setuju.