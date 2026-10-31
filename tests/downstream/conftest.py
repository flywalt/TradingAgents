"""Fixtures shared by the downstream tests.

Two rules, both learned from upstream's own suite:

* every test starts from upstream's router as it shipped — registrations are
  undone afterwards, so test order can never leak a vendor into another test;
* nothing here touches the network or a real API key.
"""

import pytest

from tradingagents_cn import calendar as cn_calendar, register as cn_register


def _router():
    from tradingagents.dataflows import router

    return router


@pytest.fixture(autouse=True)
def clean_downstream_state():
    """Undo registrations and calendar installs around every downstream test."""
    router = _router()
    vendors_before = {method: dict(impls) for method, impls in router.VENDOR_METHODS.items()}
    tools_before = {
        category: list(info["tools"]) for category, info in router.TOOLS_CATEGORIES.items()
    }
    cn_register.reset()
    cn_calendar.set_default_calendar(None)
    try:
        yield
    finally:
        cn_register.reset()
        cn_calendar.set_default_calendar(None)
        for method, impls in vendors_before.items():
            router.VENDOR_METHODS[method] = dict(impls)
        for method in list(router.VENDOR_METHODS):
            if method not in vendors_before:
                router.VENDOR_METHODS.pop(method, None)
        for category, tools in tools_before.items():
            router.TOOLS_CATEGORIES[category]["tools"] = list(tools)


@pytest.fixture
def fake_impl():
    """A cheap stand-in for a vendor implementation."""

    def impl(*args, **kwargs):
        return "ok"

    return impl
