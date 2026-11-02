"""Shared access to the self-hosted RSSHub instance.

Both the Xueqiu and CLS vendors speak the same protocol: ``?key=<token>`` access
control, RSS 2.0 payloads, RFC-822 dates. One implementation keeps the auth and
window semantics identical across sources.
"""

from __future__ import annotations

import html as html_module
import os
import re
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import UTC, date
from email.utils import parsedate_to_datetime

import requests

from tradingagents.dataflows.errors import VendorNotConfiguredError, VendorUnavailableError

BASE_ENV = "RSSHUB_BASE_URL"
TOKEN_ENV = "RSSHUB_TOKEN"

_TIMEOUT = 20
_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")
MAX_TEXT = 800


def configured() -> tuple[str, str]:
    base = (os.environ.get(BASE_ENV) or "").strip().rstrip("/")
    token = (os.environ.get(TOKEN_ENV) or "").strip()
    if not base or not token:
        raise VendorNotConfiguredError(
            f"RSSHub needs {BASE_ENV} and {TOKEN_ENV} in the environment (or .env)"
        )
    return base, token


def fetch(path: str, **params) -> str:
    """GET one route; transport and access failures map onto the router's types."""
    base, token = configured()
    query = urllib.parse.urlencode(
        {"key": token, **{k: v for k, v in params.items() if v is not None}}
    )
    try:
        response = requests.get(f"{base}{path}?{query}", timeout=_TIMEOUT)
    except requests.RequestException as exc:
        raise VendorUnavailableError(f"RSSHub unreachable: {exc}") from exc
    if response.status_code in (401, 403):
        raise VendorNotConfiguredError(
            f"RSSHub rejected the access key ({response.status_code}); check {TOKEN_ENV}"
        )
    if response.status_code >= 500:
        raise VendorUnavailableError(f"RSSHub route {path} failed upstream ({response.status_code})")
    if response.status_code != 200:
        raise VendorUnavailableError(f"RSSHub route {path} returned {response.status_code}")
    return response.text


def clean(text: str | None) -> str:
    if not text:
        return ""
    stripped = html_module.unescape(_TAG_RE.sub(" ", text))
    return _SPACE_RE.sub(" ", stripped).strip()[:MAX_TEXT]


def published(item: ET.Element) -> date | None:
    raw = (item.findtext("pubDate") or "").strip()
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw).astimezone(UTC).date()
    except (TypeError, ValueError):
        return None


def parse_items(xml_text: str, start: date | None = None, end: date | None = None) -> list[dict]:
    """RSS items as dicts, filtered on the publication date (inclusive)."""
    root = ET.fromstring(xml_text)
    items = []
    for item in root.findall("./channel/item"):
        day = published(item)
        if start is not None and (day is None or day < start):
            continue
        if end is not None and (day is None or day > end):
            continue
        items.append(
            {
                "title": clean(item.findtext("title")),
                "link": (item.findtext("link") or "").strip(),
                "published": day,
                "text": clean(item.findtext("description")),
            }
        )
    return items
