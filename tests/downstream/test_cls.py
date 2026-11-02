"""CLS telegraph: code extraction, market-wide vs per-company use, refusal."""

from __future__ import annotations

import pytest

from tradingagents.dataflows.errors import NoMarketDataError, VendorNotConfiguredError
from tradingagents_cn.vendors import cls

pytestmark = pytest.mark.unit

ANNOUNCEMENT_XML = """<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>奥精医疗：被证监会立案</title><link>https://c/1</link>
<pubDate>Sun, 01 Nov 2026 13:01:16 GMT</pubDate>
<description>奥精医疗(688613.SH)涉嫌财务数据虚假记载</description></item>
<item><title>亨通光电：董事长提议回购</title><link>https://c/2</link>
<pubDate>Sun, 01 Nov 2026 09:25:43 GMT</pubDate>
<description>亨通光电(600487.SH)提议回购1亿至2亿元</description></item>
<item><title>比亚迪10月销量</title><link>https://c/3</link>
<pubDate>Sun, 01 Nov 2026 10:19:39 GMT</pubDate>
<description>比亚迪10月新能源汽车销量49.02万辆</description></item>
<item><title>未来稿</title><link>https://c/4</link>
<pubDate>Wed, 04 Nov 2026 01:00:00 GMT</pubDate>
<description>未发生 600519.SH</description></item>
</channel></rss>"""


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_CN_CACHE", "off")
    monkeypatch.setenv("RSSHUB_BASE_URL", "https://rss.invalid")
    monkeypatch.setenv("RSSHUB_TOKEN", "test-key")
    monkeypatch.setattr(cls, "_fetch", lambda path, **params: ANNOUNCEMENT_XML)


def test_codes_are_extracted_in_order_without_duplicates():
    assert cls.extract_codes("奥精医疗(688613.SH) 与 亨通光电(600487.SH)") == [
        "688613.SH", "600487.SH"]
    assert cls.extract_codes("重复 600519.SH 和 600519.SH") == ["600519.SH"]
    assert cls.extract_codes("no code here") == []


def test_announcement_items_carry_their_codes_and_respect_the_window():
    items = cls.fetch_telegraph("announcement", "2026-11-01", "2026-11-02")

    assert [item["title"] for item in items] == [
        "奥精医疗：被证监会立案", "亨通光电：董事长提议回购", "比亚迪10月销量"]
    assert items[0]["codes"] == ["688613.SH"]
    assert items[2]["codes"] == []           # the live feed really has such items


def test_company_events_filter_by_the_extracted_code():
    events = cls.fetch_company_events("600487.SH", "2026-11-01", "2026-11-02")

    assert len(events) == 1
    assert "亨通光电" in events[0]["title"]


def test_an_unknown_category_lists_the_known_ones():
    with pytest.raises(ValueError, match="announcement"):
        cls.fetch_telegraph("company")


def test_a_foreign_symbol_is_declined():
    with pytest.raises(NoMarketDataError):
        cls.fetch_company_events("AAPL", "2026-11-01", "2026-11-02")


def test_no_matching_events_is_no_data():
    with pytest.raises(NoMarketDataError):
        cls.get_company_events("600519.SH", "2026-11-01", "2026-11-02")


def test_a_missing_token_is_reported_without_a_request(monkeypatch):
    from tradingagents_cn.vendors import rsshub

    monkeypatch.setattr(cls, "_fetch", rsshub.fetch)   # restore the real seam
    monkeypatch.delenv("RSSHUB_TOKEN", raising=False)

    with pytest.raises(VendorNotConfiguredError, match="RSSHUB_TOKEN"):
        cls.fetch_telegraph("all")
