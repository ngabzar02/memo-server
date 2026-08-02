# Swarm Benchmark — orkestrasi multi-agent

Setiap ronde benchmark MCP langsung (BRUTAL.md) diikuti siklus agent yang
di-spawn oleh O (orchestrator, = sesi opencode ini). Tujuan: mengukur, mencari
akar masalah, memperbaiki, mentune — siklus cepat sampai melewati baseline
Context7 (resolve 86%, docs hit@5 28%).

## Input siklus

- `bench/activity.log` — JSONL tiap tool call MCP (ditulis server).
- `bench/queries.json` — 22 query + expected_path_fragments.
- `bench/score.py` — evaluator activity log → hit@1/hit@5 & daftar miss.
- `bench/state.md` — state live: round, skor, open issues, keputusan.

## Peran agent (spawn via task tool oleh O)

| Kode | Agent | Tugas | Output WAJIB |
|---|---|---|---|
| B | Benchmark | Jalankan score.py, bandingkan dgn baseline, ekstrak miss lengkap (lib, query, top-5 path, ms) | `bench/rounds/R{n}.md` (≤30 fakta, tiap fakta bertag [VERIFIED] dari score/activity) |
| R | Research/Scout | Untuk tiap miss: riset web (free-search) docs resmi library → path halaman yang BENAR + struktur docs; klasifikasikan akar miss (chunk hilang / ranking / navigasi crawler / docs_url salah) | `bench/research/R{n}.md`: tabel (lib, query, expected, path benar, akar miss) + [ASUMSI] bila tidak yakin |
| F | Fixer (BE) | Implement perbaikan yang disetujui O di `src/memo/`; selfcheck modul terkait; dilarang menyentuh file milik agent lain | `bench/fixes/R{n}.md`: perubahan + hasil selfcheck |
| T | Tuner | Eksperimen parameter (RRF k, top_n rerank, chunk max_tokens, budget, threads) — tulis skenario, ukur dampak | `bench/tuning/R{n}.md`: tabel param → hasil, rekomendasi |
| RV | Reviewer | Audit output B/R/F/T: promote/demote fakta (established/suspect), verifikasi fix tidak regresi, SETUJUI round selesai | `bench/review/R{n}.md` + update fakta di `bench/state.md` |

## Protokol

1. O membaca `bench/state.md` → memastikan state ROUND-ACTIVE.
2. O spawn **B** (butuh output) → lalu **R** ‖ **F** ‖ **T** (paralel bila
   independen; R boleh paralel dgn F hanya jika F menangani isu berbeda).
3. Hanya **O** yang menulis `bench/state.md` dan memutuskan prioritas fix.
4. **F** tidak pernah menjalankan benchmark MCP langsung (itu tugas user via
   opencode); F verifikasi via selfcheck/unit saja.
5. **RV** meninjau sebelum round ditutup; tanpa persetujuan RV, O tidak
   memulai round berikutnya.
6. Tiap agent menulis HANYA chunk-nya sendiri — satu penulis per file.
7. Fakta tanpa bukti = `[ASUMSI]`; dump raw dilarang (≤30 fakta per run);
   pertanyaan tertunda → `bench/state.md` open issues.

## Siklus (per round)

```
user: bench done
  → O: state=ROUND-ACTIVE, spawn B → score + miss list
  → O: spawn R (akar miss) ‖ T (tuning) [jika ada isu param]
  → O: prioritas fix → spawn F (implement + selfcheck)
  → O: spawn RV (audit + setujui)
  → O: state=IDLE, instruksi user: restart opencode → jalankan BRUTAL lagi
```

## Kriteria selesai

- docs hit@5 ≥ 40% (dari baseline 11%→sekarang 28% C7) ATAU 3 round tanpa
  peningkatan >5pt → hentikan, tulis batas di state.md.
- resolve hit tetap 100%.
- Setiap fix memiliki selfcheck yang membuktikan.
