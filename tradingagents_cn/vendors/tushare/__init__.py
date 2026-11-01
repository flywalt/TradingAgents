"""Tushare vendor: A-share daily bars (with the run's adjustment) and the calendar.

``register_vendors`` is called by ``tradingagents_cn.register.activate()``. The
SDK is optional and imported lazily, so the package (and its tests) work without
it installed; a call without the SDK or without ``TUSHARE_TOKEN`` raises
``VendorNotConfiguredError`` and the router moves to the next vendor.
"""

from __future__ import annotations

from tradingagents_cn.bootstrap import register_category, register_vendor

from .calendar import calendar_from_frame, load_calendar
from .client import TOKEN_ENV, TushareApi, get_api, reset_api, set_api
from .flows import (
    get_margin_detail,
    get_money_flow,
    get_northbound_holdings,
    get_top_list,
)
from .fundamentals import get_fundamentals
from .indicators import SUPPORTED_INDICATORS, get_stock_stats_indicators_window
from .statements import get_balance_sheet, get_cashflow, get_income_statement
from .stock import get_stock_data

#: The router methods this vendor serves. Only prices for now: fundamentals
#: (CAS statements) and capital flows follow as separate adapters.
PROVIDERS = {
    "get_stock_data": get_stock_data,
    "get_indicators": get_stock_stats_indicators_window,
    "get_fundamentals": get_fundamentals,
    "get_balance_sheet": get_balance_sheet,
    "get_cashflow": get_cashflow,
    "get_income_statement": get_income_statement,
    "get_money_flow": get_money_flow,
    "get_northbound_holdings": get_northbound_holdings,
    "get_margin_detail": get_margin_detail,
    "get_top_list": get_top_list,
}

#: Methods that live in the downstream capital-flow category.
CATEGORY = "cn_capital_flows"
FLOW_METHODS = frozenset(
    {"get_money_flow", "get_northbound_holdings", "get_margin_detail", "get_top_list"}
)


def register_vendors() -> None:
    """Register every Tushare implementation with upstream's router."""
    register_category(CATEGORY, "A-share capital flows (资金面): money flow, northbound, margin, 龙虎榜")
    for method, impl in PROVIDERS.items():
        category = CATEGORY if method in FLOW_METHODS else None
        register_vendor(method, "tushare", impl, category=category)


__all__ = [
    "SUPPORTED_INDICATORS",
    "TOKEN_ENV",
    "TushareApi",
    "PROVIDERS",
    "calendar_from_frame",
    "get_api",
    "get_balance_sheet",
    "get_margin_detail",
    "get_money_flow",
    "get_northbound_holdings",
    "get_top_list",
    "get_cashflow",
    "get_fundamentals",
    "get_income_statement",
    "get_stock_data",
    "get_stock_stats_indicators_window",
    "load_calendar",
    "register_vendors",
    "reset_api",
    "set_api",
]
