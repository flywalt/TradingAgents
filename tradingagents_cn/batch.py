"""Batch runner: tickers x dates, one graph per task, failures isolated.

Why not upstream's ``tradingagents/backtest.py``: it constructs
``TradingAgentsGraph`` itself, so a batch through it would skip registration and
A-share identity entirely. This runner re-implements only the thin scheduling
loop and reuses the factory for every task — the analysis itself stays upstream.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from tradingagents_cn.graph import factory as graph_factory


@dataclass(frozen=True)
class BatchResult:
    ticker: str
    date: str
    rating: str | None = None
    report_path: Path | None = None
    error: str | None = None


def run_batch(
    tickers: Iterable[str],
    dates: Iterable[str],
    *,
    config: dict | None = None,
    market: str | None = None,
    selected_analysts: Sequence[str] = ("market", "social", "news", "fundamentals"),
    on_result=None,
) -> list[BatchResult]:
    """Run every ticker/date pair; one failing task does not stop the batch.

    A fresh graph per task keeps checkpoint state and configuration independent —
    the same rule the single-run path follows, for the same reason.
    """
    results: list[BatchResult] = []

    for ticker in tickers:
        for trade_date in dates:
            try:
                graph = graph_factory.build_graph(
                    config,
                    market=market,
                    symbol=ticker,
                    selected_analysts=tuple(selected_analysts),
                )
                state, rating = graph.propagate(ticker, trade_date)
                path = graph.save_reports(state, ticker)
                result = BatchResult(ticker, trade_date, rating=rating, report_path=path)
            except Exception as exc:  # noqa: BLE001 - one task must not sink the batch
                result = BatchResult(ticker, trade_date, error=f"{type(exc).__name__}: {exc}")
            results.append(result)
            if on_result is not None:
                on_result(result)
    return results
