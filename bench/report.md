# Bench memo vs Context7 — 2026-08-02 11:39

- Query count: 22 | wall time: 574s
- memo: stdio MCP via subprocess `/tmp/opencode/risktest/bin/python` (binary `memo` tidak ada di PATH), workdir /root/.local/share/memo, PYTHONPATH=/root/.local/share/memo/src; tool `resolve_library_id(library_name, query)` -> `get_docs(library_id, query)`.
- Context7: REST tanpa API key, `GET /v2/libs/search?query=` -> `GET /v2/context?query=&libraryId=`.
- Timeout: resolve 30s, get_docs 40s. Token = perkiraan chars/4. `expected_path_fragments` bersumber curated (pengetahuan umum, independen dari kedua sistem).
- Resolve hit: top-1 id mengandung nama library (dinormalisasi). Relevance hit@k: path chunk/blok (posisi ke-1..5) mengandung fragment.

## Resolve
| # | library | memo top-1 id | memo hit | memo ms | c7 top-1 id | c7 hit | c7 ms |
|---|---------|---------------|----------|---------|-------------|--------|-------|
| 1 | fastapi | fastapi | YES | 37 | /websites/fastapi_tiangolo | YES | 3,597 |
| 2 | numpy | numpy | YES | 10 | /numpy/numpy | YES | 2,351 |
| 3 | requests | requests | YES | 51 | /psf/requests | YES | 2,788 |
| 4 | express | express | YES | 10,540 | /expressjs/express | YES | 2,675 |
| 5 | flask | flask | YES | 15,558 | /pallets/flask | YES | 2,461 |
| 6 | pandas | pandas | YES | 14 | /websites/pandas_pydata | YES | 2,342 |
| 7 | sqlalchemy | sqlalchemy | YES | 19,427 | /websites/sqlalchemy_en_20 | YES | 2,203 |
| 8 | pydantic | pydantic | YES | 10,143 | /pydantic/pydantic | YES | 2,253 |
| 9 | react | react | YES | 26 | /reactjs/react.dev | YES | 2,524 |
| 10 | nextjs | nextjs | YES | 10 | /vercel/next.js | YES | 2,465 |
| 11 | polars | polars | YES | 8,811 | /pola-rs/polars | YES | 2,445 |
| 12 | duckdb | duckdb | YES | 13,039 | /duckdb/duckdb-web | YES | 2,577 |
| 13 | prisma | prisma | YES | 22,325 | /prisma/prisma | YES | 3,025 |
| 14 | tailwindcss | tailwindcss | YES | 13,789 | /hyoban/tailwindcss-icons | YES | 3,157 |
| 15 | fastmcp | fastmcp | YES | 36 | /prefecthq/fastmcp | YES | 2,672 |
| 16 | litestar | litestar | YES | 5,839 | /websites/litestar_dev | YES | 2,368 |
| 17 | sqlite-vec | sqlite-vec | YES | 18,973 | /websites/alexgarcia_xyz_sqlite-vec | YES | 3,012 |
| 18 | anthropic | anthropic | YES | 12,212 | /anthropics/anthropic-sdk-python | YES | 7,868 |
| 19 | openai | openai | YES | 10,784 | /websites/developers_openai_api | YES | 3,131 |
| 20 | click | click | YES | 10,894 | — | NO(HTTP 429) | 1,900 |
| 21 | vue | vue | YES | 10 | — | NO(HTTP 429) | 2,213 |
| 22 | django | django | YES | 17 | — | NO(HTTP 429) | 2,290 |

