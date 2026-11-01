"""Unit conversions the A-share layer serves: 元 -> 亿元, 手 -> 股, 千元 -> 元.

Every conversion is stated in an output header, so these helpers are the only
place a wrong factor can hide — hence the edge cases here (None, NaN, negatives,
float artefacts).
"""

from __future__ import annotations

import pytest

from tradingagents_cn.units import lots_to_shares, thousand_yuan_to_yuan, to_yi

pytestmark = pytest.mark.unit


def test_yi_scales_yuan_to_hundred_millions_at_two_decimals():
    assert to_yi(1_234_567_890) == "12.35"          # 12.34567890 亿, half-up
    assert to_yi(1_000_000_000) == "10.00"
    assert to_yi(0) == "0.00"


def test_negative_amounts_keep_their_sign():
    assert to_yi(-1_000_000_000) == "-10.00"


def test_missing_values_render_as_empty_not_nan():
    assert to_yi(None) == ""
    assert to_yi(float("nan")) == ""
    assert to_yi("") == ""


def test_numeric_strings_are_accepted():
    assert to_yi("1234567890") == "12.35"


def test_lots_and_thousand_yuan_convert_without_float_artefacts():
    assert lots_to_shares(59927.29) == 5_992_729
    assert thousand_yuan_to_yuan(8257381.778) == 8_257_381_778
    assert lots_to_shares(0) == 0
    assert thousand_yuan_to_yuan(None) == 0
    assert lots_to_shares(float("nan")) == 0


def test_a_huge_amount_does_not_fall_into_scientific_notation():
    rendered = to_yi(9_999_999_999_999)
    assert "e" not in rendered.lower()
    assert rendered == "100000.00"
