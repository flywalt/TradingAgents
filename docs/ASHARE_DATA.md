# ASHARE_DATA.md — A 股数据层能力与规则

> 基线：TradingAgents v0.7.1 + 下游 `tradingagents_cn`（2026-11-01）。
> 上游文件 0 修改；所有能力通过 `tradingagents_cn.register.activate()` 注入。

## 1. 能力矩阵

| 上游 router 方法 | A 股来源 | 状态 | 单位 |
| --- | --- | --- | --- |
| `get_stock_data` | Tushare `daily` / `pro_bar` | ✅ | 股 / 元 |
| `get_indicators` | Tushare 日线 **本地计算**（stockstats，13 个指标） | ✅ | 价格单位 |
| `get_fundamentals` | `stock_basic` + `daily_basic` + `fina_indicator` | ✅ | 亿元 / % |
| `get_income_statement` | `income`（CAS，合并报表） | ✅ | 亿元，YTD |
| `get_balance_sheet` | `balancesheet` | ✅ | 亿元，期末 |
| `get_cashflow` | `cashflow` | ✅ | 亿元，YTD |
| `get_money_flow`（新） | `moneyflow` | ✅ 仅接口 | 万元 |
| `get_northbound_holdings`（新） | `hk_hold` | ✅ 仅接口（逐日披露止于 2024-08-16） | 股 / % |
| `get_margin_detail`（新） | `margin_detail` | ✅ 仅接口 | 亿元 |
| `get_top_list`（新） | `top_list` | ✅ 仅接口 | 元 |
| `get_index_daily`（新） | `index_daily` | ✅ 仅接口 | 指数点 |
| `list_index_members`（API） | `index_member_all` | ✅ 仅接口 | % |
| `resolve_identity`（API） | `stock_basic` | ✅ 仅接口 | — |
| `build_market_snapshot`（API） | 日线 + 本地指标 | ✅ 仅接口 | 股 / 元 |
| 新闻 / 公告 | — | ❌ 无权限（AkShare 专题） | — |
| 涨跌停名单 | — | ❌ 无权限（本地 `trading_rules` 可算限价） | — |

"仅接口" = 已注册/可调用、有单测，但**没有接进 agent**。

## 2. 三条硬规则

1. **前视禁止**：报表只保留 `ann_date ≤ trade_date`（缺失回退 `f_ann_date`，都缺则丢弃）；
   估值取当日或之前最近交易日；同期多次公告取最新的那份。
2. **单位显式**：金额统一亿元（2 位小数，半进位），行情股/元，EPS 元/股；
   每个输出的头部写明来源、口径、单位。
3. **错误分层**：非 A 股 → `NoMarketDataError`（让位给下一家 vendor）；
   无 token/无权限 → `VendorNotConfiguredError`；网络/限流 → `VendorUnavailableError`。

## 3. 路由与严格模式

```text
默认： data_vendors = {"core_stock_apis": "tushare,yfinance",
                       "technical_indicators": "tushare,yfinance",
                       "fundamental_data": "tushare,yfinance"}
严格： cn_strict_ashare=True  -> 上述三类都变成 "tushare"（宁缺毋滥，不混口径）
```

- 非 A 股标的在适配器里抛 `NoMarketDataError`，链自动落到 Yahoo；
- 显式 `data_vendors` 配置永远优先于模式；
- 环境变量 `TRADINGAGENTS_CN_STRICT_ASHARE=1` 可整站开启严格模式。

## 4. 缓存与限流

| 项 | 行为 |
| --- | --- |
| 缓存层级 | 进程内 dict + 磁盘 `<data_cache_dir>/cn-tushare/*.pkl`（原子写） |
| TTL | 行情/资金面 1h；财报/概况/指数 24h |
| 关闭 | `TRADINGAGENTS_CN_CACHE=off` |
| 键 | 接口 + 标的 + 日期区间 + 复权口径（缺一即视为不同数据） |
| 限流 | `TRADINGAGENTS_CN_MIN_INTERVAL`（默认 0.15s，2000 积分档安全值） |

## 5. 用法

```python
from tradingagents_cn.register import activate
from tradingagents_cn.vendors.tushare import load_calendar
from tradingagents.graph import TradingAgentsGraph

config = activate().config                  # 注册 vendor + 合并配置（不联网）
load_calendar("2025-01-01", "2026-12-31")   # 真实交易日历（联网）

graph = TradingAgentsGraph(config=config)
state, rating = graph.propagate("600519.SH", "2026-10-30")
```

只取数据、不跑 agent：

```python
from tradingagents_cn.vendors.tushare.stock import get_stock_data
from tradingagents_cn.vendors.tushare.indicators import get_stock_stats_indicators_window
from tradingagents_cn.vendors.tushare.statements import get_income_statement
from tradingagents_cn.vendors.tushare.fundamentals import get_fundamentals

print(get_stock_data("600519.SH", "2026-09-01", "2026-09-30"))
print(get_stock_stats_indicators_window("600519.SH", "rsi", "2026-09-30", 10))
print(get_income_statement("600519.SH", "quarterly", "2026-09-30"))
print(get_fundamentals("600519.SH", "2026-09-30"))
```

## 6. 测试

```bash
.venv/bin/python -m pytest -q tests/downstream            # 离线：187 个
.venv/bin/python -m pytest -q -m integration tests/downstream/test_tushare_live.py   # 真实：9 个
```

## 7. 真实冒烟（2026-11-01，2000+ 积分账号）

| 检查 | 结果 |
| --- | --- |
| 集成测试 | **9 passed**（6.09s） |
| 指标一致性 | `close_50_sma` 服务值与直接对同一份 bar 求均值一致 |
| 前视 | 2026-09-30 的利润表不含 `| 2026-09-30 |` 列（三季报 10 月才公告），含 `| 2026-06-30 |` |
| 概况 | 名称「贵州茅台」、行业「白酒」、市值行存在 |
| 资金面 | `moneyflow` / `margin_detail` 均有数据 |
| 指数 | `000300.SH` 日线 + 成分表可渲染 |
| 身份 | `resolve_identity("600519.SH")["name"] == "贵州茅台"` |
| 快照 | 头部 `Vendor: tushare`，含 `rsi` 指标行 |

## 8. 限制（下一步）

1. **`get_verified_market_snapshot` 工具仍走 Yahoo**：`build_market_snapshot` 已备好，替换工具属于 agent 层改动。
2. **公司身份未接入图**：`resolve_identity` 可用，但上游仍用 Yahoo 解析；覆写 `resolve_instrument_context` 属于 agent 层。
3. **news / sentiment 两个分析师在 A 股空转**：无新闻权限、无股吧源，归"新闻与情绪专题"。
4. **资金面/指数未接 agent**：已注册但无 tool、无分析师使用。
5. **金融股（银行/保险/券商）字段**：使用通用字段集，部分字段为空；行业级字段映射未做。
6. **北交所**：无 Yahoo 备源；北交所日历本账号不可用，沿用 SSE。
7. **YTD 语义**：利润表/现金流量表是本年累计，跨季不能直接相减；表头已标注。
8. **限流/缓存是进程内 + 磁盘**，多进程并发回测仍可能撞配额。
