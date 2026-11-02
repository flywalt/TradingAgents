"""CLS (财联社) telegraph via RSSHub: a market-wide event stream.

Unlike Xueqiu's per-stock routes, CLS is one firehose for the whole market. The
`announcement` category is company-level, and most items carry the issuer's code
in the text (``(688613.SH)``), so per-company use means regex extraction rather
than a different endpoint.

Coverage is not total: in a live sample 13 of 15 announcement items carried a
code (比亚迪 and 赛力斯 did not). Extraction is therefore best-effort, and the
per-stock Xueqiu routes remain the precise source for a single name.
"""

from __future__ import annotations

import re
from datetime import date

from tradingagents.dataflows.errors import NoMarketDataError
from tradingagents_cn.cache import cached
from tradingagents_cn.vendors import rsshub
from tradingagents_cn.vendors.common import no_rows, require_ashare

BASE_ENV = rsshub.BASE_ENV
TOKEN_ENV = rsshub.TOKEN_ENV

#: The seven source-verified categories plus the unclassified firehose.
CATEGORIES: dict[str, str] = {
    "all": "/cls/telegraph",
    "watch": "/cls/telegraph/watch",
    "announcement": "/cls/telegraph/announcement",
    "red": "/cls/telegraph/red",
    "remind": "/cls/telegraph/remind",
    "fund": "/cls/telegraph/fund",
    "hk": "/cls/telegraph/hk",
    "hk_us": "/cls/telegraph/hk_us",
}

_TTL_SECONDS = 300
_CODE_RE = re.compile(r"(\d{6}\.(?:SH|SZ|BJ))")

#: Patchable seam for tests.
_fetch = rsshub.fetch
parse_items = rsshub.parse_items


def extract_codes(text: str) -> list[str]:
    """Exchange codes mentioned in an item, in first-seen order, deduplicated."""
    seen: list[str] = []
    for match in _CODE_RE.findall(text or ""):
        code = match.upper()
        if code not in seen:
            seen.append(code)
    return seen


def _dates(start_date: str | None, end_date: str | None) -> tuple[date | None, date | None]:
    start = date.fromisoformat(start_date) if start_date else None
    end = date.fromisoformat(end_date) if end_date else None
    if start and end and start > end:
        raise ValueError(f"start_date {start} is after end_date {end}")
    return start, end


def fetch_telegraph(
    category: str = "all", start_date: str | None = None, end_date: str | None = None
) -> list[dict]:
    """Items from one CLS category, window-filtered, each with its extracted codes."""
    key = str(category).strip().lower()
    if key not in CATEGORIES:
        raise ValueError(f"unknown CLS category {category!r}; known: {', '.join(CATEGORIES)}")
    start, end = _dates(start_date, end_date)
    xml_text = cached(
        "cls", f"{key}|{start}|{end}", _TTL_SECONDS,
        lambda: _fetch(CATEGORIES[key]),
    )
    items = parse_items(xml_text, start, end)
    for item in items:
        item["codes"] = extract_codes(f"{item['title']} {item['text']}")
    return items


def fetch_company_events(symbol: str, start_date: str, end_date: str) -> list[dict]:
    """Announcement-stream items that mention ``symbol``'s code."""
    canonical = require_ashare(symbol)
    return [
        item for item in fetch_telegraph("announcement", start_date, end_date)
        if canonical in item["codes"]
    ]


def _render(subject: str, items: list[dict], window: str) -> str:
    lines = [f"## {subject} ({window})", ""]
    for item in items:
        title = item["title"] or item["text"][:60]
        codes = ",".join(item.get("codes", []))
        lines.append(f"### {title}" + (f" [{codes}]" if codes else ""))
        if item["text"]:
            lines.append(item["text"])
        if item["link"]:
            lines.append(f"Link: {item['link']}")
        if item["published"]:
            lines.append(f"Published: {item['published'].isoformat()}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def get_company_events(symbol: str, start_date: str, end_date: str) -> str:
    """Company-level CLS events for one symbol (not routed yet)."""
    canonical = require_ashare(symbol)
    items = fetch_company_events(canonical, start_date, end_date)
    if not items:
        raise no_rows(symbol, canonical,
                      f"CLS mentioned {canonical} in no announcement between "
                      f"{start_date} and {end_date}")
    return _render(canonical, items, f"{start_date}..{end_date}")


def get_market_radar(start_date: str, end_date: str) -> str:
    """The unclassified firehose (macro, tape, geopolitics) for context."""
    items = fetch_telegraph("all", start_date, end_date)
    if not items:
        raise NoMarketDataError("CLS radar", "CLS radar",
                                f"no telegraph items between {start_date} and {end_date}")
    return _render("CLS 电报", items, f"{start_date}..{end_date}")


__all__ = [
    "BASE_ENV", "CATEGORIES", "TOKEN_ENV", "extract_codes", "fetch_company_events",
    "fetch_telegraph", "get_company_events", "get_market_radar",
]
