"""A-share news analyst: upstream's tools plus the domestic event stream.

The upstream node can only see what its four tools return: routed news, global
news, FRED-shaped macro and prediction markets. For a mainland listing that leaves
out the two sources that actually carry company events — the CLS announcement
stream and Xueqiu's per-stock announcements. Both are prefetched into the prompt
here; the tool set stays upstream's, so the model can still dig into news and
macro itself.

Empty blocks are stated as unavailable; the node never fills them in.
"""

from __future__ import annotations

from datetime import date, timedelta

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.analysts.turn import take_turn
from tradingagents.agents.context import get_instrument_context_from_state
from tradingagents.agents.tools import (
    get_global_news,
    get_macro_indicators,
    get_news,
    get_prediction_markets,
)
from tradingagents_cn.agents.blocks import safe
from tradingagents_cn.vendors import cls, xueqiu

TOOLS = (get_news, get_global_news, get_macro_indicators, get_prediction_markets)

_WINDOW_DAYS = 30

_SYSTEM = """You are a news and events analyst for the A-share market, covering {ticker} for the window ending {end_date}.

Two event streams are prefetched below. Read them before deciding what to look up with tools.

- CLS company events come from the market-wide announcement firehose and were filtered by this issuer's exchange code; coverage is good but not total.
- Xueqiu announcements are filed per stock; their items are authoritative for the issuer and link to the exchange PDF.
- Use the tools for company news (routed to Xueqiu for A-shares), broader market news, Chinese macro series (cpi/ppi/m2/social_financing/pmi/shibor) and, when available, prediction markets.
- Two markers carry different meanings. NO_ITEMS: the source answered and nothing matched the window - the issuer was quiet, report it as quiet. UNAVAILABLE: the source failed - report it as missing data. Never swap them, never fill either in.
- Never invent an event, a filing or a number.
- Name the basis of every number you cite: prices with their adjustment basis (前复权/qfq) and anchor date, financials with their period basis (本年累计/单季) and unit, exactly as the table headers state them. If a header does not say, call the basis unstated rather than guessing.
- Write as research: every factual claim carries its source and date; conclusions are observations with evidence, not instructions to buy or sell - another agent decides the trade.

<start_of_cls_events>
{cls_block}
<end_of_cls_events>

<start_of_xueqiu_announcements>
{announcements_block}
<end_of_xueqiu_announcements>
{instrument_context}"""


def create_news_analyst(llm):
    """Factory with upstream's contract, used by the CN graph wiring."""

    def news_analyst_node(state):
        ticker = state["company_of_interest"]
        end_date = state["trade_date"]
        start_date = (date.fromisoformat(end_date) - timedelta(days=_WINDOW_DAYS)).isoformat()

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " Use the provided tools to progress towards answering the question."
                    " Report what your tools support; another agent decides the trade."
                    " Today's date is {current_date}. You have access to: {tool_names}.\n" + _SYSTEM,
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        ).partial(
            tool_names=", ".join(tool.name for tool in TOOLS),
            current_date=end_date,
            ticker=ticker,
            end_date=end_date,
            instrument_context=get_instrument_context_from_state(state),
            cls_block=safe(
                "CLS company events",
                lambda: cls.fetch_company_events(ticker, start_date, end_date),
            ),
            announcements_block=safe(
                "Xueqiu announcements",
                lambda: xueqiu.fetch_stock_announcements(ticker, start_date, end_date),
            ),
        )

        result, report = take_turn(prompt, llm, TOOLS, state["messages"])
        return {"messages": [result], "news_report": report}

    return news_analyst_node


__all__ = ["TOOLS", "create_news_analyst"]
