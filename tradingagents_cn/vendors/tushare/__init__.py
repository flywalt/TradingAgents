"""Tushare vendor: A-share daily bars (with the run's adjustment) and the calendar.

``register_vendors`` is called by ``tradingagents_cn.register.activate()``. The
SDK is optional and imported lazily, so the package (and its tests) work without
it installed; a call without the SDK or without ``TUSHARE_TOKEN`` raises
``VendorNotConfiguredError`` and the router moves to the next vendor.
"""

from __future__ import annotations

from tradingagents_cn.register import register_vendor

from .calendar import calendar_from_frame, load_calendar
from .client import TOKEN_ENV, TushareApi, get_api, reset_api, set_api
from .fundamentals import get_fundamentals
from .indicators import SUPPORTED_INDICATORS, get_stock_stats_indicators_window
from .stock import get_stock_data

#: The router methods this vendor serves. Only prices for now: fundamentals
#: (CAS statements) and capital flows follow as separate adapters.
VENDOR_METHODS = {
    "get_stock_data": get_stock_data,
    "get_indicators": get_stock_stats_indicators_window,
    "get_fundamentals": get_fundamentals,
}


def register_vendors() -> None:
    """Register every Tushare implementation with upstream's router."""
    for method, impl in VENDOR_METHODS.items():
        register_vendor(method, "tushare", impl)


__all__ = [
    "SUPPORTED_INDICATORS",
    "TOKEN_ENV",
    "TushareApi",
    "VENDOR_METHODS",
    "calendar_from_frame",
    "get_api",
    "get_fundamentals",
    "get_stock_data",
    "get_stock_stats_indicators_window",
    "load_calendar",
    "register_vendors",
    "reset_api",
    "set_api",
]
