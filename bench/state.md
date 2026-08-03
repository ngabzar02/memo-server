# State Swarm Benchmark (live — hanya O yang menulis)

- state: `CI-READY` (test.yml hijau; build-cache 66 lib jalan di CI 30830835491; bench-heavy siap dispatch)
- baseline bench = R4 client: hit@5 28% (5/18), resolve 22/22, 6/22 kosong, latency 2.93s — lihat report-R4.md
- round terakhir: R4 (client MCP, 2026-08-03) | target 40%
- skor terakhir: resolve 94% (33/35), docs hit@5 21% (3/14) | target 40%
- target: docs hit@5 >= 40%
- CATATAN 2026-08-03: bench.yml (CI auto, hit=keyword substring, bukan client MCP) memberi memo 16/20, c7 20/20 — INFORMAL, bukan skor resmi; skor resmi hanya bench-heavy (run_bench.py, path fragment, client MCP)

## Open issues
- [ ] pydantic hanya 8 chunk dari docs.pydantic.dev (dugaan: navigasi crawler dangkal) @R
- [ ] django 1 chunk dari llms-full.txt (valid? perlu cek cakupan) @R
- [x] reingest openai/anthropic selesai: openai 27, anthropic 27 chunk @B

## Keputusan tuning (ditulis O)
- (kosong — menunggu data round 1)

## Fakta established
- resolve 100% (22/22) tercapai sebelum sistem MCP-langsung [VERIFIED: bench/report.md R0]
- rerank cross-encoder ONNX qint8: load 0.3s, 3 pairs 0.5s di ARM [VERIFIED: selfcheck 2026-08-02]
- docs_url merge: docs resmi menang atas github README [VERIFIED: resolve flask/pydantic/click]
