# BRUTAL Benchmark — Memo MCP Server, R4 (post-update)

- **Tanggal**: 2026-08-03, ~10:30–10:40 WIB
- **Metode**: 22 pasang `resolve_library_id` → `get_docs` via MCP (daemon HTTP :4041, protokol BRUTAL.md Blok A + B), skor fragment `bench/queries.json`.
- **Skor dihitung dari output yang diterima client MCP**, BUKAN dari `activity.log` (log terbukti tidak 1:1 — lihat Bug 1).
- **Verifikasi tambahan**: simulasi MCP langsung ke daemon (`/tmp/opencode/mcp_sim.py`) + repro langsung ke kode Python (`store.search`/`trim_to_tokens`) + inspeksi `docs.db`.

---

## 1. Ringkasan skor

| Metrik | R0 | R2 | R3 | R4 | Target | Context7 (R0) |
|---|---|---|---|---|---|---|
| Resolve hit | 100% | 94% | 100% | **100% (22/22)** | — | 86% |
| Docs hit@5 | 11% | 21% | 28% (5/18) | **28% (5/18)** | ≥40% | 28% |
| Docs hit@1 | 11% | 14% | 22% (4/18) | **22% (4/18)** | — | — |
| Docs latency median | 13.3s | — | 1.76s | **2.93s** | — | 3.3s |
| Latency mean | 12.5s | — | 8.8s | **9.7s** | — | 3.3s |
| Query kosong (client) | — | — | 6/22 | **6/22** | 0 | 0 |
| Skor R0–R2 valid? | **TIDAK** (dari log) | **TIDAK** | client | client | — | — |

**Kesimpulan**: stabil vs R3 (2 perbaikan korpus: express, litestar), tapi **target 40% belum bergerak** dan **bug delivery kritis masih ada** — membuat skor R0/R2 tidak dapat dipercaya.

## 2. Skor per-query (R4)

| Lib | Verdict | Bukti client (top path) | Fragment target |
|---|---|---|---|
| fastapi | **HIT@1** ✓ | `reference/dependencies` | reference/dependencies |
| numpy | **HIT@4** ✓ | `basics.broadcasting` | basics.broadcasting |
| requests | KOSONG ✗ | — (log n=0; korpus hanya 1 chunk) | user/advanced |
| express | path-miss, **semantik HIT** | 10 chunk `llms/guides-5x.txt` (Router-level middleware) — membaik drastis vs 1 chunk sampah "3.x EOL" di R3 | guide/routing |
| flask | MISS | index/tutorial, bukan quickstart | quickstart |
| pandas | MISS | semua `reference/api/pandas.DataFrame.groupby`? → ternyata `io.html` | reference/...groupby |
| sqlalchemy | KOSONG ✗ (**log: 5 hasil!**) | `[]` — Bug 1 | core/tutorial |
| pydantic | MISS (kontaminasi) | 8 chunk `docs.python.org` | concepts/models |
| react | path-miss, semantik relevan | `learn.md` (Quick Start, useState) | reference/react/useState |
| nextjs | MISS (kontaminasi) | `web.dev`/MDN, ver DB `0.0.3` | api-reference/file-conventions/page |
| polars | KOSONG ✗ (**log: 3 hasil!**) | `[]` — Bug 1 | reference/expressions |
| duckdb | **HIT@1** ✓ | `qualify` | docs/sql/query_syntax |
| prisma | **HIT@1** ✓ | `orm/prisma-schema/overview` | orm/prisma-schema |
| tailwindcss | **HIT@1** ✓ | `grid-template-columns` | grid-template-columns |
| fastmcp | MISS (chunk basi) | 7 chunk `glama.ai` padahal docs_url kini `gofastmcp.com` | — |
| litestar | semantik HIT, membaik | `usage/routing/overview.html` + dependency-injection (3 chunk) | — |
| sqlite-vec | MISS (tipis) | 1 chunk `wasm.html` saja | — |
| anthropic | KOSONG ✗ (**log: 2 hasil!**) | `[]` — Bug 1 | — |
| openai | KOSONG ✗ (**log: 1 hasil!**) | `[]` — Bug 1 | — |
| click | KOSONG ✗ (**log: 5 hasil, top=`options/` = HIT sejati!**) | `[]` — Bug 1 | options/ |
| vue | MISS | guide root, bukan `essentials` | guide/essentials |
| django | MISS (kontaminasi bahasa) | intro/overview dalam 10 bahasa (en, pt-br, pl, ko, ja, it, id, fr, es, el) | ref/models/querysets |

