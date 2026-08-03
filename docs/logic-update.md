# Logic Update — memo: logika retrieval & ingest (as-built + delta fix)

- **Versi**: 2.0 · **Tanggal**: 2026-08-03 · **Status**: ACTIVE
- **Peran**: Satu-satunya lokasi konstanta/algoritma/parameter retrieval+ingest dengan
  penunjuk `file:baris`. Dokumen lain mengutip file ini.
- **Tag**: `[V]` = diverifikasi dari source · `[A]` = asumsi · `[FIXED]` = sudah diterapkan.

---

## 1. Resolusi library (registry.py)

Urutan sumber (dari cepat/murah ke lambat/mahal):
1. `_alias` — 65 entri curated trust 95 (final tanpa network) [V: aliases.json, registry.py:26-31]
2. `_builtin` — `py:` (Python stdlib ~50) & `node:` (35 modul Node) → docs_url resmi [V: builtins.json]
3. `llmstxt.cloud` (directory.llmstxt.cloud)
4. npm / PyPI / crates.io / Go proxy / RubyGems — **6 sumber network paralel** [V: registry.py:375-384]
5. GitHub search (butuh token; rate limit anon 60 req/jam)

Trust final = `log10(downloads atau stars)` + 2.0 (llms.txt) − 2.0 (fork) − 1.0 (hanya README)
[V: registry.py:363-366]. Cache hasil 1 jam [V: registry.py:313]; llms 24 jam; versi 1 jam.

**Delta [FIXED]**: `resolve_library_id` kini backfill `latest_ver`/`versions` dari DB + merge
versi kandidat [V: server.py:104-113, registry.py:446-459] — Bug 6 R4.

**Open issue**: entri karangan untuk input sampah (trust 0.0, repo aneh) masih mungkin muncul —
guard threshold belum ada (lihat §7).

## 2. Chunking (ingest.py)

- `CHUNK_TOKENS = 256`, `OVERLAP_TOKENS = 50` (dideklarasikan) [V: ingest.py:12-13]
- `chunk_text`: heading-aware H1-H4; section ≤ 1.024 char utuh; lebih besar dipecah per-paragraf;
  estimasi token `len(p)//4` [V: ingest.py:69-110]
- Section raksasa → `_split_oversize` hard cap `max_tokens*4` (≈1.024 token) [V: ingest.py:85,101,113-126]
- Cap chunks per library: 300 (ingest) vs 200 (crawl) vs 200 (jalur MCP `chunks[:200]`) —
  **INKONSISTENSI**: tiga cap berbeda; wajib satu-tempat [V: ingest.py:253,189,212; server.py:182]

**Delta [FIXED]**: paragraph raksasa di-hard-split (sebelumnya 1 chunk 15-285k char) — Bug 2.
**Open issue**: `OVERLAP_TOKENS` tidak pernah dipakai di badan fungsi [V: ingest.py:69]
→ implementasi overlap ATAU hapus konstanta.

## 3. Crawling (ingest.py)

- 5 level sumber: llms-full.txt → llms.txt → README GitHub → BFS crawl → single page [V: ingest.py:236-263]
- BFS 4 fetch paralel; prioritas URL (query term > basics/tutorial > reference/api > lain);
  iterative deepening; cap 200; deadline [V: ingest.py:154-222]
- `_path_allowed`: netloc sama + filter bahasa EN (`_LANG_RE`) [V: ingest.py:18-25,218]
- `_looks_404`: deteksi 404-palsu berstatus 200 [V: ingest.py:284-289]
- `is_full(complete, n)`: complete AND n ≥ 3 chunk [V: ingest.py:28-31]

**Delta [FIXED]**: filter domain+bahasa aktif (Bug 4) — negatif test di selfcheck [V: ingest.py:298-304].
**Open issue (B4 residual)**: halaman dari `llms.txt`/`llms-full.txt` di-`ingest_docs` TANPA
filter `_path_allowed` [V: ingest_lib ingest.py:246-254] → link non-EN dari llms-full bisa
mengontaminasi (django masih open issue di state.md:10).

## 4. Search hybrid (store.py)

- FTS5 BM25: query term AND dulu, fallback OR untuk recall; limit 20 [V: store.py:133-148,164]
- vec0 cosine: `MATCH ? AND k=20`; cos = 1 − distance [V: store.py:142-147]
- Anti-FP (FP-3): hit dengan cos < 50% cos top-1 dibuang dari fusion (`vec_drop`) — top-1
  selalu lolos; FTS-only (tanpa query_vec) tidak kena threshold [V: store.py:139-162]
- Fusion **RRF k=60** (default param `rrf_k`, bisa di-A/B; bukan normalize+sum —
  docstring modul tidak sinkron, implementasi yang berlaku) [V: store.py:128,160]
