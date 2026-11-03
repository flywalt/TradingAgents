"""The A-share sentiment analyst: Xueqiu blocks, honest degradation, wiring."""

from __future__ import annotations

from datetime import date

import pytest
from langchain_core.messages import AIMessage

from tradingagents.dataflows.errors import VendorUnavailableError
from tradingagents_cn.agents import sentiment_analyst as cn_sentiment
from tradingagents_cn.vendors import xueqiu

pytestmark = pytest.mark.unit


class FakeLLM:
    def __init__(self):
        self.prompts: list[str] = []

    def invoke(self, messages, **kwargs):
        self.prompts.append("\n".join(str(getattr(m, "content", "")) for m in messages))
        return AIMessage(content="情绪中性，数据有限。")


def _items(text: str):
    return [{"title": text, "text": text, "link": "", "published": date(2026, 11, 1)}]


def test_prefetched_blocks_reach_the_prompt(monkeypatch):
    monkeypatch.setattr(cn_sentiment, "get_news",
                        type("T", (), {"func": staticmethod(lambda *a, **k: "雪球新闻正文")}))
    monkeypatch.setattr(xueqiu, "fetch_stock_comments", lambda *a, **k: _items("评论：太贵了"))
    monkeypatch.setattr(xueqiu, "fetch_stock_items", lambda *a, **k: _items("帖子：等回调"))
    monkeypatch.setattr(xueqiu, "fetch_hot_posts", lambda *a, **k: _items("热帖：白酒异动"))

    llm = FakeLLM()
    node = cn_sentiment.create_sentiment_analyst(llm)
    out = node({"company_of_interest": "600519.SH", "trade_date": "2026-11-02",
                "messages": [], "instrument_context": "600519.SH 贵州茅台"})

    prompt = llm.prompts[-1]
    assert "雪球新闻正文" in prompt
    assert "评论：太贵了" in prompt
    assert "帖子：等回调" in prompt
    assert "热帖：白酒异动" in prompt
    assert "600519.SH 贵州茅台" in prompt
    assert out["sentiment_report"] == "情绪中性，数据有限。"


def test_a_broken_source_is_reported_not_hidden(monkeypatch):
    monkeypatch.setattr(cn_sentiment, "get_news",
                        type("T", (), {"func": staticmethod(lambda *a, **k: "新闻")}))

    def broken(*args, **kwargs):
        raise VendorUnavailableError("rsshub down")

    monkeypatch.setattr(xueqiu, "fetch_stock_comments", broken)
    monkeypatch.setattr(xueqiu, "fetch_stock_items", broken)
    monkeypatch.setattr(xueqiu, "fetch_hot_posts", broken)

    llm = FakeLLM()
    node = cn_sentiment.create_sentiment_analyst(llm)
    node({"company_of_interest": "600519.SH", "trade_date": "2026-11-02",
          "messages": [], "instrument_context": ""})

    prompt = llm.prompts[-1]
    assert prompt.count("UNAVAILABLE:") >= 3
    assert "rsshub" in prompt
    assert "Never fabricate" in prompt


def test_the_cn_graph_uses_the_downstream_sentiment_factory(monkeypatch, tmp_path):
    from tradingagents.graph import trading_graph as upstream_graph
    from tradingagents_cn import config as cn_config
    from tradingagents_cn.graph.factory import build_graph

    calls = []

    def sentinel(llm):
        calls.append(llm)

        def node(state):
            return {}

        return node

    monkeypatch.setattr("tradingagents_cn.graph.wiring.create_sentiment_analyst", sentinel)
    monkeypatch.setattr(upstream_graph, "create_tier_client",
                        lambda config, tier, **k: type("C", (), {"get_llm": lambda self: None})())

    settings = cn_config.apply({
        "results_dir": str(tmp_path / "r"), "data_cache_dir": str(tmp_path / "c"),
        "memory_log_path": str(tmp_path / "m.md"), "llm_provider": "openai",
    })
    build_graph(settings, symbol="600519.SH")

    assert calls, "the CN graph did not use the downstream sentiment factory"


def test_a_quiet_source_is_no_items_not_unavailable():
    """Same split as blocks.py: answered-with-nothing is not a broken feed."""
    from tradingagents_cn.agents import sentiment_analyst

    assert sentiment_analyst._block([]).startswith("NO_ITEMS")


def test_a_failed_source_is_unavailable():
    from tradingagents.dataflows.errors import VendorUnavailableError

    from tradingagents_cn.agents import sentiment_analyst

    def boom():
        raise VendorUnavailableError("xueqiu down")

    assert sentiment_analyst._safe("xueqiu comments", boom).startswith("UNAVAILABLE")
