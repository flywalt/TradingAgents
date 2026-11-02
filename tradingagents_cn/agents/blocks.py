"""Shared prompt blocks for downstream analysts: bounded text, honest gaps."""

from __future__ import annotations

from tradingagents.dataflows.errors import VendorError

MAX_ITEMS = 20


def block(items: list[dict], limit: int = MAX_ITEMS) -> str:
    if not items:
        return "UNAVAILABLE: this source returned no items in the window."
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
