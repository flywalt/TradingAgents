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


def test_live_indicators_agree_with_a_direct_computation_of_the_same_bars():
    _skip_without_prerequisites()
    from tradingagents_cn.vendors.tushare import client
    from tradingagents_cn.vendors.tushare.indicators import get_stock_stats_indicators_window
    from tradingagents_cn.vendors.tushare.stock import fetch_bars

    client.reset_api()
    end = date.today()
    as_of = (end - timedelta(days=1)).isoformat()
    text = get_stock_stats_indicators_window(SYMBOL, "close_50_sma", as_of, 5)

    bars = fetch_bars(SYMBOL, (end - timedelta(days=200)).isoformat(), as_of)
    expected = f"{bars['close'].tail(50).mean():.2f}"
    served = [line.split(",")[1] for line in text.splitlines() if line and not line.startswith("#")]
    assert served[-1] == expected
    assert served[1:]  # the window has more than the last row


def test_live_statements_exclude_a_report_announced_after_the_run_date():
    _skip_without_prerequisites()
    from tradingagents_cn.vendors.tushare import client
    from tradingagents_cn.vendors.tushare.statements import get_income_statement

    client.reset_api()
    # The 2026 Q3 report is announced in late October, so a September run cannot see it.
    text = get_income_statement(SYMBOL, "quarterly", "2026-09-30")

    assert "| 2026-06-30 |" in text
    assert "| 2026-09-30 |" not in text
    assert "单位：亿元" in text


def test_live_fundamentals_carry_profile_and_valuation():
    _skip_without_prerequisites()
    from tradingagents_cn.vendors.tushare import client
    from tradingagents_cn.vendors.tushare.fundamentals import get_fundamentals

    client.reset_api()
    text = get_fundamentals(SYMBOL, date.today().isoformat())

    assert "贵州茅台" in text
    assert "白酒" in text
    assert "Total market cap:" in text


def test_live_capital_flow_endpoints_answer():
    _skip_without_prerequisites()
    from tradingagents_cn.vendors.tushare import client
    from tradingagents_cn.vendors.tushare.flows import get_margin_detail, get_money_flow

    client.reset_api()
    end = date.today()
    start = (end - timedelta(days=20)).isoformat()

    flow = get_money_flow(SYMBOL, start, end.isoformat())
    margin = get_margin_detail(SYMBOL, start, end.isoformat())

    flow_rows = [line for line in flow.splitlines() if line and not line.startswith("#")]
    margin_rows = [line for line in margin.splitlines() if line and not line.startswith("#")]
    assert len(flow_rows) > 1 and "net_mf_amount" in flow
    assert len(margin_rows) > 1
    assert "单位亿元" in margin and "为股" in margin
    header = margin_rows[0].split(",")
    row = dict(zip(header, margin_rows[-1].split(","), strict=True))
    # rzche is 元 on the wire; served in 亿元, so it must be far below 1e6.
    assert float(row["rzche"]) < 1_000_000


def test_live_index_and_identity_endpoints_answer():
    _skip_without_prerequisites()
    from tradingagents_cn.identity import resolve_identity
    from tradingagents_cn.vendors.tushare import client
    from tradingagents_cn.vendors.tushare.index import get_index_daily, list_index_members

    client.reset_api()
    end = date.today()
    daily = get_index_daily("000300.SH", (end - timedelta(days=20)).isoformat(), end.isoformat())
    members = list_index_members("000300.SH")
    identity = resolve_identity(SYMBOL)

    assert "000300.SH" in daily and "vol in 手" in daily
    member_rows = [line for line in members.splitlines() if line and not line.startswith("#")]
    header = member_rows[0].split(",")
    assert header[:2] == ["index_code", "con_code"], header
    assert 1 < len(member_rows) - 1 <= 1000, len(member_rows)
    assert "l1_code" not in members
    assert identity["name"] == "贵州茅台"


def test_live_snapshot_uses_tushare_numbers():
    _skip_without_prerequisites()
    from tradingagents_cn.snapshot import build_market_snapshot
    from tradingagents_cn.vendors.tushare import client

    client.reset_api()
    text = build_market_snapshot(SYMBOL, (date.today() - timedelta(days=1)).isoformat())

    assert text.startswith(f"# Verified market snapshot for {SYMBOL}")
    assert "Vendor: tushare" in text
    assert "- rsi:" in text
