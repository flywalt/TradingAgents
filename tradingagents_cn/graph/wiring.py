"""Rebuild the CN graph with the downstream sentiment analyst.

Upstream's ``GraphSetup`` holds its analyst factories in a local dict, so the only
way to swap one analyst without patching upstream is to rebuild the same wiring
here, reusing upstream's node factories and its per-analyst subgraph builder.

This module therefore depends on three upstream internals — ``_analyst_graph``
and the two path maps — which are registered as fragile coupling in
``docs/UPSTREAM_DELTA.md`` and pinned by ``test_upstream_compat``.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from tradingagents.agents import (
    create_aggressive_debator,
    create_bear_researcher,
    create_bull_researcher,
    create_conservative_debator,
    create_fundamentals_analyst,
    create_market_analyst,
    create_neutral_debator,
    create_news_analyst,
    create_portfolio_manager,
    create_research_manager,
    create_trader,
)
from tradingagents.agents.state import AgentState
from tradingagents.graph.analyst_execution import build_analyst_execution_plan
from tradingagents.graph.setup import DEBATE_PATH_MAP, RISK_ANALYSIS_PATH_MAP, _analyst_graph
from tradingagents_cn.agents.sentiment_analyst import create_sentiment_analyst


def build_cn_workflow(graph, selected_analysts, memory_node):
    """The upstream topology with the sentiment analyst replaced."""
    quick, deep = graph.quick_thinking_llm, graph.deep_thinking_llm
    rounds = graph.config["max_tool_rounds"]
    plan = build_analyst_execution_plan(selected_analysts)

    factories = {
        "market": lambda: create_market_analyst(quick),
        "social": lambda: create_sentiment_analyst(quick),
        "news": lambda: create_news_analyst(quick),
        "fundamentals": lambda: create_fundamentals_analyst(quick),
    }

    workflow = StateGraph(AgentState)
    for spec in plan.specs:
        workflow.add_node(spec.agent_node, _analyst_graph(spec, factories[spec.key](), rounds))

    workflow.add_node("Bull Researcher", create_bull_researcher(quick))
    workflow.add_node("Bear Researcher", create_bear_researcher(quick))
    workflow.add_node("Research Manager", create_research_manager(deep))
    workflow.add_node("Trader", create_trader(quick))
    workflow.add_node("Aggressive Analyst", create_aggressive_debator(quick))
    workflow.add_node("Conservative Analyst", create_conservative_debator(quick))
    workflow.add_node("Neutral Analyst", create_neutral_debator(quick))
    workflow.add_node("Portfolio Manager", create_portfolio_manager(deep))

    first_steps = [spec.agent_node for spec in plan.specs]
    if memory_node is not None:
        workflow.add_node("Memory Log", memory_node)
        first_steps.append("Memory Log")
    for node in first_steps:
        workflow.add_edge(START, node)
    workflow.add_edge(first_steps, "Bull Researcher")

    for debate_node in ("Bull Researcher", "Bear Researcher"):
        workflow.add_conditional_edges(
            debate_node, graph.conditional_logic.should_continue_debate, DEBATE_PATH_MAP
        )
    workflow.add_edge("Research Manager", "Trader")
    workflow.add_edge("Trader", "Aggressive Analyst")
    for risk_node in ("Aggressive Analyst", "Conservative Analyst", "Neutral Analyst"):
        workflow.add_conditional_edges(
            risk_node, graph.conditional_logic.should_continue_risk_analysis,
            RISK_ANALYSIS_PATH_MAP,
        )
    workflow.add_edge("Portfolio Manager", END)
    return workflow
