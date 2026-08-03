# Riset: Context7 — Referensi Perbandingan untuk `memo`

- **Reporter:** Agent R (Scout) — riset web, 2026-08-03
- **Tujuan:** bahan perbandingan arsitektur/engine/pipeline untuk proyek `memo` (peniru Context7)
- **Catatan kunci:** Repo open source BUKAN `context7dev/context7` melainkan **`upstash/context7`** (Context7 = produk Upstash). Nama `context7dev/context7` tidak ditemukan → [UNVERIFIED: repo itu pernah ada; semua rujukan mengarah ke upstash/context7].

## 1. Model layanan

- Context7 adalah produk komersial **Upstash** (serverless Redis/Kafka/Vector), dijalankan di infrastruktur Upstash sendiri, gratis untuk personal/edu. [VERIFIED: https://upstash.com/blog/context7-llmtxt-cursor]
- Managed cloud: MCP server URL `https://mcp.context7.com/mcp` + API key Bearer; auth OAuth 2.0/Clerk (`clerk.context7.com`). [VERIFIED: https://github.com/upstash/context7], [VERIFIED: https://raw.githubusercontent.com/upstash/context7/master/packages/mcp/src/lib/constants.ts]
- Open source hanya MCP server + CLI + SDK (TypeScript, monorepo pnpm); **API backend, parsing engine, dan crawling engine PRIVATE, tidak ada di repo**. [VERIFIED: https://github.com/upstash/context7]
- Enterprise On-Premise (self-host penuh, airgapped): Docker/K8s, vector store pilihan (LanceDB embedded/pgvector/Milvus), SSO, SOC-2. [VERIFIED: https://context7.com/docs/llms.txt]
- Dua mode penggunaan: CLI+Skills (`npx ctx7 setup`, OAuth → API key) dan MCP native. [VERIFIED: https://github.com/upstash/context7]

## 2. Pipeline ingestion

- Sumber: GitHub/GitLab/Bitbucket/git lain, website URL, llms.txt, OpenAPI spec (URL/upload), Notion, Confluence. [VERIFIED: https://context7.com/docs/llms.txt]
- Yang diindex: file docs `.md`, `.mdx`, `.markdown`, `.rst`, `.txt`, `.ipynb`; source code TIDAK diindex jika ada docs (fallback otomatis generate contoh dari source code untuk repo publik; opt-in untuk privat). [VERIFIED: https://context7.com/docs/adding-libraries.md]
- Kontrol parsing via `context7.json` di root repo (mirip robots.txt): folders/excludeFolders/excludeFiles/branch/rules/previousVersions. [VERIFIED: https://context7.com/docs/library-owners.md]
- Refresh otomatis **lazy, berbasis popularitas**: top-100 = 1 hari, top-1.000 = 15 hari, top-5.000 = 30 hari, lainnya 45 hari; hanya jika library baru diminta baru-baru ini; berjalan async tanpa menunda respons. [VERIFIED: https://context7.com/docs/library-updates.md]
- Refresh manual oleh user (halaman library / API `refresh-a-library`); library owner dapat limit refresh lebih tinggi; GitHub Action resmi untuk refresh tiap push. [VERIFIED: https://context7.com/docs/library-updates.md], [VERIFIED: https://context7.com/docs/adding-libraries.md]
- Pipeline 5 langkah (dari blog pengumuman): Parse (ekstrak code snippet+contoh) → Enrich (tambah penjelasan+metadata pakai LLM) → Vectorize (embed) → Rerank (algoritma custom) → Cache (Redis). [VERIFIED: https://upstash.com/blog/context7-llmtxt-cursor]

## 3. Chunking

- Strategi chunking internal **tidak didokumentasikan publik**; komunitas (reverse engineering) hanya menyimpulkan "semantic search + snippet extraction". [VERIFIED: https://docs.zkoss.org/small-talk/2025/10/15/we-tested-context7]
- Yang diketahui: hasil akhir per query = potongan paling relevan di-concatenate jadi string (default) atau JSON; pagination/mode/diset DefaultMaxResults dihapus. [VERIFIED: https://upstash.com/blog/new-context7]
- Dokumen diolah per-section relevan (bukan seluruh docs dimasukkan) untuk hemat token. [VERIFIED: https://ice-ice-bear.github.io/posts/2026-03-20-context7]
- Metadata: per-library ID `/owner/repo`, versi bisa di-pin (`/owner/repo@version`), reputasi sumber (High/Medium/Low/Unknown) + jumlah code snippets muncul di hasil resolve. [VERIFIED: https://raw.githubusercontent.com/upstash/context7/master/packages/mcp/src/index.ts]

## 4. Retrieval engine

- Vector DB: tidak disebutkan untuk cloud (PRIVATE); **On-Premise: LanceDB embedded, pgvector, atau Milvus** (menunjukkan cloud kemungkinan pakai salah satu dari ini). [VERIFIED: https://context7.com/docs/llms.txt]
- Embedding model: tidak disebutkan publik [UNVERIFIED]; Upstash Vector punya embedding built-in (bge dst.) tapi tidak dikonfirmasi dipakai Context7 [UNVERIFIED: https://upstash.com/docs/vector/features/embeddingmodels].
- Retrieval: vector search + **server-side reranking** ("high-quality reranking models" / "fast reranking models") — filter/rank dilakukan di server, bukan oleh LLM klien; query di-LLM-kan dulu oleh model klien (privasi: hanya query reformulated yang dikirim). [VERIFIED: https://upstash.com/blog/new-context7]
- Search library juga LLM-reranked ("intelligent LLM-powered ranking based on query context"). [VERIFIED: https://context7.com/docs/llms.txt]
- Dampak terukur arsitektur baru (benchmark internal 80+ pertanyaan, Claude Haiku + evaluator Sonnet): token konteks ↓65% (~9.7k→3.3k), latensi ↓38% (24s→15s), tool calls ↓30% (3.95→2.96). [VERIFIED: https://upstash.com/blog/new-context7]

## 5. MCP server (open source)

- Framework: **TypeScript, SDK resmi `@modelcontextprotocol/sdk`** (McpServer + StdioServerTransport + StreamableHTTPServerTransport), zod untuk skema, express untuk HTTP, undici untuk fetch API. [VERIFIED: https://raw.githubusercontent.com/upstash/context7/master/packages/mcp/src/index.ts]
- Transport: `--transport stdio` (default) atau `http` (port 3000, Streamable HTTP + session store). [VERIFIED: https://raw.githubusercontent.com/upstash/context7/master/packages/mcp/src/index.ts]
- Tools: `resolve-library-id` (nama → library ID, output: ID/name/desc/code-snippets/reputation) dan `query-docs` (libraryId + query → doc context; instruksi max 3 call per pertanyaan). Resources & prompts: kosong. [VERIFIED: https://raw.githubusercontent.com/upstash/context7/master/packages/mcp/src/index.ts]
- Backend dipanggil MCP: `https://context7.com/api` (env `CONTEXT7_API_URL`), auth API key prefix `ctx7sk`, error 401/404/429 ter-handle. [VERIFIED: https://raw.githubusercontent.com/upstash/context7/master/packages/mcp/src/lib/api.ts], [VERIFIED: https://raw.githubusercontent.com/upstash/context7/master/packages/mcp/src/lib/constants.ts]
- Repo juga memuat: CLI (`packages/cli`), SDK TS (`packages/sdk`), Vercel AI SDK tools (`packages/tools-ai-sdk`), pi extension (`packages/pi`), plugin untuk Claude/Codex/Cursor/Copilot (`plugins/`), skills (`skills/`), docs (`docs/`), Dockerfile + Smithery manifest untuk MCP registry. [VERIFIED: https://api.github.com/repos/upstash/context7/git/trees/master]

## 6. Infrastruktur & pricing

- Pricing: Free $0 (1.000 API calls/bln, public repos saja; kalau diblokir, bonus 20 calls/hari), Pro $10/seat/bln (5.000 calls/seat, lebih $10/1.000, private repo parsing $25/1M token), Enterprise custom (SOC-2, SSO, self-host). [VERIFIED: https://context7.com/docs/plans-pricing.md]
- API: REST di `context7.com/api`, semua endpoint butuh API key (header Authorization), rate limit berbeda per plan, cache disarankan berjam-hari (docs jarang berubah). [VERIFIED: https://context7.com/docs/api-guide]
- Auth identity: Clerk (`clerk.context7.com`) + OAuth; Enterprise-Managed Auth dengan JWKS (EMA). [VERIFIED: https://raw.githubusercontent.com/upstash/context7/master/packages/mcp/src/lib/constants.ts]
- Caching: Redis (disebut di pipeline) [VERIFIED: https://upstash.com/blog/context7-llmtxt-cursor]; infra cloud spesifik (region/provider) tidak disebutkan [UNVERIFIED].
- Klaim 33.000+ library terindex (per Okt 2025). [VERIFIED: https://docs.zkoss.org/small-talk/2025/10/15/we-tested-context7]

## 7. Struktur repo open source (upstash/context7, branch master, MIT, 60k+ stars, ~2.9k forks)

- `packages/mcp/` — MCP server (src/index.ts entry, lib/api.ts client backend, auth/JWT/session, schema, Dockerfile, smithery.yaml). [VERIFIED: https://api.github.com/repos/upstash/context7/git/trees/master]
- `packages/cli/` — CLI `ctx7` (setup/auth/docs/remove/upgrade + installer skill & MCP writer). [VERIFIED: idem]
- `packages/sdk/` — TypeScript SDK; `packages/tools-ai-sdk/` — tools Vercel AI SDK; `packages/pi/` — ekstensi pi.dev. [VERIFIED: idem]
- `plugins/` — plugin per-klien: claude, codex, cursor, copilot, context7-power. [VERIFIED: idem]
- `skills/` — skills agent (context7-cli, context7-mcp, find-docs); `rules/` — aturan prompt; `docs/` — 214 file docs; `i18n/` — 15 terjemahan README; `public/`, `.github/` (workflows incl. mcp-registry). [VERIFIED: idem]

## 8. Opini komunitas (tandai sebagai opini)

- OPINI | HN: "Context7 cuma pre-generated static summarization yang bisa kehilangan jawaban spesifik; pendekatan scan source code per pertanyaan lebih targeted dan tak pernah outdated". [VERIFIED: https://news.ycombinator.com/item?id=46944892]
- OPINI | HN: sukses dipakai; alternatif Docfork klaim 1 API call vs Context7 umumnya 2; Codex greps source lokal dan dianggap setara. [VERIFIED: https://news.ycombinator.com/item?id=44071551]
- OPINI | ZKOSS (eksperimen 10 pertanyaan ZK, Claude Sonnet 4.5): dengan Context7 skor turun 73.8%→59% (-15pp); 0/10 pertanyaan membaik; konklusi: retrieval Context7 bisa merugikan jika kualitas chunk rendah. [VERIFIED: https://docs.zkoss.org/small-talk/2025/10/15/we-tested-context7]
- OPINI | Kritik umum: context bloat dulu jadi keluhan #1 (Twitter), alasan arsitektur rerank-side diperkenalkan Jan 2026. [VERIFIED: https://upstash.com/blog/new-context7]

## Implikasi untuk `memo`

- [INFERRED] Backend = black box; yang bisa ditiru: perilaku API/MCP (2 tools, library ID `/owner/repo`, pin versi), refresh lazy berbasis popularitas, rerank server-side, dan tipe sumber (git repo + llms.txt + website + OpenAPI).
- [ASUMSI] Embedding/vector store bisa diganti bebas (FTS5 lokal = pilihan ponytail untuk `memo`), karena reranker server-side-lah pembeda kualitas.

## Sumber

- https://github.com/upstash/context7 (README + LICENSE MIT)
- https://context7.com/docs/overview · https://context7.com/docs/api-guide · https://context7.com/docs/llms.txt
- https://context7.com/docs/library-updates.md · https://context7.com/docs/plans-pricing.md · https://context7.com/docs/library-owners.md · https://context7.com/docs/adding-libraries.md
- https://upstash.com/blog/context7-llmtxt-cursor · https://upstash.com/blog/new-context7
- https://raw.githubusercontent.com/upstash/context7/master/packages/mcp/src/index.ts · .../lib/api.ts · .../lib/constants.ts
- https://api.github.com/repos/upstash/context7 (metadata + git/trees/master)
- https://ice-ice-bear.github.io/posts/2026-03-20-context7
- https://docs.zkoss.org/small-talk/2025/10/15/we-tested-context7
- https://news.ycombinator.com/item?id=46944892 · https://news.ycombinator.com/item?id=44071551
- https://upstash.com/docs/vector/features/embeddingmodels
