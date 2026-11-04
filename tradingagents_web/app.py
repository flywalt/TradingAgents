"""FastAPI app: a thin shell over the analysis kernel.

No analysis logic lives here. The app validates input, queues a job, streams its
progress from SQLite, and serves the artifacts the kernel wrote.
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import date
from pathlib import Path

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from tradingagents.agents.context import resolve_instrument_identity
from tradingagents.dataflows.symbols import safe_ticker_component
from tradingagents.portfolio import PortfolioContext
from tradingagents_cn import config as cn_config
from tradingagents_cn.identity import resolve_identity
from tradingagents_cn.market import CN_A_SHARE, select_profile
from tradingagents_cn.symbols import try_normalize

from . import db, jobs, labels, progress_graph, report_page, search, security
from .errors import QueueFullError, classify
from .worker import Worker

ANALYSTS = ("market", "social", "news", "fundamentals")
LANGUAGES = ("English", "中文")
MAX_QUEUED = 3

#: Display mapping: the report already carries a rating; the UI never renders
#: it as an order instruction (see spec §9).
RATING_LABELS = labels.RATING_LABELS


def served_report(path: Path) -> tuple[Path, str]:
    """Pick the file to hand the browser, and the type to declare for it.

    ``write_report_tree`` returns the complete *markdown* path — that is the
    canonical artifact — while writing a self-contained HTML page beside it.
    Serving the markdown as ``text/html`` renders it as one unformatted block,
    so prefer the HTML sibling and fall back to plain text, never claiming HTML
    for a file that is not.
    """
    if path.suffix != ".html":
        sibling = path.with_suffix(".html")
        if sibling.is_file():
            return sibling, "text/html"
        return path, "text/plain; charset=utf-8"
    return path, "text/html"


class RunRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=20)
    date: str
    analysts: list[str] = Field(default_factory=lambda: list(ANALYSTS))
    language: str = "English"
    strict: bool = False
    market: str | None = None
    portfolio: dict | None = None


def create_app(
    *,
    db_path: str | None = None,
    worker: Worker | None = None,
    execute=None,
    token: str | None = None,
    read_token: str | None = None,
    dev_no_token: bool = False,
    kviewer_base: str | None = None,
    role: str = "combined",
    engine_base: str | None = None,
    engine_token: str | None = None,
    proxy_transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    path = Path(db_path or os.environ.get("TRADINGAGENTS_WEB_DB")
                or Path.home() / ".tradingagents" / "web" / "state.db")
    conn = db.connect(path)
    conn.close()

    if role not in ("combined", "ui", "engine"):
        raise ValueError(f"unknown role: {role!r}")
    token = token if token is not None else security.configured_token()
    read_token = read_token if read_token is not None else security.configured_read_token()
    engine_token = (engine_token if engine_token is not None
                    else os.environ.get("TRADINGAGENTS_ENGINE_TOKEN"))
    if role == "engine" and engine_token:
        # the engine answers to the service token the UI holds
        token = engine_token
    token_value, read_value = token, read_token
    if not token and not dev_no_token:
        raise RuntimeError(
            f"{security.TOKEN_ENV} is not set; the web shell refuses to start. "
            "Set it, or pass dev_no_token=True on 127.0.0.1 only."
        )

    app = FastAPI(title="TradingAgents Web", docs_url=None, redoc_url=None)
    here = Path(__file__).parent
    templates = Jinja2Templates(directory=str(here / "templates"))
    templates.env.filters["rating_label"] = lambda value: RATING_LABELS.get(value, value or "")
    # Keep Chinese readable in the markup: the graph travels to the page as JSON.
    templates.env.policies["json.dumps_kwargs"] = {"sort_keys": True, "ensure_ascii": False}
    app.mount("/static", StaticFiles(directory=str(here / "static")), name="static")

    background = worker or Worker(path, execute=execute)
    app.state.worker = background
    app.state.db_path = path
    app.state.kviewer_base = (kviewer_base if kviewer_base is not None
                              else security.kviewer_base())

    app.state.role = role
    if role != "ui" and not getattr(app.state, "_started", False):
        app.state.started = background.start()
    else:
        app.state.started = []

    origins = security.cors_origins()
    if origins:
        from fastapi.middleware.cors import CORSMiddleware

        app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET"],
                           allow_headers=["Authorization", "X-Token"])

    # ---------------------------------------------------------------- auth
    def _provided_token(request: Request) -> str | None:
        header = request.headers.get("Authorization", "")
        if header.lower().startswith("bearer "):
            return header[7:].strip()
        return request.headers.get("X-Token") or request.cookies.get("tg_web_token")

    def require_write(request: Request) -> None:
        if dev_no_token:
            return
        if not security.token_matches(_provided_token(request), token):
            raise HTTPException(status_code=401, detail="token required")

    def require_read(request: Request) -> None:
        if dev_no_token:
            return
        provided = _provided_token(request)
        if security.token_matches(provided, token) or security.token_matches(provided, read_token):
            return
        raise HTTPException(status_code=401, detail="token required")

    def _conn():
        connection = db.connect(path)
        try:
            yield connection
        finally:
            connection.close()

    def _error(exc: Exception) -> JSONResponse:
        info = classify(exc)
        return JSONResponse(
            {"error": {"category": info.category, "message": info.message,
                       "action": info.action}},
            status_code=info.http_status,
        )

    # ------------------------------------------------------------- split role
    # A UI process owns the pages and forwards /api to the engine: one origin for
    # the browser, the service token never leaves the server. An engine process
    # owns the API only and refuses to render pages at all.
    if role == "ui":
        engine_url = (engine_base or os.environ.get("TRADINGAGENTS_ENGINE_URL")
                      or "http://127.0.0.1:8502").rstrip("/")
        service_token = engine_token or token_value or ""

        def _forward_headers(request: Request) -> dict:
            keep = {"accept", "content-type", "last-event-id"}
            headers = {k: v for k, v in request.headers.items() if k.lower() in keep}
            headers["authorization"] = f"Bearer {service_token}"
            return headers

        @app.get("/api/engine/health", dependencies=[Depends(require_read)])
        async def engine_health():
            try:
                async with httpx.AsyncClient(transport=proxy_transport,
                                             timeout=3) as client:
                    reply = await client.get(f"{engine_url}/healthz")
                return {"online": reply.status_code == 200}
            except httpx.HTTPError:
                return {"online": False}

        @app.api_route("/api/{path:path}",
                       methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
                       dependencies=[Depends(require_read)])
        async def proxy_api(path: str, request: Request):
            body = await request.body()
            # The client must outlive this handler: the body is streamed after
            # the response object is returned, so both are closed in the
            # background task rather than on return.
            client = httpx.AsyncClient(transport=proxy_transport, timeout=None)
            try:
                upstream = await client.send(
                    client.build_request(request.method, f"{engine_url}/api/{path}",
                                         headers=_forward_headers(request),
                                         params=request.query_params, content=body),
                    stream=True,
                )
            except httpx.HTTPError:
                await client.aclose()
                return JSONResponse({"detail": "engine unreachable"}, status_code=502)

            async def close_both():
                await upstream.aclose()
                await client.aclose()

            passing = {"content-type", "cache-control", "x-accel-buffering"}
            return StreamingResponse(
                upstream.aiter_raw(), status_code=upstream.status_code,
                headers={k: v for k, v in upstream.headers.items()
                         if k.lower() in passing},
                background=BackgroundTask(close_both),
            )

    if role == "engine":
        @app.middleware("http")
        async def api_only(request: Request, call_next):
            path = request.url.path
            if path.startswith("/api/") or path in ("/healthz", "/login"):
                return await call_next(request)
            return JSONResponse({"detail": "this process serves the API only"},
                                status_code=404)

    # ------------------------------------------------------------ validation
    def _validated(payload: RunRequest) -> dict:
        symbol = payload.symbol.strip().upper()
        if not symbol or any(ch in symbol for ch in "/\\") or ".." in symbol:
            raise ValueError(f"{symbol!r} is not a valid symbol")
        canonical = try_normalize(symbol) or symbol
        profile = select_profile(symbol=canonical, market=payload.market)
        if payload.strict and profile.key != CN_A_SHARE.key:
            raise ValueError("cn_strict_ashare is an A-share vendor policy; "
                             f"profile {profile.key} forbids it")
        try:
            trade_date = date.fromisoformat(payload.date)
        except ValueError as exc:
            raise ValueError(f"date must be YYYY-MM-DD: {payload.date!r}") from exc
        if not (date(1990, 1, 1) <= trade_date <= date.today()):
            raise ValueError("date must be between 1990-01-01 and today")
        analysts = [a.strip() for a in payload.analysts if a and a.strip()]
        if not analysts:
            raise ValueError("at least one analyst is required")
        if any(a not in ANALYSTS for a in analysts):
            raise ValueError(f"unknown analyst; choose from {', '.join(ANALYSTS)}")
        if payload.language not in LANGUAGES:
            raise ValueError(f"language must be one of {LANGUAGES}")
        portfolio_json = None
        if payload.portfolio is not None:
            model = PortfolioContext.model_validate(payload.portfolio)
            portfolio_json = model.model_dump_json()
        return {
            "symbol": canonical,
            "market": profile.market,
            "profile": profile.key,
            "trade_date": payload.date,
            "analysts": analysts,
            "language": payload.language,
            "strict": bool(payload.strict),
            "portfolio_json": portfolio_json,
        }

    # A browser that opens a page without a cookie gets a small form to type
    # the token into; API clients keep receiving JSON.
    @app.exception_handler(HTTPException)
    async def http_exception(request: Request, exc: HTTPException):
        if exc.status_code != 401 or "text/html" not in request.headers.get("accept", ""):
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
        return HTMLResponse("""<!doctype html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>登录 · TradingAgents CN</title>
