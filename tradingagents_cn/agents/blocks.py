"""Shared prompt blocks for downstream analysts: bounded text, honest gaps."""

from __future__ import annotations

from tradingagents.dataflows.errors import VendorError

MAX_ITEMS = 20


def block(items: list[dict], limit: int = MAX_ITEMS) -> str:
    """Render items; distinguish "answered with nothing" from "could not answer".

    The upstream data layer already separates NO_DATA from DATA_UNAVAILABLE, and
    the analyst should preserve that distinction: a quiet company is not a broken
    feed.
    """
    if not items:
        return "NO_ITEMS: this source answered but had nothing in the window."
    lines = []
    for item in items[:limit]:
        stamp = item["published"].isoformat() if item.get("published") else "no-date"
        body = item["text"] or item["title"]
        codes = ",".join(item.get("codes", []) or [])
        lines.append(f"- [{stamp}]" + (f" [{codes}]" if codes else "") + f" {body}")
    return "\n".join(lines)


def safe(label: str, fetch) -> str:
    """Run a prefetch; a failure becomes an explicit block, never an exception."""
    try:
        return block(fetch())
    except VendorError as exc:
        return f"UNAVAILABLE: {label} could not be fetched ({exc})."
    except Exception as exc:  # noqa: BLE001 - a broken source must not abort the node
        return f"UNAVAILABLE: {label} failed ({type(exc).__name__})."
