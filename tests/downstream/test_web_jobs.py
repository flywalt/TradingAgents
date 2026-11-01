"""Job store: queue order, recovery, event sequencing."""

from __future__ import annotations

import pytest

from tradingagents_web import db, jobs

pytestmark = pytest.mark.unit


@pytest.fixture
def conn(tmp_path):
    connection = db.connect(tmp_path / "state.db")
    try:
        yield connection
    finally:
        connection.close()


def _create(conn, symbol="600519.SH"):
    return jobs.create(conn, symbol=symbol, market="CN", profile="CN_A_SHARE",
                       trade_date="2026-10-30", analysts=["market"], language="English",
                       strict=False, portfolio_json=None)


def test_queue_position_follows_creation_order(conn):
    first, second = _create(conn), _create(conn)

    assert jobs.queue_position(conn, first) == 1
    assert jobs.queue_position(conn, second) == 2


def test_recovery_fails_running_and_requeues_pending(conn):
    running, queued = _create(conn), _create(conn)
    jobs.mark_running(conn, running)

    recovered = jobs.recover(conn)

    assert recovered == [queued]
    failed = jobs.get(conn, running)
    assert failed["status"] == "failed"
    assert failed["error_category"] == "interrupted"


def test_events_get_per_run_sequence_numbers(conn):
    run_id = _create(conn)

    assert jobs.append_event(conn, run_id, "run.started", {}) == 1
    assert jobs.append_event(conn, run_id, "node.started", {"node": "Trader"}) == 2

    events = jobs.events_after(conn, run_id, after=1)
    assert [event["seq"] for event in events] == [2]
    assert events[0]["payload"]["node"] == "Trader"


def test_finish_and_fail_are_terminal(conn):
    run_id = _create(conn)
    jobs.finish(conn, run_id, rating="Hold", run_dir="/tmp/r", report_path="/tmp/r/x.html")

    assert jobs.get(conn, run_id)["status"] == "succeeded"
    assert jobs.is_final(conn, run_id) is True

    other = _create(conn)
    jobs.fail(conn, other, category="no_data", message="none")
    assert jobs.get(conn, other)["error_category"] == "no_data"
