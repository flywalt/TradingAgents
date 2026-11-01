"""China macro series: aliases, units, point-in-time window and routing."""

from __future__ import annotations

import pandas as pd
import pytest

from tradingagents.dataflows.config import run_config
from tradingagents.dataflows.errors import NoMarketDataError
from tradingagents.dataflows.router import route_to_vendor
from tradingagents_cn import config as cn_config
from tradingagents_cn.bootstrap import bootstrap, reset
from tradingagents_cn.market import CN_A_SHARE, UPSTREAM_DEFAULT
from tradingagents_cn.vendors.tushare import client
from tradingagents_cn.vendors.tushare.macro import get_macro_indicators

pytestmark = pytest.mark.unit


class FakeApi:
    def __init__(self):
        self.calls = 0

    def cn_cpi(self, **kwargs):
        self.calls += 1
        return pd.DataFrame({
            "month": ["202605", "202606", "202607", "202610"],   # last is after the run
            "nt_yoy": [0.3, 0.5, 0.7, 9.9],
        })

    def shibor(self, **kwargs):
        self.calls += 1
        return pd.DataFrame({
            "date": ["20260929", "20260930", "20261008"],
            "3m": [1.61, 1.62, 1.70],
        })


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


def test_cpi_is_rendered_with_its_unit_and_latest_value(offline):
    text = get_macro_indicators("cpi", "2026-09-30")

    assert "CPI 同比" in text
    assert "单位: %" in text
    assert "最新 (202607): 0.70 %" in text


def test_observations_after_the_run_date_are_excluded(offline):
    text = get_macro_indicators("cpi", "2026-09-30")

    assert "9.90" not in text
    assert "202610" not in text


def test_a_daily_series_uses_its_own_columns(offline):
    text = get_macro_indicators("shibor", "2026-09-30")

    assert "SHIBOR 3M" in text
    assert "1.62" in text
    assert "20261008" not in text


def test_an_unavailable_series_is_refused_not_substituted(offline):
    with pytest.raises(ValueError, match="LPR"):
        get_macro_indicators("lpr", "2026-09-30")

    with pytest.raises(ValueError, match="yield_curve"):
        get_macro_indicators("yield_curve", "2026-09-30")


def test_an_unknown_alias_lists_what_is_supported(offline):
    with pytest.raises(ValueError, match="cpi"):
        get_macro_indicators("m3", "2026-09-30")


def test_an_empty_answer_is_no_data(offline):
    offline.cn_cpi = lambda **kwargs: pd.DataFrame()

    with pytest.raises(NoMarketDataError):
        get_macro_indicators("cpi", "2026-09-30")


def test_the_cn_profile_routes_macro_to_tushare(offline):
    settings = cn_config.apply(profile=CN_A_SHARE)
    assert settings["data_vendors"]["macro_data"] == "tushare,fred"

    with run_config(settings):
        text = route_to_vendor("get_macro_indicators", "cpi", "2026-09-30", None)

    assert text.startswith("# 宏观指标")


def test_the_default_profile_keeps_the_upstream_macro_chain():
    merged = cn_config.apply(profile=UPSTREAM_DEFAULT)

    assert merged["data_vendors"]["macro_data"] == "fred"
