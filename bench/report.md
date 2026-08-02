# Bench memo vs Context7 — 2026-08-02 09:49

- Query count: 22 | wall time: 703s
- memo: stdio MCP via subprocess `/tmp/opencode/risktest/bin/python` (binary `memo` tidak ada di PATH), workdir /root/.local/share/memo, PYTHONPATH=/root/.local/share/memo/src; tool `resolve_library_id(library_name, query)` -> `get_docs(library_id, query)`.
- Context7: REST tanpa API key, `GET /v2/libs/search?query=` -> `GET /v2/context?query=&libraryId=`.
- Timeout: resolve 30s, get_docs 40s. Token = perkiraan chars/4. `expected_path_fragments` bersumber curated (pengetahuan umum, independen dari kedua sistem).
- Resolve hit: top-1 id mengandung nama library (dinormalisasi). Relevance hit@k: path chunk/blok (posisi ke-1..5) mengandung fragment.

## Resolve
| # | library | memo top-1 id | memo hit | memo ms | c7 top-1 id | c7 hit | c7 ms |
|---|---------|---------------|----------|---------|-------------|--------|-------|
| 1 | fastapi | fastapi | YES | 11,160 | /websites/fastapi_tiangolo | YES | 3,980 |
| 2 | numpy | numpy | YES | 15,178 | /numpy/numpy | YES | 2,944 |
| 3 | requests | requests | YES | 10,626 | /psf/requests | YES | 2,922 |
| 4 | express | express | YES | 9,889 | /expressjs/express | YES | 2,529 |
| 5 | flask | flask | YES | 9,207 | /pallets/flask | YES | 2,166 |
| 6 | pandas | pandas | YES | 11,620 | /websites/pandas_pydata | YES | 3,507 |
| 7 | sqlalchemy | sqlalchemy | YES | 19,714 | /websites/sqlalchemy_en_20 | YES | 2,346 |
| 8 | pydantic | pydantic | YES | 14,581 | /pydantic/pydantic | YES | 2,724 |
| 9 | react | react | YES | 17,048 | /reactjs/react.dev | YES | 2,930 |
| 10 | nextjs | nextjs | YES | 14,250 | /websites/nextjs | YES | 2,334 |
| 11 | polars | polars | YES | 19,754 | /pola-rs/polars | YES | 2,572 |
| 12 | duckdb | duckdb | YES | 18,053 | /duckdb/duckdb-web | YES | 2,501 |
| 13 | prisma | prisma | YES | 20,614 | /prisma/prisma | YES | 3,049 |
| 14 | tailwindcss | tailwindcss | YES | 15,455 | /rails/tailwindcss-rails | YES | 2,361 |
| 15 | fastmcp | fastmcp | YES | 13,117 | /prefecthq/fastmcp | YES | 2,740 |
| 16 | litestar | litestar | YES | 12,572 | /litestar-org/litestar | YES | 2,885 |
| 17 | sqlite-vec | sqlite-vec | YES | 13,392 | /websites/alexgarcia_xyz_sqlite-vec | YES | 3,048 |
| 18 | anthropic | anthropic | YES | 19,123 | /anthropics/anthropic-sdk-python | YES | 2,442 |
| 19 | openai | openai | YES | 13,993 | /websites/developers_openai_api | YES | 2,263 |
| 20 | click | click | YES | 12,574 | /websites/click_palletsprojects_en_stable | YES | 3,663 |
| 21 | vue | vue | YES | 17,246 | /vuejs/vue | YES | 3,370 |
| 22 | django | django | YES | 17,023 | /django/django | YES | 2,451 |

