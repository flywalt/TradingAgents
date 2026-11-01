"""Insider dealings (高管/股东增减持) from Tushare's ``stk_holdertrade``.

The US pipeline reads Yahoo's insider list, which is empty for mainland filers,
so the fundamentals analyst's governance view had nothing in it. This serves the
exchange filings instead, with the same point-in-time rule as statements: a
trade announced after the run date was not public knowledge then.

Units are stated in the header: ``change_vol``/``after_share`` in 股,
``avg_price`` in 元, ``change_ratio`` in %.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd

from tradingagents.dataflows.errors import (
    NoMarketDataError,
    VendorError,
    VendorUnavailableError,
)
from tradingagents_cn.cache import cached
from tradingagents_cn.pit import announced_by
from tradingagents_cn.vendors.common import no_rows, require_ashare
from tradingagents_cn.vendors.tushare import client

_TTL_SECONDS = 24 * 60 * 60
_LOOKBACK_DAYS = 2 * 365
_KEEP = (
    "ann_date", "holder_name", "holder_type", "in_de",
    "change_vol", "change_ratio", "after_share", "avg_price",
)


def get_insider_transactions(ticker: str, trade_date: str | None = None) -> str:
    """Insider and major-holder trades announced on or before ``trade_date``."""
    canonical = require_ashare(ticker)
    as_of = _iso(trade_date) if trade_date else _today()
    start = (date.fromisoformat(as_of) - timedelta(days=_LOOKBACK_DAYS)).isoformat()

    try:
        frame = cached(
            "holdertrade",
            f"{canonical}|{start}|{as_of}",
            _TTL_SECONDS,
            lambda: client.get_api().stk_holdertrade(
                ts_code=canonical, start_date=_compact(start), end_date=_compact(as_of)
            ),
        )
    except VendorError:
        raise
    except Exception as exc:  # network, throttling, quota
        raise VendorUnavailableError(f"tushare stk_holdertrade unavailable: {exc}") from exc

    if frame is None or len(frame) == 0:
        raise NoMarketDataError(canonical, canonical, f"no insider trades between {start} and {as_of}")

    visible = announced_by(frame, as_of)
    if len(visible) == 0:
        raise no_rows(ticker, canonical, f"no insider trade announced by {as_of}")

    columns = [column for column in _KEEP if column in visible.columns]
    rows = visible.sort_values("ann_date", ascending=False)
    lines = [
        f"# Insider transactions for {canonical} (announced by {as_of})",
        "# Vendor: tushare; 单位: change_vol/after_share 为股, avg_price 为元, change_ratio 为 %"
        "; 只含该日期之前已公告的变动",
        ",".join(columns),
    ]
    for record in rows[columns].to_dict("records"):
        lines.append(",".join(_cell(record.get(column)) for column in columns))
    return "\n".join(lines) + "\n"


def _cell(value) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        return ""
    if isinstance(value, float):
        return f"{value:.4f}".rstrip("0").rstrip(".")
    return str(value)


def _iso(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"expected a YYYY-MM-DD date, got {value!r}")
    return datetime.strptime(value.strip(), "%Y-%m-%d").strftime("%Y-%m-%d")


def _today() -> str:
    from tradingagents.dataflows.date_window import get_current_date

    return _iso(get_current_date())


def _compact(iso_date: str) -> str:
    return iso_date.replace("-", "")


__all__ = ["get_insider_transactions"]
