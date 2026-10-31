"""The sync fuse: pin every upstream surface the downstream layer relies on.

Each test here corresponds to a row of the fragile-coupling table in
``docs/UPSTREAM_DELTA.md``. When an upstream release changes one of these, the
failure should name the coupling, not surface as an empty A-share report weeks
later. Fixing a failure here means updating the downstream adapter *and* the
table — not deleting the test.
"""

from __future__ import annotations

import inspect

import pytest

pytestmark = pytest.mark.unit


# --- 1. Data layer: router tables and error taxonomy ------------------------


def test_router_exposes_the_tables_we_register_into():
    from tradingagents.dataflows import router

    assert isinstance(router.VENDOR_METHODS, dict)
    assert isinstance(router.TOOLS_CATEGORIES, dict)
    for method in ("get_stock_data", "get_indicators", "get_fundamentals", "get_news"):
        assert method in router.VENDOR_METHODS, method
        assert isinstance(router.VENDOR_METHODS[method], dict)
    assert "core_stock_apis" in router.TOOLS_CATEGORIES
    assert "get_stock_data" in router.TOOLS_CATEGORIES["core_stock_apis"]["tools"]
    assert "yfinance" in router.VENDOR_METHODS["get_stock_data"]


def test_router_entry_points_keep_their_signatures():
    from tradingagents.dataflows import router

    assert list(inspect.signature(router.route_to_vendor).parameters)[0] == "method"
    parameters = list(inspect.signature(router.get_vendor).parameters)
    assert parameters[:2] == ["category", "method"]
    assert callable(router.get_category_for_method)


def test_router_methods_take_positional_arguments():
    """Adapters are called positionally by the router; keyword-only would break them."""
    from tradingagents.dataflows import router

    for method in ("get_stock_data", "get_fundamentals"):
        for vendor, impl in router.VENDOR_METHODS[method].items():
            impl = impl[0] if isinstance(impl, list) else impl
            parameters = list(inspect.signature(impl).parameters.values())
            assert parameters, f"{method}/{vendor} takes no arguments"
            assert any(
                p.kind
                in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD, p.VAR_POSITIONAL)
                for p in parameters
            ), f"{method}/{vendor} accepts no positional argument"


def test_vendor_error_taxonomy_is_the_one_the_router_reacts_to():
    from tradingagents.dataflows import errors

    assert issubclass(errors.NoMarketDataError, errors.VendorError)
    assert issubclass(errors.VendorUnavailableError, errors.VendorError)
    assert issubclass(errors.VendorNotConfiguredError, errors.VendorError)

    error = errors.NoMarketDataError("600519.SH", canonical="600519.SH", detail="stale")
    assert (error.symbol, error.canonical, error.detail) == ("600519.SH", "600519.SH", "stale")


def test_point_in_time_helpers_still_clamp_to_the_trade_date():
    from tradingagents.dataflows.date_window import as_of, as_of_window

    assert as_of("2026-01-09", "2026-01-01") == "2026-01-01"
    start, end = as_of_window("2025-12-01", "2026-01-09", "2026-01-01")
    assert end <= "2026-01-01"
    assert start <= end


def test_upstream_symbol_normalization_still_maps_a_share_codes():
    """We lean on this for the Yahoo fallback, so its A-share rules must hold."""
    from tradingagents.dataflows.symbols import normalize_symbol

    assert normalize_symbol("600519.SH") == "600519.SS"
    assert normalize_symbol("000001.SZ") == "000001.SZ"


# --- 2. State: channel names the downstream layer reads and writes ---------

EXPECTED_STATE_KEYS = {
    "messages",
    "company_of_interest",
    "asset_type",
    "instrument_context",
    "trade_date",
    "market_report",
    "sentiment_report",
    "news_report",
    "fundamentals_report",
    "investment_debate_state",
    "risk_debate_state",
    "investment_plan",
    "trader_investment_plan",
    "final_trade_decision",
    "past_context",
}


def test_agent_state_still_carries_the_channels_we_depend_on():
    from tradingagents.agents.state import AgentState

    keys = set(AgentState.__annotations__)
    assert keys >= EXPECTED_STATE_KEYS, EXPECTED_STATE_KEYS - keys


def test_debate_states_still_carry_their_counters():
    from tradingagents.agents.state import InvestDebateState, RiskDebateState

    assert {"count", "current_response", "history"} <= set(InvestDebateState.__annotations__)
    assert {"count", "latest_speaker", "history"} <= set(RiskDebateState.__annotations__)


# --- 3. Agents: factories, their signature and their registry --------------


@pytest.mark.parametrize(
    "name",
    [
        "create_market_analyst",
        "create_sentiment_analyst",
        "create_news_analyst",
        "create_fundamentals_analyst",
        "create_bull_researcher",
        "create_bear_researcher",
        "create_research_manager",
        "create_trader",
        "create_aggressive_debator",
        "create_conservative_debator",
        "create_neutral_debator",
        "create_portfolio_manager",
    ],
)
def test_every_agent_factory_is_exported_with_the_expected_arity(name):
    import tradingagents.agents as agents

    factory = getattr(agents, name, None) or getattr(agents, name.replace("create_", "create_"), None)
    assert factory is not None, f"{name} is no longer exported by tradingagents.agents"
    assert name in agents.__all__
    parameters = list(inspect.signature(factory).parameters.values())
    assert len(parameters) == 1, f"{name} changed arity: {inspect.signature(factory)}"


