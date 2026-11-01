"""Superset C of the sync guard: a changed extension must invalidate checkpoints.

Resuming a run whose node behaviour changed underneath it silently mixes two
versions of the analysis. Upstream hashes the run config into the checkpoint
thread id; these tests prove that the downstream version and the indicator
flavour actually reach that hash, using only the public ``checkpoint_scope``
API (never the private signature string, which is an implementation detail).
"""

from __future__ import annotations

import pandas as pd
import pytest

from tradingagents.graph import trading_graph as upstream_graph
from tradingagents_cn import config as cn_config
from tradingagents_cn.bootstrap import reset
from tradingagents_cn.graph.factory import build_graph
from tradingagents_cn.vendors.tushare import client

pytestmark = pytest.mark.unit

TICKER = "600519.SH"
TRADE_DATE = "2026-10-30"


class DummyClient:
    def get_llm(self):
        return None


class FakeApi:
    def stock_basic(self, **kwargs):
        return pd.DataFrame([{
            "ts_code": TICKER, "name": "贵州茅台", "area": "贵州", "industry": "白酒",
            "market": "主板", "list_date": "20010827", "delist_date": "", "list_status": "L",
        }])


@pytest.fixture(autouse=True)
def offline(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_CN_CACHE", "off")
    monkeypatch.setattr(upstream_graph, "create_tier_client", lambda config, tier, **k: DummyClient())
    client.set_api(FakeApi())
    try:
        yield tmp_path
    finally:
        client.reset_api()
        reset()


def _graph(tmp_path, **overrides):
    cfg = cn_config.apply({
        "results_dir": str(tmp_path / "results"),
        "data_cache_dir": str(tmp_path / "cache"),
        "memory_log_path": str(tmp_path / "memory.md"),
        "llm_provider": "openai",
        "checkpoint_enabled": True,
        # The test suite runs from a possibly-dirty tree; the dirty guard has its
        # own two tests below.
        "cn_allow_dirty_checkpoint": True,
        **overrides,
    })
    return build_graph(config=cfg)


def _thread_id(graph):
    with graph.checkpoint_scope(TICKER, TRADE_DATE) as thread:
        assert thread
        return thread


def test_checkpointing_off_yields_no_thread(tmp_path):
    graph = _graph(tmp_path, checkpoint_enabled=False)

    assert graph.begin_checkpoint(TICKER, TRADE_DATE) is None


def test_the_same_configuration_resumes_the_same_thread(tmp_path):
    first = _thread_id(_graph(tmp_path))
    second = _thread_id(_graph(tmp_path))

    assert first == second


def test_an_extension_version_change_starts_a_fresh_thread(tmp_path):
    old = _thread_id(_graph(tmp_path))
    new = _thread_id(_graph(tmp_path, cn_extension_version="9.9.9"))

    assert old != new


def test_an_indicator_flavour_change_starts_a_fresh_thread(tmp_path):
    tdx = _thread_id(_graph(tmp_path, cn_indicator_flavor="tdx"))
    stockstats = _thread_id(_graph(tmp_path, cn_indicator_flavor="stockstats"))

    assert tdx != stockstats


def test_the_extension_version_reaches_the_run_config(tmp_path):
    graph = _graph(tmp_path)

    assert graph.config["cn_extension_version"]
    assert "cn_extension_version" in graph.config


def test_a_dirty_worktree_refuses_resumable_checkpoints(tmp_path, monkeypatch):
    from tradingagents_cn.graph import factory as graph_factory

    monkeypatch.setattr(graph_factory, "worktree_dirty", lambda: True)
    with pytest.raises(RuntimeError, match="uncommitted worktree"):
        _graph(tmp_path, cn_allow_dirty_checkpoint=False)


def test_the_dirty_guard_can_be_lifted_for_development(tmp_path, monkeypatch):
    from tradingagents_cn.graph import factory as graph_factory

    monkeypatch.setattr(graph_factory, "worktree_dirty", lambda: True)

    graph = _graph(tmp_path, cn_allow_dirty_checkpoint=True)

    assert graph.config["cn_allow_dirty_checkpoint"] is True
