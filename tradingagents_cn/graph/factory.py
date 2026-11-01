"""The single entry point for building a runnable A-share graph.

Every caller — CLI, batch job, notebook, web worker — goes through here so that
registration happens exactly once and the graph class is the downstream one.
Calling ``TradingAgentsGraph`` directly still works for US tickers, but that
construction raises if registration never ran, which is the mistake this factory
removes.
"""

from __future__ import annotations

from tradingagents_cn.bootstrap import RegistrationReport, bootstrap
from tradingagents_cn.graph.trading_graph import CnTradingAgentsGraph

DEFAULT_ANALYSTS = ("market", "social", "news", "fundamentals")


def build_graph(
    config: dict | None = None,
    *,
    selected_analysts: tuple[str, ...] = DEFAULT_ANALYSTS,
    debug: bool = False,
    callbacks: list | None = None,
) -> CnTradingAgentsGraph:
    """Register the downstream vendors, then build the graph with the merged config."""
    report = bootstrap(config)
    return CnTradingAgentsGraph(
        selected_analysts=selected_analysts,
        debug=debug,
        config=report.config,
        callbacks=callbacks,
    )


def build_report(config: dict | None = None) -> RegistrationReport:
    """Register without building a graph (health checks, metadata, tests)."""
    return bootstrap(config)


__all__ = ["DEFAULT_ANALYSTS", "build_graph", "build_report"]
