"""Deterministic A-share instrument identity.

Upstream resolves a ticker's name and sector through Yahoo, which is thin for
mainland listings. This reads the exchange's own ``stock_basic`` row instead.

Data interface only: ``TradingAgentsGraph.resolve_instrument_context`` still
calls the Yahoo path, because redirecting it is an agent-layer change. A later
task can override that method and feed it ``format_identity``.
"""

from __future__ import annotations

from tradingagents.dataflows.errors import VendorError, VendorUnavailableError
from tradingagents_cn.cache import cached
from tradingagents_cn.vendors.common import no_rows, require_ashare
from tradingagents_cn.vendors.tushare import client

_TTL_SECONDS = 24 * 60 * 60
_FIELDS = "ts_code,name,area,industry,market,list_date,delist_date,list_status"

_EXCHANGE = {"SH": "SSE", "SZ": "SZSE", "BJ": "BSE"}


def resolve_identity(symbol: str) -> dict:
    """``{ts_code, name, industry, area, market, list_date}`` for an A-share symbol."""
    canonical = require_ashare(symbol)
    try:
        frame = cached(
            "stock_basic",
            canonical,
            _TTL_SECONDS,
            lambda: client.get_api().stock_basic(ts_code=canonical, fields=_FIELDS),
        )
    except VendorError:
        raise
    except Exception as exc:  # network, throttling, quota
        raise VendorUnavailableError(f"tushare stock_basic unavailable: {exc}") from exc

    if frame is None or len(frame) == 0:
        raise no_rows(symbol, canonical, "no profile row for this symbol")

    row = frame.iloc[0].to_dict()
    return {
        "ts_code": canonical,
        "name": str(row.get("name") or "").strip() or canonical,
        "industry": str(row.get("industry") or "").strip(),
        "area": str(row.get("area") or "").strip(),
        "market": str(row.get("market") or "").strip(),
        "list_date": _iso_or_empty(row.get("list_date")),
        "delist_date": _iso_or_empty(row.get("delist_date")),
        "list_status": str(row.get("list_status") or "").strip(),
    }


def resolve_identity_at(symbol: str, as_of: str) -> dict:
    """Identity for a run dated ``as_of``, or ``{}`` when the instrument did not exist.

    Tushare serves today's profile, so the only point-in-time facts available are
    the listing and delisting dates. A run dated before listing or after
    delisting therefore gets no identity at all rather than today's name attached
    to a company that did not trade then. Names and industries are current values
    and are labelled as such by upstream's ``build_instrument_context`` when the
    run is historical.
    """
    identity = resolve_identity(symbol)
    listed = identity.get("list_date") or ""
    delisted = identity.get("delist_date") or ""
    as_of_compact = str(as_of).replace("-", "")[:8]

    if listed and as_of_compact < listed.replace("-", ""):
        return {}
    if delisted and as_of_compact > delisted.replace("-", ""):
        return {}
    identity["exchange"] = _EXCHANGE.get(symbol.split(".")[-1].upper(), "")
    identity["identity_as_of"] = _compact(as_of)
    historical = _historical_name(identity["ts_code"], _compact(as_of))
    if historical:
        identity["name"] = historical
        identity["name_source"] = "namechange"
    else:
        identity["name_source"] = "stock_basic"
    return identity


def _historical_name(symbol: str, as_of_compact: str) -> str | None:
    """The name that was both in force and public on ``as_of``.

    Tushare's ``stock_basic`` serves today's name; ``namechange`` carries the
    history. A row is usable only when it was announced by the run date *and* its
    effective window covers that date: a rename announced on 05-03 but effective
    05-01 was not yet public on 05-02.
    """
    try:
        frame = cached(
            "namechange",
            symbol,
            _TTL_SECONDS,
            lambda: client.get_api().namechange(ts_code=symbol),
        )
    except Exception:  # noqa: BLE001 - identity is best-effort, like upstream's
        return None
    if frame is None or len(frame) == 0 or "name" not in frame.columns:
        return None

    best_name, best_start = None, ""
    for row in frame.to_dict("records"):
        start = _compact(row.get("start_date"))
        end = _compact(row.get("end_date"))
        announced = _compact(row.get("ann_date"))
        if not start or (announced and announced > as_of_compact):
            continue
        if start > as_of_compact:
            continue
        if end and end < as_of_compact:
            continue
        if start >= best_start:
            best_start, best_name = start, str(row.get("name") or "").strip() or None
    return best_name


def _compact(value: str) -> str:
    return str(value).replace("-", "")[:8]


def format_identity(identity: dict) -> str:
    """A one-line context string for a prompt, skipping fields that are empty."""
    parts = [identity.get("ts_code", ""), identity.get("name", "")]
    labels = (
        ("industry", "行业"),
        ("area", "地区"),
        ("market", "板块"),
        ("list_date", "上市"),
    )
    rendered = " ".join(part for part in parts if part)
    details = [f"{label}: {identity[key]}" for key, label in labels if identity.get(key)]
    return f"{rendered} | " + " | ".join(details) if details else rendered


def _iso_or_empty(value) -> str:
    text = str(value or "").strip()
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    return text
