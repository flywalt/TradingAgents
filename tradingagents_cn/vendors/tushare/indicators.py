"""The upstream indicator set, computed locally from Tushare bars.

Why local: the market analyst reads prices from Tushare and indicators from
Yahoo's copy of the same instrument, which are two different price bases (and
two different adjustment conventions). Computing here means one basis, one
header, one thing to debug.

stockstats happily returns a *partial-window* mean when a series is shorter than
the indicator's window, which looks like a signal and is not one. Each indicator
therefore declares the sessions it needs, and earlier rows are served empty.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
from stockstats import wrap

from tradingagents.dataflows.config import get_config
from tradingagents_cn.cache import cached
from tradingagents_cn.vendors.common import adjustment, require_ashare
from tradingagents_cn.vendors.tushare import tdx_indicators
from tradingagents_cn.vendors.tushare.stock import fetch_bars

#: The 13 names upstream's ``get_indicators`` tool documents.
SUPPORTED_INDICATORS: tuple[str, ...] = (
    "close_50_sma",
    "close_200_sma",
    "close_10_ema",
    "macd",
    "macds",
    "macdh",
    "rsi",
    "boll",
    "boll_ub",
    "boll_lb",
    "atr",
    "vwma",
    "mfi",
)

#: Sessions each indicator needs before its value means anything.
_MIN_SESSIONS = {
    "close_50_sma": 50,
    "close_200_sma": 200,
    "close_10_ema": 10,
    "macd": 35,      # 26 EMA + 9 signal
    "macds": 35,
    "macdh": 35,
    "rsi": 15,       # 14 deltas + the first close
    "boll": 20,
    "boll_ub": 20,
    "boll_lb": 20,
    "atr": 15,
    "vwma": 15,
    "mfi": 15,
}

_BARS_TTL_SECONDS = 60 * 60
_CSV_HEADER = "Date,{indicator}"

_FLAVOR_LABELS = {
    tdx_indicators.TDX_FLAVOR: "tdx (通达信口径)",
    tdx_indicators.STOCKSTATS_FLAVOR: "stockstats (维基口径)",
}


def resolve_flavor() -> str:
    """The configured indicator flavour (``cn_indicator_flavor``)."""
    raw = str(get_config().get("cn_indicator_flavor", tdx_indicators.TDX_FLAVOR)).strip().lower()
    if raw not in tdx_indicators.FLAVORS:
        raise ValueError(
            f"cn_indicator_flavor must be one of {tdx_indicators.FLAVORS}, got {raw!r}"
        )
    return raw


def get_stock_stats_indicators_window(
    symbol: str, indicator: str, as_of_date: str, look_back_days: int
) -> str:
    """One indicator's series over the last ``look_back_days`` sessions up to ``as_of_date``."""
    name = str(indicator).strip().lower()
    if name not in SUPPORTED_INDICATORS:
        raise ValueError(
            f"unknown indicator {indicator!r}; supported indicators: "
            + ", ".join(SUPPORTED_INDICATORS)
        )
    canonical = require_ashare(symbol)
    as_of = _iso(as_of_date)
    sessions = _look_back(look_back_days)
    adjust = adjustment(get_config())

    warmup_days = _MIN_SESSIONS[name] * 2 + 40
    start = (date.fromisoformat(as_of) - timedelta(days=warmup_days + sessions)).isoformat()
    bars = cached(
        "bars",
        f"{canonical}|{adjust}|{start}|{as_of}",
        _BARS_TTL_SECONDS,
        lambda: fetch_bars(canonical, start, as_of, adjust=adjust),
    )

    flavor = resolve_flavor()
    values = indicator_series(bars, name, flavor)
    window = bars["trade_date"].tail(sessions)
    observed = values.tail(sessions)

    lines = [
        f"# Indicators for {canonical} as of {as_of} (last {sessions} sessions)",
        f"# Vendor: tushare; adjustment: {adjust or 'none'}; "
        f"computation: {_FLAVOR_LABELS[flavor]} over tushare bars",
        _CSV_HEADER.format(indicator=name),
    ]
    for trading_day, value in zip(window, observed, strict=True):
        lines.append(f"{trading_day},{_decimal(value)}")
    return "\n".join(lines) + "\n"


def indicator_series(bars: pd.DataFrame, name: str, flavor: str | None = None) -> pd.Series:
    """The indicator over ``bars``, blanked where history is too short.

    ``flavor`` defaults to ``cn_indicator_flavor`` (通达信 by default).
    """
    flavor = flavor or resolve_flavor()
    if flavor == tdx_indicators.TDX_FLAVOR:
        series = tdx_indicators.compute(name, bars)
        values = pd.Series(series.to_numpy(), index=bars.index, dtype="float64")
        required = _MIN_SESSIONS[name]
        if required > 1:
            values.iloc[: required - 1] = float("nan")
        return values

    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(bars["trade_date"]),
            "open": bars["open"],
            "high": bars["high"],
            "low": bars["low"],
            "close": bars["close"],
            "volume": bars["vol"],
        }
    )
    series = wrap(frame)[name]
    values = pd.Series(series.to_numpy(), index=bars.index, dtype="float64")
    required = _MIN_SESSIONS[name]
    if required > 1:
        values.iloc[: required - 1] = float("nan")
    return values


def _decimal(value) -> str:
    if value is None or pd.isna(value):
        return ""
    return f"{float(value):.2f}"


def _iso(value: str) -> str:
    from datetime import datetime

    if not isinstance(value, str):
        raise ValueError(f"expected a YYYY-MM-DD date, got {value!r}")
    return datetime.strptime(value.strip(), "%Y-%m-%d").strftime("%Y-%m-%d")


def _look_back(value) -> int:
    try:
        sessions = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"look_back_days must be an integer, got {value!r}") from exc
    if sessions <= 0:
        raise ValueError(f"look_back_days must be positive, got {sessions}")
    return sessions
