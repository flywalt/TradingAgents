"""Single worker: one job at a time, FIFO, with crash recovery on start.

Concurrency is deliberately 1: the graph mutates process-wide configuration and
recompiles its checkpointed graph, so two jobs in one process would fight. The
queue holds at most three waiting jobs, which also caps accidental spend.
"""

from __future__ import annotations

import logging
import queue
import threading

from . import db, jobs, runner

logger = logging.getLogger(__name__)


class Worker:
    def __init__(self, db_path, execute=None, poll_seconds: float = 0.2):
        self._db_path = db_path
        self._execute = execute or runner.execute
        self._poll = poll_seconds
        self._queue: queue.Queue[str | None] = queue.Queue()
        self._thread: threading.Thread | None = None

    def submit(self, run_id: str) -> None:
        self._queue.put(run_id)

    def start(self) -> list[str]:
        conn = db.connect(self._db_path)
        try:
            requeued = jobs.recover(conn)
        finally:
            conn.close()
        for run_id in requeued:
            self.submit(run_id)
        self._thread = threading.Thread(target=self._loop, name="tradingagents-web-worker",
                                        daemon=True)
        self._thread.start()
        return requeued

    def stop(self) -> None:
        self._queue.put(None)
        if self._thread is not None:
            self._thread.join(timeout=30)

    def _loop(self) -> None:
        conn = db.connect(self._db_path)
        try:
            while True:
                run_id = self._queue.get()
                try:
                    if run_id is None:
                        return
                    self._execute(conn, run_id)
                finally:
                    self._queue.task_done()
        finally:
            conn.close()
