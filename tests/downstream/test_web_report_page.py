"""The report page, presented in the language the run was asked for.

The kernel's artifact stays English on disk; this layer only decides what the
browser is handed.
"""

from __future__ import annotations

import pytest

from tradingagents_web import report_page

pytestmark = pytest.mark.unit

SAMPLE = """<!doctype html>
<html lang="en">
<head><title>600519.SH 2026-11-02 Hold: TradingAgents report</title></head>
<body>
<header><h1><span class="ticker">600519.SH</span> <span class="rating level">Hold</span></h1>
<p class="date">Analysis of 2026-11-02</p>
<dl class="run"><div><dt>Generated</dt><dd>2026-11-02 13:22</dd></div>
<div><dt>Debate rounds</dt><dd>1</dd></div></dl></header>
<nav class="contents" aria-label="Sections"><ul><li><a href="#s1"><span class="num">I</span>
<span class="label">Analyst Team Reports</span></a><ul><li><a href="#s1-1"><span class="label">Market Analyst</span></a></li></ul></li></ul></nav>
<main><section id="s1"><h2>I. Analyst Team Reports</h2><h3 id="s1-1">Market Analyst</h3>
<p><strong>Rating</strong>: HOLD，<strong>Executive Summary</strong> 见下；<strong>HOLD</strong> 与 <strong>BUY</strong> 均为内核枚举。
正文中的 Generated、Analysts 这些词不该被翻译。</p>
<div class="table"><table><tr><th>K</th></tr><tr><td><span class="name">Prices</span></td></tr></table></div>
</section>
<section id="s5"><h2>V. Portfolio Manager Decision</h2><h3 id="s5-1">Portfolio Manager</h3>
<p>维持当前配置，重点放在确定性更高的品种上。</p>
<p>组合在本周没有需要立即执行的调整；风险预算保持不变。</p>
<p>第三段不应出现在摘要里。</p></section>
<section id="s6"><h2>Downstream run metadata</h2></section></main>
<a class="to-top" href="#top">Top</a>
</body>
</html>"""


def test_a_chinese_run_gets_a_chinese_masthead():
    out = report_page.present(SAMPLE, "中文")

    assert '<html lang="zh-CN">' in out
    assert '<p class="date">分析日期 2026-11-02</p>' in out
    assert "<dt>生成时间</dt>" in out
    assert "<dt>辩论轮次</dt>" in out
    assert "<h2>一、分析师团队报告</h2>" in out      # sections: 一、
    assert "<h2>三、下游运行元数据</h2>" in out
    assert '<span class="num">一</span>' in out
    assert '<span class="label">分析师团队报告</span>' in out   # the rail, fully open
    assert "回到顶部" in out
    assert "研究报告</title>" in out


def test_the_rating_keeps_its_kernel_word_in_the_tooltip():
    out = report_page.present(SAMPLE, "中文")

    assert '<span class="rating level" title="Hold">持有</span>' in out


def test_the_report_body_is_never_touched():
    out = report_page.present(SAMPLE, "中文")

    assert "正文中的 Generated、Analysts 这些词不该被翻译。" in out
    assert '<h3 id="s1-1">（一）市场分析师</h3>' in out   # agents: （一）


def test_an_english_run_is_returned_unchanged():
    assert report_page.present(SAMPLE, "English") == SAMPLE
    assert report_page.present(SAMPLE, None) == SAMPLE


def test_a_report_without_a_rating_is_left_alone():
    html = SAMPLE.replace(' <span class="rating level">Hold</span>', "")

    out = report_page.present(html, "中文")
    assert 'class="rating' not in out   # the masthead badge is gone with the rating
    assert '<h1><span class="ticker">600519.SH</span></h1>' in out


def _upstream_report() -> str:
    from tradingagents.report_html import render_report

    final_state = {"trade_date": "2026-10-30", "final_rating": "Hold",
                   "final_trade_decision": "Hold", "memory_note": "kept"}
    settings = {"deep_think_provider": "openai_compatible", "quick_think_provider":
                "openai_compatible", "llm_provider": "openai_compatible",
                "deep_think_llm": "m1", "quick_think_llm": "m2",
                "analysts": ("market", "news"), "max_debate_rounds": 1,
                "max_risk_discuss_rounds": 1,
                "data_vendors": {"prices": ["tushare", "yfinance"]},
                "tool_vendors": {}, "version": "0.7.1"}
    parts = [("I. Analyst Team Reports", "1_analysts",
              [("Market Analyst", "market.md", "# 市场")]),
             ("V. Portfolio Manager Decision", "5_portfolio",
              [("Portfolio Manager", "decision.md", "维持配置。")])]
    return render_report("600519.SH", final_state, settings, parts)


