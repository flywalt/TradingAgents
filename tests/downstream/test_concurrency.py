"""Concurrency: two graphs, two vendor chains, no cross-contamination.

Registration is process-wide, so the only thing keeping runs apart is the
per-run ``run_config`` context. This test makes that real: two vendors that
sleep, many interleaved calls on threads, and an assertion that every answer came
from the chain its task asked for.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from tradingagents.dataflows.config import run_config
from tradingagents.dataflows.router import route_to_vendor
from tradingagents_cn.bootstrap import register_vendor, reset

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def two_vendors():
    def slow_alpha(symbol, start, end):
        time.sleep(0.01)
        return f"alpha:{symbol}"

    def slow_beta(symbol, start, end):
        time.sleep(0.01)
        return f"beta:{symbol}"

    register_vendor("get_stock_data", "cn_alpha", slow_alpha)
    register_vendor("get_stock_data", "cn_beta", slow_beta)
    try:
        yield
    finally:
        reset()


async def _call(chain: str, symbol: str) -> str:
    def task() -> str:
        with run_config({"data_vendors": {"core_stock_apis": chain}}):
            return route_to_vendor("get_stock_data", symbol, "2026-01-01", "2026-01-09")

    return await asyncio.to_thread(task)


def test_two_chains_running_in_parallel_never_cross():
    async def scenario():
        alpha = [_call("cn_alpha", "600519.SH") for _ in range(10)]
        beta = [_call("cn_beta", "000001.SZ") for _ in range(10)]
        return await asyncio.gather(*alpha, *beta)

    results = asyncio.run(scenario())

    assert results[:10] == ["alpha:600519.SH"] * 10
    assert results[10:] == ["beta:000001.SZ"] * 10


def test_a_run_context_does_not_leak_after_it_closes():
    with run_config({"data_vendors": {"core_stock_apis": "cn_alpha"}}):
        first = route_to_vendor("get_stock_data", "600519.SH", "2026-01-01", "2026-01-09")

    with run_config({"data_vendors": {"core_stock_apis": "cn_beta"}}):
        second = route_to_vendor("get_stock_data", "600519.SH", "2026-01-01", "2026-01-09")

    assert first.startswith("alpha:")
    assert second.startswith("beta:")
