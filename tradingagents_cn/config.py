"""Downstream configuration for A-share runs.

Upstream's config is a free-form dict (``tradingagents.default_config``), and
``dataflows.config.set_config`` merges dict-valued keys one level deep. That is
enough to add downstream settings without touching upstream code:

* own keys are namespaced ``cn_*`` so they can never collide with a future
  upstream key;
* vendor routing is expressed through upstream's own ``data_vendors`` /
  ``tool_vendors`` keys, so the router needs no downstream knowledge;
* ``build_config`` is pure — it deep-copies, merges, and returns; it never
  mutates ``DEFAULT_CONFIG`` or the caller's dict.

Vendor chains are ordered, and that order is the symbol router: the A-share
adapter raises ``NoMarketDataError`` for a non-A-share symbol, so
``"tushare,yfinance"`` serves A-share tickers from Tushare and everything else
from Yahoo without any per-symbol branching.
"""

from __future__ import annotations

import os
from copy import deepcopy

#: Keys this layer owns. The ``cn_`` prefix keeps them apart from upstream's.
DEFAULT_CN_CONFIG: dict = {
    #: Which market the downstream layer treats as its own.
    "cn_market": "ashare",
    #: Price adjustment every A-share vendor serves: "qfq" (前复权), "hfq"
    #: (后复权) or "none" (不复权). Comparing prices across adjustments is a bug.
    "cn_adjust": "qfq",
    #: Extra exchange closures for the offline calendar, ISO dates. The Tushare
    #: ``trade_cal`` replaces this once its vendor is activated.
    "cn_calendar_holidays": (),
    #: Whether Beijing Stock Exchange symbols are in scope.
    "cn_include_bj": True,
    #: Strict A-share mode: chains become Tushare-only, so a Tushare outage is
    #: reported as unavailable instead of silently served from Yahoo (a
    #: different price basis). Off by default so US tickers keep working.
    "cn_strict_ashare": False,
}

#: Ordered vendor chain installed per data category. Only the categories the
#: downstream vendors actually serve are listed; anything missing keeps
#: upstream's own default, so unrelated data paths are unaffected.
VENDOR_CHAIN_DEFAULTS: dict[str, tuple[str, ...]] = {
    "core_stock_apis": ("tushare", "yfinance"),
    "technical_indicators": ("tushare", "yfinance"),
    "fundamental_data": ("tushare", "yfinance"),
}

_ENV_OVERRIDES = {
    "TRADINGAGENTS_CN_MARKET": "cn_market",
    "TRADINGAGENTS_CN_ADJUST": "cn_adjust",
    "TRADINGAGENTS_CN_INCLUDE_BJ": "cn_include_bj",
    "TRADINGAGENTS_CN_STRICT_ASHARE": "cn_strict_ashare",
}

_TRUE = ("true", "1", "yes", "on")
_FALSE = ("false", "0", "no", "off")

ADJUSTMENTS = ("qfq", "hfq", "none")


def _coerce(value: str, reference):
    """Coerce an env-var string to the type of the default it overrides."""
    if isinstance(reference, bool):
        normalized = value.strip().lower()
        if normalized in _TRUE:
            return True
        if normalized in _FALSE:
            return False
        raise ValueError(f"expected a boolean ({'/'.join(_TRUE + _FALSE)}), got {value!r}")
    if isinstance(reference, int) and not isinstance(reference, bool):
        return int(value)
    if isinstance(reference, float):
        return float(value)
    return value


def env_overrides(environ: dict | None = None) -> dict:
    """The ``TRADINGAGENTS_CN_*`` variables as config keys.

    Invalid values raise ``ValueError`` instead of silently falling back: a
    misspelled adjustment would otherwise produce a run that mixes price bases.
    """
    source = os.environ if environ is None else environ
    overlay = {}
    for env_var, key in _ENV_OVERRIDES.items():
        raw = source.get(env_var)
        if raw is None or raw == "":
            continue
        try:
            overlay[key] = _coerce(raw, DEFAULT_CN_CONFIG[key])
        except ValueError as exc:
            raise ValueError(f"Invalid value for {env_var}: {exc}") from exc
    return overlay


