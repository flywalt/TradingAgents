"""The bootstrap facade: validated, idempotent, explicit, config-neutral.

These tests pin the four things the facade exists for: business code never
touches upstream's dictionaries, registration is checked, a graph cannot be
built before registration, and vendor *selection* stays per-run.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

from tradingagents.dataflows import router
from tradingagents.dataflows.config import run_config
from tradingagents.dataflows.errors import VendorUnavailableError

from tradingagents_cn.bootstrap import (
    bootstrap as boot,
    ensure_bootstrapped,
    is_bootstrapped,
    register_vendor,
    reset as reset_bootstrap,
)

pytestmark = pytest.mark.unit

PACKAGE = Path(__file__).resolve().parents[2] / "tradingagents_cn"


def test_only_the_facade_touches_upstream_registry_tables():
    """Business code goes through bootstrap; a grep is the cheapest enforcement."""
    offenders = []
    for path in PACKAGE.rglob("*.py"):
        if path.name == "bootstrap.py":
            continue
        text = path.read_text(encoding="utf-8")
        if re.search(r"VENDOR_METHODS|TOOLS_CATEGORIES", text):
            offenders.append(str(path.relative_to(PACKAGE.parent)))
    assert offenders == []


def test_a_wrong_arity_is_rejected_where_upstream_agrees_on_one():
    """get_stock_data ships two 3-arg implementations, so 2 args is a bug."""
    def two_args(symbol, start):
        return "x"

    with pytest.raises(TypeError, match="positional"):
        register_vendor("get_stock_data", "cn_bad", two_args)


def test_an_ambiguous_method_is_not_second_guessed():
    """get_indicators ships a 4-arg and a 7-arg implementation; no contract to enforce."""
    def two_args(symbol, indicator):
        return "x"

    assert register_vendor("get_indicators", "cn_loose", two_args) is True


def test_a_graph_cannot_be_built_before_bootstrap():
    reset_bootstrap()
    with pytest.raises(RuntimeError, match="bootstrap"):
        ensure_bootstrapped()

    boot()
    ensure_bootstrapped()          # no raise
    assert is_bootstrapped() is True


def test_bootstrap_is_idempotent_and_reports_it():
    first = boot()
    second = boot()

    assert first.already_active is False
    assert second.already_active is True
    assert first.vendors == second.vendors


def test_registration_is_global_but_selection_is_per_run():
    """Two runs with different chains must route to different vendors."""
    calls = []

    def alt_stock(symbol, start, end):
        calls.append("alt")
        return "alt data"

    def second_stock(symbol, start, end):
        calls.append("second")
        return "second data"

    register_vendor("get_stock_data", "cn_alt", alt_stock)
    register_vendor("get_stock_data", "cn_alt2", second_stock)
    try:
        with run_config({"data_vendors": {"core_stock_apis": "cn_alt"}}):
            text = router.route_to_vendor("get_stock_data", "600519.SH", "2026-01-01", "2026-01-09")
        assert text == "alt data"

        with run_config({"data_vendors": {"core_stock_apis": "cn_alt2"}}):
            text = router.route_to_vendor("get_stock_data", "600519.SH", "2026-01-01", "2026-01-09")
        assert text == "second data"
        assert calls == ["alt", "second"]
    finally:
        reset_bootstrap()


def test_strict_mode_never_falls_through_to_a_different_basis():
    """With a one-vendor chain, a vendor failure is an error, not Yahoo data."""

    def broken(symbol, start, end):
        raise VendorUnavailableError("throttled")

    reached = []

    def fallback(symbol, start, end):
        reached.append("fallback")
        return "different basis"

    register_vendor("get_stock_data", "tushare", broken, replace=True)
    register_vendor("get_stock_data", "yfinance", fallback, replace=True)
    with run_config({"data_vendors": {"core_stock_apis": "tushare"}}):
        text = router.route_to_vendor("get_stock_data", "600519.SH", "2026-01-01", "2026-01-09")

    # The single-vendor chain reports unavailable data; it never reaches Yahoo.
    assert text.startswith("DATA_UNAVAILABLE")
    assert reached == []


def test_the_public_entry_points_keep_their_signatures():
    assert list(inspect.signature(boot).parameters)[0] == "config"
    parameters = inspect.signature(register_vendor).parameters
    assert list(parameters)[:3] == ["method", "vendor", "impl"]
    assert parameters["replace"].default is False
