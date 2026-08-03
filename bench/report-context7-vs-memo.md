# Context7 vs memo — Perbandingan Komprehensif

Tanggal: 2026-08-03 · Penulis: O (Orkestrator), dari riset agent R
Sumber: `bench/research/context7.md` (Context7, tag [VERIFIED: URL]) dan
`bench/research/memo-internals.md` (memo, tag `file:baris`).
Tag: [V] = terverifikasi sumber · [I] = inferred · [U] = unverified · [O] = opini komunitas.

## 0. Fakta dasar

| | **Context7** | **memo** |
|---|---|---|
| Pemilik | Upstash (komersial, produk SaaS) [V] | proyek lokal, self-host total |
| Lisensi | MIT (hanya MCP server/CLI/SDK) [V] | — (repo privat lokal) |
| Bahasa | TypeScript monorepo (pnpm) [V] | Python 3.11, 5 modul |
| Stars | 60.187 [V] | — |
| Model | managed cloud + on-premise enterprise | 100% lokal + CI cloud |
| Skala index | 33.000+ library [V] | 66 lib pre-built cache [V] |
| Biaya | Free 1.000 call/bln, Pro $10/seat, Enterprise custom [V] | Rp 0, unlimited |

## 1. Tabel komprehensif per dimensi

| Dimensi | Context7 | memo | Gap memo vs Context7 |
|---|---|---|---|
| **Model layanan** | SaaS cloud (mcp.context7.com), API key Bearer, auth Clerk/OAuth; on-premise Docker/K8s utk Enterprise (SOC-2, SSO) [V] | Local daemon HTTP :4041 + bridge stdio; no auth, no cloud [V] | memo tidak punya mode multi-user/SSO — tidak relevan utk penggunaan pribadi |
| **Open source** | Hanya MCP server+CLI+SDK yang OS; **backend parsing & crawling PRIVATE (black box)** [V] | Semua kode terbuka (5 modul) [V] | Kebalikan: memo transparan penuh, Context7 engine-nya tertutup |
| **Sumber ingestion** | git repo (GH/GL/BB), website, llms.txt, OpenAPI spec, Notion, Confluence; kontrol `context7.json` di repo (folder/exclude/version pin) [V] | llms-full.txt → llms.txt → README GitHub → crawl BFS → single page; filter domain+bahasa `_path_allowed` [V] | Context7 punya: OpenAPI, Notion/Confluence, pin versi per repo, kontrol parser pemilik library; memo belum — [I] OpenAPI & pin versi adalah gap fitur nyata |
| **Index source code** | Tidak diindex jika ada docs; fallback generate contoh dari source utk repo publik [V] | Tidak pernah sentuh source code [V] | Kecil — fallback snippet source hanya utk repo tanpa docs |
| **Refresh** | Lazy berbasis popularitas: top-100 = 1 hari, top-1k = 15, top-5k = 30, lain 45 hari; manual via API; GitHub Action resmi [V] | `_docs_changed` cek docs_url tiap 1 jam [V]; `_maybe_refresh` versi baru TTL 1/7 hari [V] | memo cek per-request (latensi & network); Context7 cek di backend (lazy, tidak ganggu request) — gap desain |
| **Pipeline ingest** | Parse (ekstrak snippet) → Enrich (LLM tambah penjelasan) → Vectorize → Rerank custom → Cache Redis [V] | fetch → extract (trafilatura) → chunk heading-aware → embed (CI) → store [V] | **memo tidak punya tahap Enrich LLM** (snippet diperkaya AI) dan tidak pakai Redis — [I] Enrich = gap fungsional, Redis = gap infra |
| **Chunking** | Internal, tak terdokumentasi; dokumen diolah per-section relevan, hasil = concat potongan [V][U detail] | 256 token, overlap 50, heading-aware H1-H4, hard-split oversize >1024, cap ~4× budget [V] | Detail Context7 tak diketahui [U]; memo sudah terbukti: chunk baseline ini penyebab miss (bench R4) |
| **Retrieval engine** | Vector search + **reranking server-side** (custom, LLM-powered utk search library) [V] | Hybrid BM25 FTS5 + cosine vec0, fusion RRF k=60 [V] | Context7 pakai LLM utk rerank; memo pakai cross-encoder ONNX kecil [I] — sama-sama rerank server-side, beda model |
| **Embedding model** | Tidak diumumkan [U] (Upstash Vector punya bge built-in, tak dikonfirmasi) | BAAI/bge-small-en-v1.5, 384-dim, threads=2 [V] | [U] — tidak bisa dibandingkan tanpa data Context7 |
| **Vector store** | Cloud: tidak disebut [U]; On-prem: LanceDB/pgvector/Milvus [V] | SQLite vec0 (embedded, single file ~16MB) [V] | memo jauh lebih ringan; skala 33k lib mustahil di SQLite — gap kapasitas |
| **Rerank model** | "high-quality/fast reranking models", tak disebut [U] | ms-marco-MiniLM-L-6-v2 ONNX qint8 (~25MB, CPU) [V] | [U] |
| **Cache** | Redis (pipeline) [V]; API disarankan cache berjam-hari [V] | SQLite lokal + TTL in-memory: registry 1 jam, llms 24 jam, docs_changed 1 jam, versi 1/7 hari [V] | memo tanpa distributed cache — tak perlu utk single-user |
| **MCP tools** | `resolve-library-id`, `query-docs` (2 tool) [V] | `get_docs`, `resolve_library_id`, `versions` (3 tool) | Setara; Context7 instruksi "max 3 call" [V] vs memo agresif-crawl per call |
| **MCP transport** | stdio default + Streamable HTTP (express, port 3000) [V] | stdio + HTTP daemon :4041 + bridge self-heal (masalah boot 30-50s diatasi) [V] | Setara; memo punya lapisan bridge unik |
| **MCP framework** | `@modelcontextprotocol/sdk` TS + zod [V] | fastmcp (Python) [V] | Bedanya ekosistem bahasa, bukan kapabilitas |
| **Auth** | API key + OAuth 2.0 + EMA/JWKS enterprise [V] | none (localhost) [V] | Non-gap utk penggunaan lokal |
| **API publik** | REST context7.com/api, rate limit per plan [V] | tidak ada REST API (hanya MCP) | Gap kecil — CLI/mcp-cukup utk pemakaian lokal |
| **Infrastruktur** | Cloud Upstash (region/provider tak disebut) [U]; Redis cache [V] | Daemon local 4041 + GitHub Actions ubuntu-latest [V] | Radikal beda: SaaS vs single-user local |
| **Skala** | 33.000+ library [V] | 66 lib pre-built + resolve dinamis [V] | Gap skala terbesar; tapi memo "gratis & unlimited" |
| **Kualitas terukur** | Internal: token ↓65%, latensi ↓38%, call ↓30% (benchmark 80+ QA, Claude Haiku+Sonnet) [V]; komunitas ZKOSS: skor turun 73.8→59% (-15pp) [O] | R4: resolve 22/22, docs hit@5 5/18 (28%), median 2.93s [V] | memo di bawah target 40%; Context7 punya kasus -15pp → tidak ada yang sempurna |
| **Offline** | Tidak (cloud) [V]; on-premise airgapped Enterprise [V] | Offline penuh setelah fetch-cache [V] | memo unggul utk offline |
| **Biaya operasional** | $10/seat/bln utk Pro [V] | Rp 0 + CI gratis (GitHub Actions) [V] | memo menang habis |
| **Testing/CI** | Repo TS dgn changesets, workflows mcp-registry [V] | Selfcheck `_demo` per modul, cache.yml CI; **tidak ada pytest** [V] | Gap kualitas: testing memo manual; Context7 punya ekosistem CI repo |
| **Ekosistem** | CLI ctx7, SDK TS, Vercel AI SDK tools, pi extension, plugins (Claude/Codex/Cursor/Copilot), skills, i18n 15 bahasa [V] | bridge lokal utk opencode saja | Gap ekosistem besar — tapi YAGNI utk single-user |

