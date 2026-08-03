# CI Agent — protokol sub-agent adaptif untuk tugas berat

- **Versi**: 1.0 · **Tanggal**: 2026-08-03 · **Status**: ACTIVE
- **Peran**: Setiap test/benchmark/tugas berat WAJIB di-spawn ke sub-agent CI (`ci-agent`),
  TIDAK dikerjakan langsung di sesi utama. Sesi utama (ponsel ARM) hanya: spawn → review →
  push → baca log.
- **Prinsip**: adaptif — file yang dibuat tergantung test pada batch itu; environment CI
  di-setup ulang per batch agar hasil akurat dan reproducible.

---

## 1. Kapan spawn

| Situasi | Contoh | Dikeriakan oleh |
|---|---|---|
| Benchmark 22 query / hit@5 | BRUTAL, R5..R10 | ci-agent (setup + trigger) |
| Test berat (pytest, sabotase, model download) | SAB-1..9, smoke bench | ci-agent |
| Riset + setup environment CI | ganti action version, cache model HF | ci-agent |
| Build-cache 66→200 lib | release asset baru | ci-agent |
| Audit/perbaikan massal | konstanta satu-tempat, deps pyproject | ci-agent |

## 2. Kontrak input (prompt template)

```
Tugas: <test/benchmark/tugas berat> untuk batch ini.
Lingkup: <lib/query/FR yang disentuh> — file yang dibuat HANYA yang dibutuhkan batch ini.
Langkah wajib:
1. Riset: baca docs/planning.md (backlog aktif), docs/quality-gates.md (metrik), bench/queries.json.
2. Setup environment CI: verifikasi/update workflow di .github/workflows/ (action version,
   cache HF model, junit, artifact upload) — hanya yang relevan batch.
3. Buat file inti testing yang dibutuhkan batch ini (test/fixture/workflow baru atau update).
4. Validasi lokal ringan (selfcheck) — tidak perlu jalankan bench berat lokal.
5. Output: daftar file diubah/dibuat + alasan + apa yang akan diukur + threshold pass/fail.
Jangan: ubah src/memo/ logika produksi tanpa task terpisah; tulis secret; jalankan bench di lokal.
```

## 3. Kontrak output ci-agent (wajib)

1. `docs/ci-agent.md` → update `## 4. Log batch` (append per batch).
2. File yang diubah/dibuat di repo (workflow, tests/, fixtures) — sudah `git add` di staged list.
3. Laporan ringkas: file → alasan → metrik yang diukur → threshold.
4. Tidak ada stub: test yang bergantung fitur belum ada ditandai `@pytest.mark.xfail(strict=True, reason="backlog: <ID>")`.

## 4. Log batch (append-only)

| Batch | Tanggal | Workflow | Trigger | Hasil (link/log) | Threshold | Verdict |
|---|---|---|---|---|---|---|
| (kosong — mulai dari batch pertama) | | | | | | |

## 5. Alur operasi dari ponsel (sesi utama)

```
1. user: "jalankan test X" → O menulis task dengan kontrak §2 → spawn ci-agent (general)
2. ci-agent: riset → setup env CI → buat file adaptif → lapor
3. O: review diff (git status/diff) → komit → git push origin main
4. O: GH_TOKEN=<from ~/.git-credentials> gh workflow run <wf> -f <inputs> --ref main
5. O: gh run watch --exit-status → gh run view --log-failed
6. O: unduh artifact: gh run download <id> -n logs -D /tmp/opencode/<batch>
7. O: catat hasil di docs/ci-agent.md §4 + update bench/state.md + quality-gates.md bila metrik berubah
```

## 6. Aturan environment CI (dari riset 2026-08-03, [V: astral docs, gh cli manual, pytest docs])

- Action version Node24-safe: `checkout@v5`, `setup-python@v6`, `cache@v5`, `upload-artifact@v5`+,
  `softprops/action-gh-release@v2` (node24 — aman). Action v4 berbasis Node20 akan FAIL setelah fall 2026.
- Python: `astral-sh/setup-uv@v9` + `python-version: 3.11` + `uv sync` (atau setup-python@v6 + pip).
- pytest: `--junitxml=pytest.xml` + `pytest-github-actions-annotate-failures` (annotation inline)
  + `-rxXs` (daftar skip/xfail di log) + xfail strict untuk backlog.
- Model HF: set `HF_HOME=$HOME/.hf`, `FASTEMBED_CACHE_PATH=$HOME/.fastembed`,
  `HF_HUB_DOWNLOAD_TIMEOUT=120`, `HF_HUB_DISABLE_PROGRESS_BARS=1`; cache kedua path via actions/cache@v5,
  key `hashFiles('pyproject.toml')`.
- Log informatif: `$GITHUB_STEP_SUMMARY` (tabel metrik + callout gagal) dengan `if: always()`;
  upload artifact: junit XML + log mentah + hasil bench, `if-no-files-found: error`, `retention-days: 14`.
- Gate bench: script Python kecil `if hit@5 < threshold: sys.exit(1)` — exit code = fail job;
  bench terhadap source langsung (bukan release asset) — zero dependency antar workflow [V: riset §4].
- Trigger: test ringan di `push` (paths src/tests/pyproject); bench berat murni `workflow_dispatch`
  + inputs (`threshold`, `query_set`) — tidak pernah jalan tanpa diminta [V: riset §7].
- Permissions: test job `contents: read` (default); `contents: write` hanya cache.yml (release).
- `concurrency: group: ${{ github.workflow }}-${{ github.ref }}` + `cancel-in-progress: true`.
- gh CLI di runner sudah terpasang; set `env: GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}` per step [V: docs GH].
- sqlite-vec==0.1.9 & onnxruntime 1.28 & fastembed: semua ber-wheel linux x64 py3.11 — tanpa apt [V: PyPI JSON].

## 7. Ketentuan non-negosiasi

- Skor bench hanya dari output client MCP (bukan activity.log) [V: report-R4.md:5,20].
- Tiap fix/test baru disertai uji sabotase (docs/testing.md SAB-1..9).
- Tanpa secret di workflow/log/artifact; GH_TOKEN hanya dari `~/.git-credentials` (mode 600).
- Threshold kualitas mengikuti `docs/quality-gates.md` — bukan angka ad-hoc per batch.
