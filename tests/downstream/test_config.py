"""Downstream config: pure merges, ordered vendor chains, loud env parsing."""

from __future__ import annotations

import copy

import pytest

from tradingagents_cn import config as cn_config

pytestmark = pytest.mark.unit


def test_defaults_add_cn_keys_and_an_ordered_chain():
    merged = cn_config.build_config()
    assert merged["cn_market"] == "ashare"
    assert merged["cn_adjust"] == "qfq"
    assert merged["cn_include_bj"] is True
    assert merged["cn_calendar_holidays"] == ()
    assert merged["data_vendors"]["core_stock_apis"] == "tushare,yfinance"


def test_build_config_never_mutates_its_input():
    base = {"data_vendors": {"core_stock_apis": "yfinance"}, "cn_adjust": "hfq"}
    before = copy.deepcopy(base)

    merged = cn_config.build_config(base)

    assert base == before
    assert merged is not base
    # An explicit choice wins over the installed chain...
    assert merged["data_vendors"]["core_stock_apis"] == "yfinance"
    assert merged["cn_adjust"] == "hfq"


def test_override_installs_the_chain_over_base_values():
    base = {"data_vendors": {"core_stock_apis": "yfinance"}}
    merged = cn_config.build_config(base, override_vendor_chain=True)
    assert merged["data_vendors"]["core_stock_apis"] == "tushare,yfinance"


def test_vendor_chain_only_touches_categories_downstream_serves():
    category_chain = cn_config.vendor_chain()
    assert list(category_chain) == ["core_stock_apis"]


def test_env_overrides_beat_defaults_and_base():
    merged = cn_config.build_config(
        {"cn_adjust": "hfq"},
        environ={"TRADINGAGENTS_CN_ADJUST": "none", "TRADINGAGENTS_CN_INCLUDE_BJ": "false"},
    )
    assert merged["cn_adjust"] == "none"
    assert merged["cn_include_bj"] is False


def test_blank_env_values_are_ignored():
    merged = cn_config.build_config(environ={"TRADINGAGENTS_CN_ADJUST": ""})
    assert merged["cn_adjust"] == "qfq"


@pytest.mark.parametrize(
    "environ",
    [
        {"TRADINGAGENTS_CN_INCLUDE_BJ": "maybe"},
        {"TRADINGAGENTS_CN_ADJUST": "forward"},
    ],
)
def test_invalid_settings_fail_at_startup(environ):
    with pytest.raises(ValueError):
        cn_config.build_config(environ=environ)


def test_apply_returns_a_complete_config_for_the_graph():
    merged = cn_config.apply()
    for key in ("results_dir", "data_cache_dir", "llm_provider", "max_debate_rounds",
                "data_vendors", "tool_vendors"):
        assert key in merged, key
    assert merged["cn_market"] == "ashare"


def test_apply_lets_the_caller_override_anything():
    merged = cn_config.apply({"cn_adjust": "hfq", "data_vendors": {"core_stock_apis": "yfinance"}})
    assert merged["cn_adjust"] == "hfq"
    assert merged["data_vendors"]["core_stock_apis"] == "yfinance"
    # A partial data_vendors override keeps the other categories.
    assert merged["data_vendors"]["news_data"] == "yfinance"


def test_apply_can_skip_the_vendor_chain():
    merged = cn_config.apply(install_vendor_chain=False)
    assert merged["data_vendors"]["core_stock_apis"] == "yfinance"
