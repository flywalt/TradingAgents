"""A-share sentiment analyst: Xueqiu replaces StockTwits/Reddit.

Upstream pre-fetches three US-centric sources and injects them into the prompt.
For a mainland listing two of those are always empty, so the report degenerates to
"no data" — honest, but useless. This node keeps the same shape (pre-fetched
blocks, structured ``SentimentReport``, no tool calls) and swaps the sources:

* company news from the routed ``get_news`` (Xueqiu in the CN profile);
* Xueqiu per-stock comments and discussion posts;
* Xueqiu market-wide hot posts as a backdrop.

The prompt is written here rather than copied from upstream; it states plainly
that an empty block must be reported as unavailable, never filled in.
"""

from __future__ import annotations

from datetime import date, timedelta

from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.context import get_instrument_context_from_state
from tradingagents.agents.schemas import SentimentReport, render_sentiment_report
from tradingagents.agents.structured import (
    NO_EXTERNAL_TOOLS,
    bind_structured,
    invoke_structured_or_freetext,
)
from tradingagents.agents.tools import get_news
from tradingagents.dataflows.errors import VendorError
from tradingagents_cn.vendors import xueqiu

_WINDOW_DAYS = 7
_MAX_ITEMS = 20

_SYSTEM = """You are a sentiment analyst for the A-share market. Build a sentiment report for {ticker} from {start_date} to {end_date} using only the pre-collected material below.

Rules:
- Every source block is prefetched. If a block says it is unavailable or is empty, say so explicitly and do not infer what it might have contained. Never fabricate posts, headlines or counts.
- Separate retail tone (Xueqiu comments and posts) from institutional framing (company news). Xueqiu skews emotional; weight repeated themes over single loud posts.
- Quote concrete details you actually see (dates, repeated complaints, catalysts). No invented numbers.
- If every source is unavailable, return a Neutral band with low confidence and state that this reflects missing data, not a balanced market.

<start_of_news>
{news_block}
<end_of_news>

<start_of_xueqiu_comments>
{comments_block}
<end_of_xueqiu_comments>

<start_of_xueqiu_posts>
{posts_block}
<end_of_xueqiu_posts>

<start_of_market_hot>
{hot_block}
<end_of_market_hot>
{instrument_context}"""


def _block(items: list[dict], limit: int = _MAX_ITEMS) -> str:
    """Render items with the same split as blocks.py: a source that answered
    with nothing is a quiet issuer, not a broken feed."""
    if not items:
        return "NO_ITEMS: this source answered but had nothing in the window."
    lines = []
    for item in items[:limit]:
        stamp = item["published"].isoformat() if item.get("published") else "no-date"
        body = item["text"] or item["title"]
        lines.append(f"- [{stamp}] {body}")
    return "\n".join(lines)


def _safe(label: str, fetch) -> str:
    try:
        return _block(fetch())
    except VendorError as exc:
        return f"UNAVAILABLE: {label} could not be fetched ({exc})."
    except Exception as exc:  # noqa: BLE001 - a broken source must not abort the node
        return f"UNAVAILABLE: {label} failed ({type(exc).__name__})."


def create_sentiment_analyst(llm):
    """Factory with upstream's contract: ``create_x(llm) -> node(state) -> dict``."""
    structured_llm = bind_structured(llm, SentimentReport, "Sentiment Analyst")

    def sentiment_analyst_node(state):
        ticker = state["company_of_interest"]
        end_date = state["trade_date"]
        start_date = (date.fromisoformat(end_date) - timedelta(days=_WINDOW_DAYS)).isoformat()
        instrument_context = get_instrument_context_from_state(state)

        news_block = _safe("company news", lambda: [{"published": None, "title": "",
                                                     "text": get_news.func(ticker, start_date, end_date)}])
        def comments_fetch():
            return xueqiu.fetch_stock_comments(ticker, start_date, end_date)

        def posts_fetch():
            return xueqiu.fetch_stock_items(ticker, "discuss", start_date, end_date)

        def hot_fetch():
            return xueqiu.fetch_hot_posts(start_date, end_date)

        prompt = ChatPromptTemplate.from_messages(
            [("system", "Today's date is {current_date}. " + NO_EXTERNAL_TOOLS + "\n" + _SYSTEM),
             MessagesPlaceholder(variable_name="messages")]
        ).partial(
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
            current_date=end_date,
            instrument_context=instrument_context,
            news_block=news_block,
            comments_block=_safe("xueqiu comments", comments_fetch),
            posts_block=_safe("xueqiu posts", posts_fetch),
            hot_block=_safe("xueqiu hot posts", hot_fetch),
        )

        messages = prompt.format_messages(messages=state["messages"])
        report_text = invoke_structured_or_freetext(
            structured_llm, llm, messages, render_sentiment_report, "Sentiment Analyst"
        )
        return {"messages": [AIMessage(content=report_text)], "sentiment_report": report_text}

    return sentiment_analyst_node


__all__ = ["create_sentiment_analyst"]
