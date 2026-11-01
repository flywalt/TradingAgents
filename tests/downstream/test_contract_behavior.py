"""Superset A of the sync guard: the behaviour those symbols are supposed to deliver.

Symbols can survive while their meaning changes. These tests exercise the
end-to-end contracts directly — a routed A-share call, a point-in-time
exclusion, an identity refusal — so a silent semantic change fails here even
when every name still exists.
"""

from __future__ import annotations

import pandas as pd
import pytest

from tradingagents.dataflows.config import run_config
from tradingagents.dataflows.router import route_to_vendor
from tradingagents_cn.bootstrap import bootstrap, reset
from tradingagents_cn.identity import resolve_identity_at
from tradingagents_cn.pit import announced_by
from tradingagents_cn.vendors.tushare import client

pytestmark = pytest.mark.unit

A_SHARE_METHODS = (
    "get_stock_data",
    "get_indicators",
    "get_verified_market_snapshot",
    "get_fundamentals",
    "get_balance_sheet",
    "get_cashflow",
    "get_income_statement",
)


def bars(count: int = 60) -> pd.DataFrame:
    days = pd.date_range("2026-01-05", periods=count, freq="B")
    closes = list(range(100, 100 + count))
    return pd.DataFrame(
        {
            "ts_code": ["600519.SH"] * count,
            "trade_date": [d.strftime("%Y%m%d") for d in days],
            "open": closes, "high": [c + 1 for c in closes],
            "low": [c - 1 for c in closes], "close": closes,
            "vol": [1000.0] * count, "amount": [1000.0] * count,
            "pct_chg": [0.5] * count,
        }
    )


class FakeApi:
    def pro_bar(self, **kwargs):
        return bars()

    def stock_basic(self, **kwargs):
        return pd.DataFrame([{
            "ts_code": "600519.SH", "name": "贵州茅台", "area": "贵州",
            "industry": "白酒", "market": "主板", "list_date": "20010827",
            "delist_date": "", "list_status": "L",
        }])


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_CN_CACHE", "off")
    client.set_api(FakeApi())
    try:
        yield
    finally:
        client.reset_api()
        reset()


def test_every_a_share_data_method_is_registered_to_tushare():
    report = bootstrap()

    for method in A_SHARE_METHODS:
        assert "tushare" in report.vendors_by_method.get(method, []), method


def test_a_routed_a_share_price_call_serves_tushare_bars():
    bootstrap()
    with run_config({"data_vendors": {"core_stock_apis": "tushare"}}):
        text = route_to_vendor("get_stock_data", "600519.SH", "2026-01-05", "2026-03-30")

    assert text.startswith("# Stock data for 600519.SH")
    assert "Vendor: tushare" in text


def test_a_report_announced_after_the_run_date_stays_invisible():
    frame = pd.DataFrame({
        "end_date": ["20260630", "20260930"],
        "ann_date": ["20260825", "20261028"],
        "report_type": ["1", "1"],
    })

    visible = announced_by(frame, "20260930")

    assert list(visible["end_date"]) == ["20260630"]


def test_identity_refuses_dates_before_listing_and_serves_dates_after():
    assert resolve_identity_at("600519.SH", "2000-01-01") == {}

    identity = resolve_identity_at("600519.SH", "2026-10-30")
    assert identity["name"] == "贵州茅台"
    assert identity["exchange"] == "SSE"
