"""Read a finished report the way a careful reader would, and list what is off.

Not a gate and not a judge: it prints the handful of things a reviewer looks for
first, so a problem seen once in a report becomes a check that runs every time.
No model, no network - every rule here is a deterministic scan of the files the
kernel wrote.

    python scripts/report_lint.py ~/.tradingagents/logs/profile-cn/600519.SH/2026-11-03/runs/<id>/report

Exit status is always 0: a lint that fails a run would be a gate, and this is
deliberately the cheaper thing that comes first.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# The script runs from the repo root; make the package importable either way.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

#: A bold label left in Latin script inside a Chinese report - whether the kernel
#: wrote it or the model invented it, the reader sees English where the page is
#: otherwise Chinese.
#: Both forms, so the same rule reads the served HTML and the raw markdown.
LATIN_BOLD = re.compile(
    r"(?:<strong>|\*\*)([A-Za-z][A-Za-z /&'-]{1,40})(?:</strong>|\*\*)")
TAG = re.compile(r"<[^>]+>")

#: A number with no source nearby is the failure mode prompt work targets.
UNSOURCED_HINT = re.compile(r"营收同比增长\s*\d|净利润同比增长\s*\d")

#: Claiming an intraday path from daily bars.
INTRADAY_CLAIM = re.compile(r"盘中(冲高|跳水|拉升|回落)")

#: The data layer's own words, used to tell "quiet" from "broken".
NO_ITEMS = re.compile(r"NO_ITEMS|无条目")
UNAVAILABLE = re.compile(r"UNAVAILABLE|不可用")


def _reader_html(report_dir: Path) -> str | None:
    """The page as served: the presentation pass applied, markup intact."""
    page = report_dir / "complete_report.html"
    if not page.is_file():
        return None
    from tradingagents_web.report_page import present

    return present(page.read_text(encoding="utf-8"), "中文")


def _files(report_dir: Path) -> list[Path]:
    return sorted(report_dir.glob("1_analysts/*.md"))


def lint(report_dir: Path) -> list[tuple[str, str, int]]:
    """(severity, finding, count) triples, most important first."""
    findings: list[tuple[str, str, int]] = []
    served = _reader_html(report_dir)
    if served is not None:
        raw = {"complete_report.html": served}
        text = {"complete_report.html": TAG.sub(" ", served)}
    else:
        files = _files(report_dir)
        if not files:
            return [("warn", "no report found (complete_report.html or 1_analysts/)", 0)]
        raw = {path.name: path.read_text(encoding="utf-8") for path in files}
        text = raw
    joined = "\n".join(text.values())

    latin = LATIN_BOLD.findall("\n".join(raw.values()))
    if latin:
        sample = ", ".join(sorted(set(latin))[:3])
        findings.append(("warn", f"bold label still in English ({sample})", len(latin)))

    intraday = len(INTRADAY_CLAIM.findall(joined))
    if intraday:
        findings.append(("warn", "intraday path claimed (daily bars only)", intraday))

    unsourced = len(UNSOURCED_HINT.findall(joined))
    if unsourced:
        findings.append(("warn", "growth figure without a visible source", unsourced))

    for name, chunk in text.items():
        if NO_ITEMS.search(chunk) and UNAVAILABLE.search(chunk):
            continue  # both markers present: the split is being used
        if re.search(r"UNAVAILABLE[^\n]*(no items|returned no)", chunk, re.I):
            findings.append(("warn", f"{name}: empty source labelled UNAVAILABLE", 1))

    if not re.search(r"前复权|qfq|后复权|不复权", joined):
        findings.append(("warn", "price basis (复权) never stated", 1))

    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report_dir", type=Path)
    args = parser.parse_args(argv)

    if not args.report_dir.is_dir():
        print(f"not a directory: {args.report_dir}", file=sys.stderr)
        return 2

    findings = lint(args.report_dir)
    if not findings:
        print(f"{args.report_dir}: nothing to flag")
        return 0
    width = max(len(finding) for _severity, finding, _count in findings)
    for severity, finding, count in findings:
        suffix = f" x{count}" if count > 1 else ""
        print(f"{severity:4}  {finding:<{width}}{suffix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
