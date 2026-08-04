"""test_ingest — chunk_text (heading + hard-split), filter domain/bahasa,
deteksi 404-palsu, full flag, SSRF guard, sitemap fallback.

API diverifikasi dari src/memo/ingest.py:
- chunk_text(text, max_tokens=512, overlap=50) ingest.py:69 (SAB-2: cap 4x
  max_tokens utk hard-split via _split_oversize)
- _path_allowed(url, base_url) ingest.py:18 (SAB-4: netloc sama + tanpa
  segmen bahasa non-EN)
- _looks_404(text) ingest.py:284
- is_full(complete, n_chunks, min_chunks=3) ingest.py:28
- _ssrf_safe(url) ingest.py:87 (I15: blok host internal/metadata)
- _sitemap_locs / _ingest_sitemap (D6: fallback docs SPA tanpa llms.txt)
"""

from pathlib import Path

import pytest

from memo import ingest

FIXTURES = Path(__file__).parent / "fixtures"


def test_chunk_text_heading_aware():
    text = "# Section One\n\nsome body text\n\n## Sub A\n\nmore text"
    chunks = ingest.chunk_text(text)
    assert len(chunks) >= 2  # heading masing-masing jadi unit sendiri
    assert any(c.startswith("# Section One") for c in chunks)
    assert any(c.startswith("## Sub A") for c in chunks)


def test_chunk_text_code_fence_parity():
    """Heading SETELAH ``` ditutup harus jadi section baru (fence parity).
    Dulu any() atas cur[] mengunci semua baris sesudah fence pertama sbg code."""
    text = "```python\n# bukan heading (dalam code)\nprint(1)\n```\n\n## Sub A\nmore"
    chunks = ingest.chunk_text(text)
    assert any(c.startswith("## Sub A") for c in chunks), \
        "heading setelah fence tertutup tidak jadi section sendiri"


def test_chunk_text_large_input_fast():
    """Regresi O(n^2): halaman 20k baris pernah ~45s (scan cur[] per baris);
    inkremental harus jauh di bawah batas. Batas longgar anti-flaky di CI."""
    import time
    text = "\n".join(f"line {i} body words {i}" for i in range(20_000))
    t0 = time.monotonic()
    ingest.chunk_text(text)
    assert time.monotonic() - t0 < 10


def test_chunk_text_respects_cap():
    text = "\n\n".join(f"Para {i} " + "B." * 400 for i in range(20))
    chunks = ingest.chunk_text(text)
    assert len(chunks) >= 2
    assert all(len(c) <= ingest.CHUNK_TOKENS * 4 for c in chunks)


def test_chunk_text_hard_split_oversize_paragraph():
    """SAB-2: paragraf raksasa di-hard-split, max piece <= 4x max_tokens."""
    chunks = ingest.chunk_text("A." * 100_000)
    assert all(len(c) <= ingest.CHUNK_TOKENS * 4 for c in chunks)
    assert len(chunks) > 1  # benar-benar terpotong, bukan 1 chunk raksasa


def test_chunk_text_returns_text_when_empty():
    assert ingest.chunk_text("") == [""]
    assert ingest.chunk_text("   ") == ["   "]


def test_extract_skips_non_html():
    """Guard CI-1: body kosong/JS-only/anti-bot tidak sampai ke trafilatura
    (pernah membanjiri log CI dgn ERROR empty HTML tree)."""
    assert ingest._extract("") == ""
    assert ingest._extract("   ") == ""
    assert ingest._extract('{"error": "rate limited"}') == ""


def test_path_allowed_same_domain_and_en(tmp_db):
    """SAB-4: path di luar domain base TIDAK diizinkan; bahasa non-EN di-skip."""
    assert ingest._path_allowed("https://nextjs.org/docs/app/page", "https://nextjs.org/docs")
    assert not ingest._path_allowed("https://web.dev/articles", "https://nextjs.org/docs")
    assert not ingest._path_allowed("https://docs.djangoproject.com/pt-br/6.0/intro/",
                                    "https://docs.djangoproject.com/en/6.0/")
    assert ingest._path_allowed("https://docs.djangoproject.com/en/6.0/ref/",
                                "https://docs.djangoproject.com/en/6.0/")


