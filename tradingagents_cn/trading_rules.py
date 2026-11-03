"""A-share trading rules the upstream framework has no notion of.

Three rules decide whether a price or a size is even legal on the mainland
boards, and getting them wrong silently produces backtests that could never
have been filled:

* **Daily price limits** — 10% on the main boards, 20% on 科创板 (``688``/``689``)
  and 创业板 (``300``/``301``/``302``), 30% on 北交所, and 5% for ST names on the
  main boards. ST names on the 20%-limit boards keep 20%.
* **Lot sizes** — 100 shares on the main boards and 北交所; 科创板 starts at 200
  and then steps by 1.
* **T+1 settlement** — shares bought today are sellable from the next session,
  which is a *calendar* question, not "+1 day".

Limits are computed from the previous close with exchange rounding (half-up to
0.01), so ``price_limits`` returns Decimals, never floats.
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from .calendar import TradingCalendar, default_calendar
from .symbols import code_of, market_of, normalize

_PENNY = Decimal("0.01")

_STAR_BOARD = ("688", "689")
_CHINEXT = ("300", "301", "302")

LIMIT_MAIN = Decimal("0.10")
LIMIT_BOARD_20 = Decimal("0.20")
LIMIT_BEIJING = Decimal("0.30")
LIMIT_ST_MAIN = Decimal("0.05")

T_PLUS_ONE = True


def is_st_name(name: str | None) -> bool:
    """Whether a listing name carries the ST / *ST marker.

    The exchange encodes risk-warning status in the name itself, so the identity
    row already answers the question the band depends on - no separate feed.
    """
    if not name:
        return False
    return str(name).strip().upper().lstrip("*").startswith("ST")


def limit_ratio(symbol: str, *, is_st: bool = False) -> Decimal:
    """The maximum daily move for ``symbol`` as a fraction of the previous close."""
    canonical = normalize(symbol)
    market, code = market_of(canonical), code_of(canonical)
    if market == "BJ":
        return LIMIT_BEIJING
    if market == "SH" and code.startswith(_STAR_BOARD):
        return LIMIT_BOARD_20
    if market == "SZ" and code.startswith(_CHINEXT):
        return LIMIT_BOARD_20
    return LIMIT_ST_MAIN if is_st else LIMIT_MAIN


def price_limits(symbol: str, prev_close, *, is_st: bool = False) -> tuple[Decimal, Decimal]:
    """The (lower, upper) tradable prices for the session after ``prev_close``.

    ``prev_close`` may be a Decimal, int, float or numeric string; it is
    quantized to 0.01 before the limits are derived, so a float artefact cannot
    shift a limit by a cent.
    """
    base = _to_price(prev_close)
    ratio = limit_ratio(symbol, is_st=is_st)
    upper = (base * (Decimal(1) + ratio)).quantize(_PENNY, rounding=ROUND_HALF_UP)
    lower = (base * (Decimal(1) - ratio)).quantize(_PENNY, rounding=ROUND_HALF_UP)
    return lower, upper


def reference_price(prev_close, cash_div_per_share=0, share_ratio=0) -> Decimal:
    """The exchange's ex-rights reference price for the next session.

    On an ex-dividend day the limit band is computed from this value, not from
    the previous close and not from a 前复权 series: on 2026-06-26 贵州茅台's
    reference was 1212.10 - 23.957 = 1188.14, while the raw close (1212.10) and
    the qfq close (1184.08) would both put the band in the wrong place.

    ``share_ratio`` is the bonus/rights ratio per existing share (10送3 -> 0.3).
    """
    base = _to_price(prev_close)
    cash = Decimal(str(cash_div_per_share or 0))
    ratio = Decimal(str(share_ratio or 0))
    if ratio <= -1:
        raise ValueError(f"share_ratio must be greater than -1, got {share_ratio!r}")
    return ((base - cash) / (Decimal(1) + ratio)).quantize(_PENNY, rounding=ROUND_HALF_UP)


def is_limit_locked(symbol: str, prev_close, close, *, is_st: bool = False) -> bool | None:
    """Whether a session closed at its limit (``None`` when the price is outside the band).

    A close outside ``[lower, upper]`` cannot happen on a real session, so it
    reports ``None`` rather than a false "not locked" for corrupt input.
    """
    lower, upper = price_limits(symbol, prev_close, is_st=is_st)
    value = _to_price(close)
    if value < lower or value > upper:
        return None
    return value in (lower, upper)


def lot_rule(symbol: str) -> tuple[int, int]:
    """The (minimum quantity, step) a board accepts."""
    canonical = normalize(symbol)
    market, code = market_of(canonical), code_of(canonical)
    if market == "SH" and code.startswith(_STAR_BOARD):
        return 200, 1
    if market == "BJ":
        return 100, 1
    return 100, 100


def lot_size(symbol: str) -> int:
    """The minimum order quantity for ``symbol``."""
    return lot_rule(symbol)[0]


def is_valid_lot(symbol: str, quantity: int) -> bool:
    """Whether ``quantity`` shares is an order the board would accept."""
    if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity <= 0:
        return False
    minimum, step = lot_rule(symbol)
    return quantity >= minimum and (quantity - minimum) % step == 0


def round_down_to_lot(symbol: str, quantity: int) -> int:
    """The largest legal quantity not above ``quantity`` (0 when below the minimum)."""
    if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity <= 0:
        return 0
    minimum, step = lot_rule(symbol)
    if quantity < minimum:
        return 0
    return minimum + ((quantity - minimum) // step) * step


def settlement_date(
    trade_date: date | str, calendar: TradingCalendar | None = None
) -> date:
    """The first session on which shares bought on ``trade_date`` are sellable (T+1)."""
    cal = calendar or default_calendar()
    return cal.next_trading_day(trade_date, include=False)


def _to_price(value) -> Decimal:
    try:
        return Decimal(str(value)).quantize(_PENNY, rounding=ROUND_HALF_UP)
    except Exception as exc:  # noqa: BLE001 - any unparsable price is the caller's bug
        raise ValueError(f"not a price: {value!r}") from exc