## 2. Fungsi tiap file memo (dari kode aktual)

| File | Fungsi | Komponen kunci |
|---|---|---|
| `pyproject.toml` | Manifest paket v1.0.0, entry `memo=server:main`; deps fastmcp/httpx/trafilatura/sqlite-vec/fastembed [V] | — |
| `src/memo/server.py` (444 baris) | Orkestrasi MCP: tools, pipeline get_docs, CLI (warmup/build-cache/fetch-cache), daemon http | `get_docs` (lock per-lib, budget 30s), `_get_docs` (pipeline 11 langkah), `_docs_changed` (TTL 1 jam), `_maybe_refresh` (versi 1/7 hari), `_embeddings` (bge-small, lazy), `_rerank` (ONNX top-10), `_build_cache`/`_fetch_cache` (CI), `_log_activity` (JSONL) |
| `src/memo/store.py` (221) | Persistensi SQLite + hybrid retrieval | `connect` (WAL+vec0), `init` schema (libs/chunks/chunks_fts/chunks_vec), `upsert_lib`, `drop_lib`, `add_chunks` (UPSERT per path), `search` (RRF k=60), `_fts_ranks` (BM25), `trim_to_tokens` (3000), `_demo` selfcheck |
| `src/memo/ingest.py` (310) | Fetch → extract → chunk → crawl | `ingest_lib` (5 level sumber), `fetch_text` (trafilatura), `parse_llms`, `chunk_text` (256/50 heading-aware), `_split_oversize`, `_crawl` (BFS 4-thread), `_path_allowed`, `_looks_404`, `is_full` (≥3 chunk) |
| `src/memo/registry.py` (481) | Resolusi nama → kandidat lib (9 sumber) | `_alias` (trust 95 curated), `_builtin` (node:/py:), `_npm`/`_pypi`/`_crates`/`_go`/`_rubygems`, `_gh_search`, `_trust_final` (fusion log10), `version_etag`, `versions_of`, cache TTL 1 jam |
| `src/memo/rerank.py` (66) | Cross-encoder ONNX tanpa torch | `CrossReranker.rerank` (pairs → logit), model ms-marco-MiniLM qint8 ~25MB, MAX_LEN 512, cache `~/.cache/memo/reranker` |
| `aliases.json` | ~65 entri curated `{repo, docs_url, trust:95}` — resolve final tanpa network | angular, django, fastapi, fastmcp, dll |
| `builtins.json` | 35 modul Node + 40+ stdlib Python → docs_url resmi | node:fs → nodejs.org, py:json → docs.python.org |
| `cache-libs.txt` | 66 lib pre-built cache (benchmark + alias + builtin) | — |
| `.github/workflows/cache.yml` | CI: pip install → `memo --build-cache` → gzip → release asset tag `cache-$sha` | ubuntu-latest, python 3.11, timeout 360m |
| `tools/fetch-cache.sh` | Varian shell unduh docs.db + verifikasi sqlite | curl, count libs+chunks>0, backup |
| `~/.local/bin/mcp-boot.sh` | Boot daemon HTTP sekali per reboot (4040 free-search, 4041 memo) | ping JSON-RPC idempoten, nohup |
| `~/.local/bin/mcp-start-memo` | Bridge stdio↔daemon :4041, self-heal, session header, timeout 120s | parse SSE `data:` |
| `bench/state.md` | State live proyek (BUILDING, skor, target) | — |
| `bench/swarm.md` | Protokol swarm O→B→R‖F‖T→RV→O, kriteria selesai | — |

