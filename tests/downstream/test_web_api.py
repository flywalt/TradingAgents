"""HTTP surface: auth, validation, queue, pages, artifact jail."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tradingagents_web import db, jobs
from tradingagents_web.app import create_app

pytestmark = pytest.mark.unit

TOKEN = "test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


class RecordingWorker:
    def __init__(self):
        self.submitted: list[str] = []

    def submit(self, run_id: str) -> None:
        self.submitted.append(run_id)

    def start(self):
        return []


@pytest.fixture
def client(tmp_path, monkeypatch):
    app = create_app(db_path=str(tmp_path / "state.db"), token=TOKEN,
                     worker=RecordingWorker())
    # Identity lookups are network calls; the API contract does not depend on them.
    import tradingagents_web.app as web_app

    monkeypatch.setattr(web_app, "resolve_identity", lambda symbol: {"name": "贵州茅台"})
    monkeypatch.setattr(web_app, "resolve_instrument_identity", lambda symbol: {"name": "Apple"})
    with TestClient(app) as test_client:
        test_client.worker = app.state.worker
        yield test_client


def test_every_api_route_requires_a_token(client):
    assert client.get("/api/runs").status_code == 401
    assert client.post("/api/runs", json={}).status_code == 401
    assert client.get("/history").status_code == 401


def test_a_run_is_queued_and_the_worker_is_notified(client):
    response = client.post("/api/runs", headers=AUTH, json={
        "symbol": "600519.SH", "date": "2026-10-30", "analysts": ["market"],
        "language": "中文",
    })

    assert response.status_code == 202
    body = response.json()
    assert body["position"] >= 1
    assert client.worker.submitted == [body["id"]]


def test_an_ambiguous_symbol_is_rejected_with_a_category(client):
    response = client.post("/api/runs", headers=AUTH, json={
        "symbol": "0700", "date": "2026-10-30", "analysts": ["market"]})

    assert response.status_code == 400
    assert response.json()["error"]["category"] == "symbol_ambiguous"


def test_strict_mode_is_refused_for_a_foreign_symbol(client):
    response = client.post("/api/runs", headers=AUTH, json={
        "symbol": "AAPL", "date": "2026-10-30", "analysts": ["market"], "strict": True})

    assert response.status_code == 400
    assert response.json()["error"]["category"] == "strict_not_allowed"


def test_the_queue_cap_is_enforced(client, tmp_path):
    conn = db.connect(tmp_path / "state.db")
    try:
        for _ in range(3):
            jobs.create(conn, symbol="600519.SH", market="CN", profile="CN_A_SHARE",
                        trade_date="2026-10-30", analysts=["market"], language="English",
                        strict=False, portfolio_json=None)
    finally:
        conn.close()

    response = client.post("/api/runs", headers=AUTH, json={
        "symbol": "600519.SH", "date": "2026-10-30", "analysts": ["market"]})

    assert response.status_code == 409
    assert response.json()["error"]["category"] == "queue_full"


def test_preview_names_the_profile_and_the_company(client):
    response = client.get("/api/preview", headers=AUTH, params={"symbol": "600519.SH"})

    assert response.status_code == 200
    assert response.json() == {"symbol": "600519.SH", "market": "CN",
                               "profile": "CN_A_SHARE", "name": "贵州茅台"}


def test_the_run_page_states_the_disclaimer_and_the_link(client, tmp_path):
    conn = db.connect(tmp_path / "state.db")
    try:
        run_id = jobs.create(conn, symbol="600519.SH", market="CN", profile="CN_A_SHARE",
                             trade_date="2026-10-30", analysts=["market"], language="中文",
                             strict=False, portfolio_json=None)
    finally:
        conn.close()

    page = client.get(f"/runs/{run_id}", headers=AUTH)

    assert page.status_code == 200
    assert "模型生成的分析记录" in page.text
    assert "600519.SH" in page.text


def test_artifacts_are_jailed_and_missing_reports_are_404(client, tmp_path):
    conn = db.connect(tmp_path / "state.db")
    try:
        run_id = jobs.create(conn, symbol="600519.SH", market="CN", profile="CN_A_SHARE",
                             trade_date="2026-10-30", analysts=["market"], language="English",
                             strict=False, portfolio_json=None)
    finally:
        conn.close()

    assert client.get(f"/runs/{run_id}/report", headers=AUTH).status_code == 404
    assert client.get(f"/runs/{run_id}/files/..%2Fsecret.md", headers=AUTH).status_code == 404


def test_the_login_route_sets_the_cookie(client):
    response = client.get("/login", params={"token": TOKEN}, follow_redirects=False)

    assert response.status_code == 303
    assert response.cookies.get("tg_web_token") == TOKEN

    bad = client.get("/login", params={"token": "nope"}, follow_redirects=False)
    assert bad.status_code == 401


def test_the_shell_refuses_to_start_without_a_token(tmp_path, monkeypatch):
    monkeypatch.delenv("TRADINGAGENTS_WEB_TOKEN", raising=False)

    with pytest.raises(RuntimeError, match="TRADINGAGENTS_WEB_TOKEN"):
        create_app(db_path=str(tmp_path / "state.db"), worker=RecordingWorker())


def test_sse_replays_from_last_event_id(client, tmp_path):
    conn = db.connect(tmp_path / "state.db")
    try:
        run_id = jobs.create(conn, symbol="600519.SH", market="CN", profile="CN_A_SHARE",
                            trade_date="2026-10-30", analysts=["market"], language="English",
                            strict=False, portfolio_json=None)
        jobs.append_event(conn, run_id, "run.started", {"symbol": "600519.SH"})
        jobs.append_event(conn, run_id, "run.failed", {"category": "internal", "final": True})
        jobs.fail(conn, run_id, category="internal", message="x")
    finally:
        conn.close()

    with client.stream("GET", f"/api/runs/{run_id}/events", headers={**AUTH, "Last-Event-ID": "1"}) as response:
        body = "".join(response.iter_text())

    assert "id: 2" in body
    assert "run.failed" in body
    assert "id: 1" not in body        # replay starts after the acknowledged event


def test_the_form_defaults_to_today_and_chinese(client):
    from datetime import date

    page = client.get("/", headers=AUTH)

    assert page.status_code == 200
    assert f'value="{date.today().isoformat()}"' in page.text
    assert 'value="中文" selected' in page.text
    assert "强制只走 Tushare" in page.text      # strict mode explained, not a mystery


def test_each_page_has_exactly_one_script_block(client, tmp_path):
    """Nested <script> tags made the page fall back to a native form post."""
    assert client.get("/", headers=AUTH).text.count("<script") == 1

    conn = db.connect(tmp_path / "state.db")
    try:
        run_id = jobs.create(conn, symbol="600519.SH", market="CN", profile="CN_A_SHARE",
                             trade_date="2026-10-30", analysts=["market"], language="中文",
                             strict=False, portfolio_json=None)
    finally:
        conn.close()

    assert client.get(f"/runs/{run_id}", headers=AUTH).text.count("<script") == 1


def test_the_report_route_serves_the_html_sibling_not_the_markdown(client, tmp_path):
    """The kernel returns complete_report.md and writes the .html beside it."""
    report_dir = tmp_path / "report"
    report_dir.mkdir()
    (report_dir / "complete_report.md").write_text("# plain markdown", encoding="utf-8")
    (report_dir / "complete_report.html").write_text(
        "<!doctype html><html><body><h1>600519.SH</h1></body></html>", encoding="utf-8")

    conn = db.connect(tmp_path / "state.db")
    try:
        run_id = jobs.create(conn, symbol="600519.SH", market="CN", profile="CN_A_SHARE",
                             trade_date="2026-10-30", analysts=["market"], language="中文",
                             strict=False, portfolio_json=None)
        jobs.finish(conn, run_id, rating="Hold", run_dir=str(tmp_path),
                    report_path=str(report_dir / "complete_report.md"))
    finally:
        conn.close()

    response = client.get(f"/runs/{run_id}/report", headers=AUTH)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<!doctype html>" in response.text
    assert "plain markdown" not in response.text


def test_a_markdown_only_report_is_served_as_plain_text(client, tmp_path):
    report_dir = tmp_path / "report"
    report_dir.mkdir()
    (report_dir / "complete_report.md").write_text("# plain markdown", encoding="utf-8")

    conn = db.connect(tmp_path / "state.db")
    try:
        run_id = jobs.create(conn, symbol="600519.SH", market="CN", profile="CN_A_SHARE",
                             trade_date="2026-10-30", analysts=["market"], language="中文",
                             strict=False, portfolio_json=None)
        jobs.finish(conn, run_id, rating="Hold", run_dir=str(tmp_path),
                    report_path=str(report_dir / "complete_report.md"))
    finally:
        conn.close()

    response = client.get(f"/runs/{run_id}/report", headers=AUTH)

    assert response.headers["content-type"].startswith("text/plain")
    assert response.text == "# plain markdown"


def test_the_report_page_follows_the_run_language(client, tmp_path):
    report_dir = tmp_path / "report"
    report_dir.mkdir()
    (report_dir / "complete_report.html").write_text(
        '<!doctype html><html lang="en"><body><p class="date">Analysis of 2026-11-02</p>'
        '<a class="to-top" href="#top">Top</a></body></html>', encoding="utf-8")

    conn = db.connect(tmp_path / "state.db")
    try:
        run_id = jobs.create(conn, symbol="600519.SH", market="CN", profile="CN_A_SHARE",
                             trade_date="2026-10-30", analysts=["market"], language="中文",
                             strict=False, portfolio_json=None)
        jobs.finish(conn, run_id, rating="Hold", run_dir=str(tmp_path),
                    report_path=str(report_dir / "complete_report.md"))
    finally:
        conn.close()

    response = client.get(f"/runs/{run_id}/report", headers=AUTH)

    assert response.status_code == 200
    assert '<html lang="zh-CN">' in response.text
    assert "回到顶部" in response.text
    assert response.headers["content-type"].startswith("text/html")


def test_an_english_report_is_served_as_written(client, tmp_path):
    report_dir = tmp_path / "report"
    report_dir.mkdir()
    (report_dir / "complete_report.html").write_text(
        '<!doctype html><html lang="en"><body><a class="to-top" href="#top">Top</a>'
        '</body></html>', encoding="utf-8")

    conn = db.connect(tmp_path / "state.db")
    try:
        run_id = jobs.create(conn, symbol="AAPL", market="US", profile="UPSTREAM_DEFAULT",
                             trade_date="2026-10-30", analysts=["market"], language="English",
                             strict=False, portfolio_json=None)
        jobs.finish(conn, run_id, rating="Hold", run_dir=str(tmp_path),
                    report_path=str(report_dir / "complete_report.md"))
    finally:
        conn.close()

    response = client.get(f"/runs/{run_id}/report", headers=AUTH)

    assert '<html lang="en">' in response.text
    assert response.text.count("回到顶部") == 0


def test_the_run_page_draws_the_graph_for_the_selected_analysts(client, tmp_path):
    conn = db.connect(tmp_path / "state.db")
    try:
        run_id = jobs.create(conn, symbol="600519.SH", market="CN", profile="CN_A_SHARE",
                             trade_date="2026-10-30", analysts=["market"], language="中文",
                             strict=False, portfolio_json=None)
    finally:
        conn.close()

    page = client.get(f"/runs/{run_id}", headers=AUTH)

    assert page.status_code == 200
    assert "panel panel--graph" in page.text
    assert 'role="img"' in page.text
    assert "多头研究员" in page.text            # a label that reaches the page from Python
    assert "情绪分析师" not in page.text         # that analyst was not selected
    assert page.text.count("<script") == 1
    assert "/static/run-page.js" in page.text


def test_a_run_stores_and_shows_the_company_name(client, monkeypatch, tmp_path):
    import tradingagents_web.app as web_app

    monkeypatch.setattr(web_app, "resolve_identity",
                        lambda symbol: {"name": "贵州茅台"})
    response = client.post("/api/runs", headers=AUTH, json={
        "symbol": "600519.SH", "date": "2026-10-30", "analysts": ["market"],
        "language": "中文",
    })

    body = response.json()
    assert response.status_code == 202
    page = client.get(f"/runs/{body['id']}", headers=AUTH)
    assert "贵州茅台 · 600519.SH" in page.text


def test_the_report_leads_with_the_company_name(client, tmp_path):
    report_dir = tmp_path / "report"
    report_dir.mkdir()
    (report_dir / "complete_report.html").write_text(
        '<!doctype html><html lang="en"><body><h1><span class="ticker">600519.SH'
        '</span></h1><a class="to-top" href="#top">Top</a></body></html>', encoding="utf-8")

    conn = db.connect(tmp_path / "state.db")
    try:
        run_id = jobs.create(conn, symbol="600519.SH", market="CN", profile="CN_A_SHARE",
                             trade_date="2026-10-30", analysts=["market"], language="中文",
                             strict=False, portfolio_json=None, display_name="贵州茅台")
        jobs.finish(conn, run_id, rating="Hold", run_dir=str(tmp_path),
                    report_path=str(report_dir / "complete_report.md"))
    finally:
        conn.close()

    page = client.get(f"/runs/{run_id}/report", headers=AUTH)

    assert "贵州茅台 · 600519.SH" in page.text


def test_the_form_search_endpoint_answers_suggestions(client, monkeypatch):
    import tradingagents_web.app as web_app

    monkeypatch.setattr(web_app.search, "suggest",
                        lambda q: [{"symbol": "600519.SH", "name": "贵州茅台"}])
    response = client.get("/api/search", params={"q": "茅台"}, headers=AUTH)

    assert response.status_code == 200
    assert response.json() == {"results": [{"symbol": "600519.SH",
                                            "name": "贵州茅台"}]}


def test_the_form_search_requires_a_token(client):
    assert client.get("/api/search", params={"q": "x"}).status_code == 401


def test_a_browser_gets_a_login_page_not_raw_json(client):
    page = client.get("/", headers={"Accept": "text/html"})

    assert page.status_code == 401
    assert page.headers["content-type"].startswith("text/html")
    assert 'action="/login"' in page.text      # a form a person can use


def test_an_api_client_still_gets_json(client):
    denied = client.get("/api/runs")

    assert denied.status_code == 401
    assert denied.headers["content-type"].startswith("application/json")


def test_the_login_cookie_survives_a_browser_restart(client):
    response = client.get("/login", params={"token": TOKEN}, follow_redirects=False)

    cookie = response.headers.get("set-cookie", "")
    assert "Max-Age=2592000" in cookie          # thirty days, not a session