<style>
 body {{ margin: 0; display: grid; place-items: center; min-height: 100vh;
   background: #faf9f6; color: #1c1f23;
   font: 16px/1.6 system-ui, "PingFang SC", "Microsoft YaHei", sans-serif; }}
 form {{ display: grid; gap: 12px; width: min(22rem, 90vw); padding: 24px;
   background: #fff; border: 1px solid #e5e7eb; border-radius: 12px; }}
 h1 {{ margin: 0; font-size: 1.1rem; }}
 input {{ padding: 10px 12px; border: 1px solid #e5e7eb; border-radius: 8px;
   font: inherit; }}
 button {{ padding: 10px; border: 0; border-radius: 8px; background: #087a59;
   color: #fff; font: inherit; cursor: pointer; }}
 p {{ margin: 0; color: #6b7280; font-size: .85rem; }}
</style></head><body>
<form method="get" action="/login">
 <h1>TradingAgents CN</h1>
 <input name="token" type="password" placeholder="访问口令" autofocus required>
 <button type="submit">进入</button>
 <p>口令在服务器的 .env（TRADINGAGENTS_WEB_TOKEN）。</p>
</form></body></html>""", status_code=401)

    # ---------------------------------------------------------------- routes
    @app.get("/login")
    def login(request: Request, token: str = ""):
        """Set the access cookie from a token in the URL (bookmark-friendly on LAN)."""
        if not (security.token_matches(token, token_value) or security.token_matches(token, read_value)):
            raise HTTPException(status_code=401, detail="bad token")
        response = RedirectResponse("/", status_code=303)
        # thirty days: a LAN shell should survive a browser restart, not
        # greet its only user with "token required" every morning
        response.set_cookie("tg_web_token", token, httponly=True, samesite="lax",
                            max_age=30 * 24 * 3600)
        return response

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    @app.get("/api/preview", dependencies=[Depends(require_read)])
    def preview(symbol: str, market: str | None = None):
        canonical = try_normalize(symbol) or symbol.strip().upper()
        try:
            profile = select_profile(symbol=canonical, market=market)
        except ValueError as exc:
            return _error(exc)
        name = None
        try:
            if profile.key == CN_A_SHARE.key:
                name = resolve_identity(canonical).get("name")
            else:
                name = resolve_instrument_identity(canonical).get("name")
        except Exception:  # noqa: BLE001 - identity is best-effort
            name = None
        return {"symbol": canonical, "market": profile.market,
                "profile": profile.key, "name": name}

    def _display_name(fields: dict) -> str | None:
        """The company's short name, best-effort: the reader knows it first."""
        try:
            if fields["profile"] == CN_A_SHARE.key:
                return resolve_identity(fields["symbol"]).get("name")
            return resolve_instrument_identity(fields["symbol"]).get("name")
        except Exception:  # noqa: BLE001 - identity is best-effort
            return None

    @app.post("/api/runs", status_code=202, dependencies=[Depends(require_write)])
    def create_run(payload: RunRequest, session=Depends(_conn)):  # noqa: B008
        try:
            fields = _validated(payload)
        except Exception as exc:  # noqa: BLE001 - mapped below
            return _error(exc)
        if jobs.queued_count(session) >= MAX_QUEUED:
            return _error(QueueFullError("queue full"))
        run_id = jobs.create(
            session, symbol=fields["symbol"], market=fields["market"],
            profile=fields["profile"], trade_date=fields["trade_date"],
            analysts=fields["analysts"], language=fields["language"],
            strict=fields["strict"], portfolio_json=fields["portfolio_json"],
            display_name=_display_name(fields),
        )
        background.submit(run_id)
        return {"id": run_id, "position": jobs.queue_position(session, run_id)}

    @app.get("/api/search", dependencies=[Depends(require_read)])
    def search_instruments(q: str = ""):
        """Suggestions for the run form: a code or name fragment."""
        return {"results": search.suggest(q)}

    @app.get("/api/runs", dependencies=[Depends(require_read)])
    def list_runs(symbol: str | None = None, status: str | None = None,
                  rating: str | None = None, page: int = 1, size: int = 20,
                  session=Depends(_conn)):  # noqa: B008
        items, total = jobs.list_runs(session, symbol=symbol, status=status,
                                      rating=rating, page=max(1, page), size=min(100, size))
        return {"items": items, "total": total, "page": page, "size": size}

    @app.get("/api/runs/{run_id}", dependencies=[Depends(require_read)])
    def run_detail(run_id: str, session=Depends(_conn)):  # noqa: B008
        job = jobs.get(session, run_id)
        if job is None:
            raise HTTPException(status_code=404, detail="no such run")
        job["report_url"] = f"/runs/{run_id}/report" if job.get("report_path") else None
        job["rating_label"] = RATING_LABELS.get(job.get("rating") or "", job.get("rating"))
        return job

    @app.post("/api/runs/{run_id}/rerun", status_code=202,
              dependencies=[Depends(require_write)])
    def rerun(run_id: str, session=Depends(_conn)):  # noqa: B008
        job = jobs.get(session, run_id)
        if job is None:
            raise HTTPException(status_code=404, detail="no such run")
        if jobs.queued_count(session) >= MAX_QUEUED:
            return _error(QueueFullError("queue full"))
        new_id = jobs.create(
            session, symbol=job["symbol"], market=job["market"], profile=job["profile"],
            trade_date=job["trade_date"], analysts=json.loads(job["analysts"]),
            language=job["language"], strict=bool(job["strict"]),
            portfolio_json=job["portfolio_json"],
        )
        background.submit(new_id)
        return {"id": new_id}

    @app.post("/api/checkpoints/clear", dependencies=[Depends(require_write)])
    def clear_checkpoints(payload: dict, session=Depends(_conn)):  # noqa: B008
        symbol = str(payload.get("symbol", "")).strip().upper()
        if not symbol:
            return _error(ValueError("symbol is required"))
        canonical = try_normalize(symbol) or symbol
        profile = select_profile(symbol=canonical)
        settings = cn_config.apply(profile=profile)
        directory = Path(settings["data_cache_dir"]) / "checkpoints"
        target = directory / f"{safe_ticker_component(canonical).upper()}.db"
        removed = 0
        for suffix in ("", "-wal", "-shm"):
            path = Path(str(target) + suffix)
            if security.is_inside(directory, path) and path.exists():
                path.unlink()
                removed += 1
        return {"cleared": removed}

    @app.get("/api/runs/{run_id}/events", dependencies=[Depends(require_read)])
    async def events(run_id: str, request: Request, session=Depends(_conn)):  # noqa: B008
        last = int(request.headers.get("Last-Event-ID") or 0)
        worker_running = True

        async def stream():
            nonlocal last, worker_running
            idle = 0.0
            finished = False
            while worker_running:
                batch = jobs.events_after(session, run_id, last)
                for event in batch:
                    last = event["seq"]
                    finished = finished or event["kind"].startswith("run.final") or (
                        event["kind"] == "run.finished" or event["kind"] == "run.failed"
                    )
                    yield f"id: {event['seq']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                if finished:
                    return
                await asyncio.sleep(0.5)
                idle += 0.5
                if idle >= 10:
                    idle = 0.0
                    yield ": ping\n\n"
                if jobs.is_final(session, run_id) and not jobs.events_after(session, run_id, last):
                    return

        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache",
                                          "X-Accel-Buffering": "no"})

    # ----------------------------------------------------------------- pages
    def _render(request: Request, name: str, **context):
        return templates.TemplateResponse(request, name, context)

    @app.get("/", response_class=HTMLResponse, dependencies=[Depends(require_read)])
    def index(request: Request, session=Depends(_conn)):  # noqa: B008
        items, _total = jobs.list_runs(session, page=1, size=10)
        return _render(request, "index.html", runs=items, analysts=ANALYSTS,
                       languages=LANGUAGES, default_language="中文",
                       today=date.today().isoformat(), kviewer=app.state.kviewer_base)

    @app.get("/history", response_class=HTMLResponse, dependencies=[Depends(require_read)])
    def history(request: Request, symbol: str | None = None, status: str | None = None,
                rating: str | None = None, page: int = 1,
                session=Depends(_conn)):  # noqa: B008
        items, total = jobs.list_runs(session, symbol=symbol, status=status, rating=rating,
                                      page=max(1, page), size=20)
        return _render(request, "history.html", runs=items, total=total, page=page,
                       symbol=symbol or "", status=status or "", rating=rating or "")

    @app.get("/runs/{run_id}", response_class=HTMLResponse,
             dependencies=[Depends(require_read)])
    def run_page(request: Request, run_id: str, session=Depends(_conn)):  # noqa: B008
        job = jobs.get(session, run_id)
        if job is None:
            raise HTTPException(status_code=404, detail="no such run")
        return _render(request, "run.html", run=job,
                       label=RATING_LABELS.get(job.get("rating") or "", ""),
                       graph=progress_graph.topology(json.loads(job["analysts"])),
                       kviewer=app.state.kviewer_base)

    @app.get("/runs/{run_id}/report", dependencies=[Depends(require_read)])
    def report(run_id: str, session=Depends(_conn)):  # noqa: B008
        job = jobs.get(session, run_id)
        if job is None or not job.get("report_path"):
            raise HTTPException(status_code=404, detail="no report yet")
        path = Path(job["report_path"])
        served, media_type = served_report(path)
        # Check the file we are about to send, not the one recorded in the job:
        # the kernel records complete_report.md but writes the HTML beside it.
        if not served.is_file():
            raise HTTPException(status_code=404, detail="report missing on disk")
        headers = {"X-Content-Type-Options": "nosniff"}
        if media_type != "text/html":
            return FileResponse(served, media_type=media_type, headers=headers)
        headers["Content-Security-Policy"] = (
            "sandbox; default-src 'none'; style-src 'unsafe-inline'")
        # The artifact stays as the kernel wrote it; only the handed-over copy is
        # translated into the run's language.
        return Response(content=report_page.present(served.read_text(encoding="utf-8"),
                                                   job.get("language"),
                                                   job.get("display_name")),
                        media_type="text/html", headers=headers)

    @app.get("/runs/{run_id}/files/{name}", dependencies=[Depends(require_read)])
    def file(run_id: str, name: str, session=Depends(_conn)):  # noqa: B008
        job = jobs.get(session, run_id)
        if job is None or not job.get("report_path"):
            raise HTTPException(status_code=404, detail="no artifact")
        run_dir = Path(job["report_path"]).parent
        path = security.safe_run_file(run_dir, name)
        if path is None:
            raise HTTPException(status_code=404, detail="not found")
        return FileResponse(path)

    return app
