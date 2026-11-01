"""A-share capital flows: order flow, northbound holdings, margin balances, 龙虎榜.

Data interfaces only — no tool and no agent reads these yet. They are registered
under their own router category (``cn_capital_flows``) so a later agent task can
wire them without touching this module.

Units are stated per endpoint rather than converted: Tushare serves order-flow
amounts in 万元 and margin balances in 元, and inventing a single unit here would
hide which one a figure came in.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from tradingagents.dataflows.errors import (
    NoMarketDataError,
    VendorError,
    VendorUnavailableError,
)
from tradingagents_cn.cache import cached
from tradingagents_cn.vendors.common import no_rows, require_ashare
from tradingagents_cn.vendors.tushare import client

CATEGORY = "cn_capital_flows"

_TTL_SECONDS = 60 * 60
_NORTHBOUND_CUTOFF = "2024-08-16"


def get_money_flow(symbol: str, start_date: str, end_date: str) -> str:
    """Per-stock order-flow breakdown (``moneyflow``), amounts in 万元."""
    canonical = require_ashare(symbol)
    start, end = _iso(start_date), _iso(end_date)
    frame = _fetch("moneyflow", canonical, start, end)
    return _render(
        "资金流 (Money flow)", canonical, frame, start, end,
        note="amounts in 万元 as served by tushare",
    )


def get_northbound_holdings(symbol: str, start_date: str, end_date: str) -> str:
    """Northbound (Stock Connect) holdings; per-stock daily disclosure ended 2024-08-16."""
    canonical = require_ashare(symbol)
    start, end = _iso(start_date), _iso(end_date)
    frame = _fetch("hk_hold", canonical, start, end)
    return _render(
        "北向持股 (Northbound holdings)", canonical, frame, start, end,
        note=(f"per-stock northbound disclosure ended {_NORTHBOUND_CUTOFF}; later dates "
              "carry no daily rows. vol in shares, ratio in %"),
    )


def get_margin_detail(symbol: str, start_date: str, end_date: str) -> str:
    """Margin-financing and short-selling balances, converted to 亿元."""
    canonical = require_ashare(symbol)
    start, end = _iso(start_date), _iso(end_date)
    frame = _fetch("margin_detail", canonical, start, end).copy()
    for column in ("rzye", "rqye", "rzmre", "rqyl"):
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce") / 10**8
    return _render(
        "融资融券 (Margin balances)", canonical, frame, start, end,
        note="amounts in 亿元",
    )


def get_top_list(trade_date: str) -> str:
    """The 龙虎榜 (Dragon-Tiger list) for one trade date."""
    day = _iso(trade_date)
    try:
        frame = cached(
            "top_list",
            day,
            _TTL_SECONDS,
            lambda: client.get_api().top_list(trade_date=_compact(day)),
        )
    except VendorError:
        raise
    except Exception as exc:
        raise VendorUnavailableError(f"tushare top_list unavailable: {exc}") from exc
    if frame is None or len(frame) == 0:
        raise no_rows(day, day, "no dragon-tiger rows for this date")
    return _render("龙虎榜 (Dragon-Tiger list)", None, frame, day, day,
                   note="amounts in 元 unless the column name says otherwise")


def _fetch(endpoint: str, canonical: str, start: str, end: str):
    call = getattr(client.get_api(), endpoint)
    try:
        frame = cached(
            endpoint,
            f"{canonical}|{start}|{end}",
            _TTL_SECONDS,
            lambda: call(ts_code=canonical, start_date=_compact(start), end_date=_compact(end)),
        )
    except VendorError:
        raise
    except Exception as exc:  # network, throttling, quota
        raise VendorUnavailableError(f"tushare {endpoint} unavailable: {exc}") from exc
    if frame is None or len(frame) == 0:
        raise NoMarketDataError(
            canonical, canonical, f"no {endpoint} rows between {start} and {end}"
        )
    return frame


def _render(title: str, canonical: str | None, frame, start: str, end: str, *, note: str) -> str:
    subject = f" for {canonical}" if canonical else ""
    window = f"{start}..{end}" if start != end else start
    columns = [str(column) for column in frame.columns]
    lines = [
        f"# {title}{subject} ({window})",
        f"# Vendor: tushare; {note}",
        ",".join(columns),
    ]
    for row in frame.to_dict("records"):
        lines.append(",".join(_cell(row.get(column)) for column in columns))
    return "\n".join(lines) + "\n"


def _cell(value) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        return ""
    if isinstance(value, (int,)):
        return str(value)
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def _iso(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"expected a YYYY-MM-DD date, got {value!r}")
    return datetime.strptime(value.strip(), "%Y-%m-%d").strftime("%Y-%m-%d")


def _compact(iso_date: str) -> str:
    return iso_date.replace("-", "")
