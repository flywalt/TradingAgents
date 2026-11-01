"""Snapshot vendor routing: the one upstream patch, and what it must not change.

The tool's name, schema, description and error semantics are the contract the
analysts were written against. The patch only changes *where* the data comes
from, so those stay pinned here.
"""

from __future__ import annotations

import pandas as pd
import pytest

from tradingagents.agents.tools import get_verified_market_snapshot
from tradingagents.dataflows import router
from tradingagents.dataflows.config import run_config
from tradingagents.dataflows.errors import VendorUnavailableError
from tradingagents.dataflows.vendors.yahoo.snapshot import build_verified_market_snapshot
from tradingagents_cn.bootstrap import bootstrap, reset
from tradingagents_cn.vendors.tushare import client

pytestmark = pytest.mark.unit

SYMBOL = "600519.SH"


def bars(count: int = 60) -> pd.DataFrame:
    days = pd.date_range("2026-01-05", periods=count, freq="B")
    closes = list(range(100, 100 + count))
    return pd.DataFrame(
        {
            "ts_code": [SYMBOL] * count,
            "trade_date": [d.strftime("%Y%m%d") for d in days],
            "open": closes, "high": [c + 1 for c in closes],
            "low": [c - 1 for c in closes], "close": closes,
            "vol": [1000.0] * count, "amount": [1000.0] * count,
            "pct_chg": [0.5] * count,
        }
    )


class FakeApi:
    def __init__(self):
        self.calls = 0

    def pro_bar(self, **kwargs):
        self.calls += 1
        return bars()


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_CN_CACHE", "off")
    fake = FakeApi()
    client.set_api(fake)
    bootstrap()
    try:
        yield fake
    finally:
        client.reset_api()
        reset()


def test_upstream_now_routes_the_snapshot_through_a_vendor():
    assert router.VENDOR_METHODS["get_verified_market_snapshot"]["yfinance"] is (
        build_verified_market_snapshot
    )
    assert "get_verified_market_snapshot" in router.TOOLS_CATEGORIES["core_stock_apis"]["tools"]


def test_the_tool_contract_is_unchanged():
    assert get_verified_market_snapshot.name == "get_verified_market_snapshot"
    schema = get_verified_market_snapshot.args_schema.model_json_schema()
    assert set(schema["properties"]) == {"symbol", "curr_date", "look_back_days", "trade_date"}
    assert schema["required"] == ["symbol", "curr_date"]
    assert get_verified_market_snapshot.description.startswith(
        "Deterministic verification snapshot for exact market-data claims."
    )


def test_an_a_share_snapshot_comes_from_tushare(offline):
    with run_config({"data_vendors": {"core_stock_apis": "tushare"}}):
        text = get_verified_market_snapshot.func(SYMBOL, "2026-03-30", 20, "")

    assert text.startswith(f"# Verified market snapshot for {SYMBOL}")
    assert "Vendor: tushare" in text
    assert offline.calls == 1


def test_strict_mode_never_falls_back_to_the_yahoo_snapshot(monkeypatch, offline):
    reached = []
    monkeypatch.setitem(
        router.VENDOR_METHODS["get_verified_market_snapshot"], "yfinance",
        lambda *a, **k: reached.append("yahoo") or "yahoo snapshot",
    )
    monkeypatch.setitem(
        router.VENDOR_METHODS["get_verified_market_snapshot"], "tushare",
        lambda *a, **k: (_ for _ in ()).throw(VendorUnavailableError("throttled")),
    )

    with run_config({"data_vendors": {"core_stock_apis": "tushare"}}):
        text = get_verified_market_snapshot.func(SYMBOL, "2026-03-30", 20, "")

    assert text.startswith("DATA_UNAVAILABLE")
    assert reached == []


def test_a_vendor_failure_keeps_the_tools_sentinel_semantics(monkeypatch, offline):
    monkeypatch.setitem(
        router.VENDOR_METHODS["get_verified_market_snapshot"], "yfinance",
        lambda *a, **k: (_ for _ in ()).throw(VendorUnavailableError("down")),
    )

    with run_config({"data_vendors": {"core_stock_apis": "yfinance"}}):
        text = get_verified_market_snapshot.func(SYMBOL, "2026-03-30", 20, "")

    assert text.startswith("DATA_UNAVAILABLE")
    assert "down" in text