Hits sejati client: **5/18 = 28%** (fastapi, numpy, duckdb, prisma, tailwindcss). Jika Bug 1 diperbaiki, potensi +3–4 hit (click, sqlalchemy, polars) → **~44% ≥ target**.

---

## 3. BUG TERVERIFIKASI (bukti kode + reproduksi)

### BUG 1 — KRITIS: "log mencatat hasil, client menerima `[]`" (delivery)

- **Lokasi**: `src/memo/store.py:186-194` — `trim_to_tokens`
  ```python
  budget, out = max_tokens * 4, []        # 3000*4 = 12.000 char
  for c in chunks:
      if len(c["text"]) > budget:         # chunk TOP-1 oversize → break!
          break
      out.append(c)
      budget -= len(c["text"])
  return out
  ```
- **Mekanisme**: `server.py:179-183` menulis log dari `hits` (`top: hits[:5]`) lalu `return trim_to_tokens(hits)`. Jika chunk peringkat-1 > 12.000 char, `break` → return `[]`. Client kosong, log tetap berisi → **semua skor berbasis `activity.log` (R0–R2) palsu**.
- **Repro** (memo venv):
  ```
  polars:   search=4 sizes=[15202,15189,17333,21469]  trimmed=0  → client []
  anthropic: search=3 sizes=[12035,285894,65971]      trimmed=0  → client []
  click:    search=8 sizes=[1862,1862,13303,...]      trimmed=2  → client [1-2] (terpotong)
  sqlalchemy: search=10 sizes=[6007,6007,2847,...]    trimmed=1  → client [1]
  ```
- **Fix yang disarankan**: `break` → `continue` (chunk oversize dilewati, sisanya tetap terkirim). Uji sabotase: panggil daemon dengan lib ber-chunk raksasa (polars/anthropic) → harus non-empty.
- **Akar masalah atasnya** (kenapa ada chunk 285k char): lihat Bug 2.

### BUG 2 — Chunking gagal pecah paragraph raksasa

- **Lokasi**: `src/memo/ingest.py:72-82` — `chunk_text`
  ```python
  para = [p.strip() for p in re.split(r"\n\s*\n", sec) if p.strip()]
  cur2, cur_tok = [], 0
  for p in para:
      pt = max(1, len(p) // 4)
      if cur2 and cur_tok + pt > max_tokens:   # guard `cur2 and` → para pertama
          out.append("\n\n".join(cur2))        # oversize DITERIMA UTUH
          cur2, cur_tok = [], 0
      cur2.append(p)                            # ← para raksasa jadi 1 chunk
      cur_tok += pt
  ```
- **Bukti DB**: chunk terbesar per lib: polars 15.202, 21.469; anthropic 285.894, 65.971 char. Section tanpa blank line (mis. docs API bergaya one-line-per-item) lolos split.
- **Fix**: jika `p` tunggal > max_tokens → hard-split per karakter batas (jangan potong di tengah kode block).

### BUG 3 — Invalidasi docs_url berubah TIDAK jalan untuk URL non-GitHub

- **Lokasi**: `src/memo/server.py:127-132`
  ```python
  if lib and not version and "github.com" in (lib.get("docs_url") or ""):
      # trap HANYA utk docs_url yg masih README GitHub
      if _docs_changed(conn, library_id): ...
  ```
- **Mekanisme**: `_docs_changed` hanya dipanggil jika docs_url mengandung `github.com`. Perubahan docs_url pada lib resmi tidak pernah diperiksa → chunk basi dipakai selamanya.
- **Bukti**:
  - `fastmcp`: registry resolve → `gofastmcp.com`/`PrefectHQ/fastmcp`, tapi DB `libs` masih `glama.ai`/`punkpeye/fastmcp` → 7 chunk glama dikirim.
  - `pydantic`: DB docs_url sudah `docs.pydantic.dev` tapi 8 chunk `docs.python.org` tersisa (tidak pernah di-drop saat docs_url berubah).
  - `nextjs`: ver DB `0.0.3` (basi) walau resolve latest kosong.
- **Fix**: hapus gate `github.com`; selalu cek `_docs_changed` dengan TTL cache; saat docs_url berubah → `drop_lib` + re-ingest.

### BUG 4 — Crawler tanpa filter domain & bahasa (kontaminasi)

- **Lokasi**: `src/memo/ingest.py` — BFS eksplorasi link tanpa allowlist (sekitar baris 116-160, `ingest_lib`).
- **Bukti**:
  - `nextjs`: 101 chunk dari `web.dev`, `developer.mozilla.org` (bukan `nextjs.org/docs`).
  - `django`: 200 chunk (cap penuh) — intro/overview dalam 10 bahasa (el, es, pt-br, pl, ko, ja, it, id, ...) memenuhi korpus sebelum konten EN selesai.
