"""Packaging: the downstream package has to end up in the distribution.

Upstream's ``pyproject.toml`` finds packages with ``include = ["tradingagents*",
"cli*"]``. ``tradingagents_cn`` happens to match that glob, but it is a happy
accident of naming, not a promise — if this test fails, the build would silently
ship without the A-share layer, so the fix is an explicit include (a recorded
upstream patch) or a separate distribution.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_setuptools_package_discovery_finds_the_downstream_package():
    # setuptools is a build dependency, not a runtime one; a test environment
    # without it skips this guard instead of failing on an unrelated import.
    pytest.importorskip("setuptools", reason="install setuptools to run the packaging guard")
    from setuptools import find_packages

    found = find_packages(where=str(REPO_ROOT), include=["tradingagents*", "cli*"])
    assert "tradingagents_cn" in found
    assert "tradingagents_cn.vendors" in found
    assert "tradingagents_cn.agents" in found
    assert "tradingagents_cn.graph" in found
    assert "tradingagents_cn.reporting" in found
    # Upstream packages are still discovered, untouched.
    assert "tradingagents" in found and "cli" in found


def test_the_downstream_package_imports_from_a_clean_interpreter():
    completed = subprocess.run(
        [sys.executable, "-c", "import tradingagents_cn; print(tradingagents_cn.__version__)"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert completed.stdout.strip() == "0.1.0.dev0"
