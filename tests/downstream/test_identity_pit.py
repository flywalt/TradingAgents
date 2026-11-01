"""Identity over time: a name must be in force *and* public on the run date.

Tushare's stock_basic serves today's name; namechange carries the history with
both an effective window and an announcement date. Using the effective window
alone leaks a rename that had not been announced yet.
"""

from __future__ import annotations

import pandas as pd
import pytest

from tradingagents_cn.identity import resolve_identity_at
from tradingagents_cn.vendors.tushare import client

pytestmark = pytest.mark.unit

BASE = {
    "ts_code": "600519.SH", "area": "贵州", "industry": "白酒",
    "market": "主板", "list_date": "20010827", "delist_date": "", "list_status": "L",
}


class FakeApi:
    def __init__(self, changes):
        self.changes = changes

    def stock_basic(self, **kwargs):
        return pd.DataFrame([{**BASE, "name": "现名"}])

    def namechange(self, **kwargs):
        return pd.DataFrame(self.changes)


@pytest.fixture(autouse=True)
def no_cache(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_CN_CACHE", "off")


def _api():
    return FakeApi([
        {"name": "旧名", "start_date": "20150101", "end_date": "20240430", "ann_date": "20150101"},
        {"name": "新名", "start_date": "20240501", "end_date": "", "ann_date": "20240503"},
    ])


def test_a_rename_is_used_once_it_is_in_force_and_public():
    client.set_api(_api())
    try:
        identity = resolve_identity_at("600519.SH", "2026-10-30")
    finally:
        client.reset_api()

    assert identity["name"] == "新名"
    assert identity["name_source"] == "namechange"


def test_a_rename_announced_after_the_run_date_is_not_used():
    """Effective 2024-05-01 but announced 2024-05-03: invisible on 05-02."""
    client.set_api(_api())
    try:
        identity = resolve_identity_at("600519.SH", "2024-05-02")
    finally:
        client.reset_api()

    assert identity["name"] == "现名"
    assert identity["name_source"] == "stock_basic"


def test_an_old_run_gets_the_name_of_its_time():
    client.set_api(_api())
    try:
        identity = resolve_identity_at("600519.SH", "2020-01-01")
    finally:
        client.reset_api()

    assert identity["name"] == "旧名"


def test_a_missing_namechange_feed_degrades_to_todays_name():
    class NoFeed(FakeApi):
        def namechange(self, **kwargs):
            raise RuntimeError("no permission")

    client.set_api(NoFeed([]))
    try:
        identity = resolve_identity_at("600519.SH", "2026-10-30")
    finally:
        client.reset_api()

    assert identity["name"] == "现名"
    assert identity["name_source"] == "stock_basic"
