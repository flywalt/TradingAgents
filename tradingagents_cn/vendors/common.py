"""Shared helpers for downstream vendor adapters.

Every adapter faces the same three questions, so they are answered once here:

* **Is this symbol ours?** A-share adapters sit first in a mixed chain
  (``tushare,yfinance``), so they must decline foreign symbols by raising
  ``NoMarketDataError`` — the router then moves to the next vendor instead of
  serving another market's prices under an A-share ticker.
* **Is the vendor configured?** A missing token raises
  ``VendorNotConfiguredError``, which the router treats as "this vendor cannot
  answer" and, if nothing else can, surfaces to the model as
  ``DATA_UNAVAILABLE``.
* **Which price basis?** ``cn_adjust`` selects 前复权/后复权/不复权; an adapter
  that silently serves unadjusted prices under a 复权 request corrupts every
  downstream comparison, so the basis is resolved here, once.
"""

from __future__ import annotations

import os

from tradingagents.dataflows.errors import NoMarketDataError, VendorNotConfiguredError
from tradingagents_cn.config import ADJUSTMENTS
from tradingagents_cn.symbols import try_normalize

#: How each ``cn_adjust`` setting is spelled by A-share vendors.
ADJUSTMENT_CODES = {"qfq": "qfq", "hfq": "hfq", "none": ""}


def require_ashare(symbol: str) -> str:
    """Canonical A-share symbol, or ``NoMarketDataError`` so the chain moves on."""
    canonical = try_normalize(symbol)
    if canonical is None:
        raise NoMarketDataError(
            symbol, canonical=symbol, detail="not an A-share symbol; this vendor serves CN only"
        )
    return canonical


def adjustment(config: dict) -> str:
    """The vendor's adjustment code for the run's ``cn_adjust`` setting."""
    value = str((config or {}).get("cn_adjust", "qfq")).lower()
    if value not in ADJUSTMENTS:
        raise ValueError(f"cn_adjust must be one of {ADJUSTMENTS}, got {value!r}")
    return ADJUSTMENT_CODES[value]


def require_token(vendor: str, env_var: str, *, environ: dict | None = None) -> str:
    """The vendor's API token, or ``VendorNotConfiguredError`` naming the variable."""
    source = os.environ if environ is None else environ
    token = (source.get(env_var) or "").strip()
    if not token:
        raise VendorNotConfiguredError(
            f"{vendor} needs {env_var} in the environment (or .env); "
            "the router will try the next vendor"
        )
    return token


def no_rows(symbol: str, canonical: str, detail: str = "vendor returned no rows") -> NoMarketDataError:
    """A ``NoMarketDataError`` for an empty (but successful) vendor answer."""
    return NoMarketDataError(symbol, canonical=canonical, detail=detail)
