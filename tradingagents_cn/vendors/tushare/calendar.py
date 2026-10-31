"""The real exchange calendar, fetched from Tushare and installed process-wide.

The offline calendar in ``tradingagents_cn.calendar`` only knows weekends, which
is not enough to date an A-share run: 春节 and 国庆 are weekdays the exchange is
closed, and a run that treats one as a session will ask for bars that cannot
exist. ``load_calendar`` replaces it with the exchange's own ``trade_cal``.

Fetching is explicit (never part of ``activate()``) so activation stays free of
network I/O, and so a stale calendar can be refreshed deliberately.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from tradingagents.dataflows.errors import VendorError, VendorUnavailableError
from tradingagents_cn.calendar import TradingCalendar, set_default_calendar
from tradingagents_cn.vendors.common import no_rows
from tradingagents_cn.vendors.tushare import client

_EXCHANGE = "SSE"


def load_calendar(
    start_date: str, end_date: str, *, exchange: str = _EXCHANGE, install: bool = True
) -> TradingCalendar:
    """Build a calendar from the exchange's open days and install it by default.

    ``start_date``/``end_date`` are ISO dates; the range must cover every date
    the runs will ask about, because a date outside it falls back to "weekday =
    open", which is exactly the guess this function exists to remove.
    """
    start, end = _iso(start_date), _iso(end_date)
    if start > end:
        raise ValueError(f"start_date {start} is after end_date {end}")

    api = client.get_api()
    try:
        frame = api.trade_cal(
            exchange=exchange,
            start_date=start.replace("-", ""),
            end_date=end.replace("-", ""),
        )
    except VendorError:
        raise
    except Exception as exc:  # network, throttling, quota
        raise VendorUnavailableError(
            f"tushare could not serve the {exchange} calendar for {start}..{end}: {exc}"
        ) from exc

    if frame is None or len(frame) == 0:
        raise no_rows(f"{exchange} calendar", exchange, f"no calendar rows for {start}..{end}")

    calendar = calendar_from_frame(frame)
    if install:
        set_default_calendar(calendar)
    return calendar


def calendar_from_frame(frame) -> TradingCalendar:
    """The calendar a ``trade_cal`` frame describes (open days become sessions)."""
    if "cal_date" not in frame.columns or "is_open" not in frame.columns:
        raise VendorUnavailableError(
            f"tushare calendar returned columns {sorted(frame.columns)}; "
            "expected cal_date and is_open"
        )

    data = frame[["cal_date", "is_open"]].copy()
    data["cal_date"] = (
        pd.to_datetime(data["cal_date"].astype(str), format="mixed", errors="raise").dt.date
    )
    opens = set(data.loc[data["is_open"].astype(str).str.strip() == "1", "cal_date"])
    if not opens:
        raise no_rows("exchange calendar", "cal_date", "no open days in the calendar frame")

    # Every weekday the exchange did not open is a holiday; weekends are already
    # closed by the calendar's own rule and stay out of the set.
    first, last = min(data["cal_date"]), max(data["cal_date"])
    holidays = []
    current = first
    while current <= last:
        if current.weekday() < 5 and current not in opens:
            holidays.append(current)
        current += timedelta(days=1)
    return TradingCalendar(holidays=holidays)


def _iso(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"expected a YYYY-MM-DD date, got {value!r}")
    return datetime.strptime(value.strip(), "%Y-%m-%d").strftime("%Y-%m-%d")


__all__ = ["calendar_from_frame", "load_calendar"]
