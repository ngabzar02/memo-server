# Audit RV — report-context7-vs-memo.md

Tanggal: 2026-08-03 · Reviewer: RV
Objek audit: `bench/report-context7-vs-memo.md` (101 baris)
Sumber pembanding: `bench/research/context7.md`, `bench/research/memo-internals.md`,
kode `src/memo/*.py`, `bench/report-R4.md`, commit history, GitHub API upstash/context7.

## VERDICT: APPROVE

Tidak ditemukan halusinasi (0 klaim mengarang). Semua klaim faktual di §0–§4
terverifikasi benar. Ada 2 salah-tag minor (faktual benar, tapi angka/detail tak
termuat di sumber yang dirujuk) — di bawah ambang REJECT (≥2 signifikan). Tidak
ada opini komunitas yang disajikan sebagai fakta ([O] dihormati di §1 baris 43).

## Temuan

### Minor (wajib diperbaiki, tidak menggugurkan)

1. `report-context7-vs-memo.md §0 baris 15` | `Stars | 60.187 [V]`
   → angka presisi tidak ada di context7.md (hanya "60k+ stars", context7.md:55).
   → Bukti: API GitHub upstash/context7 `stargazers_count=60187` → faktual BENAR,
     tapi tag [V] merujuk sumber yang tak memuatnya (salah-tag, traceability).
   → Ganti jadi `60k+ [V]` atau tambah sumber `https://api.github.com/repos/upstash/context7`.

2. `report-context7-vs-memo.md §1 baris 46` | `Repo TS dgn changesets, workflows mcp-registry [V]`
   → "changesets" tidak ada di context7.md (baris 55-61 tak menyebutnya).
   → Bukti: git/trees/master upstash/context7 memuat `.changeset/` → faktual BENAR,
     tapi tak bersumber di riset yang dirujuk.
   → Tambah sumber riset atau hilangkan kata "changesets".

### Catatan (bukan kesalahan — didukung sumber di luar dua file riset)

3. `§1 baris 30` | `hard-split oversize >1024, cap ~4× budget`
   → memo-internals hanya menyebut `_split_oversize (ingest.py:113-126)` tanpa angka.
   → Bukti kode: `ingest.py:101` `_split_oversize(p, max_tokens * 4)`; max_tokens=256 → limit 1024. BENAR.
4. `§3 item 6` | `chunking baseline (BUG2 ter-fix), chunk basi (BUG3), domain filter (BUG4), trim oversize (BUG1)`
   → BUG1-4 tak ada di memo-internals; terverifikasi di `bench/report-R4.md` §3 + commit
     `4c8ed4d "fix(R4): trim_to_tokens skip oversize; chunk hard-split; crawler filter
     domain+bahasa; docs_changed tanpa gate github; full>=3 chunk"` → semua "ter-fix" BENAR.
5. `§1 baris 43` | `R4: resolve 22/22, docs hit@5 5/18 (28%), median 2.93s [V]`
   → memo-internals memuat angka lama (state.md: 33/35, 3/14, 21%); angka R4 ada di
     `bench/report-R4.md:14-17` → BENAR. Inkonsistensi internal state.md, bukan salah laporan.
6. `§1 baris 36` | memo `3 tool (get_docs, resolve_library_id, versions)` — tak bertag;
   → kode server.py:97, 122, 255 tiga `@mcp.tool()` → BENAR.
7. `§1 baris 33` | `skala 33k lib mustahil di SQLite — gap kapasitas` — asumsi tanpa tag [I]/[O]
   di kolom gap; benar secara teknis (vec0 in-memory), disarankan diberi tag [I] agar konsisten.
8. `§0 baris 16` | `Model: managed cloud + on-premise enterprise` — tanpa tag; didukung
   context7.md:9-12 → benar, tinggal format.
9. `§2 baris 56` | `is_full (≥3 chunk)` — memo-internals tak menyebut "3", kode
   `ingest.py:28` `min_chunks=3` → BENAR.
10. `§2 baris 62` | `timeout 360m` — tak di memo-internals; `.github/workflows/cache.yml:12`
    `timeout-minutes: 360` → BENAR.

## Kesimpulan audit

- 0 halusinasi; 0 salah-tag signifikan; 2 salah-tag minor (temuan 1-2) yang faktanya
  benar dan mudah diperbaiki — tidak perlu REJECT.
- Struktur citation law terjaga: klaim Context7 bertag [V]/[U] konsisten dengan
  tag [VERIFIED: URL]/[UNVERIFIED] di context7.md (semua di-spot-check cocok).
- Opini komunitas (ZKOSS -15pp, keluhan bloat) disajikan sebagai opini, bukan fakta.
- §3 gap analysis tidak memuat fakta baru yang dibuat-buat; referensi BUG1-4 valid
  terhadap report-R4.md dan commit 4c8ed4d.
- §0 dan §4 konsisten dengan isi §1–§3.

Status: **APPROVE** — laporan dapat dipakai; perbaiki temuan 1-2 saat edit berikutnya.
