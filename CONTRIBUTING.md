# Contributing

Thanks for helping. The project is intentionally small — keep it that way.

## Add a library (most common contribution)

1. Add the library name to `cache-libs.txt` (one name per line — alias,
   package name, or stdlib id like `node:fs` / `py:json`).
2. Open a PR. The `cache.yml` GitHub Actions workflow builds the index
   automatically and publishes a new `docs.db` release asset (~16 MB).
   No local build needed.

## Run the self-checks locally

Every module ships a runnable smoke test:

```bash
python -m memo.ingest
python -m memo.registry
python -m memo.store
```

(These run in CI too — a PR fails if any of them break.)

## Test with a real agent

```bash
uv tool install .
memo --warmup flask nextjs httpx   # pre-index; then register "memo" in your MCP client
```

## Benchmark

```bash
python bench/bench.py   # 20 frozen queries vs Context7's public API (no key needed)
```

Results land in `bench/results/`; publish the summary to `bench/report.md` when you
run a full pass. Don't edit `bench/queries.md` — the query set is frozen (CP-006).

## Ground rules

- Don't commit `docs.db`, `*.db-wal`, `*.db-shm` (gitignored).
- Don't add secrets to code, config, or docs — never.
- Don't claim numbers in the README that aren't verified: no fake benchmark
  scores, no invented library counts.
- Keep the diff small: one library per PR, one fix per PR.
