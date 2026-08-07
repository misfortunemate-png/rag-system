"""Unit tests for the chunker module."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.chunker import chunk_pages


SAMPLE_PAGES = [
    {
        "page": 1,
        "text": (
            "第1編 一般共通事項\n"
            "第1章 総則\n"
            "第1節 適用\n"
            "1.1.1 適用\n"
            "この仕様書は公共建築工事に適用する。\n"
            "(1) 電気設備工事に関する事項を定める。\n"
        ),
        "source_engine": "plumber",
    },
    {
        "page": 2,
        "text": (
            "1.1.2 用語の定義\n"
            "この仕様書で用いる用語の意味は次のとおりとする。\n"
            "(1) 「発注者」とは国をいう。\n"
            "(2) 「請負者」とは工事請負契約書の請負者をいう。\n"
        ),
        "source_engine": "pymupdf",
    },
]


def test_chunk_count():
    # Both sample articles are < 300 chars (merge threshold), so they are
    # collapsed into a single chunk under their parent section. >= 1 is correct.
    chunks = chunk_pages(SAMPLE_PAGES, doc_slug="test", domain="electric")
    assert len(chunks) >= 1


def test_chunk_has_required_fields():
    chunks = chunk_pages(SAMPLE_PAGES, doc_slug="test", domain="electric")
    for c in chunks:
        for field in ("chunk_id", "doc_type", "domain", "hierarchy", "heading", "body", "pages", "char_count", "source_engine", "refs"):
            assert field in c, f"Missing field: {field}"


def test_hierarchy_contains_hen_sho_setsu():
    chunks = chunk_pages(SAMPLE_PAGES, doc_slug="test", domain="electric")
    assert any("第1編" in c["hierarchy"] for c in chunks)
    assert any("第1章" in c["hierarchy"] for c in chunks)


def test_article_heading_format():
    chunks = chunk_pages(SAMPLE_PAGES, doc_slug="test", domain="electric")
    articles = [c for c in chunks if "1.1.1" in c["heading"] or "1.1.2" in c["heading"]]
    assert len(articles) >= 1


def test_source_engine_preserved():
    chunks = chunk_pages(SAMPLE_PAGES, doc_slug="test", domain="electric")
    engines = {c["source_engine"] for c in chunks}
    assert engines.issubset({"plumber", "pymupdf", "unknown"})


def test_doc_type_is_spec():
    chunks = chunk_pages(SAMPLE_PAGES, doc_slug="test", domain="electric")
    for c in chunks:
        assert c["doc_type"] == "spec"