def test_looks_404():
    fake = (FIXTURES / "404.html").read_text()
    assert ingest._looks_404(fake)
    assert ingest._looks_404("short page: the page you're looking for is gone")
    assert ingest._looks_404("short page: not found")
    assert not ingest._looks_404("This is a completely normal documentation page "
                                 "with lots of useful content about how things work. "
                                 "It contains multiple sentences and is longer.")


def test_norm_path_dedupes_html_and_slash():
    """A8: /overview.html, /overview/, /overview -> satu bentuk (dedupe)."""
    assert ingest.norm_path("https://x.dev/a/overview.html") == \
        ingest.norm_path("https://x.dev/a/overview/") == \
        ingest.norm_path("https://x.dev/a/overview")
    assert ingest.norm_path("https://x.dev/") == "https://x.dev/"


def test_norm_path_keeps_query_free_query():
    assert "?" not in ingest.norm_path("https://x.dev/page.html?tab=1")


def test_textual_rejects_binary_assets():
    """A11: css/js/png dll ditolak (dulu meracuni korpus tailwind & httpx)."""
    assert ingest._textual("text/html; charset=utf-8")
    assert ingest._textual("text/plain")
    assert ingest._textual("application/xml")
    assert ingest._textual("")          # server lama tanpa content-type: dianggap teks
    assert not ingest._textual("image/png")
    assert not ingest._textual("text/css")
    assert not ingest._textual("application/javascript")
    assert not ingest._textual("font/woff2")


def test_is_full():
    assert not ingest.is_full(True, 1)    # 1 chunk complete != full (SAB-4/R4-BUG5)
    assert ingest.is_full(True, 5)
    assert not ingest.is_full(False, 5)


def test_llms_filter_skips_non_en_links(tmp_db):
    """SAB-9 (FP-5): llms.txt berisi link non-EN -> link tsb TIDAK boleh masuk
    korpus (base_url diberikan -> netloc beda + segmen bahasa non-EN di-skip)."""
    text = (FIXTURES / "llms.txt").read_text()
    links = ingest.parse_llms(text, base_url="https://docs.djangoproject.com/")
    assert links, "fixture llms.txt tidak terparse"
    base = "https://docs.djangoproject.com/"
    assert all(ingest._path_allowed(l["url"], base) for l in links), \
        "link non-EN (pt-br/es) masih lolos ke korpus"


def test_ssrf_blocks_internal_hosts():
    """I15: docs_url berasal npm/pypi (input tak tepercaya) — host internal,
    loopback, cloud metadata, dan .local MESTI diblok."""
    assert not ingest._ssrf_safe("http://localhost:8080/docs")
    assert not ingest._ssrf_safe("http://127.0.0.1/x")
    assert not ingest._ssrf_safe("http://10.0.0.5/x")
    assert not ingest._ssrf_safe("http://192.168.1.1/x")
    assert not ingest._ssrf_safe("http://169.254.169.254/latest/meta-data/")
    assert not ingest._ssrf_safe("http://172.16.3.9/x")
    assert not ingest._ssrf_safe("http://0.0.0.0/x")
    assert not ingest._ssrf_safe("http://foo.local/x")
    assert not ingest._ssrf_safe("http://[::1]/x")
    assert ingest._ssrf_safe("https://fastapi.tiangolo.com/")
    assert ingest._ssrf_safe("https://docs.astro.build/")


