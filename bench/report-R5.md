# Bench memo vs Context7 — 2026-08-03 16:20

- Query count: 22 | wall time: 145s
- memo: stdio MCP via subprocess `/opt/hostedtoolcache/Python/3.11.15/x64/bin/python` (binary `memo` tidak ada di PATH), workdir /home/runner/work/memo-server/memo-server, PYTHONPATH=/home/runner/work/memo-server/memo-server/src; tool `resolve_library_id(library_name, query)` -> `get_docs(library_id, query)`.
- Context7: REST tanpa API key, `GET /v2/libs/search?query=` -> `GET /v2/context?query=&libraryId=`.
- Timeout: resolve 30s, get_docs 40s. Token = perkiraan chars/4. `expected_path_fragments` bersumber curated (pengetahuan umum, independen dari kedua sistem).
- Resolve hit: top-1 id mengandung nama library (dinormalisasi). Relevance hit@k: path chunk/blok (posisi ke-1..5) mengandung fragment.

## Resolve
| # | library | memo top-1 id | memo hit | memo ms | c7 top-1 id | c7 hit | c7 ms |
|---|---------|---------------|----------|---------|-------------|--------|-------|
| 1 | fastapi | fastapi | YES | 5 | /websites/fastapi_tiangolo | YES | 1,473 |
| 2 | numpy | numpy | YES | 4 | /numpy/numpy | YES | 2,251 |
| 3 | requests | requests | YES | 3 | /psf/requests | YES | 1,518 |
| 4 | express | express | YES | 3 | /expressjs/express | YES | 1,168 |
| 5 | flask | flask | YES | 3 | /pallets/flask | YES | 1,446 |
| 6 | pandas | pandas | YES | 3 | /websites/pandas_pydata | YES | 1,108 |
| 7 | sqlalchemy | sqlalchemy | YES | 3 | /websites/sqlalchemy_en_20 | YES | 1,063 |
| 8 | pydantic | pydantic | YES | 3 | /pydantic/pydantic | YES | 972 |
| 9 | react | react | YES | 3 | /reactjs/react.dev | YES | 980 |
| 10 | nextjs | nextjs | YES | 3 | /websites/nextjs | YES | 1,296 |
| 11 | polars | polars | YES | 3 | /pola-rs/polars | YES | 1,362 |
| 12 | duckdb | duckdb | YES | 3 | /duckdb/duckdb-web | YES | 1,015 |
| 13 | prisma | prisma | YES | 3 | /prisma/web | YES | 1,215 |
| 14 | tailwindcss | tailwindcss | YES | 3 | /nguyenviet02/fluid-tailwindcss | YES | 1,220 |
| 15 | fastmcp | fastmcp | YES | 3 | /prefecthq/fastmcp | YES | 1,020 |
| 16 | litestar | litestar | YES | 3 | /litestar-org/litestar | YES | 958 |
| 17 | sqlite-vec | sqlite-vec | YES | 3 | /asg017/sqlite-vec | YES | 1,010 |
| 18 | anthropic | anthropic | YES | 3 | /anthropics/anthropic-sdk-python | YES | 1,044 |
| 19 | openai | openai | YES | 3 | /websites/developers_openai_api | YES | 1,494 |
| 20 | click | click | YES | 3 | /websites/click_palletsprojects_en_stable | YES | 1,072 |
| 21 | vue | vue | YES | 3 | /vuejs/vue | YES | 868 |
| 22 | django | django | YES | 3 | /django/django | YES | 1,056 |

## Docs (relevance)
| # | library | memo hit@k | memo chunks | memo ms | memo tok | c7 hit@k | c7 blocks | c7 ms | c7 tok |
|---|---------|------------|-------------|---------|-----------|----------|-----------|-------|--------|
| 1 | fastapi | miss | 10 | 2,777 | 2474 | @2 | 4 | 1,728 | 922 |
| 2 | numpy | @1 | 10 | 2,015 | 2394 | @2 | 4 | 1,307 | 1,004 |
| 3 | requests | @1 | 10 | 1,992 | 2151 | @1 | 4 | 1,772 | 549 |
| 4 | express | miss | 5 | 1,337 | 1259 | miss | 5 | 1,310 | 912 |
| 5 | flask | @1 | 10 | 1,427 | 2393 | @1 | 4 | 1,896 | 546 |
| 6 | pandas | miss | 10 | 1,462 | 1566 | miss | 5 | 1,782 | 774 |
| 7 | sqlalchemy | miss | 10 | 1,351 | 2303 | miss | 4 | 2,307 | 716 |
| 8 | pydantic | miss | 10 | 1,919 | 2297 | @1 | 5 | 1,712 | 918 |
| 9 | react | miss | 10 | 1,848 | 2385 | miss | 5 | 1,818 | 801 |
| 10 | nextjs | miss | 1 | 552 | 251 | miss | 5 | 1,419 | 1,051 |
| 11 | polars | miss | 1 | 1,064 | 237 | miss | 5 | 1,540 | 678 |
| 12 | duckdb | miss | 10 | 2,218 | 2104 | miss | 4 | 2,103 | 1,116 |
| 13 | prisma | @1 | 3 | 2,291 | 676 | @1 | 5 | 1,522 | 2,003 |
| 14 | tailwindcss | @1 | 1 | 1,093 | 237 | miss | 4 | 1,872 | 560 |
| 15 | fastmcp | n/a | 10 | 735 | 2139 | n/a | 5 | 1,490 | 590 |
| 16 | litestar | n/a | 10 | 1,320 | 2414 | n/a | 4 | 2,298 | 1,262 |
| 17 | sqlite-vec | n/a | 1 | 3,955 | 204 | n/a | 5 | 2,218 | 830 |
| 18 | anthropic | miss | 10 | 9,579 | 1988 | miss | 4 | 1,934 | 1,059 |
| 19 | openai | n/a | 2 | 14,384 | 466 | n/a | 5 | 1,432 | 2,162 |
| 20 | click | @1 | 4 | 3,506 | 901 | @2 | 5 | 1,568 | 1,128 |
| 21 | vue | miss | 1 | 21,352 | 254 | miss | 4 | 1,589 | 1,038 |
| 22 | django | @1 | 1 | 2,076 | 247 | @2 | 4 | 1,576 | 734 |

## Ringkasan agregat

| metrik | memo | Context7 |
|--------|------|----------|
| resolve hit | 100% (22/22) | 100% (22/22) |
| docs hit@5 (query ber-fragment) | 39% (7/18) | 44% (8/18) |
| resolve latency mean ms | 3 | 1,210 |
| docs latency mean ms | 3,326 | 1,709 |
| docs latency median ms | 1,956 | 1,720 |
| total token output (est) | 31340 | 21353 |

## Kesimpulan jujur

- Memo resolve: 100% benar; Context7 100%.
- Relevance (hit@5, fragment diketahui): memo 39% vs Context7 44%.
- Latensi docs memo (mean 3,326 ms) vs Context7 (mean 1,709 ms) — network Context7 adalah pembanding yang tidak setara di kondisi lokal.
- Resolve memo lambat (mean 3 ms) karena registry.resolve melakukan lookup network berurutan (alias->builtin->llmstxt->npm->pypi->github, timeout 10s per sumber, registry.py:210-248); Context7 resolve adalah satu HTTP call.
- Cold-cache memo (get_docs pertama >1s, hasil 0 chunk, tanpa error): 0 library (tidak ada). Pada cold cache, budget ingest internal memo 20s tidak cukup untuk fetch penuh -> hasil kosong; call berikutnya akan lanjut index.
- Query tanpa fragment (4) hanya dihitung resolve + latency, bukan relevance.