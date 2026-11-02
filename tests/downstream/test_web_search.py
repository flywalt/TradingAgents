"""Fuzzy instrument search for the run form: code or name, kviewer-style."""

from __future__ import annotations

import pytest

from tradingagents_web import search

pytestmark = pytest.mark.unit

TABLE = [
    {"ts_code": "600519.SH", "name": "贵州茅台"},
    {"ts_code": "000858.SZ", "name": "五粮液"},
    {"ts_code": "600809.SH", "name": "山西汾酒"},
    {"ts_code": "300750.SZ", "name": "宁德时代"},
    {"ts_code": "688041.SH", "name": "海光信息"},
    {"ts_code": "AAPL", "name": "Apple"},  # never matched: not an A-share row shape
]


@pytest.fixture(autouse=True)
def table(monkeypatch):
    monkeypatch.setattr(search, "_listed_table", lambda: TABLE)


def test_a_code_fragment_finds_its_stocks():
    assert search.suggest("6005") == [
        {"symbol": "600519.SH", "name": "贵州茅台"}]


def test_a_name_fragment_finds_its_stocks():
    results = search.suggest("茅台")
    assert results == [{"symbol": "600519.SH", "name": "贵州茅台"}]


def test_a_prefix_ranks_before_a_contains():
    table = [{"ts_code": "600519.SH", "name": "贵州茅台"},
             {"ts_code": "1600519.XSHG", "name": "无关"}]
    import tradingagents_web.search as s
    original = s._listed_table
    s._listed_table = lambda: table
    try:
        results = s.suggest("6005")
    finally:
        s._listed_table = original
    assert results[0]["symbol"] == "600519.SH"


def test_matches_are_limited_and_blank_is_empty():
    assert search.suggest("") == []
    assert len(search.suggest("6")) <= 8


def test_a_broken_source_answers_nothing():
    import tradingagents_web.search as s
    original = s._listed_table
    s._listed_table = lambda: (_ for _ in ()).throw(RuntimeError("tushare down"))
    try:
        assert s.suggest("6005") == []
    finally:
        s._listed_table = original


def test_the_whole_code_wins_over_longer_prefixes():
    table = [{"ts_code": "600598.SH", "name": "北大荒"},
             {"ts_code": "600519.SH", "name": "贵州茅台"}]
    import tradingagents_web.search as s
    original = s._listed_table
    s._listed_table = lambda: table
    try:
        assert s.suggest("600519")[0]["symbol"] == "600519.SH"
    finally:
        s._listed_table = original
