"""Execution: the sequence, the artifacts, the failure categories, the worker."""

from __future__ import annotations

import json
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from tradingagents_web import db, jobs, runner
from tradingagents_web.worker import Worker

pytestmark = pytest.mark.unit


class FakeGraph:
    def __init__(self, tmp_path: Path, *, fail_save: bool = False):
        self.config = {"results_dir": str(tmp_path), "cn_market_profile": "CN_A_SHARE",
                       "checkpoint_enabled": False}
        self.propagator = SimpleNamespace(get_graph_args=lambda callbacks=None: {})
        self.fail_save = fail_save
        self.recorded = False

    def create_run_state(self, symbol, trade_date, asset_type="stock", portfolio=None):
        return {"company_of_interest": symbol}

    def stream_run(self, state, **args):
        yield [], {"market_report": "m"}
        yield [], {"final_trade_decision": "**Rating**: Hold"}

    def save_reports(self, final, symbol, save_path=None):
        if self.fail_save:
            raise OSError("disk full")
        target = Path(save_path)
        target.mkdir(parents=True, exist_ok=True)
        path = target / "complete_report.html"
        path.write_text("<html></html>", encoding="utf-8")
        return path

    def record_decision(self, symbol, trade_date, final):
        self.recorded = True


def _job(conn):
    return jobs.create(conn, symbol="600519.SH", market="CN", profile="CN_A_SHARE",
                       trade_date="2026-10-30", analysts=["market"], language="Chinese",
                       strict=False, portfolio_json=None)


@pytest.fixture
def conn(tmp_path):
    connection = db.connect(tmp_path / "state.db")
    try:
        yield connection
    finally:
        connection.close()


def test_a_successful_run_records_artifacts_rating_and_decision(conn, tmp_path):
    run_id = _job(conn)
    graph = FakeGraph(tmp_path)

    runner.execute(conn, run_id, build_graph=lambda *a, **k: graph)

    job = jobs.get(conn, run_id)
    assert job["status"] == "succeeded" and job["rating"] == "Hold"
    assert graph.recorded is True

    run_dir = Path(job["run_dir"])
    assert (run_dir / "report" / "complete_report.html").is_file()
    payload = json.loads((run_dir / "job.json").read_text(encoding="utf-8"))
    assert payload["data_as_of"] == "2026-10-30"       # chart anchor contract
    assert payload["qfq_anchor"] == "2026-10-30"
    assert payload["profile"] == "CN_A_SHARE"

    kinds = [event["kind"] for event in jobs.events_after(conn, run_id)]
    assert "run.started" in kinds and "run.finished" in kinds
    assert "report.ready" in kinds


def test_a_market_error_is_classified_and_terminal(conn, tmp_path):
    run_id = _job(conn)

    def broken(*args, **kwargs):
        raise ValueError("cannot tell the market of '0700'")

    runner.execute(conn, run_id, build_graph=broken)

    job = jobs.get(conn, run_id)
    assert job["status"] == "failed" and job["error_category"] == "symbol_ambiguous"
    kinds = [event["kind"] for event in jobs.events_after(conn, run_id)]
    assert "run.failed" in kinds


def test_a_report_write_failure_keeps_its_own_category(conn, tmp_path):
    run_id = _job(conn)
    graph = FakeGraph(tmp_path, fail_save=True)

    runner.execute(conn, run_id, build_graph=lambda *a, **k: graph)

    job = jobs.get(conn, run_id)
    assert job["status"] == "failed" and job["error_category"] == "report_write"
    assert graph.recorded is False        # no memory entry without a report


def test_the_worker_runs_queued_jobs_and_reports_recovery(tmp_path):
    db_path = tmp_path / "state.db"
    conn = db.connect(db_path)
    done = []

    def execute(conn_, run_id):
        done.append(run_id)
        jobs.finish(conn_, run_id, rating="Hold", run_dir=str(tmp_path), report_path=str(tmp_path))

    queued = jobs.create(conn, symbol="600519.SH", market="CN", profile="CN_A_SHARE",
                         trade_date="2026-10-30", analysts=["market"], language="English",
                         strict=False, portfolio_json=None)
    interrupted = jobs.create(conn, symbol="000001.SZ", market="CN", profile="CN_A_SHARE",
                              trade_date="2026-10-30", analysts=["market"], language="English",
                              strict=False, portfolio_json=None)
    jobs.mark_running(conn, interrupted)
    conn.close()

    worker = Worker(db_path, execute=execute)
    requeued = worker.start()
    try:
        deadline = time.time() + 5
        while time.time() < deadline and not done:
            time.sleep(0.05)
    finally:
        worker.stop()

    assert requeued == [queued]
    assert done == [queued]
    check = db.connect(db_path)
    try:
        assert jobs.get(check, interrupted)["error_category"] == "interrupted"
    finally:
        check.close()


def test_the_run_honours_the_selected_analysts(conn, tmp_path):
    """A job that asked for one analyst must not run all four."""
    run_id = jobs.create(conn, symbol="600519.SH", market="CN", profile="CN_A_SHARE",
                         trade_date="2026-10-30", analysts=["market"], language="English",
                         strict=False, portfolio_json=None)
    graph = FakeGraph(tmp_path)
    seen = {}

    def build(config, **kwargs):
        seen.update(kwargs)
        return graph

    runner.execute(conn, run_id, build_graph=build)

    assert seen["selected_analysts"] == ("market",)


def test_progress_maps_subgraph_namespaces_to_their_analyst():
    from tradingagents_web.runner import Progress

    events = []
    progress = Progress(lambda kind, payload: events.append((kind, payload)))

    progress.on_chain_start(None, None, metadata={"langgraph_node": "agent",
                                                  "langgraph_checkpoint_ns": "news_analyst:abc"})
    progress.on_chain_end(None, metadata={"langgraph_node": "agent",
                                          "langgraph_checkpoint_ns": "News Analyst:abc"})

    assert events == [("node.started", {"node": "News Analyst"}),
                      ("node.finished", {"node": "News Analyst"})]


def test_progress_ignores_model_and_tool_nodes():
    from tradingagents_web.runner import Progress

    events = []
    progress = Progress(lambda kind, payload: events.append((kind, payload)))
    progress.on_chain_start(None, None, metadata={"langgraph_node": "model"})

    assert events == []
