"""Explicit, idempotent registration into upstream's extension surfaces.

Importing this package must not change anything: upstream's router tables are
module-level dicts, so a registration made at import time would be invisible to
the test suite and impossible to undo. Everything here therefore runs from
``activate()`` (or ``register_vendor``) and is reversible with ``reset()``.

The surfaces used are exactly the ones listed as fragile coupling in
``docs/UPSTREAM_DELTA.md``; ``tests/downstream/test_sync_guard.py`` fails the
moment upstream changes their shape, which is the point.
"""

from __future__ import annotations

import importlib
import re

_VENDOR_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")

#: Vendor modules installed by ``activate()``. A module is expected to expose
#: ``register_vendors()``; a missing module is skipped, not an error, so a build
#: without optional vendor dependencies still activates everything else.
_BUILTIN_MODULES = ("tradingagents_cn.vendors.tushare",)

# (method, vendor) -> implementation we installed
_REGISTERED: dict[tuple[str, str], object] = {}
# Methods and category entries this module created, so reset() can remove them.
_CREATED_METHODS: set[str] = set()
_CREATED_CATEGORY_ENTRIES: list[tuple[str, str]] = []
_ACTIVATED = False


class RegistrationReport:
    """What ``activate()`` installed, and the config to hand to the graph."""

    def __init__(self, config: dict, vendors: tuple[tuple[str, str], ...],
                 already_active: bool):
        self.config = config
        self.vendors = vendors
        self.already_active = already_active

    @property
    def vendors_by_method(self) -> dict[str, list[str]]:
        """Registered vendors grouped by router method, for logs and tests."""
        grouped: dict[str, list[str]] = {}
        for method, vendor in self.vendors:
            grouped.setdefault(method, []).append(vendor)
        return grouped

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (f"RegistrationReport(vendors={list(self.vendors)!r}, "
                f"already_active={self.already_active!r})")


def _router():
    from tradingagents.dataflows import router

    return router


def register_vendor(
    method: str, vendor: str, impl, *, category: str | None = None
) -> bool:
    """Install ``impl`` as ``vendor``'s implementation of ``method``.

    Returns ``False`` when the identical implementation was already registered
    (so activation is idempotent). A *different* implementation replaces the
    previous one — a reloaded adapter should win over its stale copy.

    ``category`` is required only for a method upstream does not know yet; for
    an existing method the tool's category is already recorded upstream.
    """
    router = _router()
    if not isinstance(method, str) or not method.strip():
        raise ValueError("method must be a non-empty string")
    method = method.strip()
    if not isinstance(vendor, str) or not _VENDOR_NAME_RE.match(vendor.strip().lower()):
        raise ValueError(f"vendor must be a lowercase identifier, got {vendor!r}")
    vendor = vendor.strip().lower()
    if not callable(impl):
        raise TypeError(f"impl for {method}/{vendor} must be callable")

    if method not in router.VENDOR_METHODS:
        if category is None:
            raise ValueError(
                f"unknown router method {method!r}; pass category= so it can be registered"
            )
        if category not in router.TOOLS_CATEGORIES:
            raise ValueError(
                f"unknown category {category!r}; known: {sorted(router.TOOLS_CATEGORIES)}"
            )
        router.VENDOR_METHODS[method] = {}
        _CREATED_METHODS.add(method)
        tools = router.TOOLS_CATEGORIES[category]["tools"]
        if method not in tools:
            tools.append(method)
            _CREATED_CATEGORY_ENTRIES.append((category, method))

    implementations = router.VENDOR_METHODS[method]
    if implementations.get(vendor) is impl and (method, vendor) in _REGISTERED:
        return False

    implementations[vendor] = impl
    _REGISTERED[(method, vendor)] = impl
    return True


def registered_vendors() -> tuple[tuple[str, str], ...]:
    """Every ``(method, vendor)`` pair this module installed, sorted."""
    return tuple(sorted(_REGISTERED))


def is_active() -> bool:
    """Whether ``activate()`` has run in this process."""
    return _ACTIVATED


def _install_builtins() -> None:
    for module_name in _BUILTIN_MODULES:
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError:
            continue
        registrar = getattr(module, "register_vendors", None)
        if callable(registrar):
            registrar()


def activate(config: dict | None = None, *, install_vendor_chain: bool = True) -> RegistrationReport:
    """Install the downstream vendors and return the config for the graph.

    Idempotent: a second call re-registers nothing (identical implementations are
    skipped) and reports ``already_active=True``. The returned config is a new
    dict — callers own it, and the upstream ``DEFAULT_CONFIG`` is never mutated.
    """
    global _ACTIVATED
    from tradingagents_cn import config as cn_config

    previously_active = _ACTIVATED
    _install_builtins()
    merged = cn_config.apply(config, install_vendor_chain=install_vendor_chain)
    _ACTIVATED = True
    return RegistrationReport(merged, registered_vendors(), previously_active)


def reset() -> None:
    """Undo everything ``register_vendor`` installed (tests and reloads only).

    Restores upstream's router to the shape it had before the first
    registration: our vendors are removed, and methods/category entries this
    module created are dropped again.
    """
    global _ACTIVATED
    router = _router()
    for method, vendor in list(_REGISTERED):
        implementations = router.VENDOR_METHODS.get(method)
        if isinstance(implementations, dict):
            implementations.pop(vendor, None)
    for method in list(_CREATED_METHODS):
        implementations = router.VENDOR_METHODS.get(method)
        if implementations is not None and not implementations:
            router.VENDOR_METHODS.pop(method, None)
    for category, method in _CREATED_CATEGORY_ENTRIES:
        tools = router.TOOLS_CATEGORIES.get(category, {}).get("tools")
        if tools is not None and method in tools:
            tools.remove(method)
    _REGISTERED.clear()
    _CREATED_METHODS.clear()
    _CREATED_CATEGORY_ENTRIES.clear()
    _ACTIVATED = False
