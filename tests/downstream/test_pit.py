"""Point-in-time rules for A-share reports.

A quarterly report is public knowledge only from its announcement date. A report
announced after the run date must be invisible to the analysis, and a row whose
announcement date cannot be read must be dropped rather than trusted: serving it
would be lookahead, which is the one error a backtest can never recover from.
"""

from __future__ import annotations

import pandas as pd
import pytest

from tradingagents_cn.pit import announced_by, latest_reports

pytestmark = pytest.mark.unit


def test_rows_announced_after_the_trade_date_are_dropped():
    frame = pd.DataFrame(
        {"end_date": ["20260630", "20260930"], "ann_date": ["20260825", "20261028"]}
    )

    kept = announced_by(frame, "20260930")

    assert list(kept["end_date"]) == ["20260630"]


def test_missing_or_malformed_announcement_dates_are_dropped_not_trusted():
    frame = pd.DataFrame(
        {
            "end_date": ["20260101", "20260102", "20260103"],
            "ann_date": ["", None, "2026-08-25"],
        }
    )

    kept = announced_by(frame, "20261231")

    # Only the readable announcement survives; blank/None are dropped, not treated as "already out".
    assert list(kept["end_date"]) == ["20260103"]


def test_a_dashed_date_in_the_frame_is_accepted():
    frame = pd.DataFrame({"end_date": ["20260630"], "ann_date": ["2026-08-25"]})

    assert len(announced_by(frame, "20260930")) == 1


def test_the_filing_date_is_used_when_the_announcement_date_is_missing():
    frame = pd.DataFrame(
        {"end_date": ["20260630"], "ann_date": [None], "f_ann_date": ["20260825"]}
    )

    assert len(announced_by(frame, "20260930")) == 1
    assert len(announced_by(frame, "20260824")) == 0


def test_latest_reports_keeps_only_consolidated_statements():
    frame = pd.DataFrame(
        {
            "end_date": ["20260630", "20260630"],
            "ann_date": ["20260825", "20260825"],
            "report_type": ["1", "6"],
            "revenue": [1, 99],
        }
    )

    assert list(latest_reports(frame)["revenue"]) == [1]


def test_latest_reports_keeps_the_newest_announcement_of_a_period_oldest_first():
    frame = pd.DataFrame(
        {
            "end_date": ["20260630", "20260630", "20260331"],
            "ann_date": ["20260825", "20261020", "20260425"],
            "report_type": ["1", "1", "1"],
            "revenue": [1, 2, 3],
        }
    )

    out = latest_reports(frame, periods=4)

    # Same period -> the later announcement wins; display runs oldest -> newest.
    assert list(out["revenue"]) == [3, 2]


def test_latest_reports_limits_the_number_of_periods():
    frame = pd.DataFrame(
        {
            "end_date": ["20250630", "20250930", "20251231", "20260331", "20260630"],
            "ann_date": ["20250825", "20251028", "20260328", "20260425", "20260825"],
            "report_type": ["1"] * 5,
            "revenue": [1, 2, 3, 4, 5],
        }
    )

    assert list(latest_reports(frame, periods=2)["revenue"]) == [4, 5]


def test_a_refiling_that_only_carries_the_filing_date_wins():
    """The f_ann_date fallback must also drive dedupe, not only visibility."""
    frame = pd.DataFrame(
        {
            "end_date": ["20260630", "20260630"],
            "ann_date": ["20260825", None],
            "f_ann_date": ["20260825", "20261020"],
            "revenue": [1, 2],
        }
    )

    visible = announced_by(frame, "20261231")
    out = latest_reports(visible, periods=1)

    assert list(out["revenue"]) == [2]
