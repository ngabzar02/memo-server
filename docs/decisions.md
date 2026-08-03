# Decisions (ADR) — memo: keputusan teknis tercatat

- **Peran**: registry keputusan + alasan, supaya tidak diulang/terbalik. Append-only.
- **Tag**: `[V]` = terverifikasi di source/bukti · `[A]` = keputusan manusia (asumsi desain).

| # | Keputusan | Konteks (bug/riset) | Konsekuensi | Batas / upgrade |
|---|---|---|---|---|
| 001 | Skor bench dari client MCP, bukan activity.log | Bug 1: log mencatat tapi client `[]` [V: report-R4.md:5,20] | Bench valid hanya post-fix; mcp_sim.py wajib | log tetap dicatat sebagai pelengkap |
| 002 | trim_to_tokens skip oversize (continue) bukan break | Bug 1: chunk top-1 raksasa memutus kiriman [V] | Semua chunk kecil terkirim; oversize hilang | hard-split (003) kurangi kejadian |
| 003 | Hard-split paragraph > cap 4× | Bug 2: chunk 15-285k char | tidak ada chunk raksasa; kualitas trim | cap disatukan (ADR-008) |
| 004 | docs_changed tanpa gate github.com + TTL 1 jam | Bug 3: docs_url non-GitHub tak pernah di-cek | drop_lib + re-ingest otomatis semua source | TTL cache ditingkatkan bila network overhead |
| 005 | crawler allowlist domain + bahasa EN | Bug 4: nextjs 101 chunk web.dev, django 10 bahasa | korpus relevan saja pada jalur BFS | apply ke llms.txt juga (FP-5) |
| 006 | `is_full = complete AND ≥3 chunk` | Bug 5: 1-chunk = full palsu | korpus tipis di-indeks ulang | threshold vs saran R4 ≥5 halaman — evaluasi di R6 |
| 007 | resolve backfill versi dari DB | Bug 6: metadata versi kosong di jawaban | latest_ver/versions terisi untuk lib ter-index | lib belum pernah ingest → panggil version_etag sekali |
| 008 | konstanta & cap chunk satu-tempat (200/200/300) | inkonsistensi 3 cap | satu-sumber konfigurasi | WIP (P3-04) |
| 009 | chunk lama DIBIARKAN saat versi berganti | DELETE chunks versi lama merugikan [V: server.py:246-249] | versi pakai chunk lama | pin versi (P2-01) butuh revisi |
| 010 | deadline get_docs 30 s | cold ingest lambat | respon menjawab atau parsial (full=0) | cap 20 s target M2 untuk cold |
| 011 | NO enrich LLM sampai hit@5 ≥ 60% | gap enrich Context7; mahal + butuh API key [V] | enrichment ringan CI (P2-04) pengganti | tinjau ulang bila target tercapai |
| 012 | NO REST publik / plugin / 33k scale / multi-user | YAGNI single-user [V] | fokus kualitas | buka bila konsumen kedua muncul |
| 013 | anti-false-positive = requirement MUST | FP-1..FP-5 (resolve karangan, query kosong, chunk tak relevan) | tol./filtrer di trust boundary | gate G2 |
| 014 | resolve tolak trust < 1.0 (FP-1) | entri karangan trust 0 untuk input sampah (`zzzzzz` → CreateWheel) [V: report-R4 §2] | resolve sampah → `[]` (not found); kandidat tanpa sinyal kualitas (0 stars, tanpa llms, repo tak dikenal) dibuang [FIXED: registry.py:_resolve] | tinjau threshold bila lib kecil valid tertolak |
| 015 | threshold relevansi relatif 50% cos top-1 (FP-3) | chunk tak relevan lolos (nextjs→CDN, pandas→IO, sqlite→README) [V: FP-3 logic-update §7] | hit vec dengan cos < 50% top-1 dibuang sebelum RRF [FIXED: store.py:139-162] — top-1 selalu lolos, FTS-only tanpa embedding tak kena | relatif per-query: noise tetap bila semua kandidat mirip; kandidat rerank wajib (P1) |
| 016 | RRF k tetap 60 (A/B 20-100 tidak signifikan) | replay 22 query pada release cache: semua k identik (14% hit@5); miss dominan korpus (numpy basics.broadcasting/flask quickstart tidak ter-index) [V: bench/tuning/rrf-k.md] | `store.search(..., rrf_k=60)` jadi param utk A/B ulang pasca korpus lengkap; tooling `bench/replay_rrf.py` | replay ulang WAJIB setelah cache CI baru (FP-5 + alias requests) |

Format catatan: "u" = belum di-uji / "f" = final.
