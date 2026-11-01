"""Tushare access: one lazy, authenticated client and the seam tests use.

Two rules keep this small:

* the SDK is imported only when a call is actually made, so importing the
  package (and running the test suite) never needs ``tushare`` installed;
* every call goes through ``TushareApi``, whose instance can be replaced with a
  fake (``set_api``), so the adapter is tested offline.

The token lives in ``TUSHARE_TOKEN`` (``.env`` or the environment) and is never
logged, written to a report, or echoed in an error message.
"""

from __future__ import annotations

import os
import threading
import time

from tradingagents.dataflows.errors import VendorNotConfiguredError
from tradingagents_cn.vendors.common import require_token

#: Environment variable holding the Tushare token.
TOKEN_ENV = "TUSHARE_TOKEN"

_lock = threading.Lock()
_api = None
_last_call: float | None = None

#: Seconds between real calls, the safe rate for a 2000-point account.
DEFAULT_MIN_INTERVAL = 0.15


def min_interval() -> float:
    """Seconds to leave between calls (``TRADINGAGENTS_CN_MIN_INTERVAL``, default 0.15)."""
    raw = os.environ.get("TRADINGAGENTS_CN_MIN_INTERVAL")
    if raw is None or not raw.strip():
        return DEFAULT_MIN_INTERVAL
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(
            f"TRADINGAGENTS_CN_MIN_INTERVAL must be a number of seconds, got {raw!r}"
        ) from exc
    if value < 0:
        raise ValueError(f"TRADINGAGENTS_CN_MIN_INTERVAL cannot be negative, got {value}")
    return value


def throttle() -> None:
    """Sleep so two calls are at least ``min_interval()`` apart."""
    global _last_call
    interval = min_interval()
    if interval and _last_call is not None:
        remaining = interval - (time.monotonic() - _last_call)
        if remaining > 0:
            time.sleep(remaining)
    _last_call = time.monotonic()


class TushareApi:
    """The two Tushare calls this layer makes, bound to an authenticated client."""

    def __init__(self, pro):
        self._pro = pro

    def pro_bar(self, **kwargs):
        """Adjusted/unadjusted daily bars (``ts.pro_bar``, which also needs ``api``)."""
        import tushare as ts

        throttle()
        return ts.pro_bar(api=self._pro, **kwargs)

    def trade_cal(self, **kwargs):
        """The exchange calendar (``pro.trade_cal``)."""
        return self._call("trade_cal", **kwargs)

    def stock_basic(self, **kwargs):
        """Company profile: name, industry, area, board, listing date."""
        return self._call("stock_basic", **kwargs)

    def namechange(self, **kwargs):
        """Historical name changes with effective and announcement dates."""
        return self._call("namechange", **kwargs)

    def daily_basic(self, **kwargs):
        """Valuation and trading snapshot for a session (PE/PB/PS/市值/换手)."""
        return self._call("daily_basic", **kwargs)

    def fina_indicator(self, **kwargs):
        """Financial-indicator summary per report period (EPS, ROE, margins)."""
        return self._call("fina_indicator", **kwargs)

    def income(self, **kwargs):
        """Income statement (CAS, 利润表)."""
        return self._call("income", **kwargs)

    def balancesheet(self, **kwargs):
        """Balance sheet (CAS, 资产负债表)."""
        return self._call("balancesheet", **kwargs)

    def cashflow(self, **kwargs):
        """Cash-flow statement (CAS, 现金流量表)."""
        return self._call("cashflow", **kwargs)

    def moneyflow(self, **kwargs):
        """Per-stock order-flow breakdown."""
        return self._call("moneyflow", **kwargs)

    def hk_hold(self, **kwargs):
        """Northbound (Stock Connect) holdings; per-stock disclosure ended 2024-08-16."""
        return self._call("hk_hold", **kwargs)

    def margin_detail(self, **kwargs):
        """Margin-financing and short-selling balances."""
        return self._call("margin_detail", **kwargs)

    def top_list(self, **kwargs):
        """Dragon-Tiger list (龙虎榜) for a trade date."""
        return self._call("top_list", **kwargs)

    def index_daily(self, **kwargs):
        """Index daily bars."""
        return self._call("index_daily", **kwargs)

    def index_weight(self, **kwargs):
        """Index constituent weights for a published trade date."""
        return self._call("index_weight", **kwargs)

    def index_member_all(self, **kwargs):
        """Shenwan industry classification (NOT index constituents)."""
        return self._call("index_member_all", **kwargs)

    def _call(self, endpoint: str, **kwargs):
        """Throttled call to a ``pro`` endpoint, by name."""
        throttle()
        return getattr(self._pro, endpoint)(**kwargs)


def _build_api() -> TushareApi:
    """Authenticate a real client; the only place the SDK is imported."""
    token = require_token("tushare", TOKEN_ENV)
    try:
        import tushare as ts
    except ModuleNotFoundError as exc:  # optional downstream dependency
        raise VendorNotConfiguredError(
            "tushare is not installed; run: pip install tushare"
        ) from exc
    ts.set_token(token)
    return TushareApi(ts.pro_api(token))


def get_api() -> TushareApi:
    """The process-wide client, built on first use."""
    global _api
    with _lock:
        if _api is None:
            _api = _build_api()
        return _api


def set_api(api) -> None:
    """Install a client (a fake in tests, or one with a pre-resolved token)."""
    global _api
    _api = api


def reset_api() -> None:
    """Forget the client, so the next call authenticates again."""
    global _api
    _api = None
