"""The single entry point for building a runnable A-share graph.

Every caller — CLI, batch job, notebook, web worker — goes through here so that
registration happens exactly once and the graph class is the downstream one.
Calling ``TradingAgentsGraph`` directly still works for US tickers, but that
construction raises if registration never ran, which is the mistake this factory
removes.
"""

from __future__ import annotations

from tradingagents_cn import config as cn_config
from tradingagents_cn.bootstrap import RegistrationReport, bootstrap
from tradingagents_cn.graph.trading_graph import CnTradingAgentsGraph
from tradingagents_cn.runmeta import worktree_dirty

DEFAULT_ANALYSTS = ("market", "social", "news", "fundamentals")


def build_graph(
    config: dict | None = None,
    *,
    selected_analysts: tuple[str, ...] = DEFAULT_ANALYSTS,
    debug: bool = False,
    callbacks: list | None = None,
) -> CnTradingAgentsGraph:
    """Normalize this run's config, ensure registration, build the graph.

    Registration is process-wide (``bootstrap``); configuration is per graph.
    The normalized dict is a fresh copy, so two graphs never share state.
    """
    bootstrap()
    settings = cn_config.apply(config)
    if settings.get("checkpoint_enabled") and worktree_dirty() and not settings.get(
        "cn_allow_dirty_checkpoint"
    ):
        raise RuntimeError(
            "checkpoint_enabled with an uncommitted worktree: a resume would run "
            "different code under the same version. Commit, or set "
            "cn_allow_dirty_checkpoint=True for a development run."
        )
    return CnTradingAgentsGraph(
        selected_analysts=selected_analysts,
        debug=debug,
        config=settings,
        callbacks=callbacks,
    )


def build_report() -> RegistrationReport:
    """Register without building a graph (health checks, tests)."""
    return bootstrap()


__all__ = ["DEFAULT_ANALYSTS", "build_graph", "build_report"]
