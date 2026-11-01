"""Company profile, valuation and financial summary for an A-share run.

Two rules matter more than the formatting: valuation is read as of a session at
or before the run date (never after), and the financial summary only shows a
report that had been announced by then.
"""

from __future__ import annotations

import pandas as pd
import pytest

from tradingagents.dataflows.errors import NoMarketDataError, VendorUnavailableError
from tradingagents_cn.vendors.tushare import client
from tradingagents_cn.vendors.tushare.fundamentals import get_fundamentals

pytestmark = pytest.mark.unit

SYMBOL = "600519.SH"


def basic_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ts_code": [SYMBOL],
            "name": ["贵州茅台"],
            "area": ["贵州"],
            "industry": ["白酒"],
            "market": ["主板"],
            "list_date": ["20010827"],
        }
    )


def valuation_frame() -> pd.DataFrame:
    """Two sessions: the run date and the one before it."""
    return pd.DataFrame(
        {
            "ts_code": [SYMBOL, SYMBOL],
            "trade_date": ["20260929", "20260930"],
            "pe_ttm": [30.0, 31.5],
            "pb": [8.0, 8.2],
            "ps_ttm": [9.0, 9.1],
            # Tushare serves market cap in 万元; 21,000,000 万元 = 2100 亿元.
            "total_mv": [20_000_000.0, 21_000_000.0],
            "circ_mv": [18_000_000.0, 19_000_000.0],
            "turnover_rate": [0.30, 0.35],
            "volume_ratio": [0.90, 1.10],
        }
    )


def indicator_frame() -> pd.DataFrame:
    """A filed report and a later one that must stay invisible on 2026-09-30."""
    return pd.DataFrame(
        {
            "ts_code": [SYMBOL, SYMBOL],
            "ann_date": ["20260825", "20261028"],
            "end_date": ["20260630", "20260930"],
            "eps": [20.5, 99.0],
            "roe": [30.1, 55.0],
            "grossprofit_margin": [91.5, 92.0],
            "netprofit_margin": [52.0, 53.0],
            "debt_to_assets": [18.0, 17.0],
        }
    )


class FakeApi:
    def __init__(self, basic=None, valuation=None, indicators=None):
        self.basic = basic if basic is not None else basic_frame()
        self.valuation = valuation if valuation is not None else valuation_frame()
        self.indicators = indicators if indicators is not None else indicator_frame()
        self.calls: list[tuple[str, dict]] = []

    def stock_basic(self, **kwargs):
        self.calls.append(("stock_basic", kwargs))
        return self.basic

    def daily_basic(self, **kwargs):
        self.calls.append(("daily_basic", kwargs))
        return self.valuation

    def fina_indicator(self, **kwargs):
        self.calls.append(("fina_indicator", kwargs))
        return self.indicators


@pytest.fixture(autouse=True)
def no_cache(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_CN_CACHE", "off")


@pytest.fixture
def api():
    fake = FakeApi()
    client.set_api(fake)
    try:
        yield fake
    finally:
        client.reset_api()


def test_profile_names_the_company_its_industry_and_listing(api):
    text = get_fundamentals(SYMBOL, "2026-09-30")

    assert "贵州茅台" in text
    assert "白酒" in text
    assert "贵州" in text
    assert "2001-08-27" in text


def test_valuation_comes_from_the_run_date_session(api):
    text = get_fundamentals(SYMBOL, "2026-09-30")

    assert "31.50" in text          # pe_ttm on 09-30
    assert "30.00" not in text      # pe_ttm of 09-29 must not be served


def test_market_cap_is_converted_from_wan_yuan_to_yi_yuan(api):
    text = get_fundamentals(SYMBOL, "2026-09-30")

    assert "2100.00" in text        # 21,000,000 万元
    assert "1900.00" in text        # circ_mv


def test_a_report_announced_after_the_run_date_is_invisible(api):
    text = get_fundamentals(SYMBOL, "2026-09-30")

    assert "20.50" in text          # eps of the June report
    assert "99.00" not in text      # eps of the September report, announced 10-28
    assert "2026-10-28" not in text


def test_missing_valuation_fields_render_empty_not_zero():
    frame = valuation_frame()
    frame.loc[1, "pe_ttm"] = float("nan")
    client.set_api(FakeApi(valuation=frame))
    try:
        text = get_fundamentals(SYMBOL, "2026-09-30")
    finally:
        client.reset_api()

    assert "PE (TTM):\n" in text or "PE (TTM): " in text
    assert "PE (TTM): 0.00" not in text


def test_an_unknown_symbol_is_no_data(api):
    api.basic = pd.DataFrame()
    with pytest.raises(NoMarketDataError, match="600519.SH"):
        get_fundamentals(SYMBOL, "2026-09-30")


def test_a_foreign_symbol_is_declined_before_any_call(api):
    with pytest.raises(NoMarketDataError):
        get_fundamentals("AAPL", "2026-09-30")
    assert api.calls == []


def test_a_vendor_exception_degrades_to_unavailable():
    class Broken(FakeApi):
        def stock_basic(self, **kwargs):
            raise RuntimeError("quota exceeded")

    client.set_api(Broken())
    try:
        with pytest.raises(VendorUnavailableError, match="quota"):
            get_fundamentals(SYMBOL, "2026-09-30")
    finally:
        client.reset_api()
