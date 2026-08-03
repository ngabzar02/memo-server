# Infrastructure Update — memo: distribusi, CI/CD, keamanan, observabilitas

- **Versi**: 2.0 · **Tanggal**: 2026-08-03 · **Status**: ACTIVE
- **Tag**: `[V]` = terverifikasi · `[A]` = asumsi · `[BARU]` = belum ada.

---

## 1. Topologi distribusi

```
GitHub Actions (CI, ubuntu-latest × py3.11)
  └─ build-cache: ingest cache-libs.txt → docs.db → gzip
       └─ release asset: memo-cache.db.gz, tag cache-$sha [V: cache.yml, server.py:316-388]
            └─ memo --fetch-cache: unduh → backup .pre-cache → integrity_check → rollback
                 └─ daemon HTTP 127.0.0.1:4041  ← bridge stdio mcp-start-memo ← client
```

Bridge `mcp-start-memo` (stdio) proxy → daemon :4041; self-heal boot bila daemon mati (≤ 180 s);
log daemon di `/tmp/mcp-memo.log` [V: mcp-start-memo, mcp-boot.sh].

## 2. Memori & storage budget (perangkat ARM/RAM ketat)

| Item | Ukuran | Catatan |
|---|---|---|
| docs.db (72 lib) | 55 MB + WAL 5.8 MB | target produksi: 200 lib ≈ ~150 MB [A] |
| embedding fastembed (2 model) | 65 + 88 MB | lazy load, hanya saat dipakai |
| reranker ONNX qint8 | 23-25 MB | lazy load |
| venv tools | 299 MB | hanya di dev/builder; bukan runtime target |
| target RSS daemon | < 500 MB setelah warm | [A] — ukur di R6 |

`ponytail: target RSS, upgrade = pindahkan embed ke CI (vektor sudah pre-computed di release asset)`.

## 3. CI/CD

| Workflow | Isi | Status |
|---|---|---|
| `cache.yml` | build-cache 66 lib → gzip → release asset `cache-$sha`; timeout 360 m | ACTIVE [V] |
| `bench.yml` | CI selfcheck (bench/report-context7 vs memo: `_demo` smoke) | ACTIVE [V] |
| `[BARU] tests.yml` | pytest mini (≥6 uji sabotase + FP) | BACKLOG P3-01 |
| `[BARU] smoke-bench.yml` | score.py atas release asset cache (deteksi regresi hit@5) | BACKLOG P3-02 |

Aturan: push ke main memicu build-cache penuh. Perubahan `cache-libs.txt` = 1 baris diff → asset baru.

## 4. Build & distribusi

- `uv tool install --editable .` untuk dev [V: AGENTS.md].
- Release asset gzip `memo-cache.db.gz` (~16-19 MB) [V: pengukuran]; uncompressed DB 36-55 MB.
- `tools/fetch-cache.sh` varian shell: verifikasi count libs+chunks > 0 sebelum pakai [V].
- Versi cache: `cache.version` ditulis setelah fetch-cache sukses; tag `cache-$sha` (commit) —
  cache selalu sesuai commit kode [V: server.py:316-388].

## 5. Dependencies & kemasan

**Gap**: `pyproject.toml:6-12` hanya 5 deps langsung, tapi source memakai onnxruntime, numpy,
tokenizers, packaging (transitif fastembed tapi tidak dijamin) [V]. `[BARU]` P3-05: daftarkan
deklaratif:

```
fastmcp>=2.0, httpx>=0.27, trafilatura>=1.8, sqlite-vec==0.1.9, fastembed>=0.4,
onnxruntime>=1.18, numpy>=1.26, tokenizers>=0.19, packaging>=23
```

plus `requires-python >=3.10`. Verifikasi: instal venv bersih + `memo --warmup` 1 lib.

## 6. Keamanan & privasi

| Area | Kebijakan | Status |
|---|---|---|
| Bind | daemon 127.0.0.1 saja (bukan 0.0.0.0) | [V] |
| Auth | tanpa auth (localhost); tanpa API key | [V] |
| Secret | token GitHub hanya `~/.git-credentials` (600); tidak pernah di file/log/commit/DB | [V: AGENTS.md] |
| Output tool | konten docs pihak ketiga = **untrusted input** — sanitasi & deteksi instruksi (OWASP MCP cheat sheet) | `[BARU: FP]` — referensi ContextCrush Context7 Feb 2026 |
| SSRF | crawler hanya fetch URL dari llms.txt/sitemap repo target; `_path_allowed` netloc sama | [V] + audit `[BARU]` |
| Log | tanpa query sensitif? query user tercatat di activity.log — tinjau `[BARU]` | |

Referensi insiden: ContextCrush (Context7 custom rules → prompt injection supply-chain, patch 2 hari)
[V: noma.security 2026-03-05]. memo tidak punya fitur "custom rules" — pertahankan.

## 7. Observabilitas & runbook

- Log: `bench/activity.log` JSONL (tiap tool call) [V: server.py:24-34]; daemon stderr → `/tmp/mcp-memo.log`.
- Skor: `bench/score.py` + `mcp_sim.py` (validasi independen) [V: report-R4.md:6].
- Health: bridge ping JSON-RPC (idempoten) [V: mcp-boot.sh]; `curl :4041/mcp` ping.
- `[BARU] FP-4`: fallback rerank/embed → log warning + counter (mau diukur, bukan senyap).
- Runbook:
  1. Daemon mati → `~/.local/bin/mcp-boot.sh` (self-heal bridge juga bisa boot).
  2. DB korup → `memo --fetch-cache --force` (rollback `.pre-cache` otomatis bila integrity gagal).
  3. Hasil basi → `memo --warmup <lib> --force` setelah docs_url berubah.
  4. Regresi hit@5 → replay `queries.json` pasca-restart daemon, banding report terakhir.

## 8. Lanjutan (target infra, [A])

- Systemd user unit (opsional) untuk boot daemon deterministik, menggantikan mcp-boot.sh manual.
- Pemisahan log query vs telemetri (privacy).
- Smoke bench di CI (P3-02) sebagai gate rilis asset.
