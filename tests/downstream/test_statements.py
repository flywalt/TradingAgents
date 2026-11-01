"""CAS statements served with announcement-date filtering.

Three things the analyst would otherwise get wrong, pinned here: a period
announced after the run date must not appear, the annual view must show annual
reports rather than the latest quarters, and amounts must be labelled 亿元 rather
than served as raw 元 (or as USD, which is what the US pipeline serves).
"""

from __future__ import annotations

import pandas as pd
import pytest

from tradingagents.dataflows.errors import NoMarketDataError
from tradingagents_cn.vendors.tushare import client
from tradingagents_cn.vendors.tushare.statements import (
    get_balance_sheet,
    get_cashflow,
    get_income_statement,
)

pytestmark = pytest.mark.unit

SYMBOL = "600519.SH"


def income_frame() -> pd.DataFrame:
    """Q3 is announced in late October, after a 2026-09-30 run."""
    return pd.DataFrame(
        {
            "ts_code": [SYMBOL] * 3,
            "ann_date": ["20260425", "20260825", "20261028"],
            "f_ann_date": ["20260425", "20260825", "20261028"],
            "end_date": ["20260331", "20260630", "20260930"],
            "report_type": ["1", "1", "1"],
            "total_revenue": [6.0e8, 1_234_567_890, 2.0e9],
            "revenue": [5.9e8, 1.2e9, 1.9e9],
            "oper_cost": [1.0e8, 2.0e8, 3.0e8],
            "operate_profit": [3.0e8, 7.0e8, 1.0e9],
            "total_profit": [3.1e8, 7.1e8, 1.0e9],
            "n_income": [2.5e8, 5.5e8, 8.0e8],
            "n_income_attr_p": [2.4e8, 5.4e8, 7.9e8],
            "basic_eps": [20.5, 43.0, 62.0],
        }
    )


def annual_frame() -> pd.DataFrame:
    frame = income_frame()
    extra = frame.iloc[[1]].copy()
    extra["end_date"] = "20251231"
    extra["ann_date"] = "20260328"
    extra["f_ann_date"] = "20260328"
    return pd.concat([extra, frame], ignore_index=True)


def balance_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ts_code": [SYMBOL],
            "ann_date": ["20260825"],
            "end_date": ["20260630"],
            "report_type": ["1"],
            "total_assets": [2.0e11],
            "total_liab": [3.0e10],
            "total_hldr_eqy_exc_min_int": [1.6e11],
            "money_cap": [5.0e10],
            "accounts_receiv": [1.0e9],
            "inventories": [4.0e10],
            "fix_assets": [2.0e10],
        }
    )


def cashflow_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ts_code": [SYMBOL],
            "ann_date": ["20260825"],
            "end_date": ["20260630"],
            "report_type": ["1"],
            "n_cashflow_act": [3.0e10],
            "n_cashflow_inv_act": [-5.0e9],
            "n_cash_flows_fnc_act": [-1.0e10],
            "c_fr_sale_sg": [8.0e10],
            "c_paid_goods_s": [2.0e10],
        }
    )


class FakeApi:
    """Endpoints are methods; the frames they answer with live under other names."""

    def __init__(self, income=None, balance=None, cashflow=None):
        self._income = income if income is not None else income_frame()
        self._balance = balance if balance is not None else balance_frame()
        self._cashflow = cashflow if cashflow is not None else cashflow_frame()
        self.calls: list[str] = []

    def income(self, **kwargs):
        self.calls.append("income")
        return self._income

    def balancesheet(self, **kwargs):
        self.calls.append("balancesheet")
        return self._balance

    def cashflow(self, **kwargs):
        self.calls.append("cashflow")
        return self._cashflow


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


def test_a_report_announced_after_the_run_date_is_not_a_column(api):
    text = get_income_statement(SYMBOL, "quarterly", "2026-09-30")

    assert "| 2026-06-30 |" in text
    assert "| 2026-09-30 |" not in text      # announced 2026-10-28


def test_the_annual_view_shows_annual_reports(api):
    api._income = annual_frame()

    text = get_income_statement(SYMBOL, "annual", "2026-09-30")

    assert "| 2025-12-31 |" in text
    assert "| 2026-06-30 |" not in text


def test_amounts_are_in_hundred_millions_with_the_unit_stated(api):
    text = get_income_statement(SYMBOL, "quarterly", "2026-09-30")

    assert "单位：亿元" in text
    assert "12.35" in text                  # 1,234,567,890 元
    assert "归母净利润" in text
    assert "43.00" in text                  # EPS is served raw, not scaled to 亿元


def test_ytd_basis_is_labelled(api):
    text = get_income_statement(SYMBOL, "quarterly", "2026-09-30")

    assert "本年累计" in text


def test_a_refiled_period_keeps_the_latest_announcement():
    frame = income_frame()
    refiled = frame.iloc[[1]].copy()
    refiled["ann_date"] = "20261020"        # still before the run date
    refiled["total_revenue"] = 2.0e8        # a big downward revision -> 2.00 亿元
    client.set_api(FakeApi(income=pd.concat([frame, refiled], ignore_index=True)))
    try:
        text = get_income_statement(SYMBOL, "quarterly", "2026-12-31")
    finally:
        client.reset_api()

    assert text.count("| 2026-06-30 |") == 1
    assert "2.00" in text
    assert "12.35" not in text              # the superseded filing is gone


def test_an_unknown_frequency_lists_the_supported_ones(api):
    with pytest.raises(ValueError, match="quarterly"):
        get_income_statement(SYMBOL, "monthly", "2026-09-30")


def test_all_three_statements_decline_an_empty_answer():
    client.set_api(FakeApi(income=pd.DataFrame(), balance=pd.DataFrame(),
                           cashflow=pd.DataFrame()))
    try:
        for getter in (get_income_statement, get_balance_sheet, get_cashflow):
            with pytest.raises(NoMarketDataError):
                getter(SYMBOL, "quarterly", "2026-09-30")
    finally:
        client.reset_api()


def test_balance_sheet_and_cashflow_render_their_core_fields(api):
    balance = get_balance_sheet(SYMBOL, "quarterly", "2026-09-30")
    cashflow = get_cashflow(SYMBOL, "quarterly", "2026-09-30")

    assert "资产总计" in balance and "2000.00" in balance
    assert "经营活动现金流净额" in cashflow and "300.00" in cashflow
    assert "-50.00" in cashflow            # outflows keep their sign


def test_a_foreign_symbol_is_declined_before_any_call(api):
    with pytest.raises(NoMarketDataError):
        get_balance_sheet("AAPL", "quarterly", "2026-09-30")
    assert api.calls == []