## 3. Gap analysis (memo vs Context7)

### Gap fungsional (nyata, layak dikejar)
1. **Enrichment LLM**: Context7 memperkaya snippet dengan penjelasan AI sebelum vectorize [V]. memo murni ekstraksi mentah. Dampak: chunk memo kadang kurang kontekstual — [I] penyumbang miss bench.
2. **Pin versi per-library** (`/owner/repo@version`) [V]. memo cuma latest. Penting utk reproduktifitas.
3. **OpenAPI/Notion/Confluence source** [V]. Kurang relevan utk docs library umum; YAGNI saat ini.
4. **Refresh lazy terjadwal** [V]. memo cek setiap request (overhead network ~1-2s; bukti: latency median 2.93s). Solusi memo sudah dirancang: pre-built cache CI + cache.version — tinggal konsisten.
5. **Skala library**: 33k vs 66. Tidak realistis dikejar lokal (RAM/sqlite). Mitigasi: resolve dinamis + ingest on-demand.

### Gap kualitas (paling berdampak, dari bench sendiri)
6. **Retrieval masih miss 72%** (hit@5 28%) — akar: chunking baseline (BUG2 ter-fix), chunk basi (BUG3), domain filter (BUG4), trim oversize (BUG1). Context7 punya rerank LLM yang terukur menaikkan kualitas [V].
7. **Testing**: memo tanpa pytest; regresi hanya manual bench. Context7 repo industri dgn CI.

### Keunggulan memo (bukan gap, sebaiknya dipertahankan)
- Transparansi penuh vs black box Context7
- Offline total, Rp 0, unlimited, RAM ringan (~16MB DB vs SaaS)
- Hybrid BM25+vec di single SQLite file — sederhana, portabel
- Refresh per-request justru fresh (Context7 bisa stale 45 hari utk lib kecil)

### Klasifikasi prioritas (rekomendasi)
- Segera: tutup gap #6 (sudah fix R4, tunggu bench R5)
- Nanti: #1 (enrich), #2 (pin versi), #4 (jadwal refresh)
- Jangan: #3, #5 (skala), ekosistem plugin — YAGNI single-user

## 4. Ringkasan jujur

- Context7 = produk SaaS industri (Upstash): backend private, enggine tak diketahui publik,
  terbukti menurunkan token/latensi via rerank server-side; tetapi ada kasus komunitas skor
  justru turun (-15pp ZKOSS) dan keluhan bloat di masa lalu.
- memo = klon lokal minim: semua komponen terbuka, engine sudah 1:1 (hybrid search +
  rerank server-side + cache), beda utama di enrichment LLM, skala, dan kedewasaan testing.
- Fokus memo harus di kualitas retrieval (bench), bukan mengejar fitur SaaS — gap fungsional
  hanya layak dikejar setelah hit@5 ≥ 40% tercapai.
