"""Entry points must go through the factory — enforced by a scan, not a promise.

Upstream's CLI and backtest construct ``TradingAgentsGraph`` themselves, which
would skip registration, A-share identity and run metadata. The downstream CLI
and batch runner exist so production has no reason to use those paths, and this
test keeps a future module from quietly adding a third one.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tradingagents_cn import cli
from tradingagents_cn.batch import run_batch
from tradingagents_cn.graph import factory as graph_factory

pytestmark = pytest.mark.unit

PACKAGE = Path(__file__).resolve().parents[2] / "tradingagents_cn"


class FakeGraph:
    def __init__(self, fail_on=None):
        self.calls: list[tuple[str, str]] = []
        self.fail_on = fail_on

    def propagate(self, ticker, trade_date, **kwargs):
        self.calls.append((ticker, trade_date))
        if self.fail_on == ticker:
            raise RuntimeError("provider down")
        return {"trade_date": trade_date}, "Hold"

    def save_reports(self, state, ticker, save_path=None, html=True):
        return Path("/tmp") / f"{ticker}-{state['trade_date']}.md"


def _instantiates_upstream_graph(path: Path) -> bool:
    """AST-level: a call to TradingAgentsGraph itself, not a substring in prose."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = getattr(func, "id", None) or getattr(func, "attr", None)
            if name == "TradingAgentsGraph":
                return True
    return False


def test_no_module_writes_a_direct_upstream_constructor_call():
    """The factory selects the class by profile; nothing else may hardcode it.

    The factory reaches the upstream class through a variable, so this scan sees
    no literal call — the behavioural guarantee lives in test_market_profiles.py.
    """
    offenders = [
        str(path.relative_to(PACKAGE))
        for path in PACKAGE.rglob("*.py")
        if _instantiates_upstream_graph(path)
    ]
    assert offenders == []


def test_the_downstream_cli_and_batch_import_the_factory():
    for name in ("cli.py", "batch.py"):
        text = (PACKAGE / name).read_text(encoding="utf-8")
        assert "graph_factory" in text, name


def test_the_cli_runs_through_the_factory(monkeypatch, capsys):
    seen = {}

    def fake_build(config, **kwargs):
        seen["config"] = config
        seen["analysts"] = kwargs.get("selected_analysts")
        return FakeGraph()

    monkeypatch.setattr(graph_factory, "build_graph", fake_build)

    code = cli.main(["analyze", "--ticker", "600519.SH", "--date", "2026-10-30",
                     "--analysts", "market,fundamentals", "--strict"])

    assert code == 0
    assert seen["analysts"] == ("market", "fundamentals")
    assert seen["config"]["cn_strict_ashare"] is True
    assert "report:" in capsys.readouterr().out


def test_the_cli_accepts_a_run_and_rejects_a_bypass_flag():
    """The parser is the whole surface: there is no --use-upstream-graph escape."""
    parser = cli.build_parser()
    args = parser.parse_args(["analyze", "--ticker", "600519.SH", "--date", "2026-10-30"])

    assert args.ticker == "600519.SH"
    for forbidden in ("--graph", "--backend", "--direct", "--upstream-graph"):
        with pytest.raises(SystemExit):
            parser.parse_args(["analyze", "--ticker", "X", "--date", "2026-10-30", forbidden])


def test_batch_runs_every_pair_and_isolates_failures(monkeypatch):
    graphs = {}

    def fake_build(config, **kwargs):
        ticker = "600519.SH" if len(graphs) % 2 == 0 else "000001.SZ"
        graph = FakeGraph(fail_on="000001.SZ" if ticker == "000001.SZ" else None)
        graphs[ticker] = graph
        return graph

    monkeypatch.setattr(graph_factory, "build_graph", fake_build)

    results = run_batch(["600519.SH", "000001.SZ"], ["2026-10-30"])

    assert len(results) == 2
    assert results[0].error is None and results[0].rating == "Hold"
    assert results[1].error is not None and "provider down" in results[1].error


def test_batch_uses_one_graph_per_task(monkeypatch):
    built = []

    def fake_build(config, **kwargs):
        built.append(1)
        return FakeGraph()

    monkeypatch.setattr(graph_factory, "build_graph", fake_build)

    run_batch(["600519.SH", "000001.SZ"], ["2026-10-30", "2026-10-29"])

    assert len(built) == 4


def test_batch_passes_raw_config_and_the_symbol(monkeypatch):
    seen = {}

    def fake_build(config, **kwargs):
        seen["config"] = config
        seen["symbol"] = kwargs.get("symbol")
        return FakeGraph()

    monkeypatch.setattr(graph_factory, "build_graph", fake_build)

    run_batch(["600519.SH"], ["2026-10-30"], config={"cn_strict_ashare": True})

    assert seen["config"]["cn_strict_ashare"] is True
    assert seen["symbol"] == "600519.SH"
    assert "cn_market_profile" not in seen["config"]