- Output: `trim_to_tokens` budget 3.000 token ≈ 12.000 char [V: store.py:186-188]

**Delta [FIXED]**: chunk oversize di-skip (continue), bukan break — Bug 1 [V: store.py:191,213].

## 5. Rerank (rerank.py)

- Cross-encoder ONNX `ms-marco-MiniLM-L-6-v2` qint8 (~25 MB, CPU, threads=2) [V: rerank.py:12,40-50]
- Top-10 rerank; MAX_LEN 512; doc dipotong 1.000 char/pair [V: server.py:66-93]
- Gagal load → fallback hybrid (tanpa indikasi) [V: server.py:70-77] — **silent fallback**:
  produksi harus log peringatan.

## 6. Freshness

- `_docs_changed`: cek docs_url vs DB, TTL 1 jam, TANPA gate github.com [FIXED: server.py:145-150,204-223] — Bug 3
- `_maybe_refresh`: versi baru TTL 1 hari (trust>5) / 7 hari; chunk lama DIBIARKAN (DELETE terbukti merugikan) [V: server.py:226-251]

## 7. Delta anti-false-positive (target M2 — belum semua diterapkan)

| # | Celah | Perilaku sekarang | Perilaku target | Prioritas |
|---|---|---|---|---|
| FP-1 | Input sampah di resolve | entri trust 0.0 dikembalikan (`zzzzzz` → `CreateWheel/zzzzzz`) | tolak: trust < threshold (mis. < 1) + tanpa download/stars → "library not found" | P0 |
| FP-2 | Query kosong/omong kosong di get_docs | 10 chunk default dikembalikan | respon eksplisit "query tidak spesifik — berikan topik", atau filter relevansi | P0 |
| FP-3 | Chunk tidak relevan lolos (nextjs→CDN, pandas→IO, sqlite→README) | dikirim apa adanya | threshold skor relatif (buang < 50% skor top-1) + rerank wajib | P1 |
| FP-4 | Silent fallback rerank/embed | jalan FTS-only tanpa log | log warning; metric exposure | P1 |
| FP-5 | Kontaminasi via llms.txt non-EN | masuk tanpa filter | terapkan `_path_allowed`/`_LANG_RE` ke daftar llms juga | P1 |

**Delta [FIXED 2026-08-04]**: FP-1 (trust final < 1.0 ditolak — `registry.py:_resolve`,
uji `zzzzzz` → `[]`), FP-2 (query kosong → respon eksplisit `[]` + log `reason=empty_query` —
`server.py:_get_docs`), FP-4 (fallback rerank → metrik `event=fallback, kind=rerank` di
activity log — `server.py:_get_reranker`), FP-3 (threshold relevansi relatif — `store.py:139-162`:
hit dengan cos < 50% cos top-1 dibuang sebelum fusion; cos = 1 − distance dari `chunks_vec`
(embedding ternormalisasi); FTS-only tanpa query_vec tidak kena threshold), FP-5 (filter bahasa
llms.txt — `ingest.py:66-72` `parse_llms(text, base_url)` meneruskan base ke `_path_allowed`,
netloc beda + segmen non-EN di-skip; jalur MCP `ingest_lib` kirim `base_url=base`).

Acuan eksternal: praktik "buang hasil < 50% skor top-1, return 'no relevant docs' eksplisit"
[V: neuledge/context blog 2026-02-08]; OWASP MCP cheat sheet — output tool = untrusted input,
validasi di trust boundary [V: riset web 2026-08-03].

## 8. Tabel konstanta tunggal (akan jadi satu-tempat — gap saat ini)

| Konstanta | Nilai | Lokasi sekarang | Catatan |
|---|---|---|---|
| CHUNK_TOKENS | 256 | ingest.py:12 | |
| OVERLAP_TOKENS | 50 | ingest.py:13 | TIDAK DIPAKAI — hapus/implementasi |
| cap chunk per lib | 200 / 200 / 300 | crawl:189, MCP server.py:182, ingest:253 | satu-tempat wajib |
| RRF k | 60 (default, param `rrf_k`) | store.py:128,160 | A/B 20-100: tidak signifikan (P1-03, ADR-016) |
| threshold relevansi | 50% cos top-1 | store.py:151 | relatif per-query (FP-3) |
| budget token output | 3.000 (~12.000 char) | store.py:188 | |
| deadline get_docs | 30 s | server.py:134 | |
| TTL docs_changed | 1 jam | server.py:43-44 | |
| TTL versi | 1 hari / 7 hari | server.py:226-251 | trust > 5 |
| full min chunk | 3 | ingest.py:28 | R4 sarankan ≥ 5 halaman — keputusan ADR |