def test_sitemap_locs_parses_urlset_and_index():
    """D6: urlset langsung maupun sitemapindex (-> sitemap-*.xml) terparse
    via stdlib xml.etree (namespace sitemap standar)."""
    locs = ingest._sitemap_locs(
        '<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        '<url><loc>https://docs.astro.build/en/getting-started/</loc></url>'
        '<url><loc>https://docs.astro.build/en/reference/configuration-reference/</loc></url>'
        "</urlset>")
    assert locs == ["https://docs.astro.build/en/getting-started/",
                    "https://docs.astro.build/en/reference/configuration-reference/"]
    idx = ingest._sitemap_locs(
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        '<sitemap><loc>https://docs.astro.build/sitemap-0.xml</loc></sitemap></sitemapindex>')
    assert idx == ["https://docs.astro.build/sitemap-0.xml"]
    assert ingest._sitemap_locs("not xml") == []


def test_collect_locs_follows_index_and_denies_noise(monkeypatch):
    """R10/L2-4: sitemap-index ditelusuri satu tingkat; halaman bahasa non-EN
    (de/) dan noise (blog/artikel tanggal, feeds) dibuang via _path_allowed."""
    sitemaps = {
        "https://docs.astro.build/sitemap-index.xml":
            '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            '<sitemap><loc>https://docs.astro.build/sitemap-0.xml</loc></sitemap></sitemapindex>',
        "https://docs.astro.build/sitemap-0.xml":
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            '<url><loc>https://docs.astro.build/en/getting-started/</loc></url>'
            '<url><loc>https://docs.astro.build/en/api/</loc></url>'
            '<url><loc>https://docs.astro.build/de/api/</loc></url></urlset>',
    }
    monkeypatch.setattr(ingest, "_fetch_llms", lambda url, timeout=6: sitemaps.get(url))
    locs = ingest._collect_locs(
        sitemaps["https://docs.astro.build/sitemap-index.xml"], None,
        "https://docs.astro.build", deadline=float("inf"))
    assert locs == ["https://docs.astro.build/en/getting-started/",
                    "https://docs.astro.build/en/api/"]
    assert ingest._path_allowed("https://duckdb.org/2021/10/13/windowing.html", "https://duckdb.org/") is False
    assert ingest._path_allowed("https://x.dev/feeds/atom.xml", "https://x.dev/") is False


def test_ingest_lib_llms_union_sitemap_skips_existing(monkeypatch):
    """R10/L1-1: llms + sitemap UNION — halaman llms semua diproses; sitemap
    hanya menambah halaman yg belum ada di llms; existing dihormati; path
    chunk = URL ter-norm (locale en di-strip)."""
    monkeypatch.setattr(ingest, "_fetch_parallel", lambda urls, timeout=4: {
        "llms-full": None,
        "llms": "- [Intro](https://x.dev/en/intro.html)\n- [API](https://x.dev/api/)\n",
        "sitemap-index": None,
        "sitemap": '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                   '<url><loc>https://x.dev/api/</loc></url>'
                   '<url><loc>https://x.dev/extra/</loc></url></urlset>',
    })
    calls = []
    monkeypatch.setattr(ingest, "ingest_docs", lambda url, timeout=20:
                        calls.append(url) or [{"path": url, "title": "T", "text": "b"}])
    out, complete, visited = ingest.ingest_lib(
        "https://x.dev", deadline=float("inf"),
        existing={"https://x.dev/intro"}, query="")
    assert complete is True
    assert [c["path"] for c in out] == ["https://x.dev/api", "https://x.dev/extra"]
    assert calls == ["https://x.dev/api/", "https://x.dev/extra/"]  # intro & dup skip
    assert visited == {"https://x.dev/api", "https://x.dev/extra"}


def test_ingest_lib_deadline_expired_partial(monkeypatch):
    """R10: deadline sudah habis saat probe selesai -> parsial (complete=False)
    tanpa chunk, server lanjut di call berikutnya."""
    monkeypatch.setattr(ingest, "_fetch_parallel", lambda urls, timeout=4: {k: None for k in urls})
    out, complete, visited = ingest.ingest_lib("https://x.dev", deadline=float("-inf"))
    assert out == [] and complete is False and visited == set()
