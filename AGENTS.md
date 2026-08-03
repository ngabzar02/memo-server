# AGENTS.md — memo

## Apa repo ini
memo adalah MCP server lokal peniru Context7: memberikan dokumentasi library
versi-terbaru ke agent (opencode/Claude/Cursor) lewat `resolve_library_id` /
`get_docs` / `versions`. Gratis, tanpa API key, tanpa rate limit, offline-capable
(index pre-built ~16 MB), Python 3.10+, jalan di ARM. Data tersimpan di satu
file SQLite `~/.local/share/memo/docs.db` (hybrid BM25 FTS5 + embeddings
bge-small via fastembed, fusion + token-budget trim).

## Struktur kunci
- `src/memo/server.py` — entry point MCP (`memo = memo.server:main`), resolve/get_docs/versions, CLI `--warmup` / `--build-cache` / `--fetch-cache`
- `src/memo/store.py` — SQLite + FTS5 + sqlite-vec, `trim_to_tokens` (waspada Bug 1: oversize chunk → break)
- `src/memo/ingest.py` — crawl (llms.txt/sitemap/README) + trafilatura + chunking
- `src/memo/registry.py` — resolusi nama library (aliases.json, builtins.json, npm/PyPI/GitHub)
- `src/memo/rerank.py` — cross-encoder rerank (optional)
- `docs.db` (+`.bak`) — index SQLite; JANGAN diubah langsung, hanya lewat kode
- `cache-libs.txt` — daftar library (satu per baris); PR satu baris → CI build index baru
- `.github/workflows/cache.yml` — CI ingest semua lib tiap push → release asset docs.db; `bench.yml` — CI selfcheck
- `bench/` — protokol benchmark, queries, score, state, research
- `tools/fetch-cache.sh` — unduh docs.db pre-built dari GitHub release

## Perintah penting
- Install dev: `uv tool install --editable .` (venv di `~/.local/share/uv/tools/memo/`)
- Daemon HTTP (RAM ketat): `~/.local/bin/mcp-boot.sh` (port memo 4041, free-search 4040) atau `memo --transport http --port 4041`; log di `/tmp/mcp-memo.log`
- Selfcheck tiap modul (smoke test `_demo`): `python -m memo.store`, `python -m memo.ingest`, `python -m memo.registry`
- Warmup lib: `memo --warmup flask nextjs httpx [--force]`
- Build/ambil cache: `memo --build-cache` (ingest cache-libs.txt) / `memo --fetch-cache [--force]`
- Benchmark: MCP langsung per `bench/BRUTAL.md` (daemon :4041) + `bench/bench.py` (20 query vs Context7 API, tanpa key); skor via `bench/score.py`
- Verify sistem CC-SYS: `bash /root/contextclone/_sys/verify.sh` — WAJIB PASS sebelum klaim fase selesai

## Konvensi
- WAL write: tulis `.tmp` → rename atomik untuk file state; jangan menulis langsung
- State & skor live di `bench/state.md` (hanya O yang menulis); round log di `bench/rounds/`
- Dokumen keputusan di `docs/` — index & aturan: `docs/README.md` (canonical lowercase; `docs/archive/*-v1.md` = riwayat superseded)
- Skor benchmark dihitung dari output yang diterima CLIENT MCP, BUKAN `bench/activity.log` (log tidak 1:1 — Bug 1 trim_to_tokens)
- Daemon WAJIB restart setelah ubah `server.py` sebelum tes (mcp-boot.sh idempoten)

## Aturan wajib
- `git push origin main` SETELAH SETIAP update selesai (fix, warmup, bench, dokumen) sebelum lanjut fase
- JANGAN pernah tulis secret/token/API key ke file, log, commit, atau chat — cukup `[REDACTED: ~/.git-credentials]`
- Jangan edit `docs.db` langsung selain lewat kode/server
- Benchmark target: docs hit@5 ≥ 40% → ≥ 60% (M2, `docs/quality-gates.md`); baseline Context7 28%
- Bug fixes wajib disertai uji sabotase (lihat `bench/report-R4.md` §6); skor README tidak boleh dikarang

## Pointer
- `docs/README.md` — index dokumen canonical (menggantikan pointer lama BRD/PLAN/SRS)
- `docs/planning.md` (roadmap + backlog), `docs/brd.md`, `docs/srs.md`, `docs/agent.md`, `docs/decisions.md`
- `docs/quality-gates.md` — metrik & gate (single source), `docs/logic-update.md` — konstanta/algoritma
- `bench/swarm.md` — protokol orkestrasi multi-agent benchmark
- `bench/BRUTAL.md` — protokol benchmark MCP langsung (Blok A/B)
- `bench/research/*.md` — riset (context7.md, memo-internals.md, R4.md)
- `CONTRIBUTING.md` — cara kontribusi & ground rules repo
