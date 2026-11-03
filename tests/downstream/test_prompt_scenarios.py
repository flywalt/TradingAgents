"""Golden scenarios with real tool calls.

The contract under test is not "the report reads well" but "the tool result the
model receives is the truth it must not overwrite": an unavailable symbol arrives
as NO_DATA_AVAILABLE, a loss arrives with its sign, and a limit-up close arrives
with the band that produced it.

A scripted model calls every bound tool once, so each scenario exercises the real
router -> adapter -> renderer path, not a stub at the tool boundary.
"""

from __future__ import annotations

import pandas as pd
import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from tradingagents.agents.analysts import sentiment_analyst
from tradingagents.dataflows import router
from tradingagents.dataflows.errors import NoMarketDataError
from tradingagents.graph import trading_graph as upstream_graph
from tradingagents_cn.graph.factory import build_graph
from tradingagents_cn.vendors.tushare import client

pytestmark = pytest.mark.unit

SYMBOL = "600519.SH"
TRADE_DATE = "2026-09-30"
TEXT = "Report.\n\n**Rating**: Hold\n\nFINAL TRANSACTION PROPOSAL: **HOLD**"
CAPTURED: list[str] = []

ARGS = {
    "symbol": SYMBOL, "ticker": SYMBOL, "curr_date": TRADE_DATE, "trade_date": TRADE_DATE,
    "start_date": "2026-09-01", "end_date": TRADE_DATE, "indicator": "rsi",
    "freq": "quarterly", "look_back_days": 10, "topic": "policy",
}


class ToolCallingModel(BaseChatModel):
    """Calls every bound tool once, then answers; records every prompt it sees."""

    tools: tuple = ()

    @property
    def _llm_type(self) -> str:
        return "tool-calling"

    def bind_tools(self, tools, **kwargs):
        return self.model_copy(update={"tools": tuple(tools)})

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        CAPTURED.append("\n".join(str(getattr(message, "content", "")) for message in messages))
        if self.tools and not isinstance(messages[-1], ToolMessage):
            properties = self.tools[0].tool_call_schema.model_json_schema()["properties"]
            calls = [
                {"name": tool.name, "id": f"call_{index}",
                 "args": {key: value for key, value in ARGS.items() if key in properties}}
                for index, tool in enumerate(self.tools)
            ]
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content="", tool_calls=calls))])
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=TEXT))])


class _Client:
    def __init__(self, model):
        self.model = model

    def get_llm(self):
        return self.model


def bars(limit_up: bool) -> pd.DataFrame:
    days = pd.date_range("2026-06-01", periods=60, freq="B")
    closes = [100.0] * 58 + [100.0, 110.0 if limit_up else 101.0]
    return pd.DataFrame({
        "ts_code": [SYMBOL] * 60,
        "trade_date": [d.strftime("%Y%m%d") for d in days],
        "open": closes, "high": closes, "low": closes, "close": closes,
        "vol": [1000.0] * 60, "amount": [1000.0] * 60, "pct_chg": [0.0] * 60,
    })


def loss_income() -> pd.DataFrame:
    return pd.DataFrame({
        "ts_code": [SYMBOL], "ann_date": ["20260825"], "f_ann_date": ["20260825"],
        "end_date": ["20260630"], "report_type": ["1"],
        "total_revenue": [1.0e9], "revenue": [1.0e9], "oper_cost": [8.0e8],
        "operate_profit": [-1.2e9], "total_profit": [-1.3e9],
        "n_income": [-1.5e9], "n_income_attr_p": [-1.4e9], "basic_eps": [-1.1],
    })


class FakeApi:
    def __init__(self, *, limit_up=False, unavailable=False, name="贵州茅台"):
        self.limit_up = limit_up
        self.unavailable = unavailable
        self.name = name

    def stock_basic(self, **kwargs):
        return pd.DataFrame([{
            "ts_code": SYMBOL, "name": self.name, "area": "贵州", "industry": "白酒",
            "market": "主板", "list_date": "20010827", "delist_date": "", "list_status": "L",
        }])

    def namechange(self, **kwargs):
        return pd.DataFrame([{"name": self.name, "start_date": "20250101",
                              "end_date": "", "ann_date": "20250101"}])

    def pro_bar(self, **kwargs):
        if self.unavailable:
            raise NoMarketDataError(SYMBOL, SYMBOL, "suspended: no bars in the window")
        return bars(self.limit_up)

    def income(self, **kwargs):
        return loss_income()

    def balancesheet(self, **kwargs):
        return pd.DataFrame({"ts_code": [SYMBOL], "ann_date": ["20260825"],
                             "end_date": ["20260630"], "report_type": ["1"],
                             "total_assets": [2.0e11], "total_liab": [1.5e11]})

    def cashflow(self, **kwargs):
        return pd.DataFrame({"ts_code": [SYMBOL], "ann_date": ["20260825"],
                             "end_date": ["20260630"], "report_type": ["1"],
                             "n_cashflow_act": [-3.0e8]})


