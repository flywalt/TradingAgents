"""China-Accounting-Standards statements for A-share runs.

The US pipeline reads SEC EDGAR or Yahoo, which for an A-share company is either
empty or a USD/US-GAAP view. This module serves the filed statements instead,
with three rules stated in every header:

* **unit** — amounts are 亿元 (100 million CNY); EPS stays in 元 per share;
* **basis** — 利润表 and 现金流量表 are 本年累计 (YTD, not single-quarter), the
  资产负债表 is a period-end balance; nothing is de-cumulated here;
* **point in time** — only reports announced on or before the run date, and when
  a period was refiled, the announcement that was current.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd

from tradingagents.dataflows.date_window import get_current_date
from tradingagents.dataflows.errors import (
    NoMarketDataError,
    VendorError,
    VendorUnavailableError,
)
from tradingagents_cn.cache import cached
from tradingagents_cn.pit import announced_by, latest_reports
from tradingagents_cn.units import to_yi
from tradingagents_cn.vendors.common import no_rows, require_ashare
from tradingagents_cn.vendors.tushare import client

_TTL_SECONDS = 24 * 60 * 60
_LOOKBACK_DAYS = 5 * 365
_PERIODS = 4
_FREQUENCIES = ("annual", "quarterly")

#: (label, tushare field, rendering) — ``yi`` scales 元 -> 亿元, ``raw`` serves as-is.
INCOME_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("营业总收入", "total_revenue", "yi"),
    ("营业收入", "revenue", "yi"),
    ("营业成本", "oper_cost", "yi"),
    ("营业利润", "operate_profit", "yi"),
    ("利润总额", "total_profit", "yi"),
    ("净利润", "n_income", "yi"),
    ("归母净利润", "n_income_attr_p", "yi"),
    ("基本每股收益（元/股）", "basic_eps", "raw"),
)

BALANCE_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("资产总计", "total_assets", "yi"),
    ("负债合计", "total_liab", "yi"),
    ("归母所有者权益", "total_hldr_eqy_exc_min_int", "yi"),
    ("货币资金", "money_cap", "yi"),
    ("应收账款", "accounts_receiv", "yi"),
    ("存货", "inventories", "yi"),
    ("固定资产", "fix_assets", "yi"),
)

CASHFLOW_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("经营活动现金流净额", "n_cashflow_act", "yi"),
    ("投资活动现金流净额", "n_cashflow_inv_act", "yi"),
    ("筹资活动现金流净额", "n_cash_flows_fnc_act", "yi"),
    ("销售商品收到的现金", "c_fr_sale_sg", "yi"),
    ("购买商品支付的现金", "c_paid_goods_s", "yi"),
)


def get_income_statement(
    ticker: str, freq: str = "quarterly", curr_date: str | None = None
) -> str:
    """利润表 (income statement), annual or quarterly."""
    return _statement(
        ticker,
        freq,
        curr_date,
        endpoint="income",
        title="利润表 (Income statement)",
        fields=INCOME_FIELDS,
        basis="本年累计 (YTD)",
    )


def get_balance_sheet(
    ticker: str, freq: str = "quarterly", curr_date: str | None = None
) -> str:
    """资产负债表 (balance sheet), annual or quarterly."""
    return _statement(
        ticker,
        freq,
        curr_date,
        endpoint="balancesheet",
        title="资产负债表 (Balance sheet)",
        fields=BALANCE_FIELDS,
        basis="期末余额 (period end)",
    )


def get_cashflow(ticker: str, freq: str = "quarterly", curr_date: str | None = None) -> str:
    """现金流量表 (cash-flow statement), annual or quarterly."""
    return _statement(
        ticker,
        freq,
        curr_date,
        endpoint="cashflow",
        title="现金流量表 (Cash-flow statement)",
        fields=CASHFLOW_FIELDS,
        basis="本年累计 (YTD)",
    )


def _statement(
    ticker: str,
    freq: str,
    curr_date: str | None,
    *,
    endpoint: str,
    title: str,
    fields: tuple[tuple[str, str, str], ...],
    basis: str,
) -> str:
    canonical = require_ashare(ticker)
    frequency = str(freq or "").strip().lower()
    if frequency not in _FREQUENCIES:
        raise ValueError(
            f"freq must be one of {', '.join(_FREQUENCIES)}; got {freq!r}"
        )
    as_of = _iso(curr_date or get_current_date())

    frame = _fetch(canonical, as_of, endpoint)
    visible = announced_by(frame, as_of)
    reports = latest_reports(visible, periods=_PERIODS if frequency == "quarterly" else 40,
                             report_type="1")
    if frequency == "annual":
        reports = reports[reports["end_date"].astype(str).str.endswith("1231")].tail(_PERIODS)
    if len(reports) == 0:
        raise no_rows(ticker, canonical, f"no {endpoint} report announced by {as_of}")

    columns = [str(value) for value in reports["end_date"]][::-1]   # newest first
    rows = reports.iloc[::-1]

    lines = [
        f"# {title} for {canonical}",
        f"# Vendor: tushare; 单位：亿元（1 亿元 = 10^8 元）; 口径: {basis}; 合并报表 (report_type=1)",
        f"# Trade date: {as_of}; periods: {len(rows)}; only reports announced by then",
        "",
        "| 项目 | " + " | ".join(_iso_date(column) for column in columns) + " |",
        "| --- | " + " | ".join("---" for _ in columns) + " |",
    ]
    for label, key, kind in fields:
        cells = [_cell(row.get(key), kind) for row in rows.to_dict("records")]
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def _fetch(canonical: str, as_of: str, endpoint: str):
    start = (date.fromisoformat(as_of) - timedelta(days=_LOOKBACK_DAYS)).isoformat()
    builder = getattr(client.get_api(), endpoint)
    try:
        frame = cached(
            endpoint,
            f"{canonical}|{start}|{as_of}",
            _TTL_SECONDS,
            lambda: builder(ts_code=canonical, start_date=_compact(start), end_date=_compact(as_of)),
        )
    except VendorError:
        raise
    except Exception as exc:  # network, throttling, quota
        raise VendorUnavailableError(f"tushare {endpoint} unavailable: {exc}") from exc
    if frame is None or len(frame) == 0:
        raise NoMarketDataError(canonical, canonical, f"tushare returned no {endpoint} rows")
    return frame


def _cell(value, kind: str) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        return ""
    if kind == "yi":
        return to_yi(value)
    return f"{float(value):.2f}"


def _iso_date(value: str) -> str:
    text = str(value).strip()
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    return text


def _iso(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"expected a YYYY-MM-DD date, got {value!r}")
    return datetime.strptime(value.strip(), "%Y-%m-%d").strftime("%Y-%m-%d")


def _compact(iso_date: str) -> str:
    return iso_date.replace("-", "")
