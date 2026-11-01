"""Downstream graph wiring.

`TradingAgentsGraph` hardcodes its node set and compiles immediately, so a
downstream topology or identity swap is done by subclass (one method) plus a
factory that guarantees registration ran first. See
``docs/EXTENSION_POINTS.md`` sections 2 and 4.
"""

from .factory import DEFAULT_ANALYSTS, build_graph, build_report
from .trading_graph import CnTradingAgentsGraph

__all__ = ["DEFAULT_ANALYSTS", "CnTradingAgentsGraph", "build_graph", "build_report"]
