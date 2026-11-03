"""Present the report page in the run's language, without touching the artifact.

The kernel writes ``complete_report.html`` in English: its headings, its run
details and its ``<html lang>`` are literals in ``tradingagents/report_html.py``,
which has no notion of a language. Rather than fork that renderer or patch it,
the web shell translates the handful of fixed labels on the way out. The file
on disk stays exactly what the kernel wrote, so a downstream consumer, an
archive, or a future upstream release all see the same artifact.

Everything below is a literal match on markup. Prose is never rewritten: a
sentence that happens to contain the word "Generated" survives untouched.
"""

from __future__ import annotations

import re
from html import escape

from .labels import RATING_LABELS, REPORT_SECTION_LABELS

#: The upstream markup this module depends on. If ``render_report`` is
#: restructured, ``test_the_markup_we_match_is_still_produced_upstream`` fails
#: at sync time instead of the page quietly reverting to English.
UPSTREAM_MARKERS = (
    '<html lang="en">',
    '<p class="date">Analysis of ',
    '<a class="to-top" href="#top">Top</a>',
    '<dt>Generated</dt>',
    '<dt>Deep model</dt>',
    '<dt>Quick model</dt>',
    '<dt>Analysts</dt>',
    '<dt>Debate rounds</dt>',
    '<dt>Data vendors</dt>',
    '<dt>Version</dt>',
    '<dt>Memory log</dt>',
    '<span class="ticker">',
    '<span class="rating ',
    'aria-label="Sections"',
    ': TradingAgents report</title>',
    '</head>',
    '</header>',
    '<h3 id="s',
    'Portfolio Manager</h3>',
    '--serif:',
    '--sans:',
)

_DETAIL_LABELS = {
    "Generated": "生成时间",
    "Deep model": "深度模型",
    "Quick model": "快速模型",
    "Analysts": "分析师",
    "Debate rounds": "辩论轮次",
    "Data vendors": "数据源",
    "Version": "版本",
    "Memory log": "历史记忆",
}

_NUMERALS = {"I": "一", "II": "二", "III": "三", "IV": "四", "V": "五"}

#: The kernel's node names repeat in the agent headings and the contents rail;
#: the words live in labels.py with everything else.
_AGENT_LABEL = re.compile(
    r'(<h3 id="s\d+-\d+">|<span class="label">)(Market Analyst|Sentiment Analyst|'
    r"News Analyst|Fundamentals Analyst|Memory Log|Bull Researcher|Bear Researcher|"
    r"Research Manager|Trader|Aggressive Analyst|Conservative Analyst|"
    r"Neutral Analyst|Portfolio Manager)(</h3>|</span>)")

#: The fixed labels the kernel writes into a report, taken from the source that
#: renders them (``agents/schemas.py`` and the prompts in ``agent/trader`` /
#: ``agent/managers/portfolio_manager``). Enumerated once from source rather than
#: grown by looking at outputs: the vocabulary is finite because the writers are.
#: ``test_the_schema_labels_cover_upstream`` fails when upstream adds one.
SCHEMA_LABELS = {
    "Action": "操作",
    "Entry Price": "买入价",
    "Executive Summary": "执行摘要",
    "Investment Thesis": "投资论点",
    "Position Sizing": "仓位",
    "Price Target": "目标价",
    "Rating": "评级",
    "Rating Scale": "评级刻度",
    "Rationale": "依据",
    "Reasoning": "推理",
    "Recommendation": "建议",
    "Stop Loss": "止损价",
    "Strategic Actions": "策略动作",
    "Time Horizon": "时间跨度",
}

#: `FINAL TRANSACTION PROPOSAL: **BUY**` is the one fixed phrase outside a bold
#: label; it sits in prose, so it is matched as that exact string.
FINAL_PROPOSAL = "FINAL TRANSACTION PROPOSAL:"
FINAL_PROPOSAL_ZH = "最终交易建议："

#: Enums, any casing, inside <strong> or right after the rating label.
_ENUMS = {
    "BUY": "买入", "SELL": "卖出", "HOLD": "持有",
    "OVERWEIGHT": "增持", "UNDERWEIGHT": "减持",
    "BULLISH": "看多", "BEARISH": "看空",
}
_STRONG_ENUM = re.compile(
    r"<strong>(BUY|SELL|HOLD|OVERWEIGHT|UNDERWEIGHT|BULLISH|BEARISH)</strong>", re.I)
_RATING_AFTER_LABEL = re.compile(
    r"(<strong>评级</strong>:\s*)(BUY|SELL|HOLD|OVERWEIGHT|UNDERWEIGHT)", re.I)
#: The rail shows the chapter name at rest (the full heading is too wide and the
#: upstream rail hides it entirely); hover still opens the agent sub-lists.
_NAV_SHORT = {
    "分析师团队报告": "分析",
    "研究团队结论": "研究",
    "交易团队方案": "交易",
    "风险管理团队结论": "风险",
    "组合经理决策": "决策",
    "下游运行元数据": "元数据",
}
_NAV_ENTRY = re.compile(
    r'<span class="num">([一二三四五六])</span>\s*'
    r'<span class="label">([^<]+)</span>')

