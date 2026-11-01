# A 股数据层（第二阶段）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 market analyst 与 fundamentals analyst 在 A 股上拿到同源、无前视、单位正确的数据（指标/三表/概况），并把资金面、指数做成纯数据接口，最后把环境迁到 uv。

**Architecture:** 所有新能力都在 `tradingagents_cn/` 内，通过 `register_vendor()` 注入上游 router；纯逻辑（单位、前视、缓存）抽成顶层小模块，Tushare 适配器只做"取数 → 规格化 → 渲染文本"。上游文件 0 修改。

**Tech Stack:** Python 3.13、pandas、stockstats（上游已有依赖）、tushare（可选）、pytest（离线 + `-m integration`）、uv（环境管理）。

**Spec:** `docs/superpowers/specs/2026-11-01-ashare-data-layer-design.md`

## Global Constraints

- 上游文件（`tradingagents/**`、`cli/**`、`tests/**`、`pyproject.toml` 等）**零修改**；新增代码只在 `tradingagents_cn/` 与 `tests/downstream/`。
- 单位：金额 元→**亿元（2 位小数）**；行情 `vol` 手→股、`amount` 千元→元；输出头部必须写明来源/口径/单位。
- 前视：财报仅保留 `ann_date ≤ trade_date`（缺失回退 `f_ann_date`，两者都缺则丢弃）；报表只取 `report_type == "1"`（合并报表）。
- 报表期间语义：利润表/现金流量表为 **YTD 累计**，原样输出，表头标注"本年累计"，不自行去累计。
- 错误类型：非 A 股 → `NoMarketDataError`；无 token/无权限 → `VendorNotConfiguredError`；网络/限流 → `VendorUnavailableError`；空结果 → `NoMarketDataError`。
- 默认链 `tushare,yfinance`；`cn_strict_ashare=True` 时改为单 vendor 链。
- 单测不联网、不需 token、不写用户缓存目录（用 `tmp_path` 或 `conftest` 的临时目录）。
- 每个任务：先写失败测试 → 实现 → 测试通过 → `ruff check` 通过 → 提交（提交信息带 `Refs: D-00xx` 与测试结果）。

## Review Focus

1. **公告日格式异常/缺失**（`"20250101"`、`""`、`None`）：不能被当成"已公告"，否则前视泄漏；缺失即丢弃。
2. **单位边界**：负值、None、NaN、万亿级数值，不能渲染出 `nan 亿元` 或科学计数法。
3. **指标窗口不足**（新股上市不足 200 交易日）：`close_200_sma` 等应为空，而不是 0 或抛异常。
4. **指数代码误用**（`000300` 无交易所后缀）：明确报错，不猜交易所（`000001` 同时是平安银行与上证指数）。
5. **缓存键碰撞**：不同复权口径、不同日期范围、不同接口必须落在不同键上。

---

### Task 1: 单位与前视纯函数

**Files:**
- Create: `tradingagents_cn/units.py`
- Create: `tradingagents_cn/pit.py`
- Test: `tests/downstream/test_units.py`, `tests/downstream/test_pit.py`

**Interfaces:**
- Produces: `to_yi(value, places=2) -> str`（元→亿元字符串，空值返回 `""`）、`lots_to_shares(value) -> int`、`thousand_yuan_to_yuan(value) -> int`；
  `announced_by(frame, as_of: str) -> DataFrame`、`latest_reports(frame, periods=4, report_type="1") -> DataFrame`

- [ ] **Step 1: Write the failing tests**

