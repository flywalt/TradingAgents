"""Provenance: nine fields, on every saved run, in all three artefacts.

The point is comparability — two reports can only be compared if you can tell
which upstream commit, indicator flavour and formula version produced each.
"""

from __future__ import annotations

import json
from datetime import date

import pandas as pd
import pytest

from tradingagents.graph import trading_graph as upstream_graph
from tradingagents_cn import config as cn_config
from tradingagents_cn.bootstrap import reset
from tradingagents_cn.graph.factory import build_graph
from tradingagents_cn.runmeta import FINANCIAL_FORMULA_VERSION, MARKET_RULES_VERSION, collect
from tradingagents_cn.vendors.tushare import client

pytestmark = pytest.mark.unit

REQUIRED = {
    "upstream_commit", "downstream_commit", "worktree_dirty", "extension_version",
    "data_provider", "provider_revision", "financial_formula_version",
    "market_rules_version", "data_as_of", "data_retrieved_at", "dataset_snapshot_id",
}


class DummyClient:
    def get_llm(self):
        return None


class FakeApi:
    def stock_basic(self, **kwargs):
        return pd.DataFrame([{
            "ts_code": "600519.SH", "name": "贵州茅台", "area": "贵州", "industry": "白酒",
            "market": "主板", "list_date": "20010827", "delist_date": "", "list_status": "L",
        }])


@pytest.fixture
def graph(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_CN_CACHE", "off")
    monkeypatch.setattr(upstream_graph, "create_tier_client", lambda config, tier, **k: DummyClient())
    client.set_api(FakeApi())
    cfg = cn_config.apply({
        "results_dir": str(tmp_path / "results"),
        "data_cache_dir": str(tmp_path / "cache"),
        "memory_log_path": str(tmp_path / "memory.md"),
        "llm_provider": "openai",
    })
    try:
        yield build_graph(config=cfg)
    finally:
        client.reset_api()
        reset()


def test_collect_returns_every_required_field():
    metadata = collect({"cn_extension_version": "1.2.3",
                        "data_vendors": {"core_stock_apis": "tushare,yfinance"}},
                       "2026-09-30")

    assert set(metadata) == REQUIRED
    assert metadata["extension_version"] == "1.2.3"
    assert metadata["data_as_of"] == "2026-09-30"
    assert metadata["data_provider"] == "tushare,yfinance"
    assert metadata["financial_formula_version"] == FINANCIAL_FORMULA_VERSION
    assert metadata["market_rules_version"] == MARKET_RULES_VERSION
    assert metadata["dataset_snapshot_id"] == metadata["dataset_snapshot_id"]  # deterministic
    assert all(str(value).strip() for value in metadata.values())


def test_saving_a_report_records_the_metadata_everywhere(graph, tmp_path):
    state = {
        "trade_date": "2026-09-30",
        "final_trade_decision": "**Rating**: Hold",
        "market_report": "prices",
    }

    path = graph.save_reports(state, "600519.SH")

    payload = json.loads((path.parent / "run_metadata.json").read_text(encoding="utf-8"))
    assert set(payload) == REQUIRED
    assert payload["data_as_of"] == "2026-09-30"
    assert payload["extension_version"] == graph.config["cn_extension_version"]

    # the report carries analysis only; provenance lives beside it
    markdown = path.read_text(encoding="utf-8")
    assert "Downstream run metadata" not in markdown
    assert payload["upstream_commit"] not in markdown

    page = (path.parent / "complete_report.html").read_text(encoding="utf-8")
    assert "downstream-run-metadata" not in page


def test_saving_twice_leaves_the_report_and_the_record_alone(graph):
    state = {"trade_date": date.today().isoformat(), "final_trade_decision": "**Rating**: Hold"}

    first = graph.save_reports(state, "600519.SH")
    graph.save_reports(state, "600519.SH", save_path=first.parent)

    assert first.read_text(encoding="utf-8").count("Downstream run metadata") == 0
    assert (first.parent / "run_metadata.json").is_file()
