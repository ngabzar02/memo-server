# Quality Gates — memo (single source of truth metrik & DoD)

- **Versi**: 2.0 · **Tanggal**: 2026-08-03 · **Status**: ACTIVE
- **Peran**: Satu-satunya lokasi angka target/baseline/DoD. Dokumen lain (brd, srs, planning)
  MENGUTIP file ini, tidak menyalin angka.
- **Tag**: `[V]` = terverifikasi dari `bench/report-R4.md` / source · `[A]` = asumsi, perlu uji.

---

## 1. Papan metrik

| Metrik | Baseline R4 | Target M1 | Target M2 (ungguli C7) | Cara ukur | Sumber |
|---|---|---|---|---|---|
| Docs hit@5 | 28% (5/18) | ≥ 40% | ≥ 60% | bench 22 query, skor client MCP | [V] report-R4.md:15 |
| Docs hit@1 | 22% (4/18) | ≥ 30% | ≥ 40% | idem | [V] report-R4.md:16 |
| Resolve hit | 100% (22/22) | ≥ 95% | ≥ 95% | idem | [V] report-R4.md:14 |
| Resolve entri karangan | 1 kasus (`zzzzzz` → trust 0) | 0 | 0 | uji sampah (zzzzzz, "", typo) | [V] bench empiris 2026-08-03 |
| Query kosong di client | 6/22 | 0 | 0 | bench | [V] report-R4.md:19 |
| Latency median get_docs | 2.93 s | < 2 s | < 2 s | activity.log / bench | [V] report-R4.md:17 |
| Latency cold cache (per-lib pertama) | 30-40 s (nextjs 33 s) | cap 20 s | cap 15 s | bench cold | [V] report-R4.md:139 |
| Embedding coverage (lib dengan vektor) | 49/72 (25 FTS-only) | 100% lib pre-built | 100% | `SELECT COUNT(*) FROM chunks_vec` per lib | [V] riset source 2026-08-03 |

**Pembanding Context7**: hit@5 28%, resolve 86% pada bench yang sama (R0) [V: report-R4.md:14-15].
Target M2 ≥ 60% berarti > 2× Context7 — benchmark retrieval publik pertama yang membandingkan
keduanya (Context7 tidak memublikasikan metrik akurasi retrieval apa pun [V: riset web 2026-08-03]).

## 2. Gate (exit criteria per fase)

| Gate | Kriteria | Bukti |
|---|---|---|
| **G1 (M1)** | hit@5 ≥ 40% · resolve ≥ 95% · 0 kosong · median < 2 s · 0 entri karangan | `bench/rounds/R5*.md` + report-R6 |
| **G2 (M2)** | hit@5 ≥ 60% · hit@1 ≥ 40% · cold cap 20 s · uji sampah PASS | report-R7 |
| **G3 (M3)** | `@version` berfungsi · refresh background tanpa +0.5 s latency · cache-libs ≥ 200 · pytest hijau · smoke bench 2× hijau | CI log + selfcheck |
| **G4 (rilis)** | README = angka nyata (tabel bench, bukan "TBD") · deps pyproject lengkap · konstanta satu-tempat | audit + `git grep` |

## 3. DoD per iterasi (semua harus PASS sebelum round ditutup)

1. Bench PASS: skor dihitung dari output yang **diterima client MCP**, bukan `activity.log`
   (log terbukti tidak 1:1 — Bug 1 [V: report-R4.md:5,20]).
2. Selfcheck `_demo` modul tersentuh PASS + uji sabotase relevan PASS [V: report-R4.md:154-159].
3. `git push origin main` (aturan user 2026-08-03, tertulis di AGENTS.md).
4. RV setujui round — tanpa itu O tidak memulai round berikutnya [V: bench/swarm.md].
5. No secrets: kredensial hanya di `~/.git-credentials` (mode 600); tidak pernah di file/log/commit/output.
6. Tidak ada stub, mock, placeholder, atau `[BLUM]` yang tertinggal di kode — backlog ditulis eksplisit di planning.md.

## 4. Stop criterion

- 3 round berturut-turut tanpa peningkatan ≥ +5pt pada metrik target → hentikan tuning,
  tulis batas & penyebab di `bench/state.md`, jangan buang waktu [V: bench/swarm.md:56-57].

## 5. Metode skoring (protokol — rujuk, bukan duplikat)

- Protokol lengkap: `bench/BRUTAL.md` (Blok A/B, 22 query) + `bench/queries.json` (fragment target) + `bench/score.py`.
- Validasi independen: `mcp_sim.py` (simulasi MCP langsung ke daemon) — diverifikasi di R4 [V: report-R4.md:6,190].
- Query identik antar round WAJIB (replay `queries.json`) — skor antar round hanya valid pada query sama [V: report-R4.md:114].
- Daemon :4041 WAJIB restart setelah perubahan `server.py` sebelum bench [V: AGENTS.md:37].

## 6. Peta metrik → sasaran pengguna

| Metrik | Kenapa penting untuk user |
|---|---|
| hit@5 ≥ 60% | jawaban pertama relevan; LLM tidak perlu retry |
| 0 kosong | tidak pernah "menerima apa-apa" |
| 0 entri karangan | tidak pernah menjawab dengan library fiktif (false positive) |
| median < 2 s | nyaman dipakai interaktif |
| cold ≤ 20 s | library baru tidak bikin frustrasi |
