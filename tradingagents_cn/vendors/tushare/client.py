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

import threading

from tradingagents.dataflows.errors import VendorNotConfiguredError
from tradingagents_cn.vendors.common import require_token

#: Environment variable holding the Tushare token.
TOKEN_ENV = "TUSHARE_TOKEN"

_lock = threading.Lock()
_api = None


class TushareApi:
    """The two Tushare calls this layer makes, bound to an authenticated client."""

    def __init__(self, pro):
        self._pro = pro

    def pro_bar(self, **kwargs):
        """Adjusted/unadjusted daily bars (``ts.pro_bar``, which also needs ``api``)."""
        import tushare as ts

        return ts.pro_bar(api=self._pro, **kwargs)

    def trade_cal(self, **kwargs):
        """The exchange calendar (``pro.trade_cal``)."""
        return self._pro.trade_cal(**kwargs)


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
