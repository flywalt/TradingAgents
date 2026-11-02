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
<span class="label">Analyst Team Reports</span></a></li></ul></nav>
<main><section id="s1"><h2>I. Analyst Team Reports</h2><h3>Market Analyst</h3>
<p>正文中的 Generated、Analysts 这些词不该被翻译。</p></section>
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
    assert "<h2>一、分析师团队报告</h2>" in out
    assert "<h2>下游运行元数据</h2>" in out
    assert '<span class="num">一</span>' in out
    assert '<span class="label">分析师团队报告</span>' in out
    assert "回到顶部" in out
    assert "研究报告</title>" in out


def test_the_rating_keeps_its_kernel_word_in_the_tooltip():
    out = report_page.present(SAMPLE, "中文")

    assert '<span class="rating level" title="Hold">中性</span>' in out


def test_the_report_body_is_never_touched():
    out = report_page.present(SAMPLE, "中文")

    assert "正文中的 Generated、Analysts 这些词不该被翻译。" in out
    assert "<h3>Market Analyst</h3>" in out


def test_an_english_run_is_returned_unchanged():
    assert report_page.present(SAMPLE, "English") == SAMPLE
    assert report_page.present(SAMPLE, None) == SAMPLE


def test_a_report_without_a_rating_is_left_alone():
    html = SAMPLE.replace(' <span class="rating level">Hold</span>', "")

    out = report_page.present(html, "中文")

    assert "中性" not in out
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
              [("Market Analyst", "market.md", "# 市场")])]
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