- **Fix**: allowlist domain (origin docs_url + link llms.txt saja), filter bahasa EN (heuristic: ratio huruf non-latin / daftar path `/en/`, `/es/`, ...), atau prioritas `en` lalu stop.

### BUG 5 — Korpus tipis/salah meski flag `full=1`

- **Lokasi**: `src/memo/server.py:161/176` — `full` di-set 1 berdasarkan `complete` ingest, tanpa cek kualitas.
- **Bukti**:
  - `requests`: docs_url menunjuk halaman spesifik `.../user/advanced` (bukan root) → 1 chunk, `full=1` padahal korpus tak lengkap. Sejak R0.
  - `sqlite-vec`: 1 chunk `wasm.html`.
  - `litestar`: 3 chunk (membaik dari 2).
- **Fix**: untuk lib populer, ingest root docs_url + llms.txt; `full` sebaiknya hanya saat chunk > threshold (mis. ≥5 halaman).

### BUG 6 — Metadata resolve kosong di jawaban MCP

- **Lokasi**: `src/memo/server.py:91-100` (`resolve_library_id`).
- **Bukti**: seluruh 22 resolve R3+R4 mengembalikan `latest_ver:""` dan `versions:[]`, padahal `registry.version_etag`/`memo_versions` mengembalikan daftar versi (mis. tsup 8.5.1–7.0.0). Konsumen (benchmark & user) kehilangan info versi.
- **Fix**: isi `latest_ver`/`versions` dari registry di `resolve_library_id` (jangan hanya di `_get_docs` path lib-baru).

---

## 4. Kekurangan non-bug (gap vs Context7)

1. **Latency ekor panjang**: nextjs 33.1s, openai 34.1s, prisma 31.6s, anthropic 30.7s, sqlite-vec 15.6s, express 13.3s — ingest on-demand saat cold cache. Context7 konsisten ~3s. Target: cap 20s (lanjut parsial + resume, sudah ada mekanisme `full=0` tapi data nextjs menunjukkan resume tidak pernah selesai).
2. **Skor R0/R2 tidak valid** — perlu di-scoring ulang dari client setelah Bug 1 diperbaiki.
3. **express membaik drastis di R4** (10 chunk relevan `express.Router`) — bukti pipeline benar bila korpus di-warmup penuh. Pendekatan yang sama perlu diterapkan ke lib lain.
4. **django makin parah**: 5 → 10 bahasa. Regresi karena re-ingest menambah bahasa, bukan mengganti.

## 5. Prioritas perbaikan (urutan dampak)

1. **BUG 1** (`trim_to_tokens` break→continue) — 5 menit, +3–4 hit, memperbaiki validitas seluruh benchmark.
2. **BUG 2** (`chunk_text` hard-split para raksasa) — menghilangkan chunk 15–285k char; prasyarat kualitas Bug 1 fix.
3. **BUG 4** (filter domain+bahasa crawler) — bereskan nextjs/django; drop chunk tercemar + re-warmup.
4. **BUG 3** (invalidasi docs_url) — bereskan fastmcp/pydantic.
5. **BUG 5** (full flag + warmup requests) — bereskan requests/express/pandas/sqlalchemy/nextjs/django via `--force` + verifikasi path count.
6. **BUG 6** (metadata versi) — kosmetik, cepat.
7. Re-run R5 (dengan `mcp_sim.py` sebagai verifikasi independen), skor ulang dari client, target hit@5 ≥ 40%.

## 6. Uji sabotase (wajib ada agar regresi terdeteksi)

- **Bug 1**: inject 1 chunk 20.000 char ke lib uji → `get_docs` harus tetap mengembalikan ≥1 chunk kecil lain (sebelum fix: `[]`).
- **Bug 2**: `chunk_text("A." * 100_000)` → maks chunk ≤ hard-cap (~1024 token); saat ini 1 chunk raksasa.
- **Bug 3**: ganti docs_url registry mock → DB libs + chunks harus drop/re-ingest.
- **Bug 4**: crawler hanya boleh menyimpan path di dalam domain allowlist.

## 7. Checklist perbaikan per-lib — SEMUA hasil MISS/KOSONG (17 dari 22)

Setiap lib di bawah tercatat di tabel Section 2. Kolom "Akar" merujuk ke nomor bug di Section 3; "Verifikasi" = cara memastikan hasil akhir sempurna (client menerima, bukan log).

