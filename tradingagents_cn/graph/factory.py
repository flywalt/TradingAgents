"""The single entry point for building a runnable graph, for any market.

A run's market decides the graph class: ``CN_A_SHARE`` gets the downstream
subclass (Tushare identity, A-share rules), everything else gets the upstream
class unchanged. This module is the one place allowed to instantiate the upstream
graph, which is why the AST guard names it as the exception.
"""

from __future__ import annotations

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents_cn import config as cn_config
from tradingagents_cn.bootstrap import RegistrationReport, bootstrap
from tradingagents_cn.graph.trading_graph import CnTradingAgentsGraph
from tradingagents_cn.market import select_profile
from tradingagents_cn.runmeta import worktree_dirty

DEFAULT_ANALYSTS = ("market", "social", "news", "fundamentals")


def build_graph(
    config: dict | None = None,
    *,
    market: str | None = None,
    symbol: str | None = None,
    profile: str | None = None,
    selected_analysts: tuple[str, ...] | None = None,
    debug: bool = False,
    callbacks: list | None = None,
) -> TradingAgentsGraph:
    """Normalize this run's config, ensure registration, build the graph.

    Registration is process-wide (``bootstrap``); configuration is per graph.
    The normalized dict is a fresh copy, so two graphs never share state.
    """
    # Precedence: explicit profile/market > symbol > an already-typed config.
    # A config that names its profile (from a previous apply) keeps it, so
    # callers that pre-merge settings do not have to repeat the symbol.
    chosen = select_profile(
        market=market,
        symbol=symbol,
        profile=profile or (config or {}).get("cn_market_profile"),
    )

    bootstrap()
    settings = cn_config.apply(config, profile=chosen)
    if settings.get("checkpoint_enabled") and worktree_dirty() and not settings.get(
        "cn_allow_dirty_checkpoint"
    ):
        raise RuntimeError(
            "checkpoint_enabled with an uncommitted worktree: a resume would run "
            "different code under the same version. Commit, or set "
            "cn_allow_dirty_checkpoint=True for a development run."
        )
    graph_class = CnTradingAgentsGraph if chosen.graph == "cn" else TradingAgentsGraph
    return graph_class(
        selected_analysts=selected_analysts or chosen.selected_analysts,
        debug=debug,
        config=settings,
        callbacks=callbacks,
    )


def build_report() -> RegistrationReport:
    """Register without building a graph (health checks, tests)."""
    return bootstrap()


__all__ = ["DEFAULT_ANALYSTS", "build_graph", "build_report"]