_VENDOR_NAMES = {
    "Prices": "行情", "Indicators": "指标", "Fundamentals": "基本面",
    "News": "新闻", "Macro": "宏观", "Prediction markets": "预测市场",
}

_RATING_SPAN = re.compile(r'<span class="rating ([a-z]+)">([A-Za-z]+)</span>')

#: Upstream sets the report in Charter/Georgia at 17px/1.62 and never names a
#: CJK family, so Chinese body text falls to whatever the browser defaults to
#: and sits too tight. This override only names fallbacks and re-spaces the
#: line; colour, dark mode and print all keep using upstream's variables.
_CN_STYLE = """<style id="ta-cn">
:root {
  /* The CJK family leads so digits, Latin and Han all come from one design:
     with Charter first, a line mixes DejaVu Serif digits with Noto Han and
     the numbers read broken. Digits sit on tabular widths for the tables. */
  --serif: "Noto Serif CJK SC", "Source Han Serif SC", "Source Han Serif CN",
    "Songti SC", STSong, SimSun, Charter, "Bitstream Charter", Georgia, serif;
  --sans: "Noto Sans CJK SC", "PingFang SC", "Hiragino Sans GB",
    "Microsoft YaHei", system-ui, -apple-system, "Segoe UI", sans-serif;
}
body { font: 17px/1.85 var(--serif); font-variant-numeric: tabular-nums lining-nums; }
/* The kernel demotes an agent's own markdown headings three levels (# -> h4,
 * ## -> h5), so h4-h6 are the in-text section titles a reader navigates by.
 * Upstream styled them all at 0.95rem - smaller than the 17px paragraphs under
 * them, inverting the hierarchy. Monotonic scale, nothing below body size. */
main h2 { font: 700 1.5rem/1.3 var(--sans); letter-spacing: 0; }
main h3 { font: 650 1.19rem/1.35 var(--sans); }
main h4 { font: 650 1.13rem/1.4 var(--sans); }
main h5 { font: 700 1.06rem/1.45 var(--sans); }
main h6 { font: 600 1rem/1.4 var(--sans); color: var(--muted); }
.ta-summary { margin: 1.75rem 0 0; padding: 1.05rem 1.25rem; border: 1px solid var(--edge);
  border-left: 3px solid var(--accent); border-radius: 6px; background: var(--wash); }
.ta-summary h2 { margin: 0 0 0.6rem; font: 650 1.13rem/1.3 var(--sans); }
.ta-summary p { margin: 0 0 0.7rem; font-size: 0.95rem; }
/* The rail keeps a readable chapter name at rest instead of a numeral and a
 * bare rule; the agent list opens on hover or focus. Below 72rem there is no
 * room beside a 46rem column, so upstream's compact rail is left alone. */
@media (min-width: 72rem) {
  .contents { min-width: 7.5rem; }
  .contents > ul > li > a .label { max-width: none; opacity: 1; }
  .contents:not(:hover):not(:focus-within) ul ul { display: none; }
}
.ta-summary p:last-child { margin-bottom: 0; }
.ta-summary__more { font: 0.85rem/1.4 var(--sans); }
</style>"""


def _is_chinese(language: str | None) -> bool:
    if not language:
        return False
    head = language.strip().lower()
    return head.startswith("中文") or head.startswith("zh")


def _replacements() -> list[tuple[str, str]]:
    pairs = [('<html lang="en">', '<html lang="zh-CN">'),
             (": TradingAgents report</title>", " · TradingAgents 研究报告</title>"),
             (">Analysis of ", ">分析日期 "),
             ('<a class="to-top" href="#top">Top</a>',
              '<a class="to-top" href="#top">回到顶部</a>')]
    for numeral, heading in _numbered_sections():
        pairs.append((f"<h2>{numeral}. {heading}</h2>",
                      f"<h2>{_NUMERALS[numeral]}、{REPORT_SECTION_LABELS[heading]}</h2>"))
        pairs.append((f'<span class="label">{heading}</span>',
                      f'<span class="label">{REPORT_SECTION_LABELS[heading]}</span>'))
        pairs.append((f'<span class="num">{numeral}</span>',
                      f'<span class="num">{_NUMERALS[numeral]}</span>'))
    # The downstream metadata section carries no numeral of its own.
    pairs.append(("<h2>Downstream run metadata</h2>",
                  f"<h2>{REPORT_SECTION_LABELS['Downstream run metadata']}</h2>"))
    for english, chinese in _DETAIL_LABELS.items():
        pairs.append((f"<dt>{english}</dt>", f"<dt>{chinese}</dt>"))
    return pairs


def _numbered_sections() -> list[tuple[str, str]]:
    """The five upstream sections, in the order they appear."""
    return [("I", "Analyst Team Reports"), ("II", "Research Team Decision"),
            ("III", "Trading Team Plan"), ("IV", "Risk Management Team Decision"),
            ("V", "Portfolio Manager Decision")]


