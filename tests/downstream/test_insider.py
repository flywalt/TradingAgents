"""Insider dealings: announced-by filtering, units, and the router contract."""

from __future__ import annotations

import pandas as pd
import pytest

from tradingagents.dataflows.config import run_config
from tradingagents.dataflows.errors import NoMarketDataError
from tradingagents.dataflows.router import route_to_vendor
from tradingagents_cn.bootstrap import bootstrap, reset
from tradingagents_cn.vendors.tushare import client
from tradingagents_cn.vendors.tushare.insider import get_insider_transactions

pytestmark = pytest.mark.unit

SYMBOL = "600519.SH"


class FakeApi:
    def __init__(self, frame=None):
        self.frame = frame if frame is not None else pd.DataFrame({
            "ts_code": [SYMBOL, SYMBOL],
            "ann_date": ["20260825", "20261029"],     # second is after a 09-30 run
            "holder_name": ["张三", "李四"],
            "holder_type": ["G", "G"],
            "in_de": ["DE", "IN"],
            "change_vol": [12_000.0, 30_000.0],
            "change_ratio": [0.001, 0.0025],
            "after_share": [1_000_000.0, 1_030_000.0],
            "avg_price": [1500.0, 1354.0],
        })
        self.calls = 0

    def stk_holdertrade(self, **kwargs):
        self.calls += 1
        return self.frame


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


def test_only_trades_announced_by_the_run_date_are_shown(offline):
    text = get_insider_transactions(SYMBOL, "2026-09-30")

    assert "张三" in text
    assert "李四" not in text          # announced 2026-10-29


def test_the_header_states_the_units(offline):
    text = get_insider_transactions(SYMBOL, "2026-09-30")

    assert "change_vol/after_share 为股" in text
    assert "avg_price 为元" in text
    assert "change_ratio 为 %" in text


def test_an_empty_feed_is_no_data(offline):
    offline.frame = pd.DataFrame()

    with pytest.raises(NoMarketDataError):
        get_insider_transactions(SYMBOL, "2026-09-30")


def test_a_foreign_symbol_is_declined_before_any_call(offline):
    with pytest.raises(NoMarketDataError):
        get_insider_transactions("AAPL", "2026-09-30")
    assert offline.calls == 0


def test_the_router_serves_tushare_insider_data(offline):
    from tradingagents_cn import config as cn_config

    with run_config(cn_config.apply()):
        text = route_to_vendor("get_insider_transactions", SYMBOL, "2026-09-30")

    assert text.startswith(f"# Insider transactions for {SYMBOL}")
    assert "Vendor: tushare" in text
