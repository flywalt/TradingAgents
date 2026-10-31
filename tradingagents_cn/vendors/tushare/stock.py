"""OHLCV bars from Tushare, with the run's adjustment applied.

``get_stock_data`` has the same positional signature as the router's other
implementations (``symbol, start_date, end_date``) and returns the same shape of
text: a header naming the instrument, the vendor and the price basis, then CSV
rows the analyst can read.

Three conversions happen here and are stated in the output, because a reader who
guesses them wrong will mis-price the instrument:

* ``vol`` comes in 手 (100 shares) and is served in shares;
* ``amount`` comes in 千元 and is served in CNY;
* ``pct_chg`` is Tushare's percentage change for the session, served as given.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.errors import VendorError, VendorUnavailableError
from tradingagents_cn.vendors.common import adjustment, no_rows, require_ashare
from tradingagents_cn.vendors.tushare import client

_VENDOR = "tushare"

_REQUIRED_COLUMNS = ("trade_date", "open", "high", "low", "close", "vol")
_PRICE_FIELDS = ("Open", "High", "Low", "Close")
_CSV_COLUMNS = ("Date", "Open", "High", "Low", "Close", "Volume", "Amount", "PctChg")


def get_stock_data(symbol: str, start_date: str, end_date: str) -> str:
    """Daily OHLCV bars for an A-share symbol, adjusted per ``cn_adjust``."""
    canonical = require_ashare(symbol)
    start, end = _iso(start_date), _iso(end_date)
    adjust = adjustment(get_config())

    api = client.get_api()
    try:
        frame = api.pro_bar(
            ts_code=canonical,
            adj=adjust or None,
            start_date=_compact(start),
            end_date=_compact(end),
            asset="E",
        )
    except VendorError:
        raise
    except Exception as exc:  # network, throttling, quota, unknown ts_code
        raise VendorUnavailableError(
            f"tushare could not serve {canonical} between {start} and {end}: {exc}"
        ) from exc

    if frame is None or len(frame) == 0:
        raise no_rows(symbol, canonical, f"tushare returned no bars between {start} and {end}")

    return _format(frame, canonical, start, end, adjust)


def _format(frame, canonical: str, start_date: str, end_date: str, adjust: str) -> str:
    missing = [column for column in _REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        raise VendorUnavailableError(
            f"tushare returned columns {sorted(frame.columns)}; missing {missing}"
        )

    data = frame.copy()
    data["trade_date"] = (
        pd.to_datetime(data["trade_date"].astype(str), format="mixed", errors="raise")
        .dt.strftime("%Y-%m-%d")
    )
    data = data.sort_values("trade_date")

    records = data.to_dict("records")
    lines = [
        f"# Stock data for {canonical} from {start_date} to {end_date}",
        f"# Vendor: {_VENDOR}; adjustment: {adjust or 'none'}; "
        "volume in shares; amount in CNY; prices in CNY",
        f"# Total records: {len(records)}",
        "",
        ",".join(_CSV_COLUMNS),
    ]
    for row in records:
        lines.append(
            ",".join(
                [
                    str(row["trade_date"]),
                    *(_decimal(row.get(field.lower())) for field in _PRICE_FIELDS),
                    str(_scaled(row.get("vol"), 100)),
                    str(_scaled(row.get("amount"), 1000)),
                    _decimal(row.get("pct_chg")),
                ]
            )
        )
    return "\n".join(lines) + "\n"


def _decimal(value) -> str:
    """Two decimals, or an empty cell for a missing value (never a guessed one)."""
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        return ""
    return f"{float(value):.2f}"


def _scaled(value, factor: int) -> int:
    """A unit conversion (手 -> 股, 千元 -> 元); a missing value stays 0."""
    if value is None:
        return 0
    try:
        if pd.isna(value):
            return 0
    except (TypeError, ValueError):
        return 0
    return int(round(float(value) * factor))


def _iso(value: str) -> str:
    """Validate and canonicalize an ISO date, as the yahoo vendor does."""
    if not isinstance(value, str):
        raise ValueError(f"expected a YYYY-MM-DD date, got {value!r}")
    parsed = datetime.strptime(value.strip(), "%Y-%m-%d")
    return parsed.strftime("%Y-%m-%d")


def _compact(iso_date: str) -> str:
    """``2026-01-09`` -> ``20260109``, the form Tushare's APIs take."""
    return iso_date.replace("-", "")

