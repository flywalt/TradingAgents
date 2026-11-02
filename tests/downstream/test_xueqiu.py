"""Xueqiu via RSSHub: parsing, windowing, routing, and refusal semantics."""

from __future__ import annotations

from datetime import date

import pytest

from tradingagents.dataflows.config import run_config
from tradingagents.dataflows.errors import NoMarketDataError, VendorNotConfiguredError
from tradingagents.dataflows.router import route_to_vendor
from tradingagents_cn import config as cn_config
from tradingagents_cn.bootstrap import bootstrap, reset
from tradingagents_cn.market import CN_A_SHARE, UPSTREAM_DEFAULT
from tradingagents_cn.vendors import xueqiu

pytestmark = pytest.mark.unit

NEWS_XML = """<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>重回1400</title><link>https://x/1</link>
<pubDate>Mon, 02 Nov 2026 02:25:27 GMT</pubDate>
<description>来源：格隆汇 茅台重回1400元 &lt;b&gt;上涨2.61%&lt;/b&gt;</description></item>
<item><title>旧闻</title><link>https://x/2</link>
<pubDate>Fri, 30 Oct 2026 10:36:22 GMT</pubDate>
<description>三季报</description></item>
<item><title>未来稿</title><link>https://x/3</link>
<pubDate>Wed, 04 Nov 2026 01:00:00 GMT</pubDate>
<description>尚未发生</description></item>
</channel></rss>"""

COMMENTS_XML = """<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>白酒还是贵</title><link>https://x/c1</link>
<pubDate>Mon, 02 Nov 2026 03:42:09 GMT</pubDate>
<description>&lt;a href="u"&gt;作者:&lt;/a&gt;&lt;br&gt;市场对白酒还是贵了。</description></item>
</channel></rss>"""


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_CN_CACHE", "off")
    monkeypatch.setenv("RSSHUB_BASE_URL", "https://rss.invalid")
    monkeypatch.setenv("RSSHUB_TOKEN", "test-key")
    reset()
    bootstrap()
    try:
        yield
    finally:
        reset()


def test_the_symbol_is_spelled_the_way_the_route_expects():
    assert xueqiu.xueqiu_code("600519.SH") == "SH600519"
    assert xueqiu.xueqiu_code("000001.SZ") == "SZ000001"
    with pytest.raises(NoMarketDataError):
        xueqiu.xueqiu_code("AAPL")


def test_items_are_filtered_to_the_window_and_html_is_stripped():
    items = xueqiu.parse_items(NEWS_XML, date(2026, 10, 30), date(2026, 11, 2))

    # 10-30 and 11-02 are inside the window; the 11-04 item is not.
    assert [item["title"] for item in items] == ["重回1400", "旧闻"]
    assert "<b>" not in items[0]["text"]
    assert "上涨2.61%" in items[0]["text"]
    assert items[0]["published"] == date(2026, 11, 2)


def test_a_comment_feed_keeps_its_text_and_author(monkeypatch):
    monkeypatch.setattr(xueqiu, "_fetch", lambda path, **params: COMMENTS_XML)

    items = xueqiu.fetch_stock_comments("600519.SH", "2026-11-01", "2026-11-02")

    assert "作者:" in items[0]["text"]
    assert "白酒还是贵了" in items[0]["text"]


def test_get_news_renders_title_link_and_date(monkeypatch):
    monkeypatch.setattr(xueqiu, "_fetch", lambda path, **params: NEWS_XML)

    text = xueqiu.get_news("600519.SH", "2026-10-30", "2026-11-02")

    assert text.startswith("## 600519.SH News")
    assert "### 重回1400" in text
    assert "Link: https://x/1" in text
    assert "Published: 2026-11-02" in text


def test_an_empty_answer_is_no_data(monkeypatch):
    monkeypatch.setattr(xueqiu, "_fetch", lambda path, **params: NEWS_XML)

    with pytest.raises(NoMarketDataError):
        xueqiu.get_news("600519.SH", "2026-11-05", "2026-11-06")


def test_a_rejected_key_is_a_configuration_error(monkeypatch):
    def rejected(path, **params):
        raise VendorNotConfiguredError("RSSHub rejected the access key (403)")

    monkeypatch.setattr(xueqiu, "_fetch", rejected)
    with pytest.raises(VendorNotConfiguredError):
        xueqiu.get_news("600519.SH", "2026-10-30", "2026-11-02")


def test_a_missing_token_is_reported_before_any_request(monkeypatch):
    monkeypatch.delenv("RSSHUB_TOKEN", raising=False)

    with pytest.raises(VendorNotConfiguredError, match="RSSHUB_TOKEN"):
        xueqiu.get_news("600519.SH", "2026-10-30", "2026-11-02")


def test_the_cn_profile_routes_company_news_to_xueqiu(monkeypatch):
    monkeypatch.setattr(xueqiu, "_fetch", lambda path, **params: NEWS_XML)
    settings = cn_config.apply(profile=CN_A_SHARE)
    assert settings["data_vendors"]["news_data"] == "xueqiu,yfinance"

    with run_config(settings):
        text = route_to_vendor("get_news", "600519.SH", "2026-10-30", "2026-11-02")

    assert text.startswith("## 600519.SH News")


def test_the_default_profile_keeps_yahoo_news():
    merged = cn_config.apply(profile=UPSTREAM_DEFAULT)
    assert merged["data_vendors"]["news_data"] == "yfinance"


def test_a_foreign_symbol_falls_through_to_yahoo(monkeypatch):
    """xueqiu declines non-A-shares, so the chain moves on instead of failing."""
    from tradingagents.dataflows import router

    monkeypatch.setitem(router.VENDOR_METHODS["get_news"], "yfinance",
                        lambda *a, **k: "yahoo news")

    with run_config({"data_vendors": {"news_data": "xueqiu,yfinance"}}):
        text = route_to_vendor("get_news", "AAPL", "2026-10-30", "2026-11-02")

    assert text == "yahoo news"