## Docs (relevance)
| # | library | memo hit@k | memo chunks | memo ms | memo tok | c7 hit@k | c7 blocks | c7 ms | c7 tok |
|---|---------|------------|-------------|---------|-----------|----------|-----------|-------|--------|
| 1 | fastapi | @1 | 10 | 3,125 | 2550 | @3 | 4 | 3,289 | 1,180 |
| 2 | numpy | @4 | 10 | 3,322 | 1130 | @1 | 4 | 3,058 | 1,004 |
| 3 | requests | miss | 0 | 6,675 | 1 | @1 | 4 | 3,267 | 549 |
| 4 | express | miss | 10 | 8,507 | 2354 | miss | 5 | 3,037 | 967 |
| 5 | flask | miss | 0 | 13,873 | 1 | @1 | 4 | 3,313 | 546 |
| 6 | pandas | miss | 10 | 7,705 | 2560 | miss | 5 | 2,997 | 774 |
| 7 | sqlalchemy | miss | 6 | 17,579 | 1428 | miss | 4 | 3,590 | 818 |
| 8 | pydantic | miss | 0 | 15,788 | 1 | @2 | 5 | 3,559 | 1,212 |
| 9 | react | miss | 10 | 17,464 | 2376 | miss | 4 | 3,473 | 795 |
| 10 | nextjs | miss | 0 | 7,896 | 1 | miss | 4 | 3,126 | 1,223 |
| 11 | polars | miss | 5 | 16,280 | 1188 | miss | 4 | 3,034 | 467 |
| 12 | duckdb | miss | 10 | 12,680 | 2560 | miss | 4 | 3,363 | 1,171 |
| 13 | prisma | miss | 9 | 18,748 | 1879 | miss | 5 | 3,222 | 742 |
| 14 | tailwindcss | miss | 5 | 20,359 | 1205 | miss | 5 | 3,281 | 1,623 |
| 15 | fastmcp | n/a | 6 | 9,708 | 1359 | n/a | 5 | 3,123 | 591 |
| 16 | litestar | n/a | 10 | 10,538 | 2341 | n/a | 5 | 4,144 | 2,394 |
| 17 | sqlite-vec | n/a | 1 | 15,078 | 145 | n/a | 5 | 3,145 | 686 |
| 18 | anthropic | miss | 1 | 16,312 | 256 | miss | 4 | 3,463 | 1,048 |
| 19 | openai | n/a | 0 | 14,816 | 1 | n/a | 5 | 4,343 | 2,162 |
| 20 | click | miss | 0 | 15,218 | 1 | miss | n/a | n/a | n/a |
| 21 | vue | miss | 9 | 11,855 | 2067 | miss | n/a | n/a | n/a |
| 22 | django | miss | 0 | 12,063 | 1 | miss | n/a | n/a | n/a |

## Ringkasan agregat

| metrik | memo | Context7 |
|--------|------|----------|
| resolve hit | 100% (22/22) | 86% (19/22) |
| docs hit@5 (query ber-fragment) | 11% (2/18) | 28% (5/18) |
| resolve latency mean ms | 7,843 | 2,833 |
| docs latency mean ms | 12,525 | 3,271 |
| docs latency median ms | 13,276 | 3,281 |
| total token output (est) | 25405 | 19952 |

## Kesimpulan jujur

- Memo resolve: 100% benar; Context7 86%.
- Relevance (hit@5, fragment diketahui): memo 11% vs Context7 28%.
- Latensi docs memo (mean 12,525 ms) vs Context7 (mean 3,271 ms) — network Context7 adalah pembanding yang tidak setara di kondisi lokal.
- Resolve memo lambat (mean 7,843 ms) karena registry.resolve melakukan lookup network berurutan (alias->builtin->llmstxt->npm->pypi->github, timeout 10s per sumber, registry.py:210-248); Context7 resolve adalah satu HTTP call.
- Cold-cache memo (get_docs pertama >1s, hasil 0 chunk, tanpa error): 7 library (requests, flask, pydantic, nextjs, openai, click, django). Pada cold cache, budget ingest internal memo 20s tidak cukup untuk fetch penuh -> hasil kosong; call berikutnya akan lanjut index.
- Query tanpa fragment (4) hanya dihitung resolve + latency, bukan relevance.
- Context7 docs status: skip: resolve failed.