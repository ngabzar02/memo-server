# bench/ — benchmark memo vs Context7 (anti-mock)

Harness pengukuran NYATA: dua sistem diukur pada set query yang sama.
Tidak ada mock/stub/angka hardcode — semua angka dari eksekusi live.

## Isi

| file | peran |
|------|-------|
| `queries.json` | 22 query nyata, tiap entry: `library_name`, `query`, `expected_path_fragments` (curated, boleh kosong), `source` |
| `mcp_client.py` | client MCP stdio minimal tanpa SDK eksternal: spawn subprocess server, framing JSON-RPC 2.0 per baris, `initialize` handshake, `tools/call` |
| `run_bench.py` | harness utama: 2 fase per query (`resolve_library_id` -> `get_docs` untuk memo; `GET /v2/libs/search` -> `GET /v2/context` untuk Context7), skor, render `report.md` |
| `report.md` | hasil run terakhir (di-generate, bukan ditulis tangan) |

## Cara pakai

```bash
# dari /root/.local/share/memo
/tmp/opencode/risktest/bin/python bench/run_bench.py --queries bench/queries.json --out bench/report.md
```

Flag: `--limit N` untuk membatasi query (debug). Timeout: resolve 30s, get_docs 40s
(ubah konstanta `RESOLVE_TIMEOUT` / `DOCS_TIMEOUT` di `run_bench.py`).

Catatan eksekusi:
- memo dipanggil via stdio MCP (bukan import in-process): binary `memo` tidak ada di
  PATH, jadi spawn `python -u -c "from memo.server import main; main()"` dengan
  `PYTHONPATH=src`, workdir repo root.
- Context7 tanpa API key: `/v2/libs/search` dan `/v2/context` keduanya live (verified
  2026-08-02). Kalau suatu saat `/v2/context` menolak (401/403), harness mencatat
  `N/A (butuh API key)` per query dan lanjut — hanya resolve yang diskor.
- Skor: `resolve hit` (top-1 id mengandung nama lib, dinormalisasi), `docs hit@k`
  (path chunk/blok ke-1..5 mengandung expected fragment), latency ms, token ≈ chars/4.
- Cold-cache: get_docs pertama per lib baru bisa kosong (budget ingest internal memo
  20s); call berikutnya melanjutkan index. Ini tercatat jujur di kesimpulan report.

`report.md` berisi tabel per-query (resolve + relevance), agregat, dan "Kesimpulan jujur".
