"""Multi-market profiles: the A-share path must not leak into other markets.

The rule under test is identity-based, not issuer-based: a Chinese company listed
in Hong Kong, or a US ADR, is not an A-share run. Each profile also keeps its own
vendor defaults, rules and storage.
"""

from __future__ import annotations

import asyncio

import pytest

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph import trading_graph as upstream_graph
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents_cn import config as cn_config
from tradingagents_cn.graph.factory import build_graph
from tradingagents_cn.graph.trading_graph import CnTradingAgentsGraph
from tradingagents_cn.market import (
    CN_A_SHARE,
    PROFILE_DEFAULT,
    UPSTREAM_DEFAULT,
    select_profile,
)

pytestmark = pytest.mark.unit


class DummyClient:
    def get_llm(self):
        return None


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    monkeypatch.setenv("TRADINGAGENTS_CN_CACHE", "off")
    monkeypatch.setattr(upstream_graph, "create_tier_client", lambda config, tier, **k: DummyClient())
    dirs = {
        "results_dir": str(tmp_path / "results"),
        "data_cache_dir": str(tmp_path / "cache"),
        "memory_log_path": str(tmp_path / "memory.md"),
        "llm_provider": "openai",
    }
    return dirs


def _graph(dirs, symbol, **overrides):
    return build_graph({**dirs, **overrides}, symbol=symbol)


# --- profile selection -----------------------------------------------------


def test_a_us_ticker_selects_the_upstream_profile(offline):
    graph = _graph(offline, "AAPL")

    assert type(graph) is TradingAgentsGraph
    assert graph.config["cn_market_profile"] == PROFILE_DEFAULT


def test_a_cn_suffix_selects_the_cn_profile(offline):
    graph = _graph(offline, "600519.SS")

    assert isinstance(graph, CnTradingAgentsGraph)


def test_a_hk_listing_of_a_chinese_issuer_stays_on_the_upstream_profile(offline, monkeypatch):
    monkeypatch.setattr(upstream_graph, "resolve_instrument_identity",
                        lambda ticker: {"name": "Tencent Holdings"})
    graph = _graph(offline, "0700.HK")

    assert type(graph) is TradingAgentsGraph
    context = graph.resolve_instrument_context("0700.HK", "stock", "2026-10-30")
    assert "T+1" not in context
    assert "price limit" not in context


def test_a_us_adr_of_a_chinese_company_stays_on_the_upstream_profile(offline):
    graph = _graph(offline, "BABA")

    assert type(graph) is TradingAgentsGraph


def test_an_ambiguous_or_conflicting_market_is_rejected():
    with pytest.raises(ValueError, match="cannot tell the market"):
        select_profile(symbol="0700")

    with pytest.raises(ValueError, match="contradicts"):
        select_profile(market="US", symbol="600519.SS")


def test_an_unknown_market_is_rejected():
    with pytest.raises(ValueError, match="unknown market"):
        select_profile(market="MARS", symbol=None)


# --- isolation between profiles -------------------------------------------


def test_strict_vendor_policy_exists_only_in_the_cn_profile():
    with pytest.raises(ValueError, match="A-share vendor policy"):
        cn_config.apply({"cn_strict_ashare": True}, profile=UPSTREAM_DEFAULT)

    merged = cn_config.apply({"cn_strict_ashare": True}, profile=CN_A_SHARE)
    assert merged["data_vendors"]["core_stock_apis"] == "tushare"


def test_the_default_profile_keeps_upstream_vendor_defaults():
    merged = cn_config.apply(profile=UPSTREAM_DEFAULT)

    assert merged["data_vendors"]["core_stock_apis"] == DEFAULT_CONFIG["data_vendors"]["core_stock_apis"]
    assert merged["cn_indicator_flavor"] == "stockstats"


def test_the_cn_profile_installs_its_vendor_and_indicator_defaults():
    merged = cn_config.apply(profile=CN_A_SHARE)

    assert merged["data_vendors"]["core_stock_apis"] == "tushare,yfinance"
    assert merged["cn_indicator_flavor"] == "tdx"
    assert merged["tool_vendors"]["get_insider_transactions"] == "tushare,yfinance"


def test_the_two_profiles_use_separate_storage():
    """Defaults are namespaced per profile; an explicit path is the caller's choice."""
    cn = cn_config.apply(profile=CN_A_SHARE)
    default = cn_config.apply(profile=UPSTREAM_DEFAULT)

    assert "profile-cn" in cn["results_dir"]
    assert "profile-cn" in cn["data_cache_dir"]
    assert cn["memory_log_path"].endswith("-cn.md")
    assert "profile-cn" not in default["results_dir"]


def test_the_two_profiles_resolve_side_by_side(offline, monkeypatch):
    monkeypatch.setattr(upstream_graph, "resolve_instrument_identity",
                        lambda ticker: {"name": "Tencent Holdings"})
    cn_graph = _graph(offline, "600519.SS")
    us_graph = _graph(offline, "0700.HK")

    async def run():
        return await asyncio.gather(
            asyncio.to_thread(cn_graph.resolve_instrument_context, "600519.SH", "stock", "2026-10-30"),
            asyncio.to_thread(us_graph.resolve_instrument_context, "0700.HK", "stock", "2026-10-30"),
        )

    cn_context, hk_context = asyncio.run(run())

    assert "T+1" in cn_context
    assert "T+1" not in hk_context
    assert "Tencent" in hk_context


def test_the_cn_graph_refuses_a_share_rules_under_a_foreign_profile(offline, monkeypatch):
    """Belt and braces: the CN class is not used for foreign profiles, but if it
    were, the profile flag still suppresses A-share rules."""
    from tradingagents_cn.bootstrap import bootstrap

    bootstrap()
    monkeypatch.setattr(upstream_graph, "resolve_instrument_identity", lambda ticker: {})
    merged = cn_config.apply({**offline, "cn_market_profile": PROFILE_DEFAULT}, profile=UPSTREAM_DEFAULT)
    graph = CnTradingAgentsGraph(config=merged)

    context = graph.resolve_instrument_context("600519.SH", "stock", "2026-10-30")

    assert "T+1" not in context
