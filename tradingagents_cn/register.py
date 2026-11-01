"""Deprecated import path for :mod:`tradingagents_cn.bootstrap`.

Kept so existing downstream code and documented snippets keep working; new code
should import from ``tradingagents_cn.bootstrap``. This module holds no logic of
its own — one implementation of registration, one place that touches upstream's
tables.
"""

from __future__ import annotations

from tradingagents_cn.bootstrap import (
    RegistrationReport,
    activate,
    bootstrap,
    ensure_bootstrapped,
    is_bootstrapped,
    register_category,
    register_vendor,
    registered_vendors,
    reset,
)

#: Older name for :func:`tradingagents_cn.bootstrap.is_bootstrapped`.
is_active = is_bootstrapped

__all__ = [
    "RegistrationReport",
    "activate",
    "bootstrap",
    "ensure_bootstrapped",
    "is_active",
    "is_bootstrapped",
    "register_category",
    "register_vendor",
    "registered_vendors",
    "reset",
]
