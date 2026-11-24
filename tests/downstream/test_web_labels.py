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


def test_run_times_are_shown_in_the_box_timezone():
    """库里存 UTC，页面按 +08 显示（TZ=Asia/Shanghai）。

    曾经直接切片 ISO 字符串，于是 09:07 的分析显示成 01:07。
    """
    from tradingagents_web.app import local_clock

    assert local_clock("2026-11-24T01:07:47+00:00", "%m-%d %H:%M") == "11-24 09:07"
    assert local_clock("2026-11-24T01:07:47+00:00", "%H:%M:%S") == "09:07:47"
    # 坏数据不该炸页面
    assert local_clock("", "%H:%M") == ""
    assert local_clock("not-a-time", "%H:%M") == ""


def test_templates_do_not_slice_utc_strings():
    """时间显示只有一个入口（localtime 过滤器）：别再回到切 ISO 字符串。"""
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "tradingagents_web" / "templates"
    for name in ("index.html", "history.html", "run.html"):
        text = (root / name).read_text(encoding="utf-8")
        assert "created_at[5:16]" not in text, name
        assert "| localtime" in text, name
