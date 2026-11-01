"""Tushare adapter: offline, with a fake API standing in for the SDK.

Nothing here needs ``tushare`` installed, a token, or the network. What is pinned:
the router contract (positional signature, typed errors), the unit conversions
(手 -> 股, 千元 -> 元), the adjustment actually reaching the vendor, and the
calendar really replacing the weekend-only default.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from tradingagents.dataflows import router
from tradingagents.dataflows.config import run_config
from tradingagents.dataflows.errors import (
    NoMarketDataError,
    VendorNotConfiguredError,
    VendorUnavailableError,
)
from tradingagents_cn import calendar as cn_calendar, register as cn_register
from tradingagents_cn.vendors.tushare import calendar as ts_calendar, client
from tradingagents_cn.vendors.tushare.stock import get_stock_data

pytestmark = pytest.mark.unit

SYMBOL = "600519.SH"


def bars_frame() -> pd.DataFrame:
    """Three out-of-order sessions, so ordering and units are both covered."""
    return pd.DataFrame(
        {
            "ts_code": [SYMBOL, SYMBOL, SYMBOL],
            "trade_date": ["20260107", "20260105", "20260106"],
            "open": [1700.0, 1680.5, 1690.0],
            "high": [1710.0, 1690.0, 1700.0],
            "low": [1690.0, 1675.0, 1685.0],
            "close": [1705.0, 1685.0, 1695.0],
            "pre_close": [1700.0, 1680.0, 1690.0],
            "vol": [300.0, 100.0, 200.0],          # 手
            "amount": [5115.0, 1685.0, 3390.0],    # 千元
            "pct_chg": [0.29, 0.30, 0.30],
        }
    )


def calendar_frame() -> pd.DataFrame:
    """2026-09-28..10-10 with the 国庆 closure (10-01..10-07) included."""
    days = pd.date_range("2026-09-28", "2026-10-10", freq="D")
    closed = {date(2026, 10, d) for d in range(1, 8)}
    return pd.DataFrame(
        {
            "exchange": "SSE",
            "cal_date": [d.strftime("%Y%m%d") for d in days],
            "is_open": ["0" if d.date() in closed or d.weekday() >= 5 else "1" for d in days],
        }
    )


class FakeApi:
    def __init__(self, frame=None, cal=None, error=None):
        self.frame = frame
        self.cal = cal
        self.error = error
        self.calls: list[tuple[str, dict]] = []

    def pro_bar(self, **kwargs):
        self.calls.append(("pro_bar", kwargs))
        if self.error is not None:
            raise self.error
        return self.frame

    def trade_cal(self, **kwargs):
        self.calls.append(("trade_cal", kwargs))
        if self.error is not None:
            raise self.error
        return self.cal


@pytest.fixture
def fake_api():
    api = FakeApi(bars_frame(), calendar_frame())
    client.set_api(api)
    try:
        yield api
    finally:
        client.reset_api()


def test_bars_carry_their_units_ordering_and_price_basis(fake_api):
    text = get_stock_data(SYMBOL, "2026-01-05", "2026-01-09")

    lines = text.splitlines()
    assert lines[0] == f"# Stock data for {SYMBOL} from 2026-01-05 to 2026-01-09"
    assert "adjustment: qfq" in lines[1]
    assert "volume in shares; amount in CNY" in lines[1]
    assert "qfq anchored at 2026-01-09" in lines[2]
    assert lines[3] == "# Total records: 3"
    assert lines[5] == "Date,Open,High,Low,Close,Volume,Amount,PctChg"

    rows = [line.split(",") for line in lines[6:] if line]
    assert [row[0] for row in rows] == ["2026-01-05", "2026-01-06", "2026-01-07"]
    assert rows[0] == ["2026-01-05", "1680.50", "1690.00", "1675.00", "1685.00",
                       "10000", "1685000", "0.30"]
    assert rows[2][5] == "30000"          # 300 手 -> 30,000 股
    assert rows[2][6] == "5115000"        # 5115 千元 -> 5,115,000 元


def test_the_run_adjustment_reaches_the_vendor(fake_api):
    with run_config({"cn_adjust": "hfq"}):
        get_stock_data(SYMBOL, "2026-01-05", "2026-01-09")
    assert fake_api.calls[-1][1]["adj"] == "hfq"

    with run_config({"cn_adjust": "none"}):
        get_stock_data(SYMBOL, "2026-01-05", "2026-01-09")
    assert fake_api.calls[-1][1]["adj"] is None


def test_the_vendor_is_asked_with_tushare_spellings(fake_api):
    get_stock_data("600519.SS", "2026-01-05", "2026-01-09")
    call = fake_api.calls[-1][1]
    assert call["ts_code"] == "600519.SH"     # canonical, not Yahoo's .SS
    assert (call["start_date"], call["end_date"]) == ("20260105", "20260109")


def test_foreign_symbols_are_declined_without_a_call(fake_api):
    with pytest.raises(NoMarketDataError, match="A-share"):
        get_stock_data("AAPL", "2026-01-05", "2026-01-09")
    assert fake_api.calls == []


def test_an_empty_answer_is_no_data_not_an_empty_report(fake_api):
    fake_api.frame = pd.DataFrame()
    with pytest.raises(NoMarketDataError):
        get_stock_data(SYMBOL, "2026-01-05", "2026-01-09")


def test_a_vendor_failure_degrades_to_the_next_vendor():
    client.set_api(FakeApi(error=RuntimeError("quota exceeded")))
    with pytest.raises(VendorUnavailableError, match="quota"):
        get_stock_data(SYMBOL, "2026-01-05", "2026-01-09")


def test_a_typed_vendor_error_passes_through_unchanged():
    original = VendorUnavailableError("throttled")
    client.set_api(FakeApi(error=original))
    with pytest.raises(VendorUnavailableError) as caught:
        get_stock_data(SYMBOL, "2026-01-05", "2026-01-09")
    assert caught.value is original


def test_a_missing_token_says_which_variable_to_set(monkeypatch):
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    client.reset_api()
    with pytest.raises(VendorNotConfiguredError, match="TUSHARE_TOKEN"):
        get_stock_data(SYMBOL, "2026-01-05", "2026-01-09")


def test_malformed_dates_are_a_caller_error(fake_api):
    with pytest.raises(ValueError):
        get_stock_data(SYMBOL, "2026/01/05", "2026-01-09")


def test_a_frame_without_the_expected_columns_is_a_vendor_failure(fake_api):
    fake_api.frame = pd.DataFrame({"trade_date": ["20260105"]})
    with pytest.raises(VendorUnavailableError, match="columns"):
        get_stock_data(SYMBOL, "2026-01-05", "2026-01-09")


def test_activation_registers_the_vendor_and_the_chain_routes_to_it(fake_api):
    report = cn_register.activate()
    assert ("get_stock_data", "tushare") in report.vendors
    assert router.VENDOR_METHODS["get_stock_data"]["tushare"] is get_stock_data

    with run_config({"data_vendors": {"core_stock_apis": "tushare"}, "cn_adjust": "qfq"}):
        text = router.route_to_vendor("get_stock_data", SYMBOL, "2026-01-05", "2026-01-09")
    assert text.startswith(f"# Stock data for {SYMBOL}")


def test_the_calendar_replaces_the_weekend_only_default(fake_api):
    calendar = ts_calendar.load_calendar("2026-09-28", "2026-10-10")

    assert cn_calendar.default_calendar() is calendar
    assert cn_calendar.is_approximate() is False
    assert calendar.is_trading_day("2026-09-30") is True
    assert calendar.is_trading_day("2026-10-01") is False   # 国庆, a Thursday
    assert calendar.is_trading_day("2026-10-08") is True
    assert fake_api.calls[-1] == (
        "trade_cal",
        {"exchange": "SSE", "start_date": "20260928", "end_date": "20261010"},
    )


def test_a_calendar_can_be_built_without_installing_it(fake_api):
    calendar = ts_calendar.load_calendar("2026-09-28", "2026-10-10", install=False)
    assert calendar.is_trading_day("2026-10-01") is False
    assert cn_calendar.is_approximate() is True


def test_calendar_failures_are_typed(fake_api):
    fake_api.cal = pd.DataFrame()
    with pytest.raises(NoMarketDataError):
        ts_calendar.load_calendar("2026-09-28", "2026-10-10")

    client.set_api(FakeApi(error=RuntimeError("no permission")))
    with pytest.raises(VendorUnavailableError, match="no permission"):
        ts_calendar.load_calendar("2026-09-28", "2026-10-10")


def test_a_calendar_frame_without_its_columns_is_rejected():
    with pytest.raises(VendorUnavailableError, match="cal_date"):
        ts_calendar.calendar_from_frame(pd.DataFrame({"date": ["20260105"]}))


def test_an_inverted_calendar_range_is_a_caller_error(fake_api):
    with pytest.raises(ValueError):
        ts_calendar.load_calendar("2026-10-10", "2026-09-28")
