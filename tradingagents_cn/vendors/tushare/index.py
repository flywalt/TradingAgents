"""Index data for A-share benchmarks and membership.

Index codes live in their own namespace. ``000300.SH`` is the CSI 300 while
``000300`` alone is ambiguous (``000001`` is both 平安银行 on SZSE and the SSE
Composite Index), so an index code must carry its exchange suffix and a stock
code is refused here: guessing would silently serve the wrong instrument.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta

import pandas as pd

from tradingagents.dataflows.date_window import get_current_date
from tradingagents.dataflows.errors import VendorError, VendorUnavailableError
from tradingagents_cn.cache import cached
from tradingagents_cn.vendors.common import no_rows
from tradingagents_cn.vendors.tushare import client

_TTL_SECONDS = 24 * 60 * 60
_INDEX_PATTERN = re.compile(r"^(?P<digits>\d{6})\.(?P<market>SH|SZ|CSI)$")

#: Which 6-digit prefixes each index namespace uses. ``CSI`` is provider-defined.
_INDEX_PREFIXES = {
    "SH": ("000",),      # 上证综指 / 沪深300 / 中证系列在上交所口径下
    "SZ": ("399",),      # 深证成指 / 创业板指
    "CSI": (),           # 中证指数公司自定义，前缀不固定
}


def normalize_index_code(code: str) -> str:
    """Validate an index code; it must name its exchange explicitly."""
    if not isinstance(code, str):
        raise ValueError(f"index code must be a string, got {type(code).__name__}")
    text = code.strip().upper()
    match = _INDEX_PATTERN.match(text)
    if not match:
        raise ValueError(
            f"{code!r} is not an index code; use an explicit suffix like 000300.SH, "
            "399001.SZ or 000905.CSI (a bare code is ambiguous with a stock code)"
        )
    digits, market = match.group("digits"), match.group("market")
    prefixes = _INDEX_PREFIXES[market]
    if prefixes and not digits.startswith(prefixes):
        raise ValueError(f"{code!r} is not a {market} index code (prefix must be {prefixes})")
    return f"{digits}.{market}"


def get_index_daily(index_code: str, start_date: str, end_date: str) -> str:
    """Daily bars for an index (``index_daily``)."""
    canonical = normalize_index_code(index_code)
    start, end = _iso(start_date), _iso(end_date)
    frame = _fetch(
        "index_daily", canonical, start, end,
        lambda: client.get_api().index_daily(
            ts_code=canonical, start_date=_compact(start), end_date=_compact(end)
        ),
    )
    frame = frame.copy()
    frame["trade_date"] = _display_dates(frame["trade_date"])
    return _render(f"指数行情 (Index daily) {canonical}", frame, start, end,
                   note="prices in index points; vol in 手; amount in 千元")


def list_index_members(index_code: str, trade_date: str | None = None,
                       look_back_days: int = 90) -> str:
    """Constituents and weights from ``index_weight``.

    ``index_member_all`` is the Shenwan *industry* tree (l1/l2/l3 codes), not an
    index's constituents — calling it with ``index_code`` returns the whole
    market. Weights are published per trade date, so the latest date inside the
    look-back window is served.
    """
    canonical = normalize_index_code(index_code)
    end = _iso(trade_date or get_current_date())
    start = (date.fromisoformat(end) - timedelta(days=max(1, int(look_back_days)))).isoformat()
    frame = _fetch(
        "index_weight", canonical, start, end,
        lambda: client.get_api().index_weight(
            index_code=canonical, start_date=_compact(start), end_date=_compact(end)
        ),
    )
    data = frame.copy()
    data["trade_date"] = data["trade_date"].astype(str)
    latest = data["trade_date"].max()
    data = data[data["trade_date"] == latest]
    return _render(
        f"指数成分权重 (Index weights) {canonical}", data, start, end,
        note=f"weights in %; one row per constituent for {latest}",
    )


def _fetch(endpoint: str, key: str, start: str, end: str, producer):
    try:
        frame = cached(endpoint, f"{key}|{start}|{end}", _TTL_SECONDS, producer)
    except VendorError:
        raise
    except Exception as exc:  # network, throttling, quota
        raise VendorUnavailableError(f"tushare {endpoint} unavailable: {exc}") from exc
    if frame is None or len(frame) == 0:
        raise no_rows(key, key, f"tushare returned no {endpoint} rows")
    return frame


def _render(title: str, frame, start: str, end: str, *, note: str) -> str:
    window = f"; {start}..{end}" if start else ""
    columns = [str(column) for column in frame.columns]
    lines = [
        f"# {title}{window}",
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
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def _display_dates(series) -> pd.Series:
    return pd.to_datetime(series.astype(str), format="mixed").dt.strftime("%Y-%m-%d")


def _iso(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"expected a YYYY-MM-DD date, got {value!r}")
    return datetime.strptime(value.strip(), "%Y-%m-%d").strftime("%Y-%m-%d")


def _compact(iso_date: str) -> str:
    return iso_date.replace("-", "")
