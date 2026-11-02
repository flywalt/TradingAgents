"""The Chinese words the web shell shows.

One table per kind of label, so a node renamed in the kernel fails one test
instead of quietly falling back to English on a page nobody re-reads.
"""

from __future__ import annotations

#: Kernel rating enum → the word the UI shows (see spec §9: never an instruction).
RATING_LABELS = {
    "Buy": "乐观",
    "Overweight": "偏乐观",
    "Hold": "中性",
    "Underweight": "偏审慎",
    "Sell": "审慎",
    "REVIEW": "需人工复核",
}

#: Kernel node name → the word the timeline and the graph show.
NODE_LABELS = {
    "Market Analyst": "市场分析师",
    "Sentiment Analyst": "情绪分析师",
    "News Analyst": "新闻分析师",
    "Fundamentals Analyst": "基本面分析师",
    "Memory Log": "记忆检索",
    "Bull Researcher": "多头研究员",
    "Bear Researcher": "空头研究员",
    "Research Manager": "研究经理",
    "Trader": "交易员",
    "Aggressive Analyst": "激进风险分析师",
    "Conservative Analyst": "保守风险分析师",
    "Neutral Analyst": "中性风险分析师",
    "Portfolio Manager": "组合经理",
}

#: The analyst keys a run submits, and the kernel nodes they become.
ANALYST_NODES = {
    "market": "Market Analyst",
    "social": "Sentiment Analyst",
    "news": "News Analyst",
    "fundamentals": "Fundamentals Analyst",
}

#: Upstream report section names → Chinese. The last entry is ours: the
#: downstream metadata section appended to every run's report.
REPORT_SECTION_LABELS = {
    "Analyst Team Reports": "分析师团队报告",
    "Research Team Decision": "研究团队结论",
    "Trading Team Plan": "交易团队方案",
    "Risk Management Team Decision": "风险管理团队结论",
    "Portfolio Manager Decision": "组合经理决策",
    "Downstream run metadata": "下游运行元数据",
}