```python
# tests/downstream/test_units.py
def test_yi_scales_yuan_to_hundred_millions():
    assert to_yi(1_234_567_890) == "12.35"        # 12.34567890 亿 -> 2dp half-up
    assert to_yi(-1_000_000_000) == "-10.00"
    assert to_yi(None) == "" and to_yi(float("nan")) == ""
    assert to_yi(0) == "0.00"

def test_lot_and_thousand_conversions_round_to_integers():
    assert lots_to_shares(59927.29) == 5_992_729
    assert thousand_yuan_to_yuan(8257381.778) == 8_257_381_778
    assert lots_to_shares(None) == 0

# tests/downstream/test_pit.py
def test_rows_announced_after_the_trade_date_are_dropped():
    frame = pd.DataFrame({"end_date": ["20260630", "20260930"],
                          "ann_date": ["20260825", "20261028"]})
    kept = announced_by(frame, "20260930")
    assert list(kept["end_date"]) == ["20260630"]

def test_missing_or_malformed_announcement_dates_are_dropped_not_trusted():
    frame = pd.DataFrame({"end_date": ["20260101", "20260102", "20260103"],
                          "ann_date": ["", None, "2026-08-25"]})
    assert len(announced_by(frame, "20261231")) == 0   # 都不合法 -> 丢弃

def test_latest_reports_filters_consolidated_and_keeps_newest_announcement():
    frame = pd.DataFrame({"end_date": ["20260630", "20260630", "20260331"],
                          "ann_date": ["20260825", "20261020", "20260425"],
                          "report_type": ["1", "1", "1"],
                          "revenue": [1, 2, 3]})
    out = latest_reports(frame, periods=4)
    assert list(out["revenue"]) == [2, 3]              # 同期取最新公告，按 end_date 升序
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest -q tests/downstream/test_units.py tests/downstream/test_pit.py`
Expected: FAIL（`ModuleNotFoundError: tradingagents_cn.units`）

- [ ] **Step 3: Implement**

`units.py`：`Decimal(str(value))` 走 `ROUND_HALF_UP`；`None`/NaN/不可解析 → `""`（`to_yi`）或 `0`（整数换算）。
`pit.py`：把 `ann_date`/`f_ann_date` 归一成 8 位字符串（接受 `2026-08-25` 与 `20260825`）；两者都不可解析的行丢弃；
`latest_reports` 先按 `report_type` 过滤，`sort_values(["end_date","ann_date"])` 去重取每组最后一行，再按 `end_date` 取最近 `periods` 期并升序返回。

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest -q tests/downstream/test_units.py tests/downstream/test_pit.py` → PASS

- [ ] **Step 5: Commit**

```bash
git add tradingagents_cn/units.py tradingagents_cn/pit.py tests/downstream/test_units.py tests/downstream/test_pit.py
git commit -m "feat(data): add unit conversions and point-in-time report filtering"
```

---

### Task 2: 缓存与限流

**Files:**
- Create: `tradingagents_cn/cache.py`
- Modify: `tradingagents_cn/vendors/tushare/client.py`（新增节流）
- Test: `tests/downstream/test_cache.py`

**Interfaces:**
- Produces: `cached(namespace: str, key: str, ttl_seconds: int, producer: Callable[[], T]) -> T`、`clear(namespace: str | None = None) -> None`、`enabled() -> bool`、`reset_memory_cache() -> None`（测试用的进程内缓存清零）；
  `client.min_interval() -> float`（读 `TRADINGAGENTS_CN_MIN_INTERVAL`，默认 0.15，非法值抛 `ValueError`）；`client.throttle()` 在每次真实调用前 sleep 到间隔。
- Consumes: `tradingagents.dataflows.config.get_config()["data_cache_dir"]`

- [ ] **Step 1: Write the failing tests**

```python
def test_a_second_call_is_served_from_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_DATA_CACHE_DIR", str(tmp_path))
    calls = []
    def producer():
        calls.append(1); return {"rows": 1}
    assert cached("probe", "k", 60, producer) == {"rows": 1}
    assert cached("probe", "k", 60, producer) == {"rows": 1}
    assert len(calls) == 1

