"""Indicators computed locally from Tushare bars.

The point of computing here instead of letting Yahoo serve them is that the
market analyst then reads one price basis: the same qfq bars the price tool
serves. The tests pin the two things that would silently break that: the numbers
(a hand-checked SMA, an all-gains RSI) and the "not enough history" case, where
stockstats would happily return a partial-window mean that looks like a signal.
"""

from __future__ import annotations

import pandas as pd
import pytest

from tradingagents.dataflows.errors import NoMarketDataError
from tradingagents_cn.vendors.tushare import client
from tradingagents_cn.vendors.tushare.indicators import (
    SUPPORTED_INDICATORS,
    get_stock_stats_indicators_window,
)

pytestmark = pytest.mark.unit

SYMBOL = "600519.SH"


def bars_frame(count: int, *, start_price: int = 1) -> pd.DataFrame:
    """``count`` sessions of a strictly rising close series."""
    days = pd.date_range("2026-01-05", periods=count, freq="B")
    closes = list(range(start_price, start_price + count))
    return pd.DataFrame(
        {
            "ts_code": [SYMBOL] * count,
            "trade_date": [d.strftime("%Y%m%d") for d in days],
            "open": closes,
            "high": [c + 1 for c in closes],
            "low": [c - 1 for c in closes],
            "close": closes,
            "vol": [1000.0] * count,
            "amount": [1000.0] * count,
            "pct_chg": [0.0] * count,
        }
    )


class FakeApi:
    def __init__(self, frame):
        self.frame = frame
        self.calls: list[dict] = []

    def pro_bar(self, **kwargs):
        self.calls.append(kwargs)
        return self.frame


@pytest.fixture(autouse=True)
def no_cache(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_CN_CACHE", "off")


@pytest.fixture
def api():
    fake = FakeApi(bars_frame(60))
    client.set_api(fake)
    try:
        yield fake
    finally:
        client.reset_api()


@pytest.fixture
def short_api():
    fake = FakeApi(bars_frame(20))
    client.set_api(fake)
    try:
        yield fake
    finally:
        client.reset_api()


def _rows(text: str) -> list[list[str]]:
    return [line.split(",") for line in text.splitlines() if line and not line.startswith("#")]


def test_close_50_sma_is_the_mean_of_the_last_fifty_closes(api):
    text = get_stock_stats_indicators_window(SYMBOL, "close_50_sma", "2026-03-30", 3)

    rows = _rows(text)
    assert rows[0] == ["Date", "close_50_sma"]
    assert len(rows) - 1 == 3
    assert rows[-1][1] == "35.50"        # mean(11..60)


def test_an_all_gains_series_reports_rsi_at_100(api):
    rows = _rows(get_stock_stats_indicators_window(SYMBOL, "rsi", "2026-03-30", 2))

    assert rows[-1][1] == "100.00"


def test_all_thirteen_upstream_names_are_supported():
    assert len(SUPPORTED_INDICATORS) == 13
    for name in ("close_50_sma", "close_200_sma", "close_10_ema", "macd", "macds", "macdh",
                 "rsi", "boll", "boll_ub", "boll_lb", "atr", "vwma", "mfi"):
        assert name in SUPPORTED_INDICATORS


def test_an_unknown_indicator_lists_what_is_supported(api):
    with pytest.raises(ValueError, match="close_50_sma"):
        get_stock_stats_indicators_window(SYMBOL, "rsi_14", "2026-03-30", 3)


def test_a_short_history_renders_empty_cells_not_a_partial_window(short_api):
    rows = _rows(get_stock_stats_indicators_window(SYMBOL, "close_200_sma", "2026-02-02", 5))

    assert [row[1] for row in rows[1:]] == [""] * 5


def test_a_foreign_symbol_is_declined_before_any_call(api):
    with pytest.raises(NoMarketDataError):
        get_stock_stats_indicators_window("AAPL", "rsi", "2026-03-30", 3)
    assert api.calls == []


def test_the_header_states_vendor_adjustment_and_window(api):
    text = get_stock_stats_indicators_window(SYMBOL, "rsi", "2026-03-30", 5)

    head = text.splitlines()[:2]
    assert head[0].startswith(f"# Indicators for {SYMBOL} as of 2026-03-30")
    assert "last 5 sessions" in head[0]
    assert "Vendor: tushare" in head[1]
    assert "adjustment: qfq" in head[1]
    assert "tdx" in head[1]          # default flavour: 通达信口径
