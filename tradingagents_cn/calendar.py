"""Trading-day calendar for A-share runs.

Upstream's point-in-time guards clamp a request to the run's ``trade_date`` but
know nothing about which days actually trade. A-share work does: 春节, 国庆 and
the other exchange closures are not weekdays, and a run dated on a holiday must
not be treated as a session.

The default calendar here only excludes weekends, so it is **approximate by
design** until a real calendar is installed. ``set_default_calendar`` is the
seam a vendor uses: ``tradingagents_cn.vendors.tushare`` installs the exchange's
``trade_cal`` on activation, after which the same call sites are exact.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

# Longest exchange closure in a normal year is well under this; the cap turns a
# calendar with impossible holidays into an error instead of a hang.
_MAX_SCAN_DAYS = 60


def _as_date(value: date | str) -> date:
    """Coerce an ISO date string or date-like value; never a datetime."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value.strip())
    raise TypeError(f"expected a date or ISO date string, got {type(value).__name__}")


@dataclass(frozen=True)
class TradingCalendar:
    """Sessions are weekdays minus ``holidays``.

    ``holidays`` holds exchange closures only; a weekend inside a holiday range
    is redundant but harmless.
    """

    holidays: frozenset = frozenset()

    def __post_init__(self) -> None:
        object.__setattr__(self, "holidays", frozenset(_as_date(d) for d in self.holidays))

    def is_trading_day(self, day: date | str) -> bool:
        """Whether ``day`` is a session."""
        value = _as_date(day)
        return value.weekday() < 5 and value not in self.holidays

    def next_trading_day(self, day: date | str, *, include: bool = False) -> date:
        """The first session at or after ``day`` (strictly after when ``include`` is False)."""
        value = _as_date(day)
        start = 0 if include else 1
        for offset in range(start, _MAX_SCAN_DAYS):
            candidate = value + timedelta(days=offset)
            if self.is_trading_day(candidate):
                return candidate
        raise ValueError(f"no trading day within {_MAX_SCAN_DAYS} days of {value}")

    def previous_trading_day(self, day: date | str, *, include: bool = False) -> date:
        """The last session at or before ``day`` (strictly before when ``include`` is False)."""
        value = _as_date(day)
        start = 0 if include else 1
        for offset in range(start, _MAX_SCAN_DAYS):
            candidate = value - timedelta(days=offset)
            if self.is_trading_day(candidate):
                return candidate
        raise ValueError(f"no trading day within {_MAX_SCAN_DAYS} days of {value}")

    def trading_days(self, start: date | str, end: date | str) -> list[date]:
        """Every session in ``[start, end]``, ascending."""
        first, last = _as_date(start), _as_date(end)
        if first > last:
            raise ValueError(f"start {first} is after end {last}")
        days = []
        current = first
        while current <= last:
            if self.is_trading_day(current):
                days.append(current)
            current += timedelta(days=1)
        return days


_APPROXIMATE = TradingCalendar()
_default: TradingCalendar = _APPROXIMATE


def default_calendar() -> TradingCalendar:
    """The calendar the data layer consults when none was installed."""
    return _default


def set_default_calendar(calendar: TradingCalendar | None) -> None:
    """Install ``calendar`` process-wide; ``None`` restores the weekend-only default."""
    global _default
    if calendar is not None and not isinstance(calendar, TradingCalendar):
        raise TypeError(f"expected a TradingCalendar, got {type(calendar).__name__}")
    _default = calendar or _APPROXIMATE


def is_approximate() -> bool:
    """Whether the active calendar still ignores exchange holidays."""
    return _default is _APPROXIMATE
