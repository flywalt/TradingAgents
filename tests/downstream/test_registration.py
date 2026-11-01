"""Registration behaviour: explicit, idempotent, reversible.

The router's tables are module-level dicts, so these tests care as much about
*not* changing them as about changing them: an import that registers something
would be invisible to every other test in the suite.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from tradingagents_cn import register as cn_register

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]


def _router():
    from tradingagents.dataflows import router

    return router


def test_importing_the_package_registers_nothing():
    """A fresh interpreter: import the upstream router, snapshot, import us, compare."""
    script = (
        "from tradingagents.dataflows import router\n"
        "before = {m: sorted(v) for m, v in router.VENDOR_METHODS.items()}\n"
        "tools_before = {c: list(i['tools']) for c, i in router.TOOLS_CATEGORIES.items()}\n"
        "import tradingagents_cn\n"
        "after = {m: sorted(v) for m, v in router.VENDOR_METHODS.items()}\n"
        "tools_after = {c: list(i['tools']) for c, i in router.TOOLS_CATEGORIES.items()}\n"
        "print('SAME' if (before == after and tools_before == tools_after) else 'CHANGED')\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    )
    assert completed.stdout.strip().endswith("SAME"), completed.stdout + completed.stderr


def test_registering_a_vendor_for_an_existing_method_is_idempotent(fake_impl):
    router = _router()
    assert "cn_probe" not in router.VENDOR_METHODS["get_stock_data"]

    assert cn_register.register_vendor("get_stock_data", "cn_probe", fake_impl) is True
    assert router.VENDOR_METHODS["get_stock_data"]["cn_probe"] is fake_impl

    assert cn_register.register_vendor("get_stock_data", "cn_probe", fake_impl) is False
    assert cn_register.registered_vendors() == (("get_stock_data", "cn_probe"),)


def test_registering_a_new_method_requires_and_records_its_category(fake_impl):
    router = _router()

    with pytest.raises(ValueError, match="category"):
        cn_register.register_vendor("get_northbound_flow", "cn_probe", fake_impl)
    with pytest.raises(ValueError, match="category"):
        cn_register.register_vendor("get_northbound_flow", "cn_probe", fake_impl, category="nope")

    assert cn_register.register_vendor(
        "get_northbound_flow", "cn_probe", fake_impl, category="news_data"
    )
    assert router.VENDOR_METHODS["get_northbound_flow"] == {"cn_probe": fake_impl}
    assert "get_northbound_flow" in router.TOOLS_CATEGORIES["news_data"]["tools"]
    assert router.get_category_for_method("get_northbound_flow") == "news_data"


def test_invalid_registrations_are_rejected(fake_impl):
    with pytest.raises(ValueError):
        cn_register.register_vendor("", "cn_probe", fake_impl)
    with pytest.raises(ValueError):
        cn_register.register_vendor("get_stock_data", "CN Probe", fake_impl)
    with pytest.raises(ValueError):
        cn_register.register_vendor("get_stock_data", "9probe", fake_impl)
    with pytest.raises(TypeError):
        cn_register.register_vendor("get_stock_data", "cn_probe", "not callable")


def test_a_conflicting_registration_is_refused_unless_replacement_is_explicit():
    def first(*args, **kwargs):
        return "first"

    def second(*args, **kwargs):
        return "second"

    router = _router()
    assert cn_register.register_vendor("get_stock_data", "cn_probe", first)

    with pytest.raises(ValueError, match="already registered"):
        cn_register.register_vendor("get_stock_data", "cn_probe", second)
    assert router.VENDOR_METHODS["get_stock_data"]["cn_probe"] is first

    assert cn_register.register_vendor("get_stock_data", "cn_probe", second, replace=True)
    assert router.VENDOR_METHODS["get_stock_data"]["cn_probe"] is second


def test_reset_restores_the_upstream_router(fake_impl):
    router = _router()
    before = {method: sorted(impls) for method, impls in router.VENDOR_METHODS.items()}
    tools_before = {
        category: list(info["tools"]) for category, info in router.TOOLS_CATEGORIES.items()
    }

    cn_register.register_vendor("get_stock_data", "cn_probe", fake_impl)
    cn_register.register_vendor("get_probe_only", "cn_probe", fake_impl, category="news_data")
    cn_register.reset()

    assert {m: sorted(v) for m, v in router.VENDOR_METHODS.items()} == before
    assert {
        category: list(info["tools"]) for category, info in router.TOOLS_CATEGORIES.items()
    } == tools_before
    assert cn_register.registered_vendors() == ()
    assert cn_register.is_active() is False
