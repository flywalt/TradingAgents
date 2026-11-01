"""Token comparison and the path jail for artifacts."""

from __future__ import annotations

import pytest

from tradingagents_web import security

pytestmark = pytest.mark.unit


def test_tokens_must_match_exactly_and_never_when_unset():
    assert security.token_matches("abc", "abc") is True
    assert security.token_matches("abc", "abd") is False
    assert security.token_matches(None, "abc") is False
    assert security.token_matches("abc", None) is False


def test_paths_outside_the_run_directory_are_inside_the_jail(tmp_path):
    base = tmp_path / "run"
    base.mkdir()
    (base / "complete_report.md").write_text("ok")

    assert security.safe_run_file(base, "complete_report.md") is not None
    assert security.safe_run_file(base, "../secret.md") is None
    assert security.safe_run_file(base, "/etc/passwd") is None


def test_only_whitelisted_suffixes_are_served(tmp_path):
    base = tmp_path / "run"
    base.mkdir()
    (base / "evil.sh").write_text("echo")

    assert security.safe_run_file(base, "evil.sh") is None
    assert security.is_inside(base, base / "nested" / "x") is True