def test_the_markup_we_match_is_still_produced_upstream():
    """Fragile coupling: if upstream renames its markup this fails at sync time.

    Every marker is asserted against a real ``render_report`` output, not against
    our own list: this test is the fuse that turns an upstream rename into a red
    suite instead of a page quietly reverting to English.
    """
    from tradingagents import reporting

    headings = [heading for heading, _folder, _agents in reporting._SECTIONS]
    assert headings == [
        "I. Analyst Team Reports", "II. Research Team Decision",
        "III. Trading Team Plan", "IV. Risk Management Team Decision",
        "V. Portfolio Manager Decision",
    ]
    html = _upstream_report()
    for marker in report_page.UPSTREAM_MARKERS:
        assert marker in html, marker


def test_a_chinese_report_gets_cjk_typography():
    out = report_page.present(SAMPLE, "中文")

    assert out.count('<style id="ta-cn">') == 1
    assert out.index('<style id="ta-cn">') < out.index("</head>")
    style = out[out.index('<style id="ta-cn">'):out.index("</style>", out.index('<style id="ta-cn">'))]
    assert "Noto Serif CJK SC" in style
    assert "--serif:" in style and "--sans:" in style
    assert "17px/1.85" in style


def test_an_english_report_gets_no_injected_style():
    assert "ta-cn" not in report_page.present(SAMPLE, "English")


def test_present_is_idempotent():
    once = report_page.present(SAMPLE, "中文")

    assert report_page.present(once, "中文") == once


def test_the_chinese_report_leads_with_the_decision():
    out = report_page.present(SAMPLE, "中文")

    assert '<section class="ta-summary"' in out
    assert out.index('<section class="ta-summary"') < out.index('<nav class="contents"')
    assert "核心结论" in out
    assert "维持当前配置，重点放在确定性更高的品种上。" in out
    assert "组合在本周没有需要立即执行的调整；风险预算保持不变。" in out
    assert "第三段不应出现在摘要里。" not in out.split('class="ta-summary"')[1].split("</section>")[0]
    assert 'href="#s5"' in out
    assert "阅读完整结论" in out


def test_the_full_decision_section_survives_the_summary():
    out = report_page.present(SAMPLE, "中文")

    body = out[out.index('id="s5"'):]
    for sentence in ("维持当前配置", "组合在本周没有需要立即执行的调整", "第三段不应出现在摘要里"):
        assert sentence in body


def test_a_report_without_a_decision_gets_no_summary_card():
    start = SAMPLE.index('<section id="s5">')
    html = SAMPLE[:start] + SAMPLE[SAMPLE.index("</section>", start) + len("</section>"):]

    out = report_page.present(html, "中文")

    assert 'class="ta-summary"' not in out   # the stylesheet may still be there
    assert "核心结论" not in out


def test_agent_names_are_translated_where_the_kernel_names_them():
    """The h3 headings and the contents rail repeat the kernel's node names."""
    out = report_page.present(SAMPLE, "中文")

    assert '<h3 id="s1-1">（一）市场分析师</h3>' in out          # id keeps its anchor
    assert '<span class="label">（一）市场分析师</span>' in out   # the rail too
    assert "Market Analyst" not in out


def test_kernel_enums_and_labels_are_translated_inside_strong():
    out = report_page.present(SAMPLE, "中文")

    assert "<strong>评级</strong>: 持有（HOLD）" in out
    assert "<strong>执行摘要</strong>" in out
    assert "<strong>持有（HOLD）</strong>" in out
    assert "<strong>买入（BUY）</strong>" in out
    # prose outside <strong> is never touched
    assert "均为内核枚举" in out


def test_data_vendor_groups_are_translated():
    out = report_page.present(SAMPLE, "中文")

    assert '<span class="name">行情</span>' in out
    assert '<span class="name">Prices</span>' not in out


def test_the_typography_scale_is_declared_for_chinese():
    out = report_page.present(SAMPLE, "中文")

    style = out[out.index('<style id="ta-cn">'):out.index("</style>")]
    assert "main h2" in style and "1.5rem" in style      # 一、 chapters lead
    # the kernel demotes an agent's own headings three levels (## -> h5); the
    # scale must stay monotonic and never dip below body size, or a section
    # titled "一、" renders smaller than the paragraph under it
    for rule in ("main h4", "main h5", "main h6"):
        assert rule in style, rule
    assert "1.13rem" in style                            # h4 >= body
    assert "1.06rem" in style                            # h5 == body, heavier
    assert ".ta-summary h2" in style and "1.13rem" in style


