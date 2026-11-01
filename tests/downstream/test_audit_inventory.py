"""The extension inventory must match the code, mechanically.

An audit document that drifts is worse than none: it asserts completeness while
being wrong. This test runs the same check a human would, so a new module,
config key or upstream patch cannot ship unrecorded.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[2]


def test_the_inventory_script_is_reachable():
    completed = subprocess.run(
        [sys.executable, "scripts/extension_inventory.py", "--check"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "inventory complete" in completed.stdout


def test_the_document_lists_the_upstream_patches():
    doc = (ROOT / "docs" / "EXTENSIONS.md").read_text(encoding="utf-8")

    for path in ("tradingagents/agents/tools.py", "tradingagents/dataflows/router.py"):
        assert path in doc
    assert "upstream-patch" in doc


def test_the_document_names_the_entry_points():
    doc = (ROOT / "docs" / "EXTENSIONS.md").read_text(encoding="utf-8")

    assert "tradingagents_cn.cli" in doc
    assert "build_graph" in doc
