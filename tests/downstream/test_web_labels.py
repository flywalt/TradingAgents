"""One source for the Chinese words the web shell shows."""

from __future__ import annotations

import pytest

from tradingagents_web import labels
from tradingagents_web.runner import NODE_NAMES

pytestmark = pytest.mark.unit


def test_every_kernel_node_has_a_chinese_label():
    assert set(labels.NODE_LABELS) == set(NODE_NAMES)
    assert all(label.strip() for label in labels.NODE_LABELS.values())


def test_every_analyst_key_maps_to_a_kernel_node():
    assert set(labels.ANALYST_NODES.values()) <= set(NODE_NAMES)
    assert set(labels.ANALYST_NODES) == {"market", "social", "news", "fundamentals"}


def test_rating_labels_cover_the_kernel_enums():
    assert labels.RATING_LABELS == {
        "Buy": "买入", "Overweight": "增持", "Hold": "持有",
        "Underweight": "减持", "Sell": "卖出", "REVIEW": "需人工复核",
    }


def test_the_report_sections_have_chinese_names():
    assert labels.REPORT_SECTION_LABELS["Analyst Team Reports"] == "分析师团队报告"
    assert labels.REPORT_SECTION_LABELS["Downstream run metadata"] == "下游运行元数据"
    assert len(labels.REPORT_SECTION_LABELS) == 6