def test_digits_and_han_come_from_one_typeface():
    """Charter first mixed DejaVu digits with Noto Han; one family leads now."""
    out = report_page.present(SAMPLE, "中文")

    style = out[out.index('<style id="ta-cn">'):out.index("</style>")]
    serif_decl = style[style.index("--serif:"):style.index("serif;", style.index("--serif:"))]
    assert serif_decl.index("Noto Serif CJK SC") < serif_decl.index("Charter")
    assert "tabular-nums" in style


def test_the_company_name_leads_where_there_is_room():
    out = report_page.present(SAMPLE, "中文", name="贵州茅台")

    assert '<span class="ticker">贵州茅台 · 600519.SH</span>' in out
    assert "<title>贵州茅台 600519.SH" in out


def test_a_report_without_a_name_keeps_the_plain_ticker():
    out = report_page.present(SAMPLE, "中文")

    assert '<span class="ticker">600519.SH</span>' in out


def test_the_name_leads_even_in_an_english_report():
    out = report_page.present(SAMPLE, "English", name="Kweichow Moutai")

    assert '<span class="ticker">Kweichow Moutai · 600519.SH</span>' in out


def test_every_fixed_label_the_kernel_writes_is_translated():
    """One pass, from the source that writes them - not a list grown by eye."""
    body = ("<p><strong>Investment Thesis</strong>: x</p>"
            "<p><strong>Price Target</strong>: 1400</p>"
            "<p><strong>Entry Price</strong>: 1342</p>"
            "<p><strong>Stop Loss</strong>: 1295</p>"
            "<p><strong>Position Sizing</strong>: 0.25</p>"
            "<p><strong>Time Horizon</strong>: 3 months</p>"
            "<p><strong>Action</strong>: Buy</p>"
            "<p><strong>Rationale</strong>: y</p>"
            "<p><strong>Recommendation</strong>: z</p>"
            "<p><strong>Strategic Actions</strong>: w</p>"
            "<p>FINAL TRANSACTION PROPOSAL: <strong>OVERWEIGHT</strong></p>")
    html = SAMPLE.replace("<main>", "<main>" + body)

    out = report_page.present(html, "中文")

    for english in ("Investment Thesis", "Price Target", "Entry Price", "Stop Loss",
                    "Position Sizing", "Time Horizon", "Rationale", "Recommendation",
                    "Strategic Actions", "FINAL TRANSACTION PROPOSAL"):
        assert english not in out, english
    assert "<strong>投资论点</strong>" in out
    assert "<strong>目标价</strong>" in out
    assert "最终交易建议：" in out
    assert "<strong>增持（OVERWEIGHT）</strong>" in out


def test_an_enum_value_keeps_its_kernel_word_whatever_the_casing():
    html = SAMPLE.replace("<strong>Rating</strong>: HOLD", "<strong>Rating</strong>: Overweight")

    out = report_page.present(html, "中文")

    assert "<strong>评级</strong>: 增持（OVERWEIGHT）" in out


def test_the_schema_labels_cover_upstream():
    """Fragile coupling: a label added upstream must fail here, not leak English."""
    import re
    from pathlib import Path

    sources = [Path("tradingagents/agents/schemas.py"),
               Path("tradingagents/agents/trader/trader.py"),
               Path("tradingagents/agents/managers/portfolio_manager.py")]
    labels = set()
    for path in sources:
        text = path.read_text(encoding="utf-8")
        labels |= set(re.findall(r"\*\*([A-Z][A-Za-z ]{2,24})\*\*", text))
        labels |= set(re.findall(r'\("([A-Z][A-Za-z ]{2,24})"', text))

    enums = {"Buy", "Sell", "Hold", "Overweight", "Underweight"}
    known = set(report_page.SCHEMA_LABELS) | enums | {"None"}
    assert labels <= known, labels - known


def test_the_rail_opens_fully_on_a_wide_screen():
    """PC has the room: labels are always visible and every row is listed, so
    the pointer never has to travel up and down to find a chapter."""
    out = report_page.present(SAMPLE, "中文")

    style = out[out.index('<style id="ta-cn">'):out.index("</style>")]
    assert ".contents .label { max-width: none; opacity: 1; }" in style
    assert "ul ul { display: none" not in style    # nothing is folded away
    assert '<span class="label">（一）市场分析师</span>' in out


def test_the_metadata_section_we_no_longer_write_is_dropped():
    """Reports written before this decision still carry it; the reader should
    not see a sixth chapter of provenance."""
    html = SAMPLE.replace("</body>",
                          '<section id="downstream-run-metadata">'
                          '<h2>Downstream run metadata</h2><ul><li>x</li></ul></section>'
                          "</body>")

    for language in ("中文", "English"):
        out = report_page.present(html, language)
        assert "downstream-run-metadata" not in out, language
    # the fixture's own sixth heading is a different thing; in Chinese it is the
    # translated chapter and stays
    assert "下游运行元数据" in report_page.present(html, "中文")
