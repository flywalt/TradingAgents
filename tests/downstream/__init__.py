"""Downstream (A-share) tests.

These tests are the sync fuse: they pin the upstream surfaces
``tradingagents_cn`` depends on (see ``docs/UPSTREAM_DELTA.md`` section 3), so an
upstream release that changes them fails here on the day it is pulled in rather
than in a live run.
"""
