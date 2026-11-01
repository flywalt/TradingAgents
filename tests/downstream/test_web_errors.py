"""Error classification: the user-facing half of the error taxonomy."""

from __future__ import annotations

import pytest

from tradingagents.dataflows.errors import (
    NoMarketDataError,
    VendorNotConfiguredError,
    VendorUnavailableError,
)
from tradingagents_web import errors

pytestmark = pytest.mark.unit


def test_vendor_errors_map_to_distinct_categories():
    assert errors.classify(VendorNotConfiguredError("x")).category == "vendor_unconfigured"
    assert errors.classify(VendorUnavailableError("x")).category == "vendor_unavailable"
    assert errors.classify(NoMarketDataError("600519.SH")).category == "no_data"


def test_market_selection_errors_are_user_errors():
    ambiguous = errors.classify(ValueError("cannot tell the market of '0700'"))
    conflict = errors.classify(ValueError("market=US contradicts the symbol '600519.SS'"))
    strict = errors.classify(ValueError("cn_strict_ashare is an A-share vendor policy"))

    assert ambiguous.category == "symbol_ambiguous" and ambiguous.http_status == 400
    assert conflict.category == "symbol_conflict"
    assert strict.category == "strict_not_allowed"


def test_queue_full_and_report_write_have_their_own_categories():
    assert errors.classify(errors.QueueFullError()).category == "queue_full"
    assert errors.classify(errors.ReportWriteError("disk")).category == "report_write"


def test_checkpoint_dirty_worktree_maps_to_config_blocked():
    info = errors.classify(RuntimeError("checkpoint_enabled with an uncommitted worktree"))

    assert info.category == "config_blocked"


def test_unknown_exceptions_stay_internal():
    info = errors.classify(RuntimeError("boom"))

    assert info.category == "internal"
    assert "web.log" in info.action
