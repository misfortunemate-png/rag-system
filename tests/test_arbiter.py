"""Unit tests for the arbiter module."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.extract.arbiter import _garble_rate, _fragment_rate, select_best, arbitrate_pages


def test_garble_rate_clean():
    assert _garble_rate("正常なテキスト") < 0.01


def test_garble_rate_garbled():
    assert _garble_rate("abc�def") > 0.1


def test_fragment_rate_clean():
    text = "第1節 機材\nこの節は電気設備工事に適用する。\n配線器具は所定の規格を満たすこと。"
    assert _fragment_rate(text) < 0.5


def test_select_best_picks_cleaner():
    good = {"page": 1, "text": "正常なテキスト。電気設備工事標準仕様書。", "tables": ""}
    bad = {"page": 1, "text": "abc����def", "tables": ""}
    winner, _ = select_best({"plumber": good, "pymupdf": bad})
    assert winner == "plumber"


def test_arbitrate_pages_adds_source_engine():
    pages = [{"page": 1, "text": "正常テキスト", "tables": ""}]
    result = arbitrate_pages({"plumber": pages, "pymupdf": pages})
    assert len(result) == 1
    assert "source_engine" in result[0]
