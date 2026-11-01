"""A-share trading rules: price limits, lot sizes, T+1 settlement."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from tradingagents_cn.calendar import TradingCalendar, set_default_calendar
from tradingagents_cn.trading_rules import (
    is_limit_locked,
    is_valid_lot,
    limit_ratio,
    lot_rule,
    lot_size,
    price_limits,
    reference_price,
    round_down_to_lot,
    settlement_date,
)

pytestmark = pytest.mark.unit

MAIN_SH = "600519.SH"
STAR = "688981.SH"
CHINEXT = "300750.SZ"
BEIJING = "430047.BJ"
MAIN_SZ = "000001.SZ"


@pytest.mark.parametrize(
    ("symbol", "is_st", "expected"),
    [
        (MAIN_SH, False, "0.10"),
        (MAIN_SH, True, "0.05"),
        (MAIN_SZ, False, "0.10"),
        (MAIN_SZ, True, "0.05"),
        (STAR, False, "0.20"),
        (STAR, True, "0.20"),        # ST on a 20%-limit board keeps 20%
        (CHINEXT, False, "0.20"),
        (CHINEXT, True, "0.20"),
        (BEIJING, False, "0.30"),
        (BEIJING, True, "0.30"),
    ],
)
def test_limit_ratio_follows_the_board(symbol, is_st, expected):
    assert limit_ratio(symbol, is_st=is_st) == Decimal(expected)


def test_limits_round_half_up_to_a_cent():
    assert price_limits(MAIN_SH, "10.00") == (Decimal("9.00"), Decimal("11.00"))
    # 10.05 * 1.1 = 11.055 -> 11.06; 10.05 * 0.9 = 9.045 -> 9.05
    assert price_limits(MAIN_SH, Decimal("10.05")) == (Decimal("9.05"), Decimal("11.06"))
    lower, upper = price_limits(STAR, 20)
    assert (lower, upper) == (Decimal("16.00"), Decimal("24.00"))


def test_a_close_outside_the_band_is_reported_as_unknown_not_as_false():
    assert is_limit_locked(MAIN_SH, "10.00", "11.00") is True
    assert is_limit_locked(MAIN_SH, "10.00", "9.00") is True
    assert is_limit_locked(MAIN_SH, "10.00", "10.50") is False
    assert is_limit_locked(MAIN_SH, "10.00", "12.00") is None


def test_lot_rules_follow_the_board():
    assert lot_rule(MAIN_SH) == (100, 100)
    assert lot_rule(BEIJING) == (100, 1)
    assert lot_rule(STAR) == (200, 1)
    assert lot_size(STAR) == 200


def test_odd_lots_are_rejected_on_the_main_boards_and_allowed_on_star():
    assert is_valid_lot(MAIN_SH, 100) is True
    assert is_valid_lot(MAIN_SH, 150) is False
    assert is_valid_lot(MAIN_SH, 0) is False
    assert is_valid_lot(MAIN_SH, -100) is False
    assert is_valid_lot(STAR, 199) is False
    assert is_valid_lot(STAR, 200) is True
    assert is_valid_lot(STAR, 201) is True


def test_rounding_down_never_produces_an_illegal_size():
    assert round_down_to_lot(MAIN_SH, 250) == 200
    assert round_down_to_lot(MAIN_SH, 99) == 0
    assert round_down_to_lot(STAR, 205) == 205
    assert round_down_to_lot(STAR, 199) == 0


def test_settlement_is_the_next_session_not_the_next_day():
    calendar = TradingCalendar(holidays=["2026-11-02"])
    set_default_calendar(calendar)
    assert settlement_date("2026-10-30") == date(2026, 11, 3)
    assert settlement_date(date(2026, 10, 29)) == date(2026, 10, 30)


@pytest.mark.parametrize("value", ["abc", None, object()])
def test_unparsable_prices_raise_instead_of_guessing(value):
    with pytest.raises((ValueError, TypeError)):
        price_limits(MAIN_SH, value)


def test_the_exchange_reference_price_on_an_ex_dividend_day():
    # 贵州茅台 2026-06-26: 1212.10 - 23.957 = 1188.143 -> 1188.14
    assert reference_price("1212.10", cash_div_per_share="23.957") == Decimal("1188.14")


def test_the_reference_price_handles_a_bonus_share_ratio():
    # 10送3: one existing share becomes 1.3 shares
    assert reference_price("10.00", share_ratio="0.3") == Decimal("7.69")


def test_an_impossible_share_ratio_is_rejected():
    with pytest.raises(ValueError):
        reference_price("10.00", share_ratio="-1")
