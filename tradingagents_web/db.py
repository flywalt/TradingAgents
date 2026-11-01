"""SQLite storage for the web shell: one database, two tables, no ORM.

A single database on purpose: results directories are separated by market
profile, so storing job state inside them would split history in two.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY,
  symbol TEXT NOT NULL,
  market TEXT NOT NULL,
  profile TEXT NOT NULL,
  display_name TEXT,
  trade_date TEXT NOT NULL,
  analysts TEXT NOT NULL,
  language TEXT NOT NULL,
  strict INTEGER NOT NULL DEFAULT 0,
  portfolio_json TEXT,
  status TEXT NOT NULL,
  rating TEXT,
  error_category TEXT,
  error_message TEXT,
  run_dir TEXT,
  report_path TEXT,
  created_at TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  seq INTEGER NOT NULL,
  kind TEXT NOT NULL,
  payload TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status, created_at);
CREATE INDEX IF NOT EXISTS idx_runs_symbol ON runs(symbol, trade_date);
CREATE UNIQUE INDEX IF NOT EXISTS idx_events ON events(run_id, seq);
"""


def connect(path: str | Path) -> sqlite3.Connection:
    """Open (and migrate) the database; callers own the connection."""
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version >= SCHEMA_VERSION:
        return
    conn.executescript(_SCHEMA)
    conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
    conn.commit()
