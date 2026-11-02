"""The only place downstream code touches upstream's registry tables.

Upstream exposes no registration API: `router.VENDOR_METHODS` and
`router.TOOLS_CATEGORIES` are module-level dicts. Writing to them from business
code works but has three failure modes we have already paid for once:

* a typo'd method name silently creates an unreachable entry;
* a second registration quietly replaces the first;
* an implementation whose arity differs from its neighbours breaks the router's
  positional call only when that vendor is reached.

This module is the thin adapter that fixes those: validated, idempotent,
overwrite-protected registration, plus one explicit entry point
(`bootstrap()`) that must run before a graph is built.

Nothing here binds configuration: vendor *implementations* are process-wide and
stateless, while which vendor a run uses is chosen per run from
`data_vendors`/`tool_vendors` (see `docs/ARCHITECTURE.md` §4).
"""

from __future__ import annotations

import importlib
import inspect
import re

_VENDOR_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")

#: Vendor modules installed by ``bootstrap()``. A module is expected to expose
#: ``register_vendors()``; a missing module is skipped, not an error, so a build
#: without an optional vendor dependency still activates everything else.
_BUILTIN_MODULES = ("tradingagents_cn.vendors.tushare", "tradingagents_cn.vendors.xueqiu")

# (method, vendor) -> implementation we installed
_REGISTERED: dict[tuple[str, str], object] = {}
_CREATED_METHODS: set[str] = set()
_CREATED_CATEGORY_ENTRIES: list[tuple[str, str]] = []
_CREATED_CATEGORIES: list[str] = []
_BOOTSTRAPPED = False


class RegistrationReport:
    """What ``bootstrap()`` installed. It carries no run configuration.

    Registration is process-wide and happens once; the configuration for a run
    belongs to that graph. Mixing the two here was the v2 defect this class no
    longer allows.
    """

    def __init__(self, vendors: tuple[tuple[str, str], ...], already_active: bool):
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


def _shape(impl) -> tuple[int, int, bool]:
    """(required positional args, total positional args, accepts *args)."""
    try:
        signature = inspect.signature(impl)
    except (TypeError, ValueError):
        return (0, 0, True)      # builtins/C callables: cannot inspect, do not judge
    positional = [
        parameter
        for parameter in signature.parameters.values()
        if parameter.kind in (parameter.POSITIONAL_ONLY, parameter.POSITIONAL_OR_KEYWORD)
    ]
    required = [parameter for parameter in positional if parameter.default is parameter.empty]
    varargs = any(
        parameter.kind is parameter.VAR_POSITIONAL
        for parameter in signature.parameters.values()
    )
    return (len(required), len(positional), varargs)


def check_signature(method: str, vendor: str, impl) -> None:
    """Reject an implementation that cannot accept the call its peers accept.

    The router calls vendors positionally, so parameter *names* may differ
    (``symbol`` vs ``ticker``). Arity is judged only when upstream's existing
    implementations agree on it — where they disagree (``get_indicators`` ships
    a 4-arg and a 7-arg implementation), there is no single contract to enforce
    and guessing one would reject valid adapters.
    """
    implementations = _router().VENDOR_METHODS.get(method, {})
    if not implementations:
        return

    shapes = []
    for existing_vendor, existing_impl in implementations.items():
        if isinstance(existing_impl, (list, tuple)):
            existing_impl = existing_impl[0]
        shapes.append((existing_vendor, _shape(existing_impl)))

    if any(shape[2] for _vendor, shape in shapes):
        return                                     # a peer takes *args: no contract
    totals = {shape[1] for _vendor, shape in shapes}
    if len(totals) > 1:
        return                                     # peers disagree: nothing to enforce

    expected = next(iter(totals))
    shape = _shape(impl)
    if shape[2]:
        return
    if shape[1] != expected:
        peer = next(vendor_name for vendor_name, peer_shape in shapes
                    if peer_shape[1] == expected)
        raise TypeError(
            f"{method}/{vendor} takes {shape[1]} positional args; "
            f"upstream's implementations ({peer}) take {expected} — "
            "the router calls them positionally"
        )


