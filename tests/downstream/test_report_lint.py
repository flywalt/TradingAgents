"""The report lint: deterministic checks a reader would make first."""

from __future__ import annotations

import pytest

from scripts.report_lint import lint

pytestmark = pytest.mark.unit


def _report(tmp_path, **files):
    report = tmp_path / "report"
    (report / "1_analysts").mkdir(parents=True)
    for name, text in files.items():
        (report / "1_analysts" / f"{name}.md").write_text(text, encoding="utf-8")
    return report


def test_a_clean_report_flags_nothing(tmp_path):
    report = _report(tmp_path, market="收盘 1392.05（前复权，2026-10-30）")

    assert lint(report) == []


def test_a_bold_label_left_in_english_is_flagged(tmp_path):
    report = _report(tmp_path,
                     market="**Price Target**: 1400（前复权）\n**Rationale**: x")

    findings = lint(report)
    assert any("bold label still in English" in finding for _s, finding, _c in findings)


def test_intraday_colour_from_daily_bars_is_flagged(tmp_path):
    report = _report(tmp_path, market="盘中冲高至 1400 后回落（前复权）")

    assert any("intraday path" in finding for _s, finding, _c in lint(report))


def test_an_empty_source_labelled_unavailable_is_flagged(tmp_path):
    report = _report(tmp_path, news="UNAVAILABLE — returned no items（前复权）")

    assert any("empty source labelled UNAVAILABLE" in finding
               for _s, finding, _c in lint(report))


def test_a_missing_price_basis_is_flagged(tmp_path):
    report = _report(tmp_path, market="收盘 1392.05，较前一日 +1.2%")

    assert any("复权" in finding for _s, finding, _c in lint(report))