def _localise_rating(match: re.Match) -> str:
    tone, english = match.group(1), match.group(2)
    chinese = RATING_LABELS.get(english)
    if chinese is None:
        return match.group(0)
    return f'<span class="rating {tone}" title="{english}">{chinese}</span>'


def _localise_agent_name(match: re.Match) -> str:
    from .labels import NODE_LABELS

    return f"{match.group(1)}{NODE_LABELS[match.group(2)]}{match.group(3)}"


def _localise_rating_after_label(match: re.Match) -> str:
    enum = match.group(2)
    chinese = _ENUMS[enum.upper()]
    return f"{match.group(1)}{chinese}（{enum.upper()}）"


def _localise_enum(match: re.Match) -> str:
    word = match.group(1)
    chinese = _ENUMS[word.upper()]
    return f"<strong>{chinese}（{word.upper()}）</strong>"


def _shorten_nav(match: re.Match) -> str:
    numeral, label = match.group(1), match.group(2)
    short = _NAV_SHORT.get(label)
    if not short:
        return match.group(0)
    return f'<span class="num">{numeral}</span> <span class="label">{short}</span>'


def _localise_glossary(html: str) -> str:
    html = _AGENT_LABEL.sub(_localise_agent_name, html)
    for english, chinese in SCHEMA_LABELS.items():
        html = html.replace(f"<strong>{english}</strong>", f"<strong>{chinese}</strong>")
    html = html.replace(FINAL_PROPOSAL, FINAL_PROPOSAL_ZH)
    html = _STRONG_ENUM.sub(_localise_enum, html)
    html = _RATING_AFTER_LABEL.sub(_localise_rating_after_label, html)
    for english, chinese in _VENDOR_NAMES.items():
        html = html.replace(f'<span class="name">{english}</span>',
                            f'<span class="name">{chinese}</span>')
    return html


_PM_HEADING = re.compile(r'<h3 id="(s\d+)-1">Portfolio Manager</h3>')
_PARAGRAPH = re.compile(r"<p>.*?</p>", re.S)
_TAG = re.compile(r"<[^>]+>")


def _summary_card(html: str) -> str:
    """The portfolio manager's decision, lifted to the top of the page.

    Upstream orders the report as an argument — analysts, research, trading,
    risk, and only then the decision — which suits an audit and buries the one
    paragraph a reader wants first. The card copies the first paragraphs of the
    last section; the section itself is left exactly as the kernel wrote it.
    """
    found = _PM_HEADING.search(html)
    if not found:
        return ""
    section = html.rfind("<section", 0, found.start())
    identifier = re.compile(r'id="(s\d+)"').search(html, section, found.start())
    end = html.find("</section>", found.end())
    body = html[found.end(): end if end != -1 else len(html)]
    paragraphs = _PARAGRAPH.findall(body)[:2]
    if paragraphs:
        excerpt = "\n".join(paragraphs)
    else:
        text = _TAG.sub("", body).strip()[:500]
        excerpt = f"<p>{escape(text)}</p>" if text else ""
    if not excerpt:
        return ""
    anchor = identifier.group(1) if identifier else found.group(1)
    return (f'<section class="ta-summary" aria-labelledby="ta-summary-title">\n'
            f'<h2 id="ta-summary-title">核心结论</h2>\n{excerpt}\n'
            f'<p class="ta-summary__more"><a href="#{anchor}">阅读完整结论</a></p>\n'
            f"</section>")


_TICKER_SPAN = re.compile(r'<span class="ticker">([^<]+)</span>')


def _lead_with_name(html: str, name: str) -> str:
    """The company leads where there is room; the code always follows it."""
    found = _TICKER_SPAN.search(html)
    if not found:
        return html
    ticker = found.group(1)

    def replace(match: re.Match) -> str:
        return f'<span class="ticker">{name} · {match.group(1)}</span>'

    html = _TICKER_SPAN.sub(replace, html, count=1)
    return html.replace(f"<title>{ticker} ", f"<title>{name} {ticker} ", 1)


def present(html: str, language: str | None, name: str | None = None) -> str:
    """Return the page as the run's language asked for it."""
    if not _is_chinese(language):
        return _lead_with_name(html, name) if name else html
    for old, new in _replacements():
        html = html.replace(old, new)
    html = _RATING_SPAN.sub(_localise_rating, html)
    if name:
        html = _lead_with_name(html, name)
    # Lift the decision before the glossary runs, so the card's excerpt is
    # translated by the same pass as the page around it.
    if 'class="ta-summary"' not in html:
        card = _summary_card(html)
        if card:
            html = html.replace("</header>", "</header>\n" + card, 1)
    html = _localise_glossary(html)
    html = _NAV_ENTRY.sub(_shorten_nav, html)
    if '<style id="ta-cn">' not in html:
        html = html.replace("</head>", _CN_STYLE + "\n</head>", 1)
    return html
