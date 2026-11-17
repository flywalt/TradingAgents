"""A broken data vendor must be loud at startup, not silent per call.

The tushare client is built lazily on purpose (it is an optional dependency and a
missing token is a legitimate local state). The cost of that design showed up in
production once: a clean venv whose ``six`` was missing made *every* A-share call
degrade -- preview returned ``name: null``, search returned ``[]``, the report
came out plausible but empty -- and nothing at all was written to the journal.

So the process that owns the queue probes the client once at startup: no network,
no data fetch, just "can this be built at all". A failure is a warning, never a
crash (the UI still has to serve pages and the operator still has to be able to
read the reason).
"""

from __future__ import annotations

import logging

import pytest

from tradingagents.dataflows.errors import VendorNotConfiguredError
from tradingagents_cn.vendors.tushare import client as tushare_client
from tradingagents_web.app import create_app

pytestmark = pytest.mark.unit

TOKEN = "user-token"


class RecordingWorker:
    def __init__(self):
        self.started = False

    def submit(self, run_id: str) -> None:
        raise AssertionError("no job is submitted in these tests")

    def start(self):
        self.started = True
        return []


def _engine_app(tmp_path, **kwargs):
    return create_app(db_path=str(tmp_path / "state.db"), token=TOKEN,
                      role="engine", worker=RecordingWorker(), **kwargs)


def test_startup_warns_with_the_real_cause_when_the_client_cannot_be_built(tmp_path,
                                                                          monkeypatch, caplog):
    def missing_six():
        raise VendorNotConfiguredError(
            "tushare is not importable (No module named 'six'); "
            "run: pip install -r requirements-downstream.txt")

    monkeypatch.setenv(tushare_client.TOKEN_ENV, "test-token")
    monkeypatch.setattr(tushare_client, "get_api", missing_six)

    with caplog.at_level(logging.WARNING):
        _engine_app(tmp_path)          # still builds: degradation is not a crash

    warnings = [record.getMessage() for record in caplog.records
                if record.levelno >= logging.WARNING]
    assert any("tushare" in message and "six" in message for message in warnings), \
        f"启动自检没把真实原因写进日志：{warnings}"


def test_startup_is_quiet_when_the_client_builds(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv(tushare_client.TOKEN_ENV, "test-token")
    monkeypatch.setattr(tushare_client, "get_api", lambda: object())

    with caplog.at_level(logging.WARNING):
        _engine_app(tmp_path)

    assert not [record for record in caplog.records
                if record.levelno >= logging.WARNING]


def test_the_ui_role_never_builds_the_data_client(tmp_path, monkeypatch):
    calls = []

    def build():
        calls.append(1)
        return object()

    monkeypatch.setenv(tushare_client.TOKEN_ENV, "test-token")
    monkeypatch.setattr(tushare_client, "get_api", build)

    create_app(db_path=str(tmp_path / "state.db"), token=TOKEN, role="ui",
               engine_base="http://engine", worker=RecordingWorker())

    assert calls == [], "UI 进程不该碰数据栈（它只出页面并转发 /api）"
