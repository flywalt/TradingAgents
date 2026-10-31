"""A-share (CN) research extensions built on top of TradingAgents.

Downstream-only code: it imports the upstream package but never mutates it on
import. Call ``tradingagents_cn.register.activate()`` once from your entry point
(the CLI, a notebook, a service) to install A-share vendors and configuration
for the runs that follow.

Boundary rules and the proposed layout live in ``docs/ARCHITECTURE.md``; the
upstream surfaces this package leans on are listed in ``docs/UPSTREAM_DELTA.md``
and pinned by ``tests/downstream/test_sync_guard.py``.
"""

__version__ = "0.1.0.dev0"

from .register import RegistrationReport, activate, register_vendor, registered_vendors

__all__ = [
    "RegistrationReport",
    "__version__",
    "activate",
    "register_vendor",
    "registered_vendors",
]
