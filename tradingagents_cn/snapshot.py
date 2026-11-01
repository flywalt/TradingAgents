"""A "verified market snapshot" computed from Tushare bars.

Upstream's market analyst calls ``get_verified_market_snapshot`` before making
exact claims about prices, RSI, MACD or support levels — and that tool reads
Yahoo. For an A-share run that means one basis for prices and another for the
verification of those prices.

This module offers the same idea over Tushare bars. It is a data interface: no
tool calls it yet, because swapping the analyst's tool is an agent-layer change.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd

from tradingagents_cn.cache import cached
from tradingagents_cn.vendors.common import require_ashare
from tradingagents_cn.vendors.tushare.indicators import indicator_series
from tradingagents_cn.vendors.tushare.stock import fetch_bars, resolve_adjust

_TTL_SECONDS = 60 * 60
_WARMUP_DAYS = 120


def build_market_snapshot(
    symbol: str, as_of_date: str, look_back_days: int = 30, indicators=None
) -> str:
    """Latest bar, recent closes and a few indicator values, all from one basis.

    ``indicators`` mirrors upstream's vendor signature; the snapshot always
    renders the core set, so a caller-supplied list is accepted and ignored
    rather than silently changing the report's shape.
    """
    canonical = require_ashare(symbol)
    as_of = _iso(as_of_date)
    sessions = _positive(look_back_days, "look_back_days")
    adjust = resolve_adjust()

    start = (date.fromisoformat(as_of) - timedelta(days=sessions * 2 + _WARMUP_DAYS)).isoformat()
    bars = cached(
        "bars",
        f"{canonical}|{adjust}|{start}|{as_of}",
        _TTL_SECONDS,
        lambda: fetch_bars(canonical, start, as_of, adjust=adjust),
    )
    tail = bars.tail(sessions)
    if len(tail) == 0:
        raise ValueError(f"no bars for {canonical} up to {as_of}")

    latest = tail.iloc[-1]
    lines = [
        f"# Verified market snapshot for {canonical} as of {as_of}",
        f"# Vendor: tushare; adjustment: {adjust or 'none'}; "
        "computation: local stockstats over tushare bars",
        f"# Latest session: {latest['trade_date']}",
        "",
        "## Latest bar",
        "date,open,high,low,close,volume,amount",
        ",".join(
            [
                str(latest["trade_date"]),
                _money(latest.get("open")),
                _money(latest.get("high")),
                _money(latest.get("low")),
                _money(latest.get("close")),
                _count(latest.get("vol")),
                _count(latest.get("amount")),
            ]
        ),
        "",
        "## Indicators (latest session)",
    ]
    for name in ("rsi", "macd", "macds", "boll", "boll_ub", "boll_lb", "atr"):
        value = indicator_series(bars, name).iloc[-1]
        lines.append(f"- {name}: {_money(value)}")

    lines += ["", "## Recent closes", "date,close"]
    for row in tail.to_dict("records"):
        lines.append(f"{row['trade_date']},{_money(row.get('close'))}")
    return "\n".join(lines) + "\n"


def _money(value) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        return ""
    return f"{float(value):.2f}"


def _count(value) -> str:
    if value is None:
        return "0"
    try:
        if pd.isna(value):
            return "0"
    except (TypeError, ValueError):
        return "0"
    return str(int(round(float(value))))


def _positive(value, name: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer, got {value!r}") from exc
    if number <= 0:
        raise ValueError(f"{name} must be positive, got {number}")
    return number


def _iso(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"expected a YYYY-MM-DD date, got {value!r}")
    return datetime.strptime(value.strip(), "%Y-%m-%d").strftime("%Y-%m-%d")
