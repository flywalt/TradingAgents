"""M1: the UI and the engine as two processes, one contract between them."""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from tradingagents_web.app import create_app

pytestmark = pytest.mark.unit

TOKEN = "user-token"
ENGINE_TOKEN = "engine-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


class RecordingWorker:
    def __init__(self):
        self.submitted: list[str] = []
        self.started = False

    def submit(self, run_id: str) -> None:
        self.submitted.append(run_id)

    def start(self):
        self.started = True
        return []


def _stub_engine() -> FastAPI:
    """A tiny stand-in for the engine: echoes auth, serves one event."""
    app = FastAPI()
    seen: list[str] = []
    app.state.seen = seen

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    @app.get("/api/ping")
    def ping():
        return {"pong": True}

    @app.get("/api/events")
    def events():
        def stream():
            yield 'data: {"kind": "run.started"}\n\n'
            yield 'data: {"kind": "run.finished"}\n\n'
        return StreamingResponse(stream(), media_type="text/event-stream")

    return app


def test_an_engine_process_serves_the_api_only(tmp_path):
    app = create_app(db_path=str(tmp_path / "state.db"), token=TOKEN,
                     role="engine", engine_token=ENGINE_TOKEN, worker=RecordingWorker())
    with TestClient(app) as client:
        assert client.get("/", headers=AUTH).status_code == 404      # no pages
        assert client.get("/healthz").status_code == 200
        assert client.get("/api/runs", headers={"Authorization": f"Bearer {ENGINE_TOKEN}"}
                          ).status_code == 200
        assert client.get("/api/runs", headers=AUTH).status_code == 401


def test_a_ui_process_does_not_run_jobs(tmp_path):
    worker = RecordingWorker()
    app = create_app(db_path=str(tmp_path / "state.db"), token=TOKEN, role="ui",
                     worker=worker, engine_base="http://engine")
    with TestClient(app) as client:
        assert client.get("/", headers=AUTH).status_code == 200      # pages work
    assert worker.started is False


def test_the_ui_forwards_api_calls_with_the_service_token(tmp_path, monkeypatch):
    engine = _stub_engine()
    app = create_app(db_path=str(tmp_path / "state.db"), token=TOKEN, role="ui",
                     worker=RecordingWorker(), engine_base="http://engine",
                     engine_token=ENGINE_TOKEN,
                     proxy_transport=httpx.ASGITransport(app=engine))
    with TestClient(app) as client:
        reply = client.get("/api/ping", headers=AUTH)

    assert reply.status_code == 200
    assert reply.json() == {"pong": True}


def test_the_ui_passes_sse_through(tmp_path):
    engine = _stub_engine()
    app = create_app(db_path=str(tmp_path / "state.db"), token=TOKEN, role="ui",
                     worker=RecordingWorker(), engine_base="http://engine",
                     engine_token=ENGINE_TOKEN,
                     proxy_transport=httpx.ASGITransport(app=engine))
    with TestClient(app) as client, \
            client.stream("GET", "/api/events", headers=AUTH) as reply:
        body = "".join(reply.iter_text())

    assert reply.status_code == 200
    assert reply.headers["content-type"].startswith("text/event-stream")
    assert "run.started" in body and "run.finished" in body


def test_the_ui_requires_a_user_token_before_proxying(tmp_path):
    engine = _stub_engine()
    app = create_app(db_path=str(tmp_path / "state.db"), token=TOKEN, role="ui",
                     worker=RecordingWorker(), engine_base="http://engine",
                     engine_token=ENGINE_TOKEN,
                     proxy_transport=httpx.ASGITransport(app=engine))
    with TestClient(app) as client:
        assert client.get("/api/ping").status_code == 401


def test_a_proxied_json_body_arrives_whole(tmp_path):
    """The client is closed in the background task, not on return: a body read
    after the handler returns used to arrive empty."""
    engine = _stub_engine()
    app = create_app(db_path=str(tmp_path / "state.db"), token=TOKEN, role="ui",
                     worker=RecordingWorker(), engine_base="http://engine",
                     engine_token=ENGINE_TOKEN,
                     proxy_transport=httpx.ASGITransport(app=engine))
    with TestClient(app) as client:
        reply = client.get("/api/events", headers=AUTH)

    assert "run.started" in reply.text
