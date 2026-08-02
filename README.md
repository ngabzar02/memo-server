# memo

MCP server lokal untuk dokumentasi library versi-terbaru — klon [Context7](https://context7.com) yang gratis total, unlimited, dan offline-capable. Index dibangun on-demand ke SQLite (BM25 + vektor) dari llms.txt / halaman docs resmi.

## Fitur

- **`resolve_library_id(name, query)`** — resolusi library → kandidat {repo, docs_url, trust}: alias kurasi manual → builtin stdlib (Node/Python) → directory.llmstxt.cloud → npm/PyPI (trust = downloads) → GitHub search (preferensi bahasa dari query)
- **`get_docs(library_id, query)`** — hybrid search (BM25 + embedding bge-small-en-v1.5), cache sub-ms setelah first fetch
- **`versions(library_id)`** — daftar versi yang diketahui
- Offline-capable: sekali di-index, cache permanen di SQLite (FTS5 + sqlite-vec)

## Instalasi

```bash
uv tool install git+https://github.com/ngabzar02/memo-server
```

Registrasi di `opencode.json` (atau config MCP lain):

```json
{
  "mcp": {
    "memo": {
      "type": "local",
      "command": ["<path ke uv tool bin>/memo"],
      "enabled": true
    }
  }
}
```

## Pre-index (disarankan)

Cold fetch pertama melewati batas timeout MCP (~30s) di beberapa client — panaskan cache dari shell dulu:

```bash
memo --warmup flask nextjs httpx
memo --warmup --force flask   # re-ingest (docs_url berubah / force refresh)
```

## Arsitektur

| Modul | Peran |
|---|---|
| `registry.py` | resolusi nama → {repo, docs_url, trust} |
| `ingest.py` | fetch → trafilatura → chunk 256 token (overlap 50) |
| `store.py` | SQLite: libs + chunks_fts (BM25) + chunks_vec (sqlite-vec) |
| `server.py` | FastMCP stdio server + `--warmup` CLI |

Data: `~/.local/share/memo/docs.db` (buat sekali, dipakai semua library).

## Lisensi

MIT
