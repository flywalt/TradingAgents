"""Capital flows, index data, company identity and the Tushare snapshot.

These are data interfaces only: nothing here is wired into an agent yet, so the
tests pin the contracts a later agent task will consume — registration under a
new category, an index-code namespace that never guesses an exchange, and a
snapshot built from the same bars the price tools serve.
"""

from __future__ import annotations

import pandas as pd
import pytest

from tradingagents.dataflows import router
from tradingagents.dataflows.errors import NoMarketDataError
from tradingagents_cn import register as cn_register
from tradingagents_cn.identity import format_identity, resolve_identity
from tradingagents_cn.snapshot import build_market_snapshot
from tradingagents_cn.vendors.tushare import client, index
from tradingagents_cn.vendors.tushare.flows import (
    get_margin_detail,
    get_money_flow,
    get_northbound_holdings,
    get_top_list,
)

pytestmark = pytest.mark.unit

SYMBOL = "600519.SH"


def bars_frame(count: int = 60) -> pd.DataFrame:
    days = pd.date_range("2026-01-05", periods=count, freq="B")
    closes = list(range(100, 100 + count))
    return pd.DataFrame(
        {
            "ts_code": [SYMBOL] * count,
            "trade_date": [d.strftime("%Y%m%d") for d in days],
            "open": closes,
            "high": [c + 1 for c in closes],
            "low": [c - 1 for c in closes],
            "close": closes,
            "vol": [1000.0] * count,
            "amount": [1000.0] * count,
            "pct_chg": [0.5] * count,
        }
    )


class FakeApi:
    def __init__(self):
        self.calls: list[str] = []

    def pro_bar(self, **kwargs):
        self.calls.append("pro_bar")
        return bars_frame()

    def moneyflow(self, **kwargs):
        self.calls.append("moneyflow")
        return pd.DataFrame(
            {
                "ts_code": [SYMBOL, SYMBOL],
                "trade_date": ["20260929", "20260930"],
                "buy_elg_amount": [10.0, 20.0],
                "sell_elg_amount": [5.0, 25.0],
                "net_mf_amount": [5.0, -5.0],
            }
        )

    def hk_hold(self, **kwargs):
        self.calls.append("hk_hold")
        return pd.DataFrame(
            {
                "ts_code": [SYMBOL],
                "trade_date": ["20230815"],
                "vol": [1_000_000],
                "ratio": [0.8],
            }
        )

    def margin_detail(self, **kwargs):
        self.calls.append("margin_detail")
        return pd.DataFrame(
            {
                "ts_code": [SYMBOL],
                "trade_date": ["20260930"],
                "rzye": [1.0e9],
                "rqye": [1.0e7],
            }
        )

    def top_list(self, **kwargs):
        self.calls.append("top_list")
        return pd.DataFrame(
            {
                "trade_date": ["20260930"],
                "ts_code": [SYMBOL],
                "name": ["贵州茅台"],
                "pct_change": [3.5],
                "l_buy": [1.0e8],
            }
        )

    def index_daily(self, **kwargs):
        self.calls.append("index_daily")
        return pd.DataFrame(
            {
                "ts_code": ["000300.SH"],
                "trade_date": ["20260930"],
                "close": [4012.3],
                "open": [4000.0],
            }
        )

    def index_member_all(self, **kwargs):
        self.calls.append("index_member_all")
        return pd.DataFrame(
            {
                "index_code": ["000300.SH"],
                "con_code": ["600519.SH"],
                "con_name": ["贵州茅台"],
                "weight": [5.2],
            }
        )

    def stock_basic(self, **kwargs):
        self.calls.append("stock_basic")
        return pd.DataFrame(
            {
                "ts_code": [SYMBOL],
                "name": ["贵州茅台"],
                "area": ["贵州"],
                "industry": ["白酒"],
                "market": ["主板"],
                "list_date": ["20010827"],
            }
        )


@pytest.fixture(autouse=True)
def no_cache(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_CN_CACHE", "off")


@pytest.fixture
def api():
    fake = FakeApi()
    client.set_api(fake)
    try:
        yield fake
    finally:
        client.reset_api()


def test_register_category_creates_and_rolls_back(fake_impl):
    assert cn_register.register_category("cn_capital_flows", "cn flows") is True
    assert cn_register.register_category("cn_capital_flows", "cn flows") is False
    cn_register.register_vendor("get_money_flow", "tushare", fake_impl,
                                category="cn_capital_flows")
    assert router.get_category_for_method("get_money_flow") == "cn_capital_flows"

    cn_register.reset()

    assert "cn_capital_flows" not in router.TOOLS_CATEGORIES
    assert "get_money_flow" not in router.VENDOR_METHODS


def test_activation_registers_the_four_capital_flow_methods(api):
    report = cn_register.activate()

    for method in ("get_money_flow", "get_northbound_holdings",
                   "get_margin_detail", "get_top_list"):
        assert method in report.vendors_by_method, method
        assert router.get_category_for_method(method) == "cn_capital_flows"


def test_index_codes_need_an_explicit_exchange_suffix():
    assert index.normalize_index_code("000300.SH") == "000300.SH"
    assert index.normalize_index_code("399001.SZ") == "399001.SZ"
    assert index.normalize_index_code("000905.CSI") == "000905.CSI"

    with pytest.raises(ValueError):
        index.normalize_index_code("000300")          # would have to guess SSE vs SZSE
    with pytest.raises(ValueError):
        index.normalize_index_code("600519.SH")       # a stock code, not an index


def test_index_daily_and_members_render_rows(api):
    daily = index.get_index_daily("000300.SH", "2026-09-01", "2026-09-30")
    members = index.list_index_members("000300.SH")

    assert "000300.SH" in daily and "4012.30" in daily
    assert "600519.SH" in members and "贵州茅台" in members


def test_money_flow_and_margin_rows_are_rendered(api):
    flow = get_money_flow(SYMBOL, "2026-09-01", "2026-09-30")
    margin = get_margin_detail(SYMBOL, "2026-09-01", "2026-09-30")

    assert "net_mf_amount" in flow and "-5.00" in flow
    assert "rzye" in margin and "10.00" in margin     # 1e9 元 = 10 亿元


def test_top_list_renders_a_trade_date(api):
    text = get_top_list("2026-09-30")

    assert "20260930" in text or "2026-09-30" in text
    assert "贵州茅台" in text


def test_northbound_output_documents_the_disclosure_cutoff(api):
    text = get_northbound_holdings(SYMBOL, "2023-06-01", "2023-06-30")

    assert "2024-08-16" in text


def test_capital_flow_methods_decline_a_foreign_symbol(api):
    for call in (get_money_flow, get_northbound_holdings, get_margin_detail):
        with pytest.raises(NoMarketDataError):
            call("AAPL", "2026-09-01", "2026-09-30")
    assert api.calls == []


def test_identity_reads_stock_basic(api):
    identity = resolve_identity(SYMBOL)

    assert identity["name"] == "贵州茅台"
    assert identity["industry"] == "白酒"
    assert "600519.SH" in format_identity(identity)
    assert "贵州茅台" in format_identity(identity)


def test_the_snapshot_is_built_from_the_same_bars(api):
    text = build_market_snapshot(SYMBOL, "2026-03-30", look_back_days=20)

    assert text.startswith(f"# Verified market snapshot for {SYMBOL} as of 2026-03-30")
    assert "close" in text
    assert "rsi" in text
    assert "Vendor: tushare" in text
