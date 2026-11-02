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
    '<span class="rating ',
    'aria-label="Sections"',
    ': TradingAgents report</title>',
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

_RATING_SPAN = re.compile(r'<span class="rating ([a-z]+)">([A-Za-z]+)</span>')


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


def present(html: str, language: str | None) -> str:
    """Return the page as the run's language asked for it."""
    if not _is_chinese(language):
        return html
    for old, new in _replacements():
        html = html.replace(old, new)
    return _RATING_SPAN.sub(_localise_rating, html)
