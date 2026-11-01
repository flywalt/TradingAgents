"""Market profiles: one downstream codebase, several market behaviours.

The project is not an A-share fork. A run's market decides which graph class,
identity resolver, vendor defaults, trading rules and indicator flavour apply;
``UPSTREAM_DEFAULT`` must behave exactly like the upstream package.

Selection is by **exchange and security identifier**, never by issuer
nationality, name or language: a Chinese company listed in Hong Kong is not an
A-share, and ``BABA`` is not one either.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

PROFILE_DEFAULT = "UPSTREAM_DEFAULT"
PROFILE_CN = "CN_A_SHARE"

_CN_SUFFIXES = (".SS", ".SZ", ".BJ", ".SH")
_CN_BARE = re.compile(r"^\d{6}$")
_AMBIGUOUS_BARE = re.compile(r"^\d{4,5}$")      # e.g. 0700 (HK) vs 0700 (US OTC): require market=
_KNOWN_MARKETS = {"CN", "HK", "US", "JP", "UK", "EU", "SG", "IN", "TW", "KR", "AU", "CA"}


@dataclass(frozen=True)
class MarketProfile:
    key: str
    market: str
    graph: str                       # "upstream" | "cn"
    identity: str                    # "yahoo" | "tushare"
    vendors: dict[str, str] = field(default_factory=dict)   # category -> chain
    tool_vendors: dict[str, str] = field(default_factory=dict)
    strict_allowed: bool = False
    indicator_flavor: str = "stockstats"
    injects_ashare_rules: bool = False
    selected_analysts: tuple[str, ...] = ("market", "social", "news", "fundamentals")
    optional_analysts: tuple[str, ...] = ()
    currency: str = "USD"
    reporting_language: str = "English"
    dir_suffix: str = ""

    def describe(self) -> dict:
        """A JSON-safe summary for logs and run metadata."""
        return {
            "key": self.key,
            "market": self.market,
            "graph": self.graph,
            "identity": self.identity,
            "strict_allowed": self.strict_allowed,
            "indicator_flavor": self.indicator_flavor,
            "currency": self.currency,
            "analysts": list(self.selected_analysts),
        }


UPSTREAM_DEFAULT = MarketProfile(
    key=PROFILE_DEFAULT,
    market="US",
    graph="upstream",
    identity="yahoo",
    indicator_flavor="stockstats",
    injects_ashare_rules=False,
    currency="USD",
    reporting_language="English",
)

CN_A_SHARE = MarketProfile(
    key=PROFILE_CN,
    market="CN",
    graph="cn",
    identity="tushare",
    vendors={
        "core_stock_apis": "tushare,yfinance",
        "technical_indicators": "tushare,yfinance",
        "fundamental_data": "tushare,yfinance",
    },
    tool_vendors={"get_insider_transactions": "tushare,yfinance"},
    strict_allowed=True,
    indicator_flavor="tdx",
    injects_ashare_rules=True,
    currency="CNY",
    reporting_language="中文",
    dir_suffix="cn",
)

PROFILES: dict[str, MarketProfile] = {
    UPSTREAM_DEFAULT.key: UPSTREAM_DEFAULT,
    CN_A_SHARE.key: CN_A_SHARE,
}


def get_profile(key: str) -> MarketProfile:
    profile = PROFILES.get(str(key).strip().upper())
    if profile is None:
        raise ValueError(f"unknown market profile {key!r}; known: {sorted(PROFILES)}")
    return profile


def _market_for_symbol(symbol: str) -> str | None:
    text = str(symbol).strip().upper()
    if not text:
        return None
    if text.endswith(_CN_SUFFIXES) or _CN_BARE.match(text):
        return "CN"
    if text.endswith(".HK"):
        return "HK"
    if _AMBIGUOUS_BARE.match(text):
        return None            # 0700 could be HK or a US OTC code: the caller must say
    return "US"


def select_profile(
    *, market: str | None = None, symbol: str | None = None, profile: str | None = None
) -> MarketProfile:
    """Pick the profile for a run, refusing to guess when the identity is unclear.

    Precedence: explicit profile > explicit market > symbol suffix/format.
    A conflict between the two explicit arguments is an error, not a tie-break.
    """
    if profile:
        chosen = get_profile(profile)
        inferred = _market_for_symbol(symbol) if symbol else None
        if market and chosen.market != str(market).strip().upper():
            inferred = str(market).strip().upper()
        if inferred and chosen.market != inferred:
            raise ValueError(
                f"profile {chosen.key} is {chosen.market}, but the run identifies as {inferred}"
            )
        return chosen

    if market:
        code = str(market).strip().upper()
        inferred = _market_for_symbol(symbol) if symbol else None
        if inferred and inferred != code:
            raise ValueError(
                f"market={code} contradicts the symbol {symbol!r} (looks like {inferred})"
            )
        if code not in _KNOWN_MARKETS:
            raise ValueError(f"unknown market {market!r}; known: {sorted(_KNOWN_MARKETS)}")
        return CN_A_SHARE if code == "CN" else UPSTREAM_DEFAULT

    inferred = _market_for_symbol(symbol) if symbol else None
    if inferred is None:
        raise ValueError(
            f"cannot tell the market of {symbol!r}; pass market= (e.g. 'HK', 'US', 'CN') "
            "instead of relying on a guess"
        )
    return CN_A_SHARE if inferred == "CN" else UPSTREAM_DEFAULT
