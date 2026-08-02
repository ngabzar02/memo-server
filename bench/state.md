# State Swarm Benchmark (live — hanya O yang menulis)

- state: `IDLE`
- round terakhir: R0 (subprocess bench 2026-08-02, sebelum sistem MCP-langsung)
- skor terakhir: resolve 100%, docs hit@5 11% (2/18) | C7 baseline 86%/28%
- target: docs hit@5 >= 40%

## Open issues
- [ ] pydantic hanya 8 chunk dari docs.pydantic.dev (dugaan: navigasi crawler dangkal) @R
- [ ] django 1 chunk dari llms-full.txt (valid? perlu cek cakupan) @R
- [ ] reingest openai/anthropic status saat round 1 (dicek saat "bench done") @B

## Keputusan tuning (ditulis O)
- (kosong — menunggu data round 1)

## Fakta established
- resolve 100% (22/22) tercapai sebelum sistem MCP-langsung [VERIFIED: bench/report.md R0]
- rerank cross-encoder ONNX qint8: load 0.3s, 3 pairs 0.5s di ARM [VERIFIED: selfcheck 2026-08-02]
- docs_url merge: docs resmi menang atas github README [VERIFIED: resolve flask/pydantic/click]