REAL_METHODS = {"get_stock_data", "get_income_statement", "get_balance_sheet", "get_cashflow"}


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    CAPTURED.clear()
    monkeypatch.setenv("TRADINGAGENTS_CN_CACHE", "off")
    model = ToolCallingModel()
    monkeypatch.setattr(upstream_graph, "create_tier_client", lambda config, tier, **k: _Client(model))
    monkeypatch.setattr(sentiment_analyst, "fetch_stocktwits_messages", lambda *a, **k: "no posts")
    monkeypatch.setattr(sentiment_analyst, "fetch_reddit_posts", lambda *a, **k: "no posts")
    yield tmp_path, monkeypatch
    client.reset_api()


def _stub_the_rest(monkeypatch):
    """Patch after the graph is built: bootstrap() re-registers the real providers."""
    for method, vendors in list(router.VENDOR_METHODS.items()):
        if method in REAL_METHODS:
            continue
        for vendor in vendors:
            monkeypatch.setitem(vendors, vendor, lambda *a, _m=method, **k: f"{_m} stub")


def _run(fixture, api, *, strict=False):
    tmp_path, monkeypatch = fixture
    client.set_api(api)
    graph = build_graph({
        "results_dir": str(tmp_path / "results"),
        "data_cache_dir": str(tmp_path / "cache"),
        "memory_log_path": str(tmp_path / "memory.md"),
        "llm_provider": "openai",
        "output_language": "English",
        "cn_strict_ashare": strict,
    }, symbol=SYMBOL)
    _stub_the_rest(monkeypatch)
    graph.propagate(SYMBOL, TRADE_DATE)
    return "\n".join(CAPTURED)


def test_an_unavailable_symbol_reaches_the_model_as_a_sentinel(offline):
    captured = _run(offline, FakeApi(unavailable=True), strict=True)

    assert "NO_DATA_AVAILABLE" in captured
    assert "Do not estimate or fabricate values" in captured
    # The instruction and the sentinel travel together; nothing else in the
    # captured prompts claims a price for this window.
    assert "Stock data for" not in captured


def test_a_loss_is_served_with_its_sign(offline):
    captured = _run(offline, FakeApi(), strict=True)

    assert "-15.00" in captured          # 净利润 -1.5e9 元 = -15.00 亿元
    assert "本年累计" in captured
    assert "单位：亿元" in captured


def test_a_limit_up_close_arrives_with_the_band_that_governs_it(offline):
    captured = _run(offline, FakeApi(limit_up=True), strict=True)

    assert "110.00" in captured          # the close itself
    assert "±10%" in captured            # the board rule from the context layer
    assert "NO_DATA_AVAILABLE" not in captured


def test_the_agents_state_the_missing_data_split(offline):
    """NO_ITEMS is a quiet issuer, UNAVAILABLE is a broken source - the model
    must be told the difference where it reads, in both analysts."""
    captured = _run(offline, FakeApi(limit_up=True))

    assert "NO_ITEMS: the source answered" in captured
    assert "the issuer was quiet" in captured
    assert "UNAVAILABLE: the source failed" in captured
    assert "Never swap them" in captured
    # both analysts carry the rule, not just one of them
    assert captured.count("NO_ITEMS: the source answered") >= 2


def test_the_news_analyst_is_told_to_name_the_basis(offline):
    """A number without its basis is a different number; the prompt must demand it."""
    captured = _run(offline, FakeApi(limit_up=True))

    assert "adjustment basis" in captured
    assert "anchor date" in captured
    assert "period basis" in captured
    assert "本年累计" in captured            # the requirement names the basis it means


def test_the_analysts_write_from_the_data(offline):
    """Evidence discipline, not a compliance posture: sources, no invented numbers."""
    captured = _run(offline, FakeApi(limit_up=True))

    assert "Every factual claim carries its source and date" in captured
    assert captured.count("Do not describe what the data cannot show") >= 2
    assert "Before answering, re-read once" in captured
    # the compliance framing this tool does not need was withdrawn
    assert "not instructions to buy or sell" not in captured


def test_an_st_name_reaches_the_model_with_its_five_percent_band(offline):
    """The name says ST; the band must not still read ±10%."""
    captured = _run(offline, FakeApi(name="ST 茅台"))

    assert "±5%" in captured
    assert "ST name" in captured
    assert "±10%" not in captured


def test_a_plain_name_is_told_st_status_is_unknown(offline):
    captured = _run(offline, FakeApi())

    assert "±10%" in captured
    assert "ST status is unknown" in captured


def test_the_prompts_carry_a_good_and_a_bad_example(offline):
    """A do/don't pair from real drifting: intraday colour from daily bars."""
    captured = _run(offline, FakeApi(limit_up=True))

    assert "前复权" in captured                       # the good example names the basis
    assert "盘中冲高至 1400 后回落" in captured        # the bad example is shown to be rejected
    assert "营收同比增长 12%" in captured             # numbers not in the data are rejected


def test_a_daily_bar_window_is_not_dressed_up_as_intraday(offline):
    """The data layer says daily; the prompt forbids implying otherwise."""
    captured = _run(offline, FakeApi(limit_up=True, ))
    assert "A daily bar is a daily bar" in captured


def test_the_price_table_states_its_basis_and_anchor(offline):
    """On an ex-rights stretch the anchor decides historical prices; the model
    must receive that statement with the table, not just a bare series."""
    captured = _run(offline, FakeApi(limit_up=True))

    assert "# Price basis: qfq anchored at 2026-09-30" in captured
