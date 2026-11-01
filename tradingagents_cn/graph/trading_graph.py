"""Downstream graph: the same kernel, with A-share identity wired in.

Only one method is overridden. Everything else — graph construction, checkpoint
semantics, memory, reporting — is inherited, so an upstream change to the graph
reaches us without a copy to maintain.

``resolve_instrument_context`` is the single seam every agent's prompt goes
through (12/12 modules interpolate ``{instrument_context}``), which is why the
identity fix lives here and not in a prompt.

Upstream's own contract is preserved deliberately:
* the signature is identical to v0.7.1 (pinned by ``test_upstream_compat``);
* ``build_instrument_context`` still renders the text, including its
  historical-run caveat that a name is the *current* name;
* a non-A-share ticker, a missing profile, or a vendor outage falls back to the
  inherited Yahoo resolver instead of failing the run (the upstream behaviour).
"""

import logging
from typing import Any

from tradingagents.agents.context import build_instrument_context
from tradingagents.dataflows.date_window import get_current_date
from tradingagents.dataflows.errors import VendorError
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents_cn.bootstrap import ensure_bootstrapped
from tradingagents_cn.identity import resolve_identity_at
from tradingagents_cn.runmeta import attach as attach_run_metadata, collect as collect_run_metadata
from tradingagents_cn.symbols import is_ashare
from tradingagents_cn.trading_rules import limit_ratio, lot_rule

logger = logging.getLogger(__name__)


class CnTradingAgentsGraph(TradingAgentsGraph):
    """``TradingAgentsGraph`` that resolves A-share identity from Tushare."""

    def __init__(
        self,
        selected_analysts=("market", "social", "news", "fundamentals"),
        debug=False,
        config: dict[str, Any] = None,
        callbacks: list | None = None,
    ):
        # Registration must precede graph construction: a graph built first
        # captures no vendors and fails later as a routing error.
        ensure_bootstrapped()
        super().__init__(
            selected_analysts=selected_analysts,
            debug=debug,
            config=config,
            callbacks=callbacks,
        )

    def resolve_instrument_context(
        self, ticker: str, asset_type: str = "stock", trade_date: str | None = None
    ) -> str:
        """Identity context for ``ticker``; same signature and contract as upstream."""
        identity = self._ashare_identity(ticker, trade_date)
        if identity:
            context = build_instrument_context(ticker, asset_type, identity, trade_date)
        else:
            context = super().resolve_instrument_context(ticker, asset_type, trade_date)
        if is_ashare(ticker):
            context += _trading_constraints(ticker)
        return context

    def run_metadata(self, trade_date: str, ticker: str | None = None) -> dict:
        """Provenance for this run (also attached to every saved report)."""
        return collect_run_metadata(self.config, trade_date, ticker)

    def save_reports(self, final_state, ticker, save_path=None, html=True):
        """Upstream's report tree, plus the downstream provenance block."""
        path = super().save_reports(final_state, ticker, save_path=save_path, html=html)
        metadata = self.run_metadata(str(final_state.get("trade_date") or ""), ticker)
        attach_run_metadata(path, metadata)
        return path

    def _ashare_identity(self, ticker: str, trade_date: str | None) -> dict:
        if not is_ashare(ticker):
            return {}
        try:
            return resolve_identity_at(ticker, trade_date or get_current_date())
        except VendorError as exc:
            # Fail open exactly like upstream: a profile outage must not abort a
            # run, it just leaves the context ticker-only.
            logger.warning("A-share identity unavailable for %s: %s", ticker, exc)
            return {}


def _trading_constraints(ticker: str) -> str:
    """The A-share rules an agent must respect when it proposes a trade.

    Facts only — the band, the settlement rule and the lot size are deterministic
    and cheap to state. ST status and suspensions are *not* in this feed, and the
    text says so instead of letting the model assume they are absent.
    """
    ratio = limit_ratio(ticker) * 100
    minimum, step = lot_rule(ticker)
    lots = (f"{minimum} shares minimum, then 1-share increments" if step == 1
            else f"{minimum}-share lots")
    return (
        f" A-share trading rules: daily price limit ±{ratio:.0f}% (board rule); "
        "ST status and suspensions are unavailable from this data feed — do not assume "
        f"either; T+1 settlement (shares bought today are sellable from the next session); "
        f"orders in {lots}; any proposed fill must sit inside the limit band."
    )