def register_category(name: str, description: str) -> bool:
    """Create a router category so new downstream methods have a home."""
    router = _router()
    if not isinstance(name, str) or not name.strip():
        raise ValueError("category name must be a non-empty string")
    name = name.strip().lower()
    if name in router.TOOLS_CATEGORIES:
        return False
    router.TOOLS_CATEGORIES[name] = {"description": description, "tools": []}
    _CREATED_CATEGORIES.append(name)
    return True


def register_vendor(
    method: str, vendor: str, impl, *, category: str | None = None, replace: bool = False
) -> bool:
    """Install ``impl`` as ``vendor``'s implementation of ``method``.

    Returns ``False`` when the identical implementation was already registered
    (so activation is idempotent). A *different* implementation is an error
    unless ``replace=True``: silent replacement is how a stale copy wins.

    ``category`` is required only for a method upstream does not know yet.
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
    existing = implementations.get(vendor)
    if existing is not None and (method, vendor) in _REGISTERED:
        if existing is impl:
            return False
        if not replace:
            raise ValueError(
                f"{method}/{vendor} is already registered with a different implementation; "
                "pass replace=True if that is deliberate"
            )

    check_signature(method, vendor, impl)
    implementations[vendor] = impl
    _REGISTERED[(method, vendor)] = impl
    return True


def registered_vendors() -> tuple[tuple[str, str], ...]:
    """Every ``(method, vendor)`` pair this module installed, sorted."""
    return tuple(sorted(_REGISTERED))


def is_bootstrapped() -> bool:
    """Whether ``bootstrap()`` has run in this process."""
    return _BOOTSTRAPPED


def ensure_bootstrapped() -> None:
    """Fail loudly when a graph is built before registration.

    A graph built first captures no vendors, and the failure then appears far
    from its cause (as "Configured vendor(s) ['tushare'] not available").
    """
    if not _BOOTSTRAPPED:
        raise RuntimeError(
            "tradingagents_cn.bootstrap() must run before a graph is constructed "
            "(use tradingagents_cn.graph.factory.build_graph)"
        )


def _install_builtins() -> None:
    for module_name in _BUILTIN_MODULES:
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError:
            continue
        registrar = getattr(module, "register_vendors", None)
        if callable(registrar):
            registrar()


def bootstrap() -> RegistrationReport:
    """Register the downstream vendors. No configuration is read or written.

    Idempotent and process-wide. ``build_graph(config)`` is the one place a run's
    configuration is produced and bound; calling it without bootstrapping fails
    in ``ensure_bootstrapped``.
    """
    global _BOOTSTRAPPED
    previously = _BOOTSTRAPPED
    _install_builtins()
    _BOOTSTRAPPED = True
    return RegistrationReport(registered_vendors(), previously)


#: Backwards-compatible alias: older downstream code and docs say ``activate()``.
#: It no longer accepts a config — registration and configuration are separate.
activate = bootstrap


def reset() -> None:
    """Undo everything ``register_vendor`` installed (tests and reloads only)."""
    global _BOOTSTRAPPED
    router = _router()
    for method, vendor in list(_REGISTERED):
        implementations = router.VENDOR_METHODS.get(method)
        if isinstance(implementations, dict):
            implementations.pop(vendor, None)
    for method in list(_CREATED_METHODS):
        implementations = router.VENDOR_METHODS.get(method)
        if implementations is not None and not implementations:
            router.VENDOR_METHODS.pop(method, None)
    for category in _CREATED_CATEGORIES:
        router.TOOLS_CATEGORIES.pop(category, None)
    for category, method in _CREATED_CATEGORY_ENTRIES:
        tools = router.TOOLS_CATEGORIES.get(category, {}).get("tools")
        if tools is not None and method in tools:
            tools.remove(method)
    _REGISTERED.clear()
    _CREATED_METHODS.clear()
    _CREATED_CATEGORY_ENTRIES.clear()
    _CREATED_CATEGORIES.clear()
    _BOOTSTRAPPED = False
