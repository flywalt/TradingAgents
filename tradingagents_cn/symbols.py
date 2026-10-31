"""A-share symbol normalization.

The canonical downstream form is ``<6 digits>.<MARKET>`` with MARKET in
``SH`` / ``SZ`` / ``BJ`` — the same shape Tushare uses (``ts_code``), so vendor
adapters never have to translate twice. Users and upstream callers type many
other shapes, and every A-share vendor would otherwise need its own parser:

    user types                 canonical      why
    ------------------------   ------------   --------------------------------
    600519, sh600519, 600519.SS  600519.SH    Yahoo spells Shanghai ``.SS``
    SH.600519, 600519.XSHG       600519.SH    Tushare-doc and RQData spellings
    000001, sz000001             000001.SZ    Shenzhen
    430047, bj430047, 920001     430047.BJ    Beijing Stock Exchange
    510300, 159915               510300.SH    ETFs follow their exchange prefix

An explicit suffix always wins, but a suffix that contradicts the code's own
prefix raises instead of being silently rewritten: ``600519.SZ`` is a typo, not
an instruction.
"""

from __future__ import annotations

import re

MARKETS = ("SH", "SZ", "BJ")

# Longest prefixes first where they would otherwise be shadowed by 2-char ones.
_SH_PREFIXES_3 = ("600", "601", "603", "605", "688", "689", "900")
_SZ_PREFIXES_3 = ("000", "001", "002", "003", "004", "200", "300", "301", "302")
_BJ_PREFIXES_3 = ("430", "831", "832", "833", "834", "835", "836", "837", "838",
                  "839", "870", "871", "872", "873", "920")
# 2-char prefixes cover funds/ETFs and convertible bonds on each exchange.
_SH_PREFIXES_2 = ("11", "50", "51", "52", "56", "58")
_SZ_PREFIXES_2 = ("12", "15", "16", "18")

_SUFFIXES = {"SH": "SH", "SS": "SH", "XSHG": "SH", "SZ": "SZ", "XSHE": "SZ", "BJ": "BJ"}
_YAHOO_SUFFIX = {"SH": "SS", "SZ": "SZ"}

_CODE_SUFFIX_RE = re.compile(r"^(?P<code>\d{6})(?:\.(?P<suffix>[A-Z]{2,4}))?$")
_PREFIX_CODE_RE = re.compile(r"^(?P<suffix>SH|SZ|BJ)\.?(?P<code>\d{6})$")


def market_for_code(code: str) -> str | None:
    """The exchange a bare 6-digit code belongs to, or None when unrecognised."""
    if len(code) != 6 or not code.isdigit():
        return None
    for prefixes, market in (
        (_SH_PREFIXES_3, "SH"),
        (_SZ_PREFIXES_3, "SZ"),
        (_BJ_PREFIXES_3, "BJ"),
    ):
        if code[:3] in prefixes:
            return market
    for prefixes, market in (
        (_SH_PREFIXES_2, "SH"),
        (_SZ_PREFIXES_2, "SZ"),
    ):
        if code[:2] in prefixes:
            return market
    return None


def normalize(symbol: str) -> str:
    """Canonical ``<code>.<MARKET>`` for any accepted A-share spelling.

    Raises ``ValueError`` for anything that is not an A-share symbol — vendor
    adapters turn that into ``NoMarketDataError`` so the router can move on to
    the next vendor instead of serving another market's data.
    """
    if not isinstance(symbol, str):
        raise ValueError(f"symbol must be a string, got {type(symbol).__name__}")
    raw = symbol.strip().upper()
    if not raw:
        raise ValueError("symbol is empty")

    match = _CODE_SUFFIX_RE.match(raw)
    explicit: str | None = None
    if match:
        code = match.group("code")
        suffix = match.group("suffix")
        if suffix is not None:
            explicit = _SUFFIXES.get(suffix)
            if explicit is None:
                raise ValueError(f"unknown exchange suffix in {symbol!r}")
    else:
        match = _PREFIX_CODE_RE.match(raw)
        if not match:
            raise ValueError(f"{symbol!r} is not an A-share symbol")
        code = match.group("code")
        explicit = _SUFFIXES[match.group("suffix")]

    inferred = market_for_code(code)
    if inferred is None:
        raise ValueError(f"{symbol!r} is not an A-share symbol")
    if explicit is not None and explicit != inferred:
        raise ValueError(
            f"{symbol!r} says {explicit} but code {code} belongs to {inferred}"
        )
    return f"{code}.{inferred}"


def try_normalize(symbol: str) -> str | None:
    """``normalize`` for callers that route on "is this ours?" rather than fail."""
    try:
        return normalize(symbol)
    except ValueError:
        return None


def is_ashare(symbol: str) -> bool:
    """Whether ``symbol`` names an A-share instrument, without raising."""
    return try_normalize(symbol) is not None


def code_of(symbol: str) -> str:
    """The 6-digit code of a canonical symbol (normalizing if needed)."""
    return normalize(symbol).split(".", 1)[0]


def market_of(symbol: str) -> str:
    """The exchange (``SH`` / ``SZ`` / ``BJ``) of a canonical symbol."""
    return normalize(symbol).split(".", 1)[1]


def to_yahoo(symbol: str) -> str:
    """The Yahoo Finance spelling of an A-share symbol.

    Yahoo lists Shanghai as ``.SS`` and Shenzhen as ``.SZ`` and carries no
    Beijing Stock Exchange listing, so a BJ symbol raises rather than returning
    a code Yahoo would answer with an empty frame.
    """
    canonical = normalize(symbol)
    market = canonical.split(".", 1)[1]
    if market not in _YAHOO_SUFFIX:
        raise ValueError(f"Yahoo Finance does not list {canonical} (Beijing Stock Exchange)")
    return f"{canonical.split('.', 1)[0]}.{_YAHOO_SUFFIX[market]}"


def to_tushare(symbol: str) -> str:
    """Tushare's ``ts_code`` for an A-share symbol (already canonical)."""
    return normalize(symbol)


def from_yahoo(symbol: str) -> str:
    """Canonical A-share spelling of a Yahoo ticker (``600519.SS`` -> ``600519.SH``)."""
    normalized = try_normalize(symbol)
    if normalized is None:
        raise ValueError(f"{symbol!r} is not a Yahoo A-share ticker")
    return normalized