def vendor_chain(
    categories: dict[str, tuple[str, ...]] | None = None, *, strict: bool = False
) -> dict:
    """A ``data_vendors`` fragment for the categories downstream vendors serve.

    ``strict`` keeps only the first (A-share) vendor of each chain, so a Tushare
    failure surfaces as unavailable data rather than as a silent switch to a
    different price basis.
    """
    chosen = VENDOR_CHAIN_DEFAULTS if categories is None else categories
    if strict:
        chosen = {category: vendors[:1] for category, vendors in chosen.items()}
    return {category: ",".join(vendors) for category, vendors in chosen.items()}


def build_config(
    base: dict | None = None,
    *,
    environ: dict | None = None,
    install_vendor_chain: bool = True,
    override_vendor_chain: bool = False,
) -> dict:
    """Merge downstream defaults over ``base`` (``DEFAULT_CONFIG`` when omitted).

    Precedence, lowest to highest: downstream defaults, ``base``, env overrides.
    An explicit ``base["data_vendors"][category]`` wins over the installed chain
    unless ``override_vendor_chain`` asks for the chain — a caller who chose a
    vendor must not be silently overridden.
    """
    merged = deepcopy(base) if base is not None else {}

    for key, value in DEFAULT_CN_CONFIG.items():
        merged.setdefault(key, deepcopy(value))

    merged.update(env_overrides(environ))
    _validate(merged)

    if install_vendor_chain:
        vendors = merged.get("data_vendors")
        if not isinstance(vendors, dict):
            vendors = merged["data_vendors"] = {}
        chain = vendor_chain(strict=bool(merged.get("cn_strict_ashare")))
        for category, chain_value in chain.items():
            if override_vendor_chain or category not in vendors:
                vendors[category] = chain_value
    return merged


def _validate(config: dict) -> None:
    adjust = config.get("cn_adjust")
    if adjust is not None and str(adjust).lower() not in ADJUSTMENTS:
        raise ValueError(f"cn_adjust must be one of {ADJUSTMENTS}, got {adjust!r}")
    config["cn_adjust"] = str(adjust).lower()


def apply(
    overrides: dict | None = None,
    *,
    environ: dict | None = None,
    install_vendor_chain: bool = True,
) -> dict:
    """Downstream config over upstream's ``DEFAULT_CONFIG``, with ``overrides`` on top.

    Precedence, lowest to highest: downstream defaults, upstream defaults,
    ``overrides``, ``TRADINGAGENTS_CN_*`` env vars. Env wins so a deployment can
    pin a mode (e.g. strict A-share chains) that application code cannot
    silently downgrade. The result is always a full config (upstream keys
    included), so it can go straight into ``TradingAgentsGraph(config=...)``.

    Vendor chains are installed last, from the *final* ``cn_strict_ashare``, and
    skip any category the caller set explicitly — a caller who chose a vendor
    must not be overridden by a mode flag.
    """
    from tradingagents.default_config import DEFAULT_CONFIG

    explicit = deepcopy(overrides or {})
    merged = deepcopy(DEFAULT_CONFIG)
    for key, value in DEFAULT_CN_CONFIG.items():
        merged.setdefault(key, deepcopy(value))
    merged = _overlay(merged, explicit)
    merged.update(env_overrides(environ))
    _validate(merged)

    if install_vendor_chain:
        vendors = merged.get("data_vendors")
        if not isinstance(vendors, dict):
            vendors = merged["data_vendors"] = {}
        chosen = explicit.get("data_vendors") or {}
        chain = vendor_chain(strict=bool(merged.get("cn_strict_ashare")))
        for category, chain_value in chain.items():
            if category not in chosen:
                vendors[category] = chain_value
    return merged


def _overlay(base: dict, overlay: dict) -> dict:
    """Merge ``overlay`` into ``base``: dict values one level deep, scalars replace."""
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key].update(deepcopy(value))
        else:
            base[key] = value
    return base
