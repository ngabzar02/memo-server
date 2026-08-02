# memo

**Context7-style docs for your coding agent — free, unlimited, offline, private.**

memo is a local [MCP](https://modelcontextprotocol.io) server that gives your agent
up-to-date library documentation — the same idea as [Context7](https://context7.com),
minus the strings attached: no billing meter, no API key, no rate limit, and your
queries never leave your machine.

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](#license)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://python.org)
[![MCP](https://img.shields.io/badge/MCP-stdio-8A2BE2)](https://modelcontextprotocol.io)
![Version](https://img.shields.io/badge/version-1.0.0-orange)
[![GitHub release](https://img.shields.io/github/v/release/ngabzar02/memo-server)](https://github.com/ngabzar02/memo-server/releases)
![Downloads](https://img.shields.io/github/downloads/ngabzar02/memo-server/total)
![Stars](https://img.shields.io/github/stars/ngabzar02/memo-server)

---

## Why memo?

LLMs hallucinate APIs. They answer from stale training data — and most "docs tools"
fix that by sending your queries to someone else's server. memo fixes it on your
machine:

| | memo | Context7 |
|---|---|---|
| **Price** | $0, forever | Free tier is **1,000 API calls/month**, then you're blocked (20 bonus calls/day); Pro is **$10/seat/month**, $10 per extra 1,000 calls ([context7.com/plans](https://context7.com/plans)) |
| **API key** | None. Works out of the box | OAuth setup that generates an API key, sent as a `Bearer` token to `mcp.context7.com` |
| **Offline** | Yes — one pre-built index (~16 MB) and you never touch the network again | Online only |
| **Rate limit** | None. Unlimited, always | 1,000 calls/month on free tier |
| **Privacy** | Queries resolved locally from `docs.db`; nothing leaves your device (network only on a first-ever cache miss for an unindexed library) | Every query + library name is sent to Upstash's servers |
| **Run anywhere** | Python 3.10+, works on ARM (Raspberry Pi / Android-ish devices) | CLI needs Node.js 18+; backend runs on their infra |

Honest caveat: nothing here beats a curated docs provider in *coverage*. memo ships
with **65 pre-built libraries** today, and adding one is a one-line PR
(see [Contributing](#contributing)).

## Quickstart (60 seconds)

Requires Python 3.10+ and [uv](https://docs.astral.sh/uv/):

```bash
# 1) install
uv tool install git+https://github.com/ngabzar02/memo-server

# 2) optional but recommended: download the pre-built index (65 libraries, ~16 MB)
bash tools/fetch-cache.sh

# 3) register the server, then ask your agent about any library
```

### opencode (`opencode.json`)

```json
{
  "mcp": {
    "memo": {
      "type": "local",
      "command": ["memo"],
      "enabled": true
    }
  }
}
```

### Claude Desktop (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "memo": {
      "command": "memo"
    }
  }
}
```

### Cursor (`.cursor/mcp.json`)

```json
{
  "mcpServers": {
    "memo": {
      "command": "memo"
    }
  }
}
```

> Make sure the `memo` binary is on your `PATH` (uv installs it into
> `~/.local/bin`). First call on a never-indexed library takes ~5–60 s
> (fetch + index once); every call after that is sub-millisecond.

## How it works

One SQLite file, no services, no secrets:

1. **`resolve_library_id`** — turns `"flask"` into candidate library IDs with trust scores: curated aliases → built-in stdlib (`py:json`, `node:fs`) → `directory.llmstxt.cloud` → npm/PyPI (trust = download counts) → GitHub search.
2. **`get_docs`** — cache hit is sub-ms; on miss it crawls the docs (llms.txt → sitemap → README), extracts clean text with trafilatura, and chunks it (256 tokens, 50 overlap).
3. **Hybrid search** — BM25 (SQLite FTS5) always, plus cosine similarity over embeddings (`bge-small-en-v1.5` via fastembed/ONNX, stored in sqlite-vec) when vectors exist; normalized score fusion, top hits trimmed to a token budget. On-device the MCP path is FTS-first; full vectors come from the pre-built cache or `memo --warmup`.
4. **`versions`** — version history from npm/PyPI when available.
5. **Pre-built cache** — a GitHub Actions workflow ingests all 65 libraries on every push and publishes the resulting `docs.db` (~16 MB) as a release asset. One download, and you're fully offline.

```
registry → ingest (llms.txt/sitemap/crawl) → SQLite FTS5 + sqlite-vec
        → hybrid BM25+vector fusion → token-budget trim → MCP stdio → your agent
```

Data lives at `~/.local/share/memo/docs.db`. Query it with any SQLite client.

## Benchmark

20 real-world queries (frozen in `bench/queries.md`: 8 Python, 6 Node/TS, 3 web/frontend,
3 Go/other) scored binary hit/miss against Context7's public API:

| # | Query | Target | memo | Context7 |
|---|---|---|---|---|
| 1 | how to create a route with a path parameter | flask | TBD | TBD |
| 2 | how to use async tasks and queues | celery | TBD | TBD |
| 3 | how to make a HTTP request with a timeout | requests | TBD | TBD |
| 4 | how to paginate results in the sqlalchemy ORM | sqlalchemy | TBD | TBD |
| 5 | how to define a custom logger | logging | TBD | TBD |
| 6 | how to read a CSV file into a DataFrame | pandas | TBD | TBD |
| 7 | how to seed random numbers for reproducibility | numpy | TBD | TBD |
| 8 | how to send multipart file upload | httpx | TBD | TBD |
| 9 | how to use environment variables in a script | python-dotenv | TBD | TBD |
| 10 | how to handle websocket connections | websockets | TBD | TBD |
| 11 | how to write a custom middleware | express | TBD | TBD |
| 12 | how to validate an email address | validator | TBD | TBD |
| 13 | how to use async fs read in a script | fs-extra | TBD | TBD |
| 14 | how to emit typed events | node:events | TBD | TBD |
| 15 | how to parse a query string | qs | TBD | TBD |
| 16 | how to read environment variables | dotenv | TBD | TBD |
| 17 | how to render a list with keys | react | TBD | TBD |
| 18 | how to add global CSS | nextjs | TBD | TBD |
| 19 | how to create a custom hook | react | TBD | TBD |
| 20 | how to run a goroutine | go | TBD | TBD |

TBD — the benchmark suite lives in `bench/bench.py`; results will be published to
`bench/report.md` when it runs.

## memo vs Context7 vs mcpdoc

| | **memo** | **Context7** | **mcpdoc** |
|---|---|---|---|
| Price | $0 | Free 1,000 calls/mo, then Pro $10/seat ([plans](https://context7.com/plans)) | $0 |
| API key / OAuth | No | Yes | No |
| Server | Local (stdio) | Remote (`mcp.context7.com`) | Local (stdio/SSE) |
| Offline-capable | Yes, pre-built index | No | No persistent index |
| Pre-built library index | Yes — 65 libs, ~16 MB | Yes (server-side) | No |
| Library registry / name resolution | Yes — aliases, stdlib, npm/PyPI, GitHub | Yes | No — you configure each `llms.txt` source manually |
| Search | Hybrid BM25 + vector embeddings | Server-side retrieval | None — fetches and parses on every call |
| Version history | Yes (npm/PyPI) | Yes | No |
| Rate limit | None | Yes (free tier) | None |
| Your query leaves your device | No | Yes | Only to the docs sites you configured |
| Language | Python 3.10+ | CLI needs Node 18+ | Python |

## Roadmap

- [x] MCP server: `resolve_library_id` / `get_docs` / `versions` (Context7-compatible API shape)
- [x] Hybrid retrieval: FTS5 BM25 + embeddings, one-file SQLite
- [x] Pre-built cache pipeline (65 libraries, GitHub Actions → release asset)
- [ ] Publish `bench/report.md` — 20-query benchmark vs Context7
- [ ] Publish memo to PyPI (currently install via git)
- [ ] Self-service: add a library at runtime without a PR
- [ ] More libraries every week — the list is `cache-libs.txt`, one line each

## Contributing

One-line library additions, bugs, benchmarks — see [CONTRIBUTING.md](CONTRIBUTING.md).
Short version: add the library name to `cache-libs.txt` in a PR; CI builds and
ships the new index automatically.

## License

MIT — see [LICENSE](LICENSE). Use it, fork it, ship it.
