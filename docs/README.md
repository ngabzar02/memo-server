# docs/ — Index dokumen memo (canonical)

- **Versi**: 2.0 · **Tanggal**: 2026-08-03 · **Status**: ACTIVE
- **Aturan**: file lowercase = canonical (satu-sumber). File uppercase di `docs/archive/` = draft v1 (superseded, boleh dikutip sebagai riwayat).
- **Tag dokumen**: `[V: sumber]` = fakta terverifikasi · `[A: alasan]` = asumsi · `[BARU]` = belum di kode.

## Peta file

| File | Peran | Konsumen | Menggantikan |
|---|---|---|---|
| `docs/README.md` (ini) | index + aturan dokumen | semua agent | — |
| `docs/quality-gates.md` | **single source metrik & gate** | brd, srs, planning, agent | — |
| `docs/architecture-update.md` | arsitektur as-built | developer, srs | memo-internals.md §1-2 (riwayat) |
| `docs/logic-update.md` | **single source konstanta & algoritma** | developer, tuning | — |
| `docs/brd.md` | business/product requirements | stakeholder | `archive/BRD-v1.md` |
| `docs/srs.md` | requirement FR/NFR/data/interface | developer | `archive/SRS-v1.md` |
| `docs/planning.md` | roadmap R5-R10 + backlog | O, semua agent | `archive/PLAN-v1.md` |
| `docs/infrastructure-update.md` | CI/CD, keamanan, observabilitas | ops/CI | memo-internals §5,§8 (riwayat) |
| `docs/decisions.md` | ADR (keputusan + alasan) | semua | — |
| `docs/agent.md` | manual agent/swarm | agent | AGENTS.md (ringkas) |
| `docs/testing.md` | strategi uji sabotase + pytest | F, RV | — |

## Aturan pemeliharaan

1. Angka metrik hanya hidup di `quality-gates.md`; konstanta hanya di `logic-update.md`;
   backlog hanya di `planning.md` — file lain **mengutip**, tidak menyalin (single source of truth).
2. Semua klaim bertag sumber; tanpa tag = `[A]` (jangan mengarang).
3. Tidak ada stub/placeholder: item belum dikerjakan ditulis eksplisit sebagai backlog dengan ID (P0-xx).
4. Perubahan perilaku → catat di `decisions.md` (ADR) + update `logic-update.md` (delta).
5. Perubahan file → sinkronkan pointer di `AGENTS.md` (root) dan file terkait.

## Alur kerja dokumen

- **Fix kode** → update `logic-update.md` (delta) + `decisions.md` + `testing.md` (SAB) → bench → `quality-gates.md` (skor).
- **Fitur baru** → `planning.md` (backlog P2) + `srs.md` (FR) → implement → ADR.
- **Laporan bench** → hidup di `bench/` (report-R{n}.md), BUKAN di docs/ (hindari duplikasi).

## Status saat ini (2026-08-03)

- Bug R4: 4 FIXED (B1/B2/B3/B6), 2 PARSIAL (B4 jalur llms, B5 threshold/requests) — detail `logic-update.md`.
- Baseline: hit@5 28% · target M2 ≥ 60% · 0 kosong · median < 2 s — `quality-gates.md`.
- Round aktif: R5 (P0 validasi + anti-false-positive) — `planning.md`.
