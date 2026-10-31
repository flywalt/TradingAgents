"""Live Tushare checks: run with ``-m integration`` and a real token.

Excluded from the default suite (``pyproject`` sets ``-m "not integration"``) so
a clone can run its tests without a token, a paid quota, or the network. Use it
to verify a freshly configured account:

    TUSHARE_TOKEN=... .venv/bin/python -m pytest -q -m integration \
        tests/downstream/test_tushare_live.py
"""

from __future__ import annotations

import os
from datetime import date, timedelta

import pytest

pytestmark = pytest.mark.integration

SYMBOL = "600519.SH"


def _skip_without_prerequisites() -> None:
    if not os.environ.get("TUSHARE_TOKEN"):
        pytest.skip("TUSHARE_TOKEN is not set")
    pytest.importorskip("tushare", reason="pip install tushare to run the live checks")


def test_live_daily_bars_are_served_with_the_run_adjustment():
    _skip_without_prerequisites()
    from tradingagents_cn.vendors.tushare import client
    from tradingagents_cn.vendors.tushare.stock import get_stock_data

    client.reset_api()
    end = date.today()
    start = end - timedelta(days=20)
    text = get_stock_data(SYMBOL, start.isoformat(), end.isoformat())

    assert text.startswith(f"# Stock data for {SYMBOL}")
    assert "adjustment: qfq" in text
    rows = [line for line in text.splitlines() if line and not line.startswith("#")]
    assert rows[0] == "Date,Open,High,Low,Close,Volume,Amount,PctChg"
    assert len(rows) > 1, "no bars returned in the last 20 days"


def test_live_exchange_calendar_closes_a_known_holiday():
    _skip_without_prerequisites()
    from tradingagents_cn.vendors.tushare import client
    from tradingagents_cn.vendors.tushare.calendar import load_calendar

    client.reset_api()
    calendar = load_calendar("2026-09-25", "2026-10-12", install=False)

    assert calendar.is_trading_day("2026-10-01") is False   # 国庆
    assert calendar.is_trading_day("2026-10-09") is True


def test_live_beijing_symbol_is_served_even_though_yahoo_has_no_listing():
    """BJ has no Yahoo fallback, so this is the one market Tushare must serve."""
    _skip_without_prerequisites()
    from tradingagents_cn.vendors.tushare import client
    from tradingagents_cn.vendors.tushare.stock import get_stock_data

    client.reset_api()
    end = date.today()
    start = end - timedelta(days=60)
    text = get_stock_data("920002.BJ", start.isoformat(), end.isoformat())

    assert text.startswith("# Stock data for 920002.BJ")
    rows = [line for line in text.splitlines() if line and not line.startswith("#")]
    assert len(rows) > 1, "no Beijing bars returned in the last 60 days"
