"""Downstream command line: the A-share entry point that cannot bypass the factory.

Upstream's ``cli/run.py`` constructs ``TradingAgentsGraph`` directly, so using it
means no registration, no Tushare identity, no metadata and a silent Yahoo data
path. This module exists so that production runs have an entry point that always
goes through ``build_graph()``.

Deliberately small: argument parsing, one graph per task, print where the report
landed. Interactive wizards and display belong to a later web/CLI layer.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from tradingagents_cn import config as cn_config
from tradingagents_cn.graph import factory as graph_factory

DEFAULT_ANALYSTS = "market,social,news,fundamentals"


def _analysts(value: str) -> tuple[str, ...]:
    keys = tuple(part.strip() for part in str(value).split(",") if part.strip())
    if not keys:
        raise argparse.ArgumentTypeError("at least one analyst is required")
    return keys


def _base_config(args) -> dict:
    overrides: dict = {}
    if getattr(args, "strict", False):
        overrides["cn_strict_ashare"] = True
    if getattr(args, "output", None):
        overrides["results_dir"] = str(Path(args.output).expanduser())
    return overrides


def analyze(args) -> int:
    graph = graph_factory.build_graph(
        _base_config(args),
        market=args.market,
        symbol=args.ticker,
        selected_analysts=args.analysts,
    )
    state, rating = graph.propagate(args.ticker, args.date)
    path = graph.save_reports(state, args.ticker)
    print(f"{args.ticker} {args.date}: {rating}")
    print(f"report: {path}")
    return 0


def batch(args) -> int:
    from tradingagents_cn.batch import run_batch

    results = run_batch(
        tickers=args.tickers,
        dates=args.dates,
        config=_base_config(args),
        market=args.market,
        selected_analysts=args.analysts,
    )
    failures = 0
    for result in results:
        if result.error:
            failures += 1
            print(f"{result.ticker} {result.date}: FAILED ({result.error})")
        else:
            print(f"{result.ticker} {result.date}: {result.rating} -> {result.report_path}")
    return 1 if failures else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tradingagents-cn", description="A-share research runs")
    sub = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--analysts", type=_analysts,
                        default=_analysts(DEFAULT_ANALYSTS),
                        help="comma separated analyst keys")
    common.add_argument("--strict", action="store_true",
                        help="Tushare-only chains (CN_A_SHARE only)")
    common.add_argument("--market",
                        help="market code (CN/HK/US/...); inferred from the symbol when omitted")
    common.add_argument("--output", help="results directory override")

    single = sub.add_parser("analyze", parents=[common], help="run one ticker/date")
    single.add_argument("--ticker", required=True)
    single.add_argument("--date", required=True, help="YYYY-MM-DD")
    single.set_defaults(func=analyze)

    many = sub.add_parser("batch", parents=[common], help="run tickers x dates")
    many.add_argument("--tickers", type=_analysts, required=True)
    many.add_argument("--dates", type=_analysts, required=True)
    many.set_defaults(func=batch)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover - module entry point
    sys.exit(main())
