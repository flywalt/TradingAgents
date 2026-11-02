"""Live CLS checks against the self-hosted RSSHub (needs RSSHUB_* in .env)."""

from __future__ import annotations

import os
from datetime import date, timedelta

import pytest

pytestmark = pytest.mark.integration


def _skip() -> None:
    if not os.environ.get("RSSHUB_BASE_URL") or not os.environ.get("RSSHUB_TOKEN"):
        pytest.skip("RSSHUB_BASE_URL/RSSHUB_TOKEN are not set")


def test_live_announcement_stream_carries_codes():
    _skip()
    from tradingagents_cn.vendors import cls

    end = date.today()
    items = cls.fetch_telegraph("announcement", (end - timedelta(days=3)).isoformat(), end.isoformat())

    assert len(items) >= 10
    with_codes = [item for item in items if item["codes"]]
    assert len(with_codes) >= len(items) * 0.7, "code coverage dropped below the observed ~87%"


def test_live_market_radar_answers():
    _skip()
    from tradingagents_cn.vendors import cls

    end = date.today()
    items = cls.fetch_telegraph("all", (end - timedelta(days=1)).isoformat(), end.isoformat())

    assert items
