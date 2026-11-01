"""Unit conversions for A-share data.

Two conventions differ from the US pipeline and are stated in every output
header, so the factors live in exactly one place:

* amounts are reported in **亿元 (100 million CNY)** because that is how A-share
  filings and research read; the wire values arrive in 元;
* turnover arrives in 手 (100 shares) and 千元, and is served in 股 and 元.

Missing values render as an empty cell, never as ``nan`` or a guessed zero —
except for the integer conversions, where the counts the router needs must be a
number and a missing count can only mean "nothing traded".
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

YI = Decimal(10) ** 8


def _decimal(value) -> Decimal | None:
    """Parse a numeric-ish value; ``None`` for missing, blank or non-numeric."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = Decimal(text)
    except (InvalidOperation, ValueError):
        return None
    if not parsed.is_finite():
        return None
    return parsed


def to_yi(value, places: int = 2) -> str:
    """``元`` -> ``亿元`` with fixed decimals (half-up), empty for missing values."""
    parsed = _decimal(value)
    if parsed is None:
        return ""
    quantum = Decimal(1).scaleb(-places)
    scaled = (parsed / YI).quantize(quantum, rounding=ROUND_HALF_UP)
    return f"{scaled:f}"


def _scaled_int(value, factor: int) -> int:
    parsed = _decimal(value)
    if parsed is None:
        return 0
    return int((parsed * factor).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def lots_to_shares(value) -> int:
    """``手`` -> ``股`` (1 手 = 100 股)."""
    return _scaled_int(value, 100)


def thousand_yuan_to_yuan(value) -> int:
    """``千元`` -> ``元``."""
    return _scaled_int(value, 1000)
