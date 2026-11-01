"""Provenance for every run: who produced the data, with which code, as of when.

A report without this is unanswerable six months later: "which upstream commit
was this built on, which indicator flavour, which formula version?" Those
answers decide whether two reports are comparable at all.

The fields are collected from four places — git (both commits), the run config
(extension version, provider chains), the installed vendor SDK, and module-level
version constants for the formula/rule sets that live in this package.
"""

from __future__ import annotations

import html as html_module
import importlib.metadata
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

#: Bump when the statement field mapping, units or PIT rules change shape.
FINANCIAL_FORMULA_VERSION = "2026.11-stmt1"
#: Bump when limit ratios, lot rules or the calendar semantics change.
MARKET_RULES_VERSION = "2026.11-rules1"

_REPO_ROOT = Path(__file__).resolve().parents[1]
_MARKER = "## Downstream run metadata"


def _git_short(revision: str) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(_REPO_ROOT), "rev-parse", "--short", revision],
            capture_output=True, text=True, timeout=3, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return completed.stdout.strip() or "unknown"


def _providers(config: dict) -> str:
    chains = list((config.get("data_vendors") or {}).values())
    named = {vendor.strip() for chain in chains for vendor in str(chain).split(",") if vendor.strip()}
    return ",".join(sorted(named)) or "unknown"


def _provider_revision() -> str:
    try:
        return f"tushare {importlib.metadata.version('tushare')}"
    except importlib.metadata.PackageNotFoundError:
        return "tushare not installed"


def collect(config: dict, trade_date: str) -> dict:
    """The nine provenance fields recorded for a run."""
    return {
        "upstream_commit": _git_short("upstream/main"),
        "downstream_commit": _git_short("HEAD"),
        "extension_version": str(config.get("cn_extension_version") or "unknown"),
        "data_provider": _providers(config),
        "provider_revision": _provider_revision(),
        "financial_formula_version": FINANCIAL_FORMULA_VERSION,
        "market_rules_version": MARKET_RULES_VERSION,
        "data_as_of": str(trade_date or "unknown"),
        "data_retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def attach(report_path: Path, metadata: dict) -> None:
    """Write the metadata next to the report and into both rendered forms."""
    report_path = Path(report_path)
    directory = report_path.parent
    (directory / "run_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    markdown = report_path
    if markdown.exists():
        text = markdown.read_text(encoding="utf-8")
        if _MARKER not in text:
            lines = [_MARKER, ""] + [f"- {key}: {value}" for key, value in metadata.items()]
            markdown.write_text(text.rstrip() + "\n\n" + "\n".join(lines) + "\n", encoding="utf-8")

    page = directory / "complete_report.html"
    if page.exists():
        page_text = page.read_text(encoding="utf-8")
        if "downstream-run-metadata" not in page_text:
            rows = "".join(
                f"<li><code>{html_module.escape(key)}</code>: "
                f"{html_module.escape(str(value))}</li>"
                for key, value in metadata.items()
            )
            block = (
                '<section id="downstream-run-metadata">'
                "<h2>Downstream run metadata</h2><ul>" + rows + "</ul></section>"
            )
            page_text = page_text.replace("</body>", block + "\n</body>", 1)
            page.write_text(page_text, encoding="utf-8")
