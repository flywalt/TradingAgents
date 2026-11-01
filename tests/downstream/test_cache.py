"""TTL cache and call throttling.

The cache exists because a backtest calls the same endpoint dozens of times and
the account's quota is finite; it must therefore be correct (never serve another
adjustment's bars), bounded (TTL), and switchable off. Tests use their own
directory so a developer's real cache is never read or written.
"""

from __future__ import annotations

import os
import time

import pytest

from tradingagents_cn import cache
from tradingagents_cn.vendors.tushare import client

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_CN_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("TRADINGAGENTS_CN_CACHE", raising=False)
    cache.reset_memory_cache()
    cache.clear()
    yield tmp_path
    cache.reset_memory_cache()


def test_a_second_call_is_served_from_memory_or_disk():
    calls = []

    def producer():
        calls.append(1)
        return {"rows": 1}

    assert cache.cached("probe", "k", 60, producer) == {"rows": 1}
    assert cache.cached("probe", "k", 60, producer) == {"rows": 1}
    assert len(calls) == 1


def test_an_expired_entry_is_refetched(isolated_cache):
    calls = []

    def producer():
        calls.append(1)
        return "v"

    cache.cached("probe", "k", 60, producer)
    assert len(calls) == 1

    for path in isolated_cache.rglob("*.pkl"):
        old = time.time() - 7200
        os.utime(path, (old, old))
    cache.reset_memory_cache()

    cache.cached("probe", "k", 60, producer)
    assert len(calls) == 2


def test_a_corrupt_entry_is_a_miss_not_a_crash(isolated_cache):
    cache.cached("probe", "k", 60, lambda: "first")
    for path in isolated_cache.rglob("*.pkl"):
        path.write_bytes(b"not a pickle")
    cache.reset_memory_cache()

    assert cache.cached("probe", "k", 60, lambda: "second") == "second"


def test_different_keys_never_share_an_entry():
    calls = []

    def producer(tag):
        def inner():
            calls.append(tag)
            return tag

        return inner

    cache.cached("probe", "600519.SH|qfq|2026-01-01|2026-01-09", 60, producer("a"))
    cache.cached("probe", "600519.SH|hfq|2026-01-01|2026-01-09", 60, producer("b"))
    cache.cached("probe", "600519.SH|qfq|2026-01-02|2026-01-09", 60, producer("c"))

    assert calls == ["a", "b", "c"]


def test_the_cache_can_be_switched_off(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_CN_CACHE", "off")
    calls = []

    def producer():
        calls.append(1)
        return "v"

    cache.cached("probe", "k", 60, producer)
    cache.cached("probe", "k", 60, producer)

    assert len(calls) == 2
    assert not list(cache._root().rglob("*.pkl"))


def test_clear_removes_files_and_memory(tmp_path):
    cache.cached("probe", "k", 60, lambda: "v")
    assert list(tmp_path.rglob("*.pkl"))

    cache.clear()

    assert not list(tmp_path.rglob("*.pkl"))
    assert cache.cached("probe", "k", 60, lambda: "again") == "again"


def test_throttle_waits_between_calls(monkeypatch):
    slept = []
    monkeypatch.setattr(client.time, "sleep", lambda seconds: slept.append(seconds))
    monkeypatch.setattr(client, "_last_call", None)
    monkeypatch.setenv("TRADINGAGENTS_CN_MIN_INTERVAL", "0.2")

    client.throttle()
    assert slept == []                       # the first call never waits

    client.throttle()
    assert len(slept) == 1
    assert 0.15 < slept[0] <= 0.2


def test_min_interval_defaults_to_a_quota_safe_value(monkeypatch):
    monkeypatch.delenv("TRADINGAGENTS_CN_MIN_INTERVAL", raising=False)
    assert client.min_interval() == pytest.approx(0.15)


def test_an_invalid_interval_fails_loudly(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_CN_MIN_INTERVAL", "fast")
    with pytest.raises(ValueError, match="TRADINGAGENTS_CN_MIN_INTERVAL"):
        client.min_interval()

    monkeypatch.setenv("TRADINGAGENTS_CN_MIN_INTERVAL", "-1")
    with pytest.raises(ValueError, match="TRADINGAGENTS_CN_MIN_INTERVAL"):
        client.min_interval()
