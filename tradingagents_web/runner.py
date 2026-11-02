"""Turn one queued job into a run: the only place that calls the graph.

The sequence matters and is documented in ``docs/B4_INTERACTION_SPEC.md`` §5:
stream, merge the cumulative state, write the report, then record the decision,
then clear the checkpoint. Writing the report first means a disk failure cannot
leave a memory entry for a run whose report never existed.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from langchain_core.callbacks import BaseCallbackHandler

from tradingagents.agents.rating import is_review, run_rating
from tradingagents.dataflows.symbols import safe_ticker_component
from tradingagents.portfolio import PortfolioContext
from tradingagents_cn.graph import factory as graph_factory

from . import errors, jobs
from .errors import ReportWriteError

logger = logging.getLogger(__name__)

#: Upstream's node vocabulary (graph/setup.py). Anything else (model, tools,
#: subgraph internals) is mapped to its parent or ignored.
NODE_NAMES = (
    "Market Analyst", "Sentiment Analyst", "News Analyst", "Fundamentals Analyst",
    "Memory Log", "Bull Researcher", "Bear Researcher", "Research Manager", "Trader",
    "Aggressive Analyst", "Conservative Analyst", "Neutral Analyst", "Portfolio Manager",
)
_REPORT_KEYS = (
    "market_report", "sentiment_report", "news_report", "fundamentals_report",
    "investment_plan", "trader_investment_plan", "final_trade_decision",
)


def _normalise(text) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(text).lower()).strip("_")


class Progress(BaseCallbackHandler):
    """Maps LangGraph node callbacks to web events; ignores model/tool nodes."""

    def __init__(self, emit):
        self._emit = emit
        self._open: set[str] = set()

    def _node(self, metadata) -> str | None:
        metadata = metadata or {}
        name = metadata.get("langgraph_node")
        if name in NODE_NAMES:
            return name
        # Inside an analyst's subgraph the node is "agent"/"tools"; the parent is
        # only visible in the checkpoint namespace, whose punctuation varies
        # ("News Analyst:abc", "news_analyst:abc").
        namespace = _normalise(metadata.get("langgraph_checkpoint_ns", ""))
        for node in NODE_NAMES:
            if namespace.startswith(_normalise(node)):
                return node
        return None

    def on_chain_start(self, serialized, inputs, *, metadata=None, **kwargs):
        node = self._node(metadata)
        if node and node not in self._open:
            self._open.add(node)
            self._emit("node.started", {"node": node})

    def on_chain_end(self, outputs, *, metadata=None, **kwargs):
        node = self._node(metadata)
        if node and node in self._open:
            self._open.discard(node)
            self._emit("node.finished", {"node": node})


def _job_overrides(job: dict) -> dict:
    overrides = {"output_language": job["language"]}
    if job.get("strict"):
        overrides["cn_strict_ashare"] = True
    return overrides


def execute(conn, run_id: str, *, build_graph=None) -> None:
    """Run one job; every outcome is recorded, never raised to the worker."""
    build_graph = build_graph or graph_factory.build_graph
    job = jobs.get(conn, run_id)
    if job is None:
        return

    def emit(kind: str, payload: dict) -> None:
        jobs.append_event(conn, run_id, kind, payload)

    jobs.mark_running(conn, run_id)
    try:
        graph = build_graph(
            _job_overrides(job),
            symbol=job["symbol"],
            market=job["market"],
            selected_analysts=tuple(json.loads(job["analysts"])),
        )
        profile = graph.config.get("cn_market_profile", job["profile"])
        emit("run.started", {"symbol": job["symbol"], "date": job["trade_date"],
                             "profile": profile})

        portfolio = (
            PortfolioContext.model_validate_json(job["portfolio_json"])
            if job.get("portfolio_json") else None
        )
        run_dir = _run_dir(graph, job, run_id)
        report_dir = run_dir / "report"
        run_dir.mkdir(parents=True, exist_ok=True)
        # Recorded before the run so a failure can still write web.log here.
        conn.execute("UPDATE runs SET run_dir=? WHERE id=?", (str(run_dir), run_id))
        conn.commit()

        progress = Progress(emit)
        seen: set[str] = set()
        final: dict = {}

        state = graph.create_run_state(job["symbol"], job["trade_date"],
                                       asset_type="stock", portfolio=portfolio)
        args = graph.propagator.get_graph_args(callbacks=[progress])
        checkpoint = None
        if graph.config.get("checkpoint_enabled"):
            checkpoint = graph.begin_checkpoint(job["symbol"], job["trade_date"], "stock", portfolio)
            if checkpoint:
                args.setdefault("config", {}).setdefault("configurable", {})["thread_id"] = checkpoint
                state = graph.checkpoint_input(state)

        try:
            for _messages, chunk in graph.stream_run(state, **args):
                if not isinstance(chunk, dict):
                    continue
                final.update(chunk)
                for key in _REPORT_KEYS:
                    if key not in seen and final.get(key):
                        seen.add(key)
                        emit("report.ready", {"key": key})
        finally:
            if checkpoint:
                graph.end_checkpoint()

        try:
            path = graph.save_reports(final, job["symbol"], save_path=report_dir)
        except OSError as exc:
            raise ReportWriteError(str(exc)) from exc

        _write_job_json(run_dir, job, profile, graph)
        graph.record_decision(job["symbol"], job["trade_date"], final)
        if checkpoint:
            graph.clear_checkpoint_on_success(job["symbol"], job["trade_date"], "stock", portfolio)

        rating = run_rating(final)
        jobs.finish(conn, run_id, rating=rating, run_dir=str(run_dir), report_path=str(path))
        emit("run.finished", {"rating": rating, "review": bool(is_review(rating)),
                              "report_url": f"/runs/{run_id}/report", "final": True})
    except Exception as exc:  # noqa: BLE001 - the job boundary reports, never raises
        info = errors.classify(exc)
        logger.exception("run %s failed (%s)", run_id, info.category)
        _log_failure(conn, run_id, exc)
        jobs.fail(conn, run_id, category=info.category, message=info.message)
        emit("run.failed", {"category": info.category, "message": info.message,
                            "action": info.action, "final": True})


def _run_dir(graph, job: dict, run_id: str) -> Path:
    root = Path(graph.config["results_dir"])
    return (root / safe_ticker_component(job["symbol"]) / job["trade_date"]
            / "runs" / run_id)


def _write_job_json(run_dir: Path, job: dict, profile: str, graph) -> None:
    from tradingagents_cn.runmeta import collect

    payload = {
        "run_id": job["id"],
        "symbol": job["symbol"],
        "market": job["market"],
        "profile": profile,
        "trade_date": job["trade_date"],
        "analysts": json.loads(job["analysts"]),
        "language": job["language"],
        "strict": bool(job["strict"]),
        # The chart service anchors 前复权 to the last row of the window it is
        # given; recording this is what keeps a report comparable later.
        "data_as_of": job["trade_date"],
        "qfq_anchor": job["trade_date"],
        "metadata": collect(graph.config, job["trade_date"], job["symbol"]),
    }
    (run_dir / "job.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _log_failure(conn, run_id: str, exc: BaseException) -> None:
    """Stack traces go to the run directory, not into the event stream."""
    job = jobs.get(conn, run_id)
    if not job or not job.get("run_dir"):
        return
    try:
        import traceback

        path = Path(job["run_dir"]) / "web.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write("".join(traceback.format_exception(exc)))
    except OSError:
        logger.warning("could not write web.log for %s", run_id)
