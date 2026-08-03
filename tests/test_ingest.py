"""test_ingest — chunk_text (heading + hard-split), filter domain/bahasa,
deteksi 404-palsu, full flag.

API diverifikasi dari src/memo/ingest.py:
- chunk_text(text, max_tokens=256, overlap=50) ingest.py:69 (SAB-2: cap 4x
  max_tokens utk hard-split via _split_oversize)
- _path_allowed(url, base_url) ingest.py:18 (SAB-4: netloc sama + tanpa
  segmen bahasa non-EN)
- _looks_404(text) ingest.py:284
- is_full(complete, n_chunks, min_chunks=3) ingest.py:28
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


def test_chunk_text_respects_cap():
    text = "\n\n".join(f"Para {i} " + "B." * 400 for i in range(20))
    chunks = ingest.chunk_text(text)
    assert len(chunks) >= 2
    assert all(len(c) <= 256 * 4 for c in chunks)


def test_chunk_text_hard_split_oversize_paragraph():
    """SAB-2: paragraf raksasa di-hard-split, max piece <= 4x max_tokens."""
    chunks = ingest.chunk_text("A." * 100_000)
    assert all(len(c) <= 256 * 4 for c in chunks)
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
