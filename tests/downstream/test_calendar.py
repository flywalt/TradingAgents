"""Trading calendar: sessions are weekdays minus exchange closures, and the seam
through which a real exchange calendar is installed."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from tradingagents_cn.calendar import (
    TradingCalendar,
    default_calendar,
    is_approximate,
    set_default_calendar,
)

pytestmark = pytest.mark.unit

# 2026-10-31 is a Saturday; 2026-10-30 the Friday before it.
SATURDAY = date(2026, 10, 31)
FRIDAY = date(2026, 10, 30)
MONDAY = date(2026, 11, 2)


def test_weekends_are_not_sessions():
    calendar = TradingCalendar()
    assert calendar.is_trading_day(FRIDAY) is True
    assert calendar.is_trading_day(SATURDAY) is False
    assert calendar.is_trading_day("2026-10-31") is False


def test_injected_holidays_close_an_otherwise_open_weekday():
    calendar = TradingCalendar(holidays=["2026-10-01", date(2026, 10, 2)])
    assert calendar.is_trading_day(date(2026, 10, 1)) is False   # Thursday, 国庆
    assert calendar.is_trading_day(date(2026, 10, 2)) is False
    assert calendar.is_trading_day(date(2026, 10, 5)) is True    # Monday after


def test_next_and_previous_session_skip_weekends_and_holidays():
    calendar = TradingCalendar(holidays=["2026-11-02"])
    assert calendar.next_trading_day(FRIDAY) == date(2026, 11, 3)
    assert calendar.next_trading_day(FRIDAY, include=True) == FRIDAY
    assert calendar.previous_trading_day(MONDAY) == FRIDAY
    assert calendar.previous_trading_day(MONDAY, include=True) == date(2026, 10, 30)


def test_trading_days_returns_the_sessions_in_order():
    calendar = TradingCalendar()
    days = calendar.trading_days("2026-10-26", "2026-11-01")
    assert days == [date(2026, 10, d) for d in (26, 27, 28, 29, 30)]


def test_inverted_window_is_a_caller_error():
    with pytest.raises(ValueError):
        TradingCalendar().trading_days("2026-11-02", "2026-10-30")


def test_an_impossible_calendar_fails_loudly_instead_of_looping():
    calendar = TradingCalendar(holidays=[date(2026, 10, 1)])
    full_year_closed = TradingCalendar(
        holidays=[date(2027, 1, 1) + timedelta(days=i) for i in range(200)]
    )
    assert calendar.is_trading_day(date(2026, 10, 5)) is True
    with pytest.raises(ValueError):
        full_year_closed.next_trading_day(date(2026, 12, 31))


def test_default_calendar_is_approximate_until_a_vendor_installs_one():
    assert is_approximate() is True
    assert default_calendar().is_trading_day(SATURDAY) is False

    installed = TradingCalendar(holidays=["2026-10-30"])
    set_default_calendar(installed)
    assert default_calendar() is installed
    assert is_approximate() is False

    set_default_calendar(None)
    assert is_approximate() is True


def test_installing_something_that_is_not_a_calendar_is_rejected():
    with pytest.raises(TypeError):
        set_default_calendar({"holidays": []})


def test_holiday_values_must_be_dates():
    with pytest.raises((TypeError, ValueError)):
        TradingCalendar(holidays=[20261001])
