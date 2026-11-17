"""The UI process must not load the analysis stack.

Measured on the deployed box: importing ``tradingagents_web.worker`` pulled
``tradingagents_web.runner`` -- and with it the whole graph (langgraph +
langchain). The UI renders pages and forwards ``/api``; it never executes a job,
so it never needs any of that.

Honest scope: ``tradingagents.agents.context`` (imported by ``app.py`` for
identity resolution) already drags in langchain, so this is a small win, not the
"tens of MB" it looks like. It is still the right shape -- a role that cannot
run a job must not pay for the machinery that does.

These run in subprocesses: ``sys.modules`` in the pytest process is polluted by
every other test, so an in-process assertion would pass or fail for the wrong
reason.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]


def _run(code: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-c", code], cwd=REPO_ROOT,
                          capture_output=True, text=True, timeout=120)


def test_importing_the_web_shell_does_not_load_the_runner():
    completed = _run(
        "import sys, tradingagents_web.app\n"
        "assert 'tradingagents_web.runner' not in sys.modules, 'app 导入链把 runner 拉进来了'\n"
        "print('ok')\n"
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "ok"


def test_a_worker_that_never_runs_a_job_does_not_load_the_runner(tmp_path):
    database = tmp_path / "state.db"
    completed = _run(
        "import sys\n"
        "from tradingagents_web.worker import Worker\n"
        f"worker = Worker({str(database)!r})\n"
        "worker.start()\n"
        "worker.stop()\n"
        "assert 'tradingagents_web.runner' not in sys.modules, '空队列也把分析栈拉起来了'\n"
        "print('ok')\n"
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "ok"


def test_the_default_execute_is_resolved_when_a_job_runs(tmp_path, monkeypatch):
    """Laziness must not cost correctness: no ``execute`` given means "the runner".

    The queue is fed directly (no DB bookkeeping needed) and the runner is
    stubbed, so this asserts the wiring, not a real analysis.
    """
    from tradingagents_web import runner, worker as worker_module

    seen: list[str] = []
    monkeypatch.setattr(runner, "execute", lambda conn, run_id: seen.append(run_id))

    instance = worker_module.Worker(str(tmp_path / "state.db"))
    instance.submit("run-1")
    instance.start()
    instance.stop()

    assert seen == ["run-1"]
