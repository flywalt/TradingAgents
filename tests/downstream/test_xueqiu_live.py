"""Live checks against the self-hosted RSSHub (needs RSSHUB_* in .env)."""

from __future__ import annotations

import os
from datetime import date, timedelta

import pytest

pytestmark = pytest.mark.integration

SYMBOL = "600519.SH"


def _skip() -> None:
    if not os.environ.get("RSSHUB_BASE_URL") or not os.environ.get("RSSHUB_TOKEN"):
        pytest.skip("RSSHUB_BASE_URL/RSSHUB_TOKEN are not set")


def test_live_stock_news_route_answers():
    _skip()
    from tradingagents_cn.vendors.xueqiu import get_news

    end = date.today()
    text = get_news(SYMBOL, (end - timedelta(days=60)).isoformat(), end.isoformat())

    assert text.startswith(f"## {SYMBOL} News")
    assert "Published:" in text


def test_live_comments_and_hot_posts_answer():
    _skip()
    from tradingagents_cn.vendors.xueqiu import fetch_hot_posts, fetch_stock_comments

    end = date.today()
    start = (end - timedelta(days=14)).isoformat()
    comments = fetch_stock_comments(SYMBOL, start, end.isoformat())
    hot = fetch_hot_posts(start, end.isoformat())

    assert comments and any(item["text"] for item in comments)
    assert isinstance(hot, list)
