# TUSHARE.md — A 股数据接入（行情 / 复权 / 交易日历）

第一阶段只接三样东西：**日线行情、复权、交易所交易日历**。
财报（CAS 口径）、资金面（北向/龙虎榜/融资融券）、公告新闻**不在本阶段**。

---

## 1. 前置条件

| 项目 | 要求 |
| --- | --- |
| Tushare 积分 | **≥ 2000**（`daily`/`pro_bar` 含复权、`trade_cal` 可用）；基础 120 积分无法取复权与多数财报 |
| Python 包 | `tushare`（**不写进 `pyproject.toml`**，见下方"为什么不改上游依赖"） |
| Token | `.env` 中的 `TUSHARE_TOKEN=...`（**不要**提交，`.gitignore` 已排除 `.env`） |

```bash
.venv/bin/python -m pip install -i https://pypi.org/simple tushare
printf '\nTUSHARE_TOKEN=你的token\n' >> .env
```

> 为什么不改上游依赖：`pyproject.toml` 是上游文件，加一行 `tushare` 就是一条需要长期 rebase 的补丁。
> 下游把 SDK 作为**可选依赖**处理：没装时抛 `VendorNotConfiguredError`，路由自动落到下一家 vendor。

---

## 2. 怎么用

```python
from tradingagents_cn.register import activate                 # 注册 vendor + 生成配置
from tradingagents_cn.vendors.tushare import load_calendar     # 真实交易日历
from tradingagents.graph import TradingAgentsGraph

report = activate()                       # 幂等；返回完整 config（含上游默认值）
load_calendar("2025-01-01", "2026-12-31") # 显式拉取并安装（网络调用，不放进 activate）

graph = TradingAgentsGraph(config=report.config)
final_state, rating = graph.propagate("600519.SH", "2026-10-30")
graph.save_reports(final_state, "600519.SH")
```

要点：

- `activate()` **不联网**，只注册与合并配置；日历要显式 `load_calendar()`。
- `load_calendar()` 的区间必须覆盖你将要跑的所有 `trade_date`；区间外的日期会退回"工作日=开市"的近似规则。
- 标的代码用规范形式 `600519.SH` / `000001.SZ` / `430047.BJ`；`600519.SS`、`sh600519` 也会被规范化。

---

## 3. 路由与回退

`activate()` 把 `data_vendors.core_stock_apis` 设为 `"tushare,yfinance"`：

```
get_stock_data(600519.SH) ─► tushare  ✅
get_stock_data(AAPL)      ─► tushare 抛 NoMarketDataError（非 A 股）─► yfinance ✅
tushare 限流/无权限        ─► VendorUnavailableError ─► yfinance ✅
两家都失败                ─► DATA_UNAVAILABLE 哨兵文本（模型收到"数据不可用"，不会编造价格）
```

- 非 A 股标的**不会**被 Tushare 接走，而是在适配器里用 `NoMarketDataError` 主动让位。
- 显式配置永远优先：`activate({"data_vendors": {"core_stock_apis": "yfinance"}})` 会保留你的选择。

---

## 4. 单位与口径（写进输出头部，供模型与人工核对）

| 项 | Tushare 原始 | 本层输出 |
| --- | --- | --- |
| 成交量 `vol` | 手（100 股） | **股** |
| 成交额 `amount` | 千元 | **元** |
| 价格 | 元 | 元，两位小数 |
| 复权 | `adj` 参数 | 由 `cn_adjust` 决定：`qfq` / `hfq` / `none` |
| 涨跌幅 | `pct_chg` | 百分比，原样 |

输出首行固定写明标的、区间与复权口径，例如：

```
# Stock data for 600519.SH from 2026-01-05 to 2026-01-09
# Vendor: tushare; adjustment: qfq; volume in shares; amount in CNY; prices in CNY
# Total records: 5
```

---

## 5. 交易日历

```python
from tradingagents_cn.calendar import default_calendar, is_approximate
from tradingagents_cn.trading_rules import settlement_date

default_calendar().is_trading_day("2026-10-01")   # False（国庆，周四）
settlement_date("2026-09-30")                     # 下一交易日（T+1）
is_approximate()                                  # False：已装真实日历
```

- 默认日历**只排除周末**，`is_approximate()` 返回 `True`，用于提醒"还没装真实日历"。
- `load_calendar()` 把区间内所有"工作日但交易所休市"的日期记为节假日，装入 `TradingCalendar`。

---

## 6. 已知限制（下一步要解决）

1. **技术指标仍来自 Yahoo**：`technical_indicators` 类别没有改路由，`get_indicators` 用 Yahoo 的 OHLCV 算指标，
   而 `get_stock_data` 用 Tushare 的价格 → **同一份报告里可能混用两种价格口径**。
   下一步应实现"基于 Tushare 日线本地计算指标"的 vendor，再把该类别纳入链。
2. **标的身份仍走 yfinance**：`TradingAgentsGraph.resolve_instrument_context()` 用 Yahoo 查公司名/行业，
   A 股覆盖不全时会退化为"只有代码"。下游可覆写该方法改用 Tushare `stock_basic`（未实现）。
3. **停牌 / 次新股**：区间内无成交会返回 `NO_DATA_AVAILABLE`（这是期望行为，不是 bug）。
4. **涨跌停 / T+1 / 整手规则已实现但未接入 agent**：当前只在 `trading_rules.py` 提供计算与校验，
   尚未注入 prompt 或做交易可行性过滤。
5. **复权口径切换**：`qfq` 序列会随新的除权事件变化，跨日期保存的指标不可直接比较；回测请固定一种口径并记录。
6. **积分限流**：适配器未做本地限流与缓存；大批量回测可能触发 Tushare 频率限制
   （表现为 `VendorUnavailableError` → 回落 Yahoo）。需要时再加"限流 + 磁盘缓存"。

---

## 7. 测试

```bash
# 离线单测（不需要 tushare、不需要 token、不联网）
.venv/bin/python -m pytest -q tests/downstream/test_tushare_vendor.py

# 真实联网冒烟（需要 TUSHARE_TOKEN 与已安装 tushare）
TUSHARE_TOKEN=... .venv/bin/python -m pytest -q -m integration tests/downstream/test_tushare_live.py
```

离线测试用 `client.set_api(FakeApi(...))` 注入假客户端，覆盖：非 A 股让位、空结果、限流异常、
复权参数传参、单位换算、排序、日期校验、日历安装与节假日判定。
