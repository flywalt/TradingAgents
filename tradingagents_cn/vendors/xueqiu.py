"""Xueqiu (雪球) via a self-hosted RSSHub instance.

Three routes cover what the A-share pipeline was missing:

* ``stock_info/<CODE>/news`` — per-stock news with title, source and a summary;
* ``stock_info/<CODE>/discuss`` — per-stock posts (sentiment input);
* ``stock_comments/<CODE>`` — comments on a stock (sentiment input);
* ``xueqiu/hots`` — market-wide hot posts.

Auth is the instance's access key, passed as ``?key=`` (a Bearer header is
rejected by RSSHub's access control). The key lives in ``RSSHUB_TOKEN``; the base
URL in ``RSSHUB_BASE_URL``. Neither is ever logged or written into a report.

Dates arrive as RFC-822 GMT; the window is applied on the **date** so an item
published late on the run date is still visible (upstream's news window includes
the end date).
"""

from __future__ import annotations

from datetime import date

from tradingagents_cn.cache import cached
from tradingagents_cn.vendors import rsshub
from tradingagents_cn.vendors.common import no_rows, require_ashare

BASE_ENV = rsshub.BASE_ENV
TOKEN_ENV = rsshub.TOKEN_ENV

_TTL_SECONDS = 60 * 60

# Kept as module attributes so tests can patch the seam without network access.
_fetch = rsshub.fetch
_clean = rsshub.clean
_published = rsshub.published
parse_items = rsshub.parse_items


def xueqiu_code(symbol: str) -> str:
    """``600519.SH`` -> ``SH600519`` (the spelling the route expects)."""
    canonical = require_ashare(symbol)
    code, market = canonical.split(".", 1)
    return f"{market}{code}"


def _window(start_date: str, end_date: str) -> tuple[date, date]:
    return date.fromisoformat(start_date), date.fromisoformat(end_date)


def fetch_stock_items(symbol: str, kind: str, start_date: str, end_date: str) -> list[dict]:
    """Items from ``stock_info/<CODE>/<kind>`` (news/discuss/announcement/trans)."""
    code = xueqiu_code(symbol)
    start, end = _window(start_date, end_date)
    xml_text = cached(
        "xueqiu", f"stock_info|{code}|{kind}|{start}|{end}", _TTL_SECONDS,
        lambda: _fetch(f"/xueqiu/stock_info/{code}/{kind}"),
    )
    return parse_items(xml_text, start, end)


def fetch_stock_announcements(symbol: str, start_date: str, end_date: str) -> list[dict]:
    """Per-stock announcements (title + PDF link), window-filtered."""
    return fetch_stock_items(symbol, "announcement", start_date, end_date)


def fetch_stock_comments(symbol: str, start_date: str, end_date: str) -> list[dict]:
    code = xueqiu_code(symbol)
    start, end = _window(start_date, end_date)
    xml_text = cached(
        "xueqiu", f"comments|{code}|{start}|{end}", _TTL_SECONDS,
        lambda: _fetch(f"/xueqiu/stock_comments/{code}"),
    )
    return parse_items(xml_text, start, end)


def fetch_hot_posts(start_date: str, end_date: str) -> list[dict]:
    start, end = _window(start_date, end_date)
    xml_text = cached(
        "xueqiu", f"hots|{start}|{end}", _TTL_SECONDS,
        lambda: _fetch("/xueqiu/hots"),
    )
    return parse_items(xml_text, start, end)


def _render(subject: str, items: list[dict], window: str) -> str:
    lines = [f"## {subject} News, {window}:", ""]
    for item in items:
        title = item["title"] or item["text"][:60]
        lines.append(f"### {title}")
        if item["text"]:
            lines.append(item["text"])
        if item["link"]:
            lines.append(f"Link: {item['link']}")
        if item["published"]:
            lines.append(f"Published: {item['published'].isoformat()}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def get_news(ticker: str, start_date: str, end_date: str) -> str:
    """Per-stock news for an A-share symbol, as the router's ``get_news`` expects."""
    canonical = require_ashare(ticker)
    items = fetch_stock_items(canonical, "news", start_date, end_date)
    if not items:
        raise no_rows(ticker, canonical,
                      f"xueqiu returned no news between {start_date} and {end_date}")
    return _render(canonical, items[:20], f"from {start_date} to {end_date}")


def get_announcements(ticker: str, start_date: str, end_date: str) -> str:
    """Exchange announcements for an A-share symbol (not routed yet)."""
    canonical = require_ashare(ticker)
    items = fetch_stock_announcements(canonical, start_date, end_date)
    if not items:
        raise no_rows(ticker, canonical,
                      f"xueqiu returned no announcements between {start_date} and {end_date}")
    return _render(canonical, items[:20], f"from {start_date} to {end_date}")


def register_vendors() -> None:
    from tradingagents_cn.bootstrap import register_vendor

    register_vendor("get_news", "xueqiu", get_news)


__all__ = [
    "BASE_ENV", "TOKEN_ENV", "fetch_hot_posts", "fetch_stock_comments",
    "fetch_stock_items", "get_announcements", "get_news", "parse_items",
    "register_vendors", "xueqiu_code",
]