def test_analyst_spec_registry_keeps_its_fields():
    from tradingagents.graph.analyst_execution import (
        ANALYST_NODE_SPECS,
        AnalystNodeSpec,
        build_analyst_execution_plan,
    )

    assert {"key", "agent_node", "report_key", "tools"} <= set(AnalystNodeSpec.__dataclass_fields__)
    assert {"market", "social", "news", "fundamentals"} <= set(ANALYST_NODE_SPECS)

    plan = build_analyst_execution_plan(["market"])
    assert [spec.key for spec in plan.specs] == ["market"]
    assert plan.specs[0].report_key == "market_report"

    with pytest.raises(ValueError):
        build_analyst_execution_plan(["no_such_analyst"])


# --- 4. Graph: the seams downstream wiring and the CLI rely on ---------------


def test_graph_setup_keeps_its_injection_points():
    from tradingagents.graph.setup import GraphSetup

    parameters = inspect.signature(GraphSetup.setup_graph).parameters
    assert "selected_analysts" in parameters
    assert "memory_node" in parameters


def test_trading_graph_keeps_the_methods_downstream_overrides():
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    for name in ("resolve_instrument_context", "_run_signature", "save_reports",
                 "_memory_step", "propagate", "run_settings"):
        assert callable(getattr(TradingAgentsGraph, name, None)), name

    parameters = list(inspect.signature(TradingAgentsGraph.propagate).parameters)
    assert parameters[1:3] == ["company_name", "trade_date"]
    assert "asset_type" in parameters and "portfolio" in parameters


def test_conditional_logic_keeps_its_router_methods():
    from tradingagents.graph.conditional_logic import ConditionalLogic

    logic = ConditionalLogic(max_debate_rounds=1, max_risk_discuss_rounds=1)
    # A fresh debate starts with the bull; a fresh risk round with the aggressive
    # analyst. Both reads are the counters downstream wiring has to keep feeding.
    debate_state = {"investment_debate_state": {"count": 0, "current_response": ""}}
    risk_state = {"risk_debate_state": {"count": 0, "latest_speaker": ""}}
    assert logic.should_continue_debate(debate_state) == "Bull Researcher"
    assert logic.should_continue_risk_analysis(risk_state) == "Aggressive Analyst"


def test_checkpointer_helpers_are_still_plain_functions():
    from tradingagents.graph import checkpointer

    for name in ("get_checkpointer", "thread_id", "checkpoint_step", "clear_checkpoint"):
        assert callable(getattr(checkpointer, name, None)), name
    assert checkpointer.thread_id("600519", "2026-01-09") != checkpointer.thread_id(
        "600519", "2026-01-09", "signature"
    )


# --- 5. Config, ratings, reporting, model providers --------------------------


def test_config_entry_points_are_unchanged():
    from tradingagents.dataflows import config as data_config
    from tradingagents.default_config import DEFAULT_CONFIG, build_default_config

    assert callable(build_default_config)
    assert callable(data_config.set_config)
    assert callable(data_config.get_config)
    assert callable(data_config.run_config)
    for key in ("data_vendors", "tool_vendors", "benchmark_map", "output_language"):
        assert key in DEFAULT_CONFIG, key


def test_rating_vocabulary_is_still_the_five_tier_contract():
    from tradingagents.agents import rating

    assert rating.RATINGS_5_TIER == ("Buy", "Overweight", "Hold", "Underweight", "Sell")
    assert rating.RATING_REVIEW == "REVIEW"
    assert rating.extract_rating("**Rating**: Buy") == "Buy"


def test_reporting_sections_keep_their_shape():
    from tradingagents import reporting

    assert isinstance(reporting._SECTIONS, tuple)
    folders = []
    for section in reporting._SECTIONS:
        heading, folder, agents = section
        assert isinstance(heading, str) and isinstance(folder, str)
        assert agents and all(len(entry) == 3 for entry in agents)
        folders.append(folder)
    assert folders == ["1_analysts", "2_research", "3_trading", "4_risk", "5_portfolio"]
    assert callable(reporting.write_report_tree)


def test_model_provider_registry_still_covers_the_vendors_we_use():
    from tradingagents.llm_clients import create_llm_client, create_tier_client, tier_provider
    from tradingagents.llm_clients.openai_client import OPENAI_COMPATIBLE_PROVIDERS

    assert callable(create_llm_client) and callable(create_tier_client)
    assert callable(tier_provider)
    for provider in ("openai", "deepseek", "qwen", "glm", "kimi", "openai_compatible"):
        assert provider in OPENAI_COMPATIBLE_PROVIDERS, provider
