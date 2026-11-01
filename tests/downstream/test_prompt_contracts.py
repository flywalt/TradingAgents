"""Prompt contracts: what each agent is actually told, captured not assumed.

The harness runs the whole graph with a scripted model that records the messages
it receives, so the assertions are about real prompts rather than about the code
that builds them. No tool calls are bound: the question here is what enters the
prompt (identity, A-share constraints, profile), not how tools answer.
"""

from __future__ import annotations

import pandas as pd
import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from tradingagents.agents.analysts import sentiment_analyst
from tradingagents.dataflows import router
from tradingagents.graph import trading_graph as upstream_graph
from tradingagents_cn.graph.factory import build_graph
from tradingagents_cn.vendors.tushare import client

pytestmark = pytest.mark.unit

TEXT = "Report.\n\n**Rating**: Overweight\n\nFINAL TRANSACTION PROPOSAL: **BUY**"
TRADE_DATE = "2026-10-30"

#: The twelve nodes that call a model. If the graph gains or loses one, this list
#: is the place the change surfaces.
EXPECTED_NODES = 12


class RecordingModel(BaseChatModel):
    """Records every message list it is asked to answer, then answers with TEXT."""

    prompts: list = []

    @property
    def _llm_type(self) -> str:
        return "recording"

    def bind_tools(self, tools, **kwargs):
        """No tool calls: this harness tests what enters the prompt, not tools."""
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        object.__setattr__(self, "prompts", self.prompts + [
            "\n".join(str(getattr(message, "content", "")) for message in messages)
        ])
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=TEXT))])


class _Client:
    def __init__(self, model):
        self.model = model

    def get_llm(self):
        return self.model


class FakeApi:
    def stock_basic(self, **kwargs):
        return pd.DataFrame([{
            "ts_code": "600519.SH", "name": "贵州茅台", "area": "贵州", "industry": "白酒",
            "market": "主板", "list_date": "20010827", "delist_date": "", "list_status": "L",
        }])

    def namechange(self, **kwargs):
        return pd.DataFrame([{
            "name": "贵州茅台", "start_date": "20010827", "end_date": "", "ann_date": "20010827",
        }])


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    monkeypatch.setenv("TRADINGAGENTS_CN_CACHE", "off")
    model = RecordingModel()
    monkeypatch.setattr(upstream_graph, "create_tier_client", lambda config, tier, **k: _Client(model))
    monkeypatch.setattr(sentiment_analyst, "fetch_stocktwits_messages", lambda *a, **k: "no posts")
    monkeypatch.setattr(sentiment_analyst, "fetch_reddit_posts", lambda *a, **k: "no posts")
    monkeypatch.setitem(router.VENDOR_METHODS["get_news"], "yfinance",
                        lambda *a, **k: "company news stub")
    monkeypatch.setitem(router.VENDOR_METHODS["get_global_news"], "yfinance",
                        lambda *a, **k: "global news stub")
    monkeypatch.setattr(upstream_graph, "resolve_instrument_identity",
                        lambda ticker: {"name": "Apple Inc.", "industry": "Consumer Electronics"})
    client.set_api(FakeApi())
    try:
        yield model, tmp_path
    finally:
        client.reset_api()


def _run(model, tmp_path, symbol):
    graph = build_graph({
        "results_dir": str(tmp_path / "results"),
        "data_cache_dir": str(tmp_path / "cache"),
        "memory_log_path": str(tmp_path / "memory.md"),
        "llm_provider": "openai",
        "output_language": "English",
    }, symbol=symbol)
    graph.propagate(symbol, TRADE_DATE)
    return graph


def test_every_node_receives_the_a_share_identity_and_constraints(offline):
    model, tmp_path = offline

    _run(model, tmp_path, "600519.SH")

    # Twelve nodes, plus a free-text retry for each structured one (the scripted
    # model cannot parse structured output). Every one must still carry identity.
    assert len(model.prompts) >= EXPECTED_NODES
    for index, prompt in enumerate(model.prompts):
        assert "600519.SH" in prompt, f"node {index} lost the ticker"
        assert "贵州茅台" in prompt, f"node {index} lost the company name"
        assert "A-share trading rules" in prompt, f"node {index} lost the trading constraints"
        assert "T+1" in prompt, f"node {index} lost the settlement rule"


def test_the_constraints_state_what_the_feed_cannot_tell(offline):
    model, tmp_path = offline

    _run(model, tmp_path, "600519.SH")

    prompt = model.prompts[0]
    assert "±10%" in prompt
    assert "ST status and suspensions are unavailable" in prompt


def test_a_us_run_carries_no_a_share_constraints(offline):
    model, tmp_path = offline

    _run(model, tmp_path, "AAPL")

    assert len(model.prompts) >= EXPECTED_NODES
    for prompt in model.prompts:
        assert "A-share trading rules" not in prompt
        assert "T+1" not in prompt
        assert "Apple Inc." in prompt


def test_the_report_records_the_profile(offline):
    model, tmp_path = offline
    graph = _run(model, tmp_path, "600519.SH")

    state = graph.create_run_state("600519.SH", TRADE_DATE)
    metadata = graph.run_metadata(TRADE_DATE, "600519.SH")

    assert graph.config["cn_market_profile"] == "CN_A_SHARE"
    assert metadata["extension_version"] == graph.config["cn_extension_version"]
    assert "贵州茅台" in state["instrument_context"]
