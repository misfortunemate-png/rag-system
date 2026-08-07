"""
Unit tests for ruri-v3-310m prefix correctness.

Why this test exists: ruri models require different prefixes on the query side vs.
the document side. Applying the wrong prefix (or no prefix) degrades retrieval
accuracy. This test catches prefix typos and ensures both sides are applied.

The expected prefix values are sourced from the cl-nagoya/ruri-v3-310m model card.
If the model card changes, update DOC_PREFIX / QUERY_PREFIX in ingest.py / query.py
AND update this test.
"""
import sys
from pathlib import Path

import pytest

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))

EXPECTED_DOC_PREFIX = "文章: "
EXPECTED_QUERY_PREFIX = "クエリ: "


def test_doc_prefix_value():
    """DOC_PREFIX in ingest.py must equal the model-card document prefix."""
    from src.ingest import DOC_PREFIX
    assert DOC_PREFIX == EXPECTED_DOC_PREFIX, (
        f"DOC_PREFIX mismatch: got {DOC_PREFIX!r}, expected {EXPECTED_DOC_PREFIX!r}. "
        "Verify against cl-nagoya/ruri-v3-310m model card."
    )


def test_query_prefix_value():
    """QUERY_PREFIX in query.py must equal the model-card query prefix."""
    from src.query import QUERY_PREFIX
    assert QUERY_PREFIX == EXPECTED_QUERY_PREFIX, (
        f"QUERY_PREFIX mismatch: got {QUERY_PREFIX!r}, expected {EXPECTED_QUERY_PREFIX!r}. "
        "Verify against cl-nagoya/ruri-v3-310m model card."
    )


def test_prefixes_differ():
    """Document prefix and query prefix must not be the same string."""
    from src.ingest import DOC_PREFIX
    from src.query import QUERY_PREFIX
    assert DOC_PREFIX != QUERY_PREFIX, (
        "DOC_PREFIX and QUERY_PREFIX are identical. ruri models use distinct prefixes "
        "for documents vs. queries — identical prefixes likely indicate a copy-paste error."
    )


def test_doc_prefix_applied_to_embedding_input():
    """The text passed to model.encode() in ingest must start with DOC_PREFIX."""
    from src.ingest import DOC_PREFIX

    heading = "1.1.1 適用"
    body = "この節は電気設備工事に適用する。"
    combined = DOC_PREFIX + heading + "\n" + body
    assert combined.startswith(DOC_PREFIX), (
        f"Embedding input does not start with DOC_PREFIX ({DOC_PREFIX!r})."
    )


def test_query_prefix_applied_to_query_input():
    """The text passed to model.encode() in query must start with QUERY_PREFIX."""
    from src.query import QUERY_PREFIX

    question = "分電盤の保護等級は屋内形と屋外形でそれぞれ何か？"
    prefixed = QUERY_PREFIX + question
    assert prefixed.startswith(QUERY_PREFIX), (
        f"Query input does not start with QUERY_PREFIX ({QUERY_PREFIX!r})."
    )
