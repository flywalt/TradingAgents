"""Symbol normalization: the one spelling every adapter and test agrees on."""

from __future__ import annotations

import pytest

from tradingagents_cn.symbols import (
    code_of,
    from_yahoo,
    is_ashare,
    market_for_code,
    market_of,
    normalize,
    to_tushare,
    to_yahoo,
    try_normalize,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("600519", "600519.SH"),
        ("600519.SH", "600519.SH"),
        ("600519.SS", "600519.SH"),          # Yahoo's spelling of Shanghai
        ("600519.XSHG", "600519.SH"),        # RQData-style suffix
        ("sh600519", "600519.SH"),
        ("SH.600519", "600519.SH"),
        ("  600519.sh  ", "600519.SH"),
        ("000001", "000001.SZ"),
        ("000001.SZ", "000001.SZ"),
        ("sz.000001", "000001.SZ"),
        ("300750", "300750.SZ"),             # 创业板
        ("688981", "688981.SH"),             # 科创板
        ("689009", "689009.SH"),
        ("430047", "430047.BJ"),             # 北交所
        ("920001", "920001.BJ"),
        ("510300", "510300.SH"),             # ETF follows its exchange prefix
        ("159915", "159915.SZ"),
    ],
)
def test_accepted_spellings_normalize_to_code_dot_market(raw, expected):
    assert normalize(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "AAPL",
        "600519.HK",
        "600519.SZ",      # suffix contradicts the code's own exchange
        "000001.SS",      # same conflict in the other direction
        "12345",
        "60051X",
        "",
        "   ",
        "BTCUSD",
        "not-a-symbol",
    ],
)
def test_foreign_or_contradictory_symbols_are_rejected(raw):
    with pytest.raises(ValueError):
        normalize(raw)
    assert try_normalize(raw) is None
    assert is_ashare(raw) is False


def test_non_string_input_is_rejected():
    with pytest.raises(ValueError):
        normalize(None)


def test_market_for_code_knows_the_three_exchanges():
    assert market_for_code("600519") == "SH"
    assert market_for_code("000001") == "SZ"
    assert market_for_code("430047") == "BJ"
    assert market_for_code("999999") is None
    assert market_for_code("60051") is None


def test_accessors_return_the_parts_we_route_on():
    assert code_of("600519.SS") == "600519"
    assert market_of("600519.SS") == "SH"
    assert to_tushare("600519.SS") == "600519.SH"


def test_yahoo_mapping_covers_shanghai_and_shenzhen_only():
    assert to_yahoo("600519.SH") == "600519.SS"
    assert to_yahoo("000001.SZ") == "000001.SZ"
    with pytest.raises(ValueError, match="Beijing"):
        to_yahoo("430047.BJ")


def test_yahoo_tickers_come_back_to_the_canonical_form():
    assert from_yahoo("600519.SS") == "600519.SH"
    assert from_yahoo("000001.SZ") == "000001.SZ"
    with pytest.raises(ValueError):
        from_yahoo("AAPL")
