"""Instrument resolver wiring: one override, all twelve agents.

The test proves the flow the requirement cares about — resolver → state →
prompts — without depending on prompt wording: the resolver is exercised
directly, the state is inspected after ``create_run_state``, and every agent
module is checked for the interpolation that carries the value.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pandas as pd
import pytest

from tradingagents.dataflows.date_window import get_current_date
from tradingagents.graph import trading_graph as upstream_graph
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents_cn import config as cn_config
from tradingagents_cn.bootstrap import bootstrap, reset
from tradingagents_cn.graph.factory import build_graph
from tradingagents_cn.graph.trading_graph import CnTradingAgentsGraph
from tradingagents_cn.vendors.tushare import client

pytestmark = pytest.mark.unit

AGENTS_DIR = Path(__file__).resolve().parents[2] / "tradingagents" / "agents"


class FakeApi:
    def __init__(self, row=None, error=None):
        self.row = row if row is not None else {
            "ts_code": "600519.SH",
            "name": "贵州茅台",
            "area": "贵州",
            "industry": "白酒",
            "market": "主板",
            "list_date": "20010827",
            "delist_date": "",
            "list_status": "L",
        }
        self.error = error

    def stock_basic(self, **kwargs):
        if self.error is not None:
            raise self.error
        return pd.DataFrame([self.row])


class DummyClient:
    def get_llm(self):
        return None


@pytest.fixture(autouse=True)
def no_cache(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_CN_CACHE", "off")


@pytest.fixture
def ashare_api():
    fake = FakeApi()
    client.set_api(fake)
    try:
        yield fake
    finally:
        client.reset_api()


@pytest.fixture
def graph(tmp_path, monkeypatch, ashare_api):
    monkeypatch.setattr(upstream_graph, "create_tier_client", lambda config, tier, **k: DummyClient())
    cfg = cn_config.apply({
        "results_dir": str(tmp_path / "results"),
        "data_cache_dir": str(tmp_path / "cache"),
        "memory_log_path": str(tmp_path / "memory.md"),
        "llm_provider": "openai",
    })
    return build_graph(config=cfg)


def test_the_downstream_signatures_match_upstream_exactly():
    assert (inspect.signature(CnTradingAgentsGraph.resolve_instrument_context)
            == inspect.signature(TradingAgentsGraph.resolve_instrument_context))
    assert (inspect.signature(CnTradingAgentsGraph.__init__)
            == inspect.signature(TradingAgentsGraph.__init__))


def test_current_a_share_context_names_the_company_and_its_industry(graph):
    context = graph.resolve_instrument_context("600519.SH", "stock", get_current_date())

    assert "600519.SH" in context
    assert "贵州茅台" in context
    assert "Industry: 白酒" in context
    assert "Resolved identity" in context


def test_a_historical_run_keeps_the_name_but_not_todays_classification(graph):
    context = graph.resolve_instrument_context("600519.SH", "stock", "2026-09-30")

    assert "贵州茅台" in context
    assert "Industry:" not in context          # upstream's PIT rule, inherited


def test_a_run_before_listing_gets_no_identity(graph):
    context = graph.resolve_instrument_context("600519.SH", "stock", "2000-01-01")

    assert "贵州茅台" not in context
    assert "600519.SH" in context


def test_a_run_after_delisting_gets_no_identity(ashare_api, graph):
    ashare_api.row = {**ashare_api.row, "delist_date": "20200101"}

    context = graph.resolve_instrument_context("600519.SH", "stock", "2026-10-30")

    assert "贵州茅台" not in context


def test_a_foreign_ticker_falls_back_to_the_upstream_resolver(graph, monkeypatch):
    monkeypatch.setattr(
        upstream_graph, "resolve_instrument_identity",
        lambda ticker: {"name": "Apple Inc.", "sector": "Technology", "industry": "Consumer Electronics"},
    )

    context = graph.resolve_instrument_context("AAPL", "stock", "2026-10-30")

    assert "Apple Inc." in context


def test_a_profile_outage_degrades_instead_of_failing_the_run(ashare_api, graph):
    ashare_api.error = RuntimeError("quota exceeded")

    context = graph.resolve_instrument_context("600519.SH", "stock", "2026-10-30")

    assert "600519.SH" in context
    assert "贵州茅台" not in context


def test_the_identity_reaches_the_run_state(graph):
    state = graph.create_run_state("600519.SH", "2026-10-30")

    assert "贵州茅台" in state["instrument_context"]


def test_every_agent_module_interpolates_the_identity_context():
    modules = sorted(path for path in AGENTS_DIR.glob("*/*.py") if path.name != "__init__.py")
    with_context = [path for path in modules if "instrument_context" in path.read_text(encoding="utf-8")]

    assert len(with_context) == 12, [path.name for path in modules if path not in with_context]


def test_a_graph_cannot_be_built_before_registration(tmp_path, monkeypatch):
    monkeypatch.setattr(upstream_graph, "create_tier_client", lambda config, tier, **k: DummyClient())
    reset()
    cfg = cn_config.apply({
        "results_dir": str(tmp_path / "r"),
        "data_cache_dir": str(tmp_path / "c"),
        "memory_log_path": str(tmp_path / "m.md"),
        "llm_provider": "openai",
    })

    with pytest.raises(RuntimeError, match="bootstrap"):
        CnTradingAgentsGraph(config=cfg)

    bootstrap()
    CnTradingAgentsGraph(config=cfg)     # no raise once registered


def test_trading_constraints_follow_the_board(graph):
    main = graph.resolve_instrument_context("600519.SH", "stock", "2026-10-30")
    star = graph.resolve_instrument_context("688981.SH", "stock", "2026-10-30")
    beijing = graph.resolve_instrument_context("430047.BJ", "stock", "2026-10-30")

    assert "±10%" in main and "T+1" in main
    assert "±20%" in star
    assert "±30%" in beijing and "1-share increments" in beijing


def test_a_foreign_ticker_gets_no_a_share_rules(graph, monkeypatch):
    monkeypatch.setattr(
        upstream_graph, "resolve_instrument_identity",
        lambda ticker: {"name": "Apple Inc."},
    )

    context = graph.resolve_instrument_context("AAPL", "stock", "2026-10-30")

    assert "T+1" not in context
    assert "price limit" not in context
