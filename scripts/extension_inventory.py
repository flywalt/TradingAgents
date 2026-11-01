#!/usr/bin/env python3
"""Inventory of everything this downstream adds, and a check that the doc matches.

Auditability needs two properties: the list is complete (nothing ships without
being recorded), and the record is true (the doc names paths that exist). This
script prints the inventory and, with --check, fails when docs/EXTENSIONS.md is
missing an item.

Usage:
    python scripts/extension_inventory.py            # print markdown inventory
    python scripts/extension_inventory.py --check    # verify docs/EXTENSIONS.md
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "tradingagents_cn"
TESTS = ROOT / "tests" / "downstream"
DOC = ROOT / "docs" / "EXTENSIONS.md"


def modules() -> list[str]:
    return sorted(str(path.relative_to(ROOT)) for path in PACKAGE.rglob("*.py"))


def tests() -> list[str]:
    return sorted(str(path.relative_to(ROOT)) for path in TESTS.glob("test_*.py"))


def config_keys() -> list[str]:
    sys.path.insert(0, str(ROOT))
    from tradingagents_cn.config import DEFAULT_CN_CONFIG

    return sorted(DEFAULT_CN_CONFIG)


def env_vars() -> list[str]:
    sys.path.insert(0, str(ROOT))
    from tradingagents_cn.config import _ENV_OVERRIDES

    return sorted(_ENV_OVERRIDES)


def registered_methods() -> list[str]:
    sys.path.insert(0, str(ROOT))
    from tradingagents_cn.bootstrap import bootstrap, registered_vendors, reset

    bootstrap()
    try:
        return sorted({f"{vendor}:{method}" for method, vendor in registered_vendors()})
    finally:
        reset()


def upstream_files() -> list[str]:
    """Files the downstream modified in the upstream tree (patches, not additions)."""
    try:
        completed = subprocess.run(
            ["git", "-C", str(ROOT), "diff", "--name-only", "upstream/main..HEAD",
             "--", "tradingagents", "cli", "tests", "pyproject.toml", "README.md"],
            capture_output=True, text=True, check=False, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    added = set(
        subprocess.run(
            ["git", "-C", str(ROOT), "diff", "--name-only", "--diff-filter=A",
             "upstream/main..HEAD", "--", "tradingagents", "cli", "tests", "pyproject.toml"],
            capture_output=True, text=True, check=False, timeout=10,
        ).stdout.split()
    )
    return sorted(path for path in completed.stdout.split() if path and path not in added)


def inventory() -> dict:
    return {
        "modules": modules(),
        "tests": tests(),
        "config_keys": config_keys(),
        "env_vars": env_vars(),
        "registered": registered_methods(),
        "upstream_files": upstream_files(),
    }


def render(data: dict) -> str:
    lines = ["# inventory", "", "## modules", *data["modules"], "", "## tests", *data["tests"],
             "", "## config keys", *data["config_keys"], "", "## env vars", *data["env_vars"],
             "", "## registered vendor methods", *data["registered"], "",
             "## upstream files modified", *data["upstream_files"]]
    return "\n".join(lines)


def missing(doc_text: str, data: dict) -> list[str]:
    wanted = (
        data["modules"] + data["tests"] + data["config_keys"] + data["env_vars"]
        + data["upstream_files"]
    )
    return [item for item in wanted if item not in doc_text]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    data = inventory()
    if not args.check:
        print(render(data))
        return 0

    if not DOC.exists():
        print(f"missing {DOC.relative_to(ROOT)}", file=sys.stderr)
        return 1
    gaps = missing(DOC.read_text(encoding="utf-8"), data)
    if gaps:
        print("EXTENSIONS.md does not mention:", *gaps, sep="\n  ", file=sys.stderr)
        return 1
    print(f"inventory complete: {len(data['modules'])} modules, {len(data['tests'])} test files, "
          f"{len(data['config_keys'])} config keys, {len(data['upstream_files'])} upstream files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
