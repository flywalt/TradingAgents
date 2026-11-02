"""Job and event persistence: the only place that writes SQL."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import UTC, datetime

_TERMINAL = {"succeeded", "failed"}

#: LangGraph runs parallel branches in threads, so callbacks write events from
#: several threads at once. One SQLite connection cannot serve them concurrently
#: (the sequence read and the insert tear, losing events or killing the run), so
#: every event append is serialised here. The critical section is one small
#: statement pair; the run itself stays parallel.
_EVENT_LOCK = threading.Lock()


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def create(
    conn: sqlite3.Connection,
    *,
    symbol: str,
    market: str,
    profile: str,
    trade_date: str,
    analysts: list[str],
    language: str,
    strict: bool,
    portfolio_json: str | None,
    display_name: str | None = None,
) -> str:
    run_id = uuid.uuid4().hex
    conn.execute(
        """INSERT INTO runs (id, symbol, market, profile, display_name, trade_date,
                             analysts, language, strict, portfolio_json, status, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?, 'queued', ?)""",
        (run_id, symbol, market, profile, display_name, trade_date,
         json.dumps(analysts), language, int(strict), portfolio_json, _now()),
    )
    conn.commit()
    return run_id


def get(conn: sqlite3.Connection, run_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
    return dict(row) if row else None


def list_runs(
    conn: sqlite3.Connection,
    *,
    symbol: str | None = None,
    status: str | None = None,
    rating: str | None = None,
    page: int = 1,
    size: int = 20,
) -> tuple[list[dict], int]:
    clauses, params = [], []
    for column, value in (("symbol", symbol), ("status", status), ("rating", rating)):
        if value:
            clauses.append(f"{column}=?")
            params.append(value)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    total = conn.execute(f"SELECT COUNT(*) FROM runs {where}", params).fetchone()[0]
    rows = conn.execute(
        f"SELECT * FROM runs {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
        [*params, size, (page - 1) * size],
    ).fetchall()
    return [dict(row) for row in rows], total


def mark_running(conn: sqlite3.Connection, run_id: str) -> None:
    conn.execute("UPDATE runs SET status='running', started_at=? WHERE id=?", (_now(), run_id))
    conn.commit()


def finish(
    conn: sqlite3.Connection, run_id: str, *, rating: str, run_dir: str, report_path: str
) -> None:
    conn.execute(
        """UPDATE runs SET status='succeeded', rating=?, run_dir=?, report_path=?,
                            finished_at=? WHERE id=?""",
        (rating, run_dir, report_path, _now(), run_id),
    )
    conn.commit()


def fail(conn: sqlite3.Connection, run_id: str, *, category: str, message: str) -> None:
    conn.execute(
        """UPDATE runs SET status='failed', error_category=?, error_message=?,
                            finished_at=? WHERE id=?""",
        (category, message[:2000], _now(), run_id),
    )
    conn.commit()


def append_event(conn: sqlite3.Connection, run_id: str, kind: str, payload: dict) -> int:
    """Append with a per-run sequence number; the stream id is this sequence.

    Safe to call from any thread: the sequence is read, used and committed under
    one lock, so concurrent appends cannot collide on (run_id, seq).
    """
    with _EVENT_LOCK:
        seq = conn.execute(
            "SELECT COALESCE(MAX(seq), 0) + 1 FROM events WHERE run_id=?", (run_id,)
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO events (run_id, seq, kind, payload, created_at) VALUES (?,?,?,?,?)",
            (run_id, seq, kind, json.dumps(payload, ensure_ascii=False), _now()),
        )
        conn.execute(
            """DELETE FROM events WHERE run_id=? AND kind='message' AND seq <= ?""",
            (run_id, seq - 5000),
        )
        conn.commit()
    return seq


def events_after(conn: sqlite3.Connection, run_id: str, after: int = 0) -> list[dict]:
    rows = conn.execute(
        "SELECT seq, kind, payload, created_at FROM events WHERE run_id=? AND seq>? ORDER BY seq",
        (run_id, after),
    ).fetchall()
    return [
        {"seq": row["seq"], "kind": row["kind"],
         "payload": json.loads(row["payload"]), "at": row["created_at"]}
        for row in rows
    ]


def is_final(conn: sqlite3.Connection, run_id: str) -> bool:
    row = conn.execute("SELECT status FROM runs WHERE id=?", (run_id,)).fetchone()
    return bool(row and row["status"] in _TERMINAL)


def recover(conn: sqlite3.Connection) -> list[str]:
    """After a crash: interrupt running jobs, re-queue pending ones in order."""
    conn.execute(
        """UPDATE runs SET status='failed', error_category='interrupted',
                            error_message='service restarted while running',
                            finished_at=? WHERE status='running'""",
        (_now(),),
    )
    queued = [row["id"] for row in conn.execute(
        "SELECT id FROM runs WHERE status='queued' ORDER BY rowid"
    ).fetchall()]
    conn.commit()
    return queued


def queue_position(conn: sqlite3.Connection, run_id: str) -> int:
    """1-based position among queued jobs (0 for a job that is no longer queued)."""
    row = conn.execute("SELECT status, rowid FROM runs WHERE id=?", (run_id,)).fetchone()
    if row is None or row["status"] != "queued":
        return 0
    # rowid is the insertion order; created_at has one-second resolution and
    # would tie two jobs queued in the same second.
    return conn.execute(
        "SELECT COUNT(*) FROM runs WHERE status='queued' AND rowid<=?",
        (row["rowid"],),
    ).fetchone()[0]


def queued_count(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM runs WHERE status='queued'").fetchone()[0]


def running_count(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM runs WHERE status='running'").fetchone()[0]