## Docs (relevance)
| # | library | memo hit@k | memo chunks | memo ms | memo tok | c7 hit@k | c7 blocks | c7 ms | c7 tok |
|---|---------|------------|-------------|---------|-----------|----------|-----------|-------|--------|
| 1 | fastapi | @1 | 10 | 17,388 | 2550 | @3 | 4 | 3,662 | 1,238 |
| 2 | numpy | miss | 0 | 439 | 1 | @2 | 4 | 3,504 | 1,004 |
| 3 | requests | @1 | 10 | 462 | 2560 | @1 | 4 | 7,727 | 549 |
| 4 | express | miss | 10 | 218 | 2354 | miss | 4 | 2,889 | 613 |
| 5 | flask | miss | 2 | 9,744 | 283 | @1 | 4 | 3,325 | 658 |
| 6 | pandas | miss | 10 | 114 | 2560 | miss | 5 | 2,984 | 774 |
| 7 | sqlalchemy | miss | 6 | 14,747 | 1428 | miss | 4 | 5,481 | 801 |
| 8 | pydantic | miss | 0 | 13,898 | 1 | @2 | 5 | 3,165 | 974 |
| 9 | react | miss | 10 | 583 | 2376 | miss | 4 | 3,572 | 630 |
| 10 | nextjs | miss | 10 | 171 | 2277 | miss | 5 | 3,200 | 1,051 |
| 11 | polars | miss | 5 | 12,546 | 1188 | miss | 4 | 2,945 | 467 |
| 12 | duckdb | miss | 10 | 380 | 2560 | miss | 5 | 4,523 | 1,228 |
| 13 | prisma | miss | 9 | 22,479 | 1879 | miss | 4 | 3,411 | 750 |
| 14 | tailwindcss | miss | 5 | 22,965 | 1205 | miss | 4 | 3,280 | 617 |
| 15 | fastmcp | n/a | 0 | 14,804 | 1 | n/a | 5 | 4,123 | 693 |
| 16 | litestar | n/a | 0 | 13,172 | 1 | n/a | 4 | 3,052 | 1,136 |
| 17 | sqlite-vec | n/a | 1 | 15,343 | 256 | n/a | 5 | 2,900 | 686 |
| 18 | anthropic | miss | 0 | 14,650 | 1 | miss | 4 | 3,157 | 1,059 |
| 19 | openai | n/a | 0 | 16,455 | 1 | n/a | 5 | 3,125 | 2,162 |
| 20 | click | miss | 0 | 18,542 | 1 | miss | 4 | 3,440 | 1,110 |
| 21 | vue | miss | 9 | 12,279 | 2067 | miss | 4 | 3,146 | 997 |
| 22 | django | miss | 7 | 13,111 | 1599 | @2 | 4 | 3,234 | 734 |

## Ringkasan agregat

| metrik | memo | Context7 |
|--------|------|----------|
| resolve hit | 100% (22/22) | 100% (22/22) |
| docs hit@5 (query ber-fragment) | 11% (2/18) | 33% (6/18) |
| resolve latency mean ms | 14,827 | 2,806 |
| docs latency mean ms | 9,706 | 3,702 |
| docs latency median ms | 12,412 | 3,302 |
| total token output (est) | 27149 | 19931 |

## Kesimpulan jujur

- Memo resolve: 100% benar; Context7 100%.
- Relevance (hit@5, fragment diketahui): memo 11% vs Context7 33%.
- Latensi docs memo (mean 9,706 ms) vs Context7 (mean 3,702 ms) — network Context7 adalah pembanding yang tidak setara di kondisi lokal.
- Resolve memo lambat (mean 14,827 ms) karena registry.resolve melakukan lookup network berurutan (alias->builtin->llmstxt->npm->pypi->github, timeout 10s per sumber, registry.py:210-248); Context7 resolve adalah satu HTTP call.
- Cold-cache memo (get_docs pertama >1s, hasil 0 chunk, tanpa error): 6 library (pydantic, fastmcp, litestar, anthropic, openai, click). Pada cold cache, budget ingest internal memo 20s tidak cukup untuk fetch penuh -> hasil kosong; call berikutnya akan lanjut index.
- 0 hasil pada cache hangat (search cepat, tanpa error): numpy — retrieval miss (BM25 AND semua kata + tidak ada vektor untuk lib FTS-only), bukan cold-cache.
- Query tanpa fragment (4) hanya dihitung resolve + latency, bukan relevance.
- False-positive heuristik resolve: c7 tailwindcss -> `/rails/tailwindcss-rails` (wrapper Rails, bukan Tailwind CSS asli) — heuristik norm-substring tidak sempurna.