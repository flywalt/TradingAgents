"""Downstream graph wiring.

The upstream graph hardcodes its node set and compiles immediately, so a
downstream topology (extra analyst, A-share context injection) is built here by
reusing upstream's node factories and checkpoint helpers. See
``docs/EXTENSION_POINTS.md`` sections 2 and 4 for why this is a rebuild rather
than a fork of ``graph/setup.py``.
"""