def test_ttl_expiry_refetches(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_DATA_CACHE_DIR", str(tmp_path))
    calls = []
    def producer():
        calls.append(1); return "v"
    cached("probe", "k", 60, producer)
    cached("probe", "k", 60, producer)
    assert len(calls) == 1
    # 把磁盘条目 mtime 拨回 2 小时前，再关掉进程内缓存重新读
    for path in tmp_path.rglob("*.pkl"):
        os.utime(path, (time.time() - 7200, time.time() - 7200))
    _reset_memory_cache()
    cached("probe", "k", 60, producer)
    assert len(calls) == 2

def test_cache_can_be_switched_off(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_CN_CACHE", "off")
    ... assert len(calls) == 2

def test_different_keys_never_share_an_entry(tmp_path, monkeypatch):
    # 同一 namespace，key 含 qfq / hfq 与不同日期 -> 三次 producer 调用
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest -q tests/downstream/test_cache.py` → FAIL（无 `tradingagents_cn.cache`）

- [ ] **Step 3: Implement**

`cache.py`：磁盘路径 `Path(get_config()["data_cache_dir"])/"cn-tushare"/f"{namespace}-{sha256(key)[:16]}.pkl"`；写盘用临时文件 + `os.replace` 原子替换；读盘失败（损坏/版本不符）当未命中；进程内 `dict` 作为一级缓存。
`client.py`：模块级 `_last_call`，`throttle()` 计算 `min_interval() - elapsed` 并 `time.sleep`（<0 则不睡）；`TushareApi.pro_bar/trade_cal` 调用前执行 `throttle()`。

- [ ] **Step 4: Run tests to verify they pass** → PASS

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(data): add ttl cache and call throttling for tushare"
```

---

### Task 3: 技术指标（本地计算）

**Files:**
- Create: `tradingagents_cn/vendors/tushare/indicators.py`
- Modify: `tradingagents_cn/vendors/tushare/stock.py`（抽出 `fetch_bars()` 供指标复用）
- Modify: `tradingagents_cn/vendors/tushare/__init__.py`（`VENDOR_METHODS` 增加 `get_indicators`）
- Test: `tests/downstream/test_indicators.py`

**Interfaces:**
- Consumes: `fetch_bars(symbol, start_date, end_date) -> DataFrame`（列：`trade_date, open, high, low, close, vol, amount`，按日期升序，`trade_date` 为 `YYYY-MM-DD` 字符串）
- Produces: `SUPPORTED_INDICATORS: tuple[str, ...]`（13 个，含 `mfi`）、`get_stock_stats_indicators_window(symbol, indicator, as_of_date, look_back_days) -> str`

- [ ] **Step 1: Write the failing tests**

```python
def test_indicator_matches_a_hand_computed_sma(fake_api):
    # 6 根合成日线，close = 1..6；look_back_days 覆盖 3 天 -> 最后一天 3 日均值 = 5.0
    text = get_stock_stats_indicators_window("600519.SH", "close_50_sma", "2026-01-06", 3)
    assert "close_50_sma" in text
    assert text.rstrip().splitlines()[-1].split(",")[-1] == "nan" or "5.00" in text

def test_all_thirteen_upstream_names_are_accepted():
    assert len(SUPPORTED_INDICATORS) == 13 and "mfi" in SUPPORTED_INDICATORS

def test_unknown_indicator_is_rejected_with_the_supported_names():
    with pytest.raises(ValueError, match="rsi"):
        get_stock_stats_indicators_window("600519.SH", "rsi_14", "2026-01-06", 30)

def test_a_short_history_yields_empty_values_not_zeros(fake_api):
    # 只有 20 根 bar 时 close_200_sma 全为空，不能出现 0
    ...

def test_non_a_share_symbol_is_declined_before_any_call(fake_api):
    with pytest.raises(NoMarketDataError):
        get_stock_stats_indicators_window("AAPL", "rsi", "2026-01-06", 30)
    assert fake_api.calls == []
```

- [ ] **Step 2: Run to verify failure** → FAIL

- [ ] **Step 3: Implement**

`fetch_bars` 复用现有 `get_stock_data` 的取数/复权/错误映射，返回规范化 DataFrame；`get_stock_data` 改为渲染 `fetch_bars` 的结果（输出格式不变，既有测试必须继续通过）。
指标用 `stockstats.wrap(df)` 计算，列名按上游 13 个名字映射（`boll` → `boll`、`macds` → `macds` 等）；对 `look_back_days` 窗口尾部的缺失值保留为空字符串。
输出头两行：`# Indicators for <canonical> as of <as_of_date> (last N sessions)`、`# Vendor: tushare; adjustment: <cfg>; computation: local stockstats over tushare bars`；表头 `Date,<indicator>`。

- [ ] **Step 4: Run tests** → 新增测试 PASS 且 `tests/downstream/test_tushare_vendor.py` 仍 PASS

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(indicators): compute the upstream indicator set from tushare bars"
```

---

### Task 4: 公司概况与估值

**Files:**
- Create: `tradingagents_cn/vendors/tushare/fundamentals.py`
- Modify: `tradingagents_cn/vendors/tushare/__init__.py`（注册 `get_fundamentals`）
- Test: `tests/downstream/test_fundamentals.py`

**Interfaces:**
- Produces: `get_fundamentals(ticker: str, curr_date: str) -> str`
- Consumes: `client.get_api()`（`stock_basic`、`daily_basic`、`fina_indicator`）、`pit.announced_by`、`units.to_yi`

- [ ] **Step 1: Write the failing tests**

```python
def test_valuation_is_taken_from_the_latest_session_not_after(fake_api):
    # daily_basic 返回 2026-09-29 与 2026-09-30 两行；curr_date=2026-09-30 取 09-30
    text = get_fundamentals("600519.SH", "2026-09-30")
    assert "2026-09-30" in text and "PE" in text

def test_profile_names_the_company_and_industry(fake_api):
    assert "贵州茅台" in text and "白酒" in text and "贵州" in text

def test_financial_summary_ignores_a_report_announced_later(fake_api):
    # fina_indicator 含 ann_date=2026-10-28 的一期；curr_date=2026-09-30 时不得出现该期 EPS
    assert "2026-10-28" not in text

def test_missing_valuation_fields_render_as_empty_not_zero(fake_api):
    # daily_basic 返回 NaN 的 pe/pb -> 输出中为空，不出现 "0.00"
```

- [ ] **Step 2: Run to verify failure** → FAIL

- [ ] **Step 3: Implement**

三段式文本：`# Fundamentals for <code> (<name>) as of <date>` / 概况（名称/行业/地区/市场/上市日）/ 估值（交易日 + PE/PB/PS/总市值(亿)/流通市值(亿)/换手率/量比）/ 财务摘要（最近一期，前视过滤后：EPS/ROE/毛利率/净利率/资产负债率）。
数值缺失 → 空字符串；市值走 `to_yi`。

- [ ] **Step 4: Run tests** → PASS

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(fundamentals): add a-share profile, valuation and financial summary"
```

---

### Task 5: 三表（CAS，防前视）

**Files:**
- Create: `tradingagents_cn/vendors/tushare/statements.py`
- Modify: `tradingagents_cn/vendors/tushare/__init__.py`（注册 `get_income_statement`、`get_balance_sheet`、`get_cashflow`）
- Test: `tests/downstream/test_statements.py`

**Interfaces:**
- Produces: `get_income_statement(ticker, freq="quarterly", curr_date=None) -> str`、`get_balance_sheet(...)`、`get_cashflow(...)`；
  字段表常量 `INCOME_FIELDS / BALANCE_FIELDS / CASHFLOW_FIELDS`（`((中文标签, tushare字段), ...)`，各 12~16 项）
- Consumes: `pit.latest_reports`、`units.to_yi`

- [ ] **Step 1: Write the failing tests**

```python
def test_a_report_announced_after_the_trade_date_is_excluded(fake_api):
    text = get_income_statement("600519.SH", "quarterly", "2026-09-30")
    assert "2026-09-30" not in text          # 三季报 10 月才公告
    assert "2026-06-30" in text

def test_annual_and_quarterly_select_different_periods(fake_api):
    assert "2025-12-31" in get_income_statement("600519.SH", "annual", "2026-09-30")

def test_amounts_are_scaled_to_hundred_millions_with_a_stated_unit(fake_api):
    text = get_income_statement("600519.SH", "quarterly", "2026-09-30")
    assert "单位：亿元" in text
    assert "营业收入" in text and "12.35" in text     # revenue 1_234_567_890 元

def test_duplicate_periods_keep_the_latest_announcement(fake_api):
    # 2026-06-30 两行（ann_date 08-25 与 10-20）；curr_date=2026-12-31 时只显示后者
    text = get_income_statement("600519.SH", "quarterly", "2026-12-31")
    assert text.count("2026-06-30") == 1
    assert "修订后" in text or "2.00" in text   # 取最新公告那份数值

def test_ytd_is_labelled_and_not_de_cumulated(fake_api):
    assert "本年累计" in text

def test_unknown_frequency_is_rejected(fake_api):
    with pytest.raises(ValueError, match="quarterly"):
        get_income_statement("600519.SH", "monthly", "2026-09-30")

def test_all_three_statements_miss_data_identically(fake_api):
    # 空 frame -> NoMarketDataError（三个入口一致）
```

- [ ] **Step 2: Run to verify failure** → FAIL

- [ ] **Step 3: Implement**

共用 `_render(statement_name, frame, freq, curr_date, fields, label)`：`latest_reports(frame, periods=4)` → 前视过滤 → 逐期渲染一列（金额 `to_yi`）；表头 `# <名称> for <code> (亿元, 本年累计 / 期末余额)`，并列出期数与口径；`freq` 仅接受 `annual`/`quarterly`，其余 `ValueError` 列出合法值。
字段选择：`INCOME_FIELDS` 含 `total_revenue/revenue/oper_cost/operate_profit/total_profit/n_income/n_income_attr_p/basic_eps` 等；`BALANCE_FIELDS` 含 `total_assets/total_liab/total_hldr_eqy_exc_min_int/money_cap/accounts_receiv/inventories/fixed_assets`；`CASHFLOW_FIELDS` 含 `n_cashflow_act/n_cashflow_inv_act/n_cash_flows_fnc_act/c_fr_sale_sg/c_paid_goods_s`。

- [ ] **Step 4: Run tests** → PASS

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(statements): serve cas statements with announcement-date filtering"
```

---

### Task 6: 资金面、指数、公司身份（仅接口）

**Files:**
- Modify: `tradingagents_cn/register.py`（`register_category`）
- Create: `tradingagents_cn/vendors/tushare/flows.py`, `index.py`, `tradingagents_cn/identity.py`
- Modify: `tradingagents_cn/vendors/tushare/__init__.py`
- Test: `tests/downstream/test_flows_index_identity.py`

**Interfaces:**
- Produces: `register_category(name: str, description: str) -> bool`；
  `get_money_flow(symbol, start_date, end_date)`、`get_northbound_holdings(symbol, start_date, end_date)`、`get_margin_detail(symbol, start_date, end_date)`、`get_top_list(trade_date)`（注册到新类别 `cn_capital_flows`）；
  `normalize_index_code(code) -> str`（必须带 `.SH/.SZ/.CSI`）、`get_index_daily(index_code, start_date, end_date)`、`list_index_members(index_code)`；
  `resolve_identity(symbol) -> dict`、`format_identity(identity: dict) -> str`；
  `build_market_snapshot(symbol, as_of_date, look_back_days=30) -> str`（Tushare 版"验证快照"，供 agent 层后续替换用，本阶段不接线）

- [ ] **Step 1: Write the failing tests**

```python
def test_register_category_creates_and_rolls_back(fake_impl):
    register_category("cn_capital_flows", "cn flows")
    register_vendor("get_money_flow", "tushare", fake_impl, category="cn_capital_flows")
    assert router.get_category_for_method("get_money_flow") == "cn_capital_flows"
    reset()
    assert "cn_capital_flows" not in router.TOOLS_CATEGORIES

def test_capital_flow_methods_are_registered_after_activation():
    report = activate()
    for method in ("get_money_flow", "get_northbound_holdings", "get_margin_detail", "get_top_list"):
        assert ("tushare" , ) and method in report.vendors_by_method

def test_index_codes_require_an_explicit_exchange_suffix():
    assert normalize_index_code("000300.SH") == "000300.SH"
    with pytest.raises(ValueError): normalize_index_code("000300")     # 不猜交易所
    with pytest.raises(ValueError): normalize_index_code("600519.SH")  # 股票代码不是指数

def test_index_daily_and_members_render_rows(fake_api): ...
def test_identity_reads_stock_basic(fake_api):
    identity = resolve_identity("600519.SH")
    assert identity["name"] == "贵州茅台" and identity["industry"] == "白酒"
    assert "600519.SH" in format_identity(identity)
def test_northbound_cutoff_is_documented_in_the_output(fake_api):
    assert "2024-08-16" in get_northbound_holdings("600519.SH", "2023-06-01", "2023-06-30")
```

- [ ] **Step 2: Run to verify failure** → FAIL

- [ ] **Step 3: Implement**

`register_category` 写入 `router.TOOLS_CATEGORIES`（幂等），`reset()` 记录并删除新建类别。
`flows.py` 每个入口：`require_ashare` → 取数（`moneyflow`/`hk_hold`/`margin_detail`/`top_list`）→ 前视无关（历史流水）→ 渲染 CSV 风格表格；`hk_hold` 输出头写明 "per-stock northbound disclosure ended 2024-08-16"。
`index.py`：`normalize_index_code` 用 `^\d{6}\.(SH|SZ|CSI)$`；`get_index_daily` 调 `index_daily`；`list_index_members` 调 `index_member_all(index_code=...)`。
`identity.py`：`stock_basic` → dict（`ts_code,name,industry,area,market,list_date`），失败抛上游类型错误。

- [ ] **Step 4: Run tests** → PASS

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(data): add cn capital flows, index and identity interfaces"
```

---

### Task 7: 配置链与严格模式

**Files:**
- Modify: `tradingagents_cn/config.py`
- Test: `tests/downstream/test_config.py`（追加用例）

**Interfaces:**
- Produces: `DEFAULT_CN_CONFIG["cn_strict_ashare"] = False`；`vendor_chain(strict=False)`；`build_config(..., override_vendor_chain=True)` 时严格模式装单链

- [ ] **Step 1: Write the failing tests**

```python
def test_strict_mode_installs_single_vendor_chains():
    merged = cn_config.apply({"cn_strict_ashare": True})
    assert merged["data_vendors"]["core_stock_apis"] == "tushare"
    assert merged["data_vendors"]["technical_indicators"] == "tushare"
    assert merged["data_vendors"]["fundamental_data"] == "tushare"

def test_default_mode_keeps_the_fallback_chain():
    merged = cn_config.apply()
    assert merged["data_vendors"]["technical_indicators"] == "tushare,yfinance"

def test_strict_mode_can_come_from_the_environment():
    merged = cn_config.apply(environ={"TRADINGAGENTS_CN_STRICT_ASHARE": "1"})
    assert merged["cn_strict_ashare"] is True
```

- [ ] **Step 2: Run to verify failure** → FAIL

- [ ] **Step 3: Implement**

`cn_strict_ashare` 加入 `DEFAULT_CN_CONFIG` 与 `_ENV_OVERRIDES`（布尔强转，非法值 `ValueError`）；`vendor_chain(strict)` 在 strict 时对 `core_stock_apis/technical_indicators/fundamental_data` 返回单 vendor 元组；`build_config` 先读合并后的 `cn_strict_ashare` 再选链（env 覆盖优先）。

- [ ] **Step 4: Run tests** → PASS 且既有 config 测试仍 PASS

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(config): add strict a-share vendor mode"
```

---

### Task 8: 真实数据冒烟 + 文档

**Files:**
- Modify: `tests/downstream/test_tushare_live.py`（每个新接口一条）
- Create: `docs/ASHARE_DATA.md`（能力矩阵、单位/前视/缓存规则、限制）
- Modify: `docs/UPSTREAM_DELTA.md`（台账追加行）

- [ ] **Step 1: 写集成用例**（`-m integration`，token 缺失即 `skip`）

```python
def test_live_indicator_matches_a_direct_computation(): ...
def test_live_statements_exclude_reports_announced_after_the_date(): ...
def test_live_fundamentals_has_profile_and_valuation(): ...
def test_live_money_flow_and_margin_are_available(): ...
def test_live_index_members_and_daily_are_available(): ...
def test_live_identity_reads_the_company_name(): ...
```

- [ ] **Step 2: 跑集成测试**

Run: `.venv/bin/python -m pytest -q -m integration tests/downstream/test_tushare_live.py`
Expected: 全部 PASS（不 PASS 就修实现，不放宽断言）

- [ ] **Step 3: 写 `docs/ASHARE_DATA.md`**（能力表 + 规则 + 6 条限制 + 冒烟数字）并更新台账

- [ ] **Step 4: 全量回归**

Run: `.venv/bin/python -m pytest -q && .venv/bin/python -m ruff check .`
Expected: 全部通过，测试数 ≥ 1538 + 本轮新增

- [ ] **Step 5: Commit**

```bash
git commit -m "test(data): cover the live a-share endpoints and document the data layer"
```

---

### Task 9: uv 迁移

**Files:**
- Create: `requirements-downstream.txt`、`requirements-lock.txt`、`docs/DEV_ENV.md`

- [ ] **Step 1: 记录当前环境基线**

```bash
.venv/bin/python -m pip freeze > /tmp/opencode/pip-freeze-before.txt
.venv/bin/python -m pytest -q | tail -2   # 记录数字
```

- [ ] **Step 2: 安装 uv 并备份旧环境**

```bash
.venv/bin/python -m pip install -i https://pypi.org/simple uv
mv .venv .venv-pip-backup
```

- [ ] **Step 3: 建 uv 环境并用旧版本做约束**

```bash
~/.local/bin/uv venv .venv --python 3.13
~/.local/bin/uv pip install -e ".[dev]" -c /tmp/opencode/pip-freeze-before.txt
~/.local/bin/uv pip install -r requirements-downstream.txt
```

- [ ] **Step 4: 验证；失败即回滚**

```bash
~/.local/bin/uv run pytest -q            # 必须与 Step 1 同样的测试数、全绿
~/.local/bin/uv run ruff check .
~/.local/bin/uv run pytest -q -m integration tests/downstream/test_tushare_live.py
# 任一失败：rm -rf .venv && mv .venv-pip-backup .venv，并停下汇报
```

- [ ] **Step 5: 生成锁文件与文档**

```bash
~/.local/bin/uv pip freeze > requirements-lock.txt
```

`docs/DEV_ENV.md` 写：uv 安装、`uv pip install -r` 与 `-e .` 的日常用法、锁文件更新（改依赖 → 重装 → 重新 freeze）、
回滚步骤（`.venv-pip-backup`）、以及"为什么不动上游 pyproject"。

- [ ] **Step 6: 提交**

```bash
git add requirements-downstream.txt requirements-lock.txt docs/DEV_ENV.md
git commit -m "chore(env): manage the virtualenv with uv and pin a downstream lockfile"
```

---

## 交付判定

1. `tests/downstream/` 覆盖：单位、前视、缓存、指标、概况、三表、资金面、指数、身份、严格模式。
2. 默认套件全绿且数量增加；`-m integration` 全绿（真实账号）。
3. `ruff check .` 全绿；上游文件 `git diff --stat upstream/main -- tradingagents cli tests pyproject.toml` 为空。
4. `docs/ASHARE_DATA.md`、`docs/DEV_ENV.md` 存在且含冒烟数字。
5. 台账 `docs/UPSTREAM_DELTA.md` 每条提交都有 `D-xxxx` 行。
