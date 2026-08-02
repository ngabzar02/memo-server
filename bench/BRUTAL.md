# Brutal Benchmark — MCP langsung via opencode

Loop: saya perbaiki → Anda **restart opencode** → jalankan prompt di bawah →
bilang "bench done" → saya baca `bench/activity.log` (score.py) → perbaiki lagi.

Kenapa MCP langsung: server yang dipakai opencode adalah yang sebenarnya diuji;
tidak ada subprocess bench yang bisa mati di tengah jalan.

## Cara pakai

1. Restart opencode (agar server memo dimuat ulang — perubahan server.py aktif).
2. Hapus `bench/activity.log` biar skor bersih (atau biarkan, score.py dedup per query).
3. Paste **Blok A**, tunggu selesai. Lalu paste **Blok B**.
4. Ketik "bench done".

## Blok A (11 query)

Panggil `resolve_library_id` lalu `get_docs` untuk tiap pasangan berikut (satu per satu, berurutan):

- fastapi | dependency injection with Depends for authentication
- numpy | broadcasting rules for array arithmetic
- requests | session reuse and connection pooling
- express | routing with express.Router middleware
- flask | quickstart routing and URL building
- pandas | groupby aggregate operations dataframe
- sqlalchemy | select statements core expression tutorial
- pydantic | model fields validation and types
- react | useState hook state management
- nextjs | app router page navigation
- polars | expressions for select and filter

## Blok B (11 query)

- duckdb | window functions in query syntax
- prisma | schema relations one to many
- tailwindcss | utility classes responsive design
- fastmcp | define tools and prompts
- litestar | dependency injection and middleware
- sqlite-vec | sqlite virtual table search
- anthropic | messages api tool use
- openai | chat completions with function calling
- click | command options and arguments decorator
- vue | template syntax directives
- django | queryset filtering with Q objects

## Hasil

Ketik "bench done" → saya (O) menjalankan **swarm** (lihat `bench/swarm.md`):
agent B (skor) → R (riset akar miss) ‖ T (tuning) → F (fix) → RV (audit) →
instruksi restart untuk round berikutnya. Target: docs hit@5 ≥ 40%.

Setiap round dicatat di `bench/rounds/R{n}.md`; state live di `bench/state.md`.