| # | Lib | Status R4 | Akar masalah | Aksi perbaikan | Verifikasi (harus non-empty + fragment hit) |
|---|---|---|---|---|---|
| 1 | click | KOSONG (log: 5, top=`options/` = HIT sejati) | **Bug 1** (trim) | fix `trim_to_tokens` break→continue | client ≥1 chunk; fragment `options/` |
| 2 | sqlalchemy | KOSONG (log: 5) | **Bug 1** | fix trim | client ≥1 chunk; fragment `core/tutorial` |
| 3 | polars | KOSONG (log: 3) | **Bug 1** + **Bug 2** (chunk 15–21k) | fix trim + hard-split para | client ≥1 chunk; fragment `reference/expressions` |
| 4 | anthropic | KOSONG (log: 2) | **Bug 1** + **Bug 2** (chunk 285k!) | fix trim + hard-split | client ≥1 chunk |
| 5 | openai | KOSONG (log: 1) | **Bug 1** + **Bug 2** (chunk 17k) | fix trim + hard-split | client ≥1 chunk |
| 6 | requests | KOSONG (korpus 1 chunk, sejak R0) | **Bug 5** (full=1 palsu; docs_url halaman spesifik) | ingest root `requests.readthedocs.io` + llms.txt; `full` hanya jika ≥5 halaman | client ≥1 chunk; fragment `user/advanced` |
| 7 | pydantic | MISS (8 chunk docs.python.org) | **Bug 3** (invalidasi) | drop chunk python.org, re-ingest `docs.pydantic.dev` | chunk path `docs.pydantic.dev/concepts/models` |
| 8 | nextjs | MISS (101 chunk web.dev/MDN, ver basi 0.0.3) | **Bug 4** (domain) + **Bug 3** (ver) | filter domain `nextjs.org/docs`; drop + re-warmup | chunk path `nextjs.org/docs/api-reference/...` |
| 9 | django | MISS (200 chunk, 10 bahasa) | **Bug 4** (bahasa) | filter `/en/` + drop bahasa lain; pastikan querysets masuk sebelum cap | chunk `ref/models/querysets` EN |
| 10 | fastmcp | MISS (7 chunk glama.ai) | **Bug 3** (docs_url tak ter-update) | drop lib, re-ingest `gofastmcp.com` | chunk path `gofastmcp.com` |
| 11 | flask | MISS (index/tutorial, bukan quickstart) | korpus kurang kedalaman (llms.txt?) | warmup `flask.palletsprojects.com/en/stable/quickstart` | chunk `quickstart` |
| 12 | pandas | MISS (semua `io.html`) | crawler terjebak 1 halaman | warmup `reference/api/pandas.DataFrame.groupby` | chunk `reference/api/...groupby` |
| 13 | vue | MISS (guide root, bukan essentials) | korpus kurang kedalaman | warmup `guide/essentials` | chunk `guide/essentials` |
| 14 | sqlite-vec | MISS (1 chunk wasm.html) | **Bug 5** (tipis) | warmup halaman SQL functions/tutorial | ≥3 chunk relevan |
| 15 | express | path-miss tapi **semantik HIT** (10 chunk relevan) | fragment `guide/routing` vs path `llms/guides-5x.txt` | opsional: chunk per-halaman bukan 1 file raksasa; kalau diinginkan hit eksak, petakan path llms→URL asli | — (sudah bagus) |
| 16 | react | path-miss, semantik relevan (learn.md) | korpus dari `learn.md` bukan `reference/react/useState` | warmup halaman `reference/react/useState` | chunk `reference/react/useState` |
| 17 | litestar | semantik HIT (3 chunk, membaik) | korpus tipis | warmup `usage/routing` + `usage/dependency-injection` | ≥3 chunk; sudah ok |

**Ringkas**: Bug 1 (fix 5 menit) menyelamatkan 5 lib (click, sqlalchemy, polars, anthropic, openai); Bug 2 menyelamatkan 3; Bug 3+4 bereskan 4 (pydantic, nextjs, django, fastmcp); warmup + Bug 5 bereskan 5 (requests, flask, pandas, vue, sqlite-vec). Potensi akhir: **17–20/22 hit@5 (~77–91%)**, jauh di atas target 40%.

## 8. Lampiran bukti

- Reproduksi Bug 1: `/root/.local/share/memo/bench/` (jalankan ulang blok "Repro" di atas dengan venv `~/.local/share/uv/tools/memo/bin/python`).
- Simulasi daemon (session MCP penuh): `/tmp/opencode/mcp_sim.py` — sqlalchemy/click/anthropic/requests → `"content":[],"structuredContent":{"result":[]}` meski log berisi.
- Baseline DB: 32.788.480 bytes; activity.log 178 baris sebelum R4.
