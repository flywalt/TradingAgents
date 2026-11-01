# MARKET_PROFILES.md — 多市场 Profile（设计 + 骨架）

> 本项目是 **多市场 TradingAgents Downstream**，不是 A 股专用 Fork。
> 本阶段只做架构、配置隔离与测试；不新增中国市场 Agent、不改 Prompt。

## 1. 两个 Profile

| 维度 | `UPSTREAM_DEFAULT` | `CN_A_SHARE` |
| --- | --- | --- |
| 市场识别 | 非 A 股交易所/代码 | `.SS/.SZ/.BJ/.SH`、6 位纯数字 |
| Graph 类 | 上游 `TradingAgentsGraph`（原样） | `CnTradingAgentsGraph`（子类） |
| 身份解析 | Yahoo（上游原逻辑） | Tushare `stock_basic` + `namechange`（PIT） |
| Vendor 默认 | 不覆盖，沿用上游 `DEFAULT_CONFIG` | `tushare,yfinance`（三类）+ `get_insider_transactions` |
| 严格策略 | **禁止**（`cn_strict_ashare` 会报错） | 允许，7 个受管工具 + insider 锁 Tushare |
| 指标口径 | `stockstats`（维基口径，与上游一致） | `tdx`（通达信） |
| 交易规则 | **不注入**（无 T+1/涨跌停/整手） | 注入上下文（涨跌停/T+1/整手/ST 不可假设） |
| 输出语言 | English | 中文（`output_language` 可覆盖） |
| 币种 | USD | CNY |
| 存储 | 上游默认路径 | `…/profile-cn` 子目录 + `memory-cn.md` |

数据类（`tradingagents_cn/market.py::MarketProfile`）包含：
`key / market / graph / identity / vendors / tool_vendors / strict_allowed /
indicator_flavor / injects_ashare_rules / selected_analysts / optional_analysts /
currency / reporting_language / dir_suffix`。

`optional_analysts` 目前为空——Policy / Announcement / Shareholder Activity
三个 A 股专属角色**尚未实现**，字段先留位，避免以后改数据结构。

## 2. 市场识别（不猜）

优先级：显式 `profile` > 显式 `market` > 标的标识推断。

| 输入 | 结果 |
| --- | --- |
| `600519.SS`、`000001.SZ`、`430047.BJ`、`600519` | `CN_A_SHARE` |
| `0700.HK` | `UPSTREAM_DEFAULT`（**港股不是 A 股**，即使发行人是中国公司） |
| `BABA`、`AAPL` | `UPSTREAM_DEFAULT` |
| `0700`（4~5 位纯数字） | **报错**：可能是港股也可能是美股 OTC，要求 `market=` |
| `market="US"` + `600519.SS` | **报错**：显式市场与标识矛盾 |

**绝不**按发行人国籍、公司名或语言判断市场。

## 3. Graph Factory 分流

```python
build_graph(config=None, *, market=None, symbol=None, profile=None, ...)
    profile = select_profile(market=..., symbol=..., profile=... or config["cn_market_profile"])
    bootstrap()
    settings = cn_config.apply(config, profile=profile)   # profile 决定 vendor/口径/目录
    graph_cls = CnTradingAgentsGraph if profile.graph == "cn" else TradingAgentsGraph
```

- `UPSTREAM_DEFAULT` 走**上游类**，不经过 A 股身份、规则、指标口径；
- `CN_A_SHARE` 走子类（仅覆写身份解析 + 约束注入）；
- 工厂是**唯一**允许选择上游类的代码（AST 扫描保证没有别处直连）；
- CLI 增加 `--market`，Batch 按标的逐个选 profile。

## 4. 隔离

| 资源 | 隔离方式 |
| --- | --- |
| config | 每个 Graph 一份 `cn_config.apply()` 副本；`cn_market_profile` 进入配置 |
| 运行上下文 | `run_config()` ContextVar（上游已有） |
| results/cache/memory | CN profile 默认追加 `profile-cn`；显式路径由调用方负责 |
| checkpoint | 跟随 `data_cache_dir`，同时受 `cn_extension_version` 等版本键约束 |
| 凭证 | 仍在 `.env`；不同 profile 用不同变量（`TUSHARE_TOKEN` vs 上游 LLM key） |
| provider 日志 | 按 profile 目录落盘（待 B4 实现，当前为进程日志） |

**并发**：不同 Graph 并行已实测（`test_concurrency.py` / `test_market_profiles.py`）；
同一 Graph 并发 checkpoint 仍不支持。

## 5. 目录调整方案

```text
tradingagents_cn/
├── market.py                 # MarketProfile + 识别规则（本阶段新增）
├── config.py                 # profile 感知的配置合并
├── graph/
│   ├── factory.py            # profile 分流（唯一选择上游类的地方）
│   └── trading_graph.py      # CN 子类（仅 CN profile 使用）
├── vendors/tushare/          # CN providers
├── cli.py / batch.py         # 入口，接受 --market
└── profiles/                 # 预留：市场变多时按市场拆配置文件，现在不建空洞
```

不新建第二仓库、不复制官方源码。

## 6. 多市场测试计划（对照审计 10 项）

| # | 审计要求 | 现状 |
| --- | --- | --- |
| 1 | AAPL + UPSTREAM_DEFAULT | ✅ `test_market_profiles.py::test_a_us_ticker_selects_the_upstream_profile` |
| 2 | 600519.SS + CN_A_SHARE | ✅ `test_a_cn_suffix_selects_the_cn_profile` |
| 3 | 0700.HK + UPSTREAM_DEFAULT | ✅ `test_a_hk_listing_…`（含无 T+1 断言） |
| 4 | BABA + UPSTREAM_DEFAULT | ✅ `test_a_us_adr_…` |
| 5 | 市场配置错误拒绝 | ✅ 歧义 `0700`、冲突 `US + .SS`、未知市场 |
| 6 | Vendor 严格隔离 | ✅ 严格模式在默认 profile 报错；CN profile 锁 Tushare |
| 7 | Prompt 与市场规则隔离 | ✅ CN 类在默认 profile 下不注入规则；HK 上下文无 T+1 |
| 8 | Checkpoint 与缓存隔离 | ⚠️ 部分：默认目录按 profile 分离已测；checkpoint 行为测试已有，跨 profile 端到端待 B4 |
| 9 | 双 Profile 并发 | ✅ `test_the_two_profiles_resolve_side_by_side`（线程并发） |
| 10 | 海外 Profile 对照上游回归 | ⚠️ 结构级：类、vendor 默认、指标口径一致已测；输出级对照需脚本化模型全图回归（B3 评测骨架里做） |

## 7. 已知边界

1. `UPSTREAM_DEFAULT` 只是"不走 CN 定制"，不代表我们实现了港股/美股专属规则（无 T+1、无涨跌停概念，与上游一致）。
2. `optional_analysts` 为空：A 股专属 Agent 未实现，本阶段不新增。
3. Prompt 本地化未做：CN profile 的语言只通过 `output_language` 生效。
4. 数据源严格策略只覆盖 CN；海外沿用上游路由与回退语义。
5. provider 日志分目录、凭证分 profile 的**自动化**未做，当前靠 `.env` 与显式路径。
