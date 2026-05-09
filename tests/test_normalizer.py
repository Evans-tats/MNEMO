"""Tests for src/ingest/normalizer.py"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.ingest.normalizer import (
    NormalizedDoc,
    _clean_whitespace,
    _heading_title,
    _strip_frontmatter,
    normalise,
)

# ── _strip_frontmatter ────────────────────────────────────────────────────────

def test_strip_frontmatter_basic():
    text = "---\ntitle: Hello\nauthor: Alice\n---\n\n# Body\nContent."
    body, fm = _strip_frontmatter(text)
    assert fm["title"] == "Hello"
    assert fm["author"] == "Alice"
    assert body.startswith("# Body")


def test_strip_frontmatter_no_frontmatter():
    text = "# Just a heading\nSome content."
    body, fm = _strip_frontmatter(text)
    assert body == text
    assert fm == {}


def test_strip_frontmatter_empty_values():
    text = '---\ntitle: ""\n---\n\nBody.'
    body, fm = _strip_frontmatter(text)
    assert fm["title"] == ""


# ── _heading_title ────────────────────────────────────────────────────────────

def test_heading_title_found():
    assert _heading_title("# My Article\nContent") == "My Article"


def test_heading_title_not_found():
    assert _heading_title("No heading here") == ""


def test_heading_title_skips_h2():
    assert _heading_title("## Sub heading\nContent") == ""


# ── _clean_whitespace ─────────────────────────────────────────────────────────

def test_clean_whitespace_collapses_blank_lines():
    text = "a\n\n\n\n\nb"
    result = _clean_whitespace(text)
    # 4+ blank lines collapse to max 2 blank lines (= "\n\n\n" between content)
    assert "\n\n\n\n" not in result
    assert "a" in result
    assert "b" in result


def test_clean_whitespace_strips_trailing():
    text = "line one   \nline two  "
    result = _clean_whitespace(text)
    for line in result.splitlines():
        assert line == line.rstrip()


# ── normalise: markdown ───────────────────────────────────────────────────────

def test_normalise_markdown_basic(tmp_path: Path):
    f = tmp_path / "articles" / "test.md"
    f.parent.mkdir()
    f.write_text("# My Article\n\nSome content here.", encoding="utf-8")

    doc = normalise(f)
    assert doc is not None
    assert doc.title == "My Article"
    assert "Some content" in doc.content
    assert doc.source_path == f


def test_normalise_markdown_with_frontmatter(tmp_path: Path):
    f = tmp_path / "articles" / "fm.md"
    f.parent.mkdir()
    f.write_text('---\ntitle: FM Title\ntags: ai\n---\n\n# Ignored\nBody.', encoding="utf-8")

    doc = normalise(f)
    assert doc is not None
    assert doc.title == "FM Title"
    assert doc.metadata["tags"] == "ai"


def test_normalise_markdown_image_collection(tmp_path: Path):
    img = tmp_path / "articles" / "fig.png"
    img.parent.mkdir(exist_ok=True)
    img.write_bytes(b"\x89PNG\r\n\x1a\n")  # minimal PNG header

    f = tmp_path / "articles" / "with-img.md"
    f.write_text(f"# Article\n\n![figure](fig.png)\n\nContent.", encoding="utf-8")

    doc = normalise(f)
    assert doc is not None
    assert len(doc.images) == 1
    assert doc.images[0][0] == img.resolve()


# ── normalise: plain text ─────────────────────────────────────────────────────

def test_normalise_text_plain(tmp_path: Path):
    f = tmp_path / "notes.txt"
    f.write_text("Just some notes.\nLine two.", encoding="utf-8")

    doc = normalise(f)
    assert doc is not None
    assert "Just some notes" in doc.content


def test_normalise_text_python_file(tmp_path: Path):
    f = tmp_path / "script.py"
    f.write_text("def hello():\n    print('hi')\n", encoding="utf-8")

    doc = normalise(f)
    assert doc is not None
    assert "```python" in doc.content
    assert "def hello" in doc.content


# ── normalise: images (returns None) ─────────────────────────────────────────

def test_normalise_image_returns_none(tmp_path: Path):
    img_dir = tmp_path / "images"
    img_dir.mkdir()
    f = img_dir / "photo.png"
    f.write_bytes(b"\x89PNG")

    result = normalise(f)
    assert result is None


# ── normalise: CSV data ───────────────────────────────────────────────────────

def test_normalise_csv(tmp_path: Path):
    f = tmp_path / "datasets" / "data.csv"
    f.parent.mkdir()
    f.write_text("name,age,city\nAlice,30,NYC\nBob,25,LA\n", encoding="utf-8")

    doc = normalise(f)
    assert doc is not None
    assert "name" in doc.content
    assert "Alice" in doc.content
    assert "Schema" in doc.content


def test_normalise_csv_empty(tmp_path: Path):
    f = tmp_path / "datasets" / "empty.csv"
    f.parent.mkdir()
    f.write_text("", encoding="utf-8")

    doc = normalise(f)
    assert doc is not None  # should not crash


# ── normalise: JSON ───────────────────────────────────────────────────────────

# def test_normalise_json(tmp_path: Path):
#     f = tmp_path / "datasets" / "config.json"
#     f.parent.mkdir()
#     f.write_text('{"key": "value", "num": 42}', encoding="utf-8")

#     doc = normalise(f)
#     assert doc is not None
#     assert "key" in doc.content
#     assert "```json" in doc.content


# def test_normalise_invalid_json(tmp_path: Path):
#     f = tmp_path / "datasets" / "bad.json"
#     f.parent.mkdir()
#     f.write_text("{not valid json!!", encoding="utf-8")

#     doc = normalise(f)
#     assert doc is not None  # should not raise


# # ── NormalizedDoc dataclass ───────────────────────────────────────────────────

# def test_normalized_doc_defaults(tmp_path: Path):
#     f = tmp_path / "test.md"
#     f.write_text("# X", encoding="utf-8")
#     doc = NormalizedDoc(content="hello", title="Hi", source_path=f)
#     assert doc.images == []
#     assert doc.metadata == {}


# # ── _url_to_slug (imported from web_fetch) ────────────────────────────────────

# def test_url_to_slug_basic():
#     from tools.web_fetch import _url_to_slug
#     slug = _url_to_slug("https://example.com/blog/my-article")
#     assert "example" in slug
#     assert " " not in slug
#     assert slug == slug.lower()


# def test_url_to_slug_strips_www():
#     from tools.web_fetch import _url_to_slug
#     slug = _url_to_slug("https://www.example.com/path")
#     assert "www" not in slug


# def test_url_to_slug_max_length():
#     from tools.web_fetch import _url_to_slug
#     long_url = "https://example.com/" + "a" * 200
#     slug = _url_to_slug(long_url)
#     assert len(slug) <= 80
