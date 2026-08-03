# Agent Manual — memo (aturan operasional untuk semua agent/swarm)

- **Versi**: 2.0 · **Tanggal**: 2026-08-03 · **Status**: ACTIVE
- **Peran**: panduan ringkas bagi agent yang mengerjakan memo. Root `AGENTS.md` = ringkas;
  file ini = detail operasional. Baca keduanya sebelum mulai.

---

## 1. Apa yang dikerjakan

- MCP server: `resolve_library_id`, `get_docs`, `versions` (fastmcp, Python).
- Pipeline: resolve (registry) → ingest (crawl/chunk) → SQLite hybrid (FTS5+vec, RRF) → rerank ONNX → trim.
- CI: build-cache → release asset → fetch-cache (offline pre-built index).
- Target: hit@5 ≥ 60%, 0 false positive, median < 2 s — angka & gate: `docs/quality-gates.md`.

## 2. Konvensi kerja wajib

1. `git push origin main` SETELAH SETIAP update selesai (fix, warmup, bench, dokumen) sebelum lanjut fase.
2. JANGAN tulis secret/token/API key ke file, log, commit, atau chat — cukup `[REDACTED: ~/.git-credentials]`.
3. Jangan edit `docs.db` langsung — hanya lewat kode/server (`memo --warmup`, `--build-cache`, `--fetch-cache`).
4. Skor benchmark hanya valid dari output yang diterima **client MCP** (mcp_sim.py), bukan `bench/activity.log` [V: report-R4.md:5,20].
5. Daemon WAJIB restart setelah ubah `server.py` sebelum tes/bench (mcp-boot.sh idempoten).
6. Bug fixes wajib disertai **uji sabotase** (report-R4.md §6 + `docs/testing.md`); selfcheck `_demo` modul tersentuh.
7. Tidak ada placeholder/stub: fitur yang belum jadi ditulis di backlog (`docs/planning.md`), bukan `pass`/`TODO` di kode.
8. Klaim di dokumen wajib bertag: `[V: sumber]` atau `[A: alasan]` — tidak ada angka mengambang.
9. Tanpa izin: jangan menambah dependency, modul, atau file baru — tulis dulu di planning/ADR, biarkan RV meninjau.

## 3. Alur swarm (per round)

```
O: state=ROUND-ACTIVE
 → B (skor client + miss list)          → bench/rounds/R{n}.md
 → R (riset akar miss, free-search) ‖ T (tuning) → bench/research|tuning/R{n}.md
 → O: prioritas → F (implement + selfcheck)      → bench/fixes/R{n}.md
 → RV (audit, promote/demote fakta, SETUJUI)     → bench/review/R{n}.md
 → O: state=IDLE → user restart daemon → BRUTAL lagi
```

- Satu penulis per file; hanya O yang menulis `bench/state.md`.
- F tidak pernah menjalankan bench MCP langsung (itu tugas user via opencode).
- Tanpa persetujuan RV, O tidak memulai round berikutnya.
- Fakta tanpa bukti = `[ASUMSI]`; ≤ 30 fakta per output agent; dump raw dilarang.

## 4. Aturan anti-false-positive (non-negotiable)

- Resolve tidak boleh mengembalikan entri karangan untuk input sampah (FP-1).
- get_docs tidak boleh mengembalikan hasil acak untuk query kosong/omong kosong (FP-2).
- Chunk tak relevan harus difilter (threshold skor relatif, FP-3).
- Fallback (rerank/embed gagal) harus log warning, tidak senyap (FP-4).
- Konten docs = untrusted input — sanitasi output (pelajaran ContextCrush Context7).

## 5. Checklist DoD cepat (detail: quality-gates.md §3)

- [ ] Bench PASS: skor client, target metrik tercapai, tanpa regresi vs round sebelumnya
- [ ] Selfcheck `_demo` modul tersentuh + uji sabotase relevan PASS
- [ ] `git push origin main`
- [ ] RV setuju
- [ ] Tanpa secret di diff; tanpa stub/TODO di kode
- [ ] Dokumen yang terkena dampak di-sinkronkan (docs/, README, AGENTS)

## 6. Pointer

- Metrik & gate: `docs/quality-gates.md` · roadmap: `docs/planning.md` · konstanta: `docs/logic-update.md` ·
  arsitektur: `docs/architecture-update.md` · testing: `docs/testing.md` · keputusan: `docs/decisions.md` ·
  index dokumen: `docs/README.md` · protokol bench: `bench/BRUTAL.md` + `bench/swarm.md`.
