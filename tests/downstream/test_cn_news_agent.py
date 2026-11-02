"""The A-share news analyst: domestic event blocks join upstream's tools."""

from __future__ import annotations

from datetime import date

import pytest
from langchain_core.messages import AIMessage

from tradingagents.dataflows.errors import VendorUnavailableError
from tradingagents_cn.agents import news_analyst as cn_news
from tradingagents_cn.vendors import cls, xueqiu

pytestmark = pytest.mark.unit


def _items(text: str, codes=None):
    return [{"title": text, "text": text, "link": "", "codes": codes or [],
             "published": date(2026, 11, 1)}]


@pytest.fixture
def captured(monkeypatch):
    box = {}

    def fake_take_turn(prompt, llm, tools, messages):
        box["prompt"] = prompt
        return AIMessage(content="报告"), "新闻报告正文"

    monkeypatch.setattr(cn_news, "take_turn", fake_take_turn)
    return box


def test_domestic_event_blocks_reach_the_prompt(captured, monkeypatch):
    monkeypatch.setattr(cls, "fetch_company_events",
                        lambda *a, **k: _items("公告：被立案", ["688613.SH"]))
    monkeypatch.setattr(xueqiu, "fetch_stock_announcements",
                        lambda *a, **k: _items("三季报公告"))

    node = cn_news.create_news_analyst(object())
    out = node({"company_of_interest": "600519.SH", "trade_date": "2026-11-02",
                "messages": [], "instrument_context": "600519.SH 贵州茅台"})

    partial = captured["prompt"].partial_variables
    assert "被立案" in partial["cls_block"] and "688613.SH" in partial["cls_block"]
    assert "三季报公告" in partial["announcements_block"]
    assert "600519.SH 贵州茅台" in partial["instrument_context"]
    assert out["news_report"] == "新闻报告正文"


def test_a_broken_event_stream_is_reported_not_hidden(captured, monkeypatch):
    def broken(*args, **kwargs):
        raise VendorUnavailableError("rsshub down")

    monkeypatch.setattr(cls, "fetch_company_events", broken)
    monkeypatch.setattr(xueqiu, "fetch_stock_announcements", broken)

    node = cn_news.create_news_analyst(object())
    node({"company_of_interest": "600519.SH", "trade_date": "2026-11-02",
          "messages": [], "instrument_context": ""})

    partial = captured["prompt"].partial_variables
    assert partial["cls_block"].startswith("UNAVAILABLE")
    assert "rsshub" in partial["cls_block"]
    assert partial["announcements_block"].startswith("UNAVAILABLE")


def test_the_cn_graph_uses_the_downstream_news_factory(monkeypatch, tmp_path):
    from tradingagents.graph import trading_graph as upstream_graph
    from tradingagents_cn import config as cn_config
    from tradingagents_cn.graph.factory import build_graph

    calls = []

    def sentinel(llm):
        calls.append(llm)
        return lambda state: {}

    monkeypatch.setattr("tradingagents_cn.graph.wiring.create_news_analyst", sentinel)
    monkeypatch.setattr(upstream_graph, "create_tier_client",
                        lambda config, tier, **k: type("C", (), {"get_llm": lambda self: None})())

    settings = cn_config.apply({
        "results_dir": str(tmp_path / "r"), "data_cache_dir": str(tmp_path / "c"),
        "memory_log_path": str(tmp_path / "m.md"), "llm_provider": "openai",
    })
    build_graph(settings, symbol="600519.SH")

    assert calls, "the CN graph did not use the downstream news factory"


def test_an_empty_source_is_reported_as_no_items_not_unavailable():
    from tradingagents_cn.agents import blocks

    assert blocks.block([]).startswith("NO_ITEMS")
    rendered = blocks.safe("source", lambda: [])
    assert rendered.startswith("NO_ITEMS")
