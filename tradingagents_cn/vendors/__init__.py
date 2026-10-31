"""Downstream data vendors: one module or package per A-share source.

A vendor module exposes ``register_vendors()``, which registers its functions
with upstream's router. Functions must match the router method's positional
signature exactly and must raise the typed errors in
``tradingagents.dataflows.errors`` — the router's fallback chain reacts to the
type, not the message.
"""
