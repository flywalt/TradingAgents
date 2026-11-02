# EXTENSIONS.md — 本地扩展清单（可审计）

> 本文件由 `scripts/extension_inventory.py` 校验：新增模块、测试、配置键、环境变量、上游补丁
> 若未在此登记，`--check` 会失败。**测试 `tests/downstream/test_audit_inventory.py` 强制该检查。**
>
> 基线：上游 `TauricResearch/TradingAgents` v0.7.1（`c454491`）。当前下游版本见 `tradingagents_cn/_version.py`。

## 1. 一句话总览

在**不修改上游分析框架**的前提下，新增了一个独立数据层（Tushare）、A 股身份/规则、多市场 Profile、
运行元数据与同步治理。上游改动仅 3 个文件、2 个 `upstream-patch:` 提交；其余全部为新增文件。

## 2. 模块清单（全部为新增文件）

### 2.1 基础设施

| 文件 | 职责 |
| --- | --- |
| `tradingagents_cn/__init__.py` | 包入口，导出 `bootstrap`/`register_vendor` 等 |
| `tradingagents_cn/_version.py` | 下游版本单一来源（进入运行配置与 checkpoint 身份） |
| `tradingagents_cn/bootstrap.py` | **唯一**写上游注册表的地方：签名/重复/覆盖校验、幂等、`ensure_bootstrapped()` |
| `tradingagents_cn/register.py` | 兼容 shim（无逻辑），旧导入路径 |
| `tradingagents_cn/config.py` | `cn_*` 配置、vendor 链、严格模式、Profile 感知、目录隔离 |
| `tradingagents_cn/market.py` | `MarketProfile` + `UPSTREAM_DEFAULT` / `CN_A_SHARE` + 市场识别 |
| `tradingagents_cn/cache.py` | 有界内存 + 磁盘 TTL 缓存、原子写、过期清理 |
| `tradingagents_cn/runmeta.py` | 11 项运行元数据 + 渲染到 md/json/html + 脏工作区检测 |
| `tradingagents_cn/pit.py` | 公告日前视过滤、同期去重（报表） |
| `tradingagents_cn/units.py` | 元→亿元、手→股、千元→元 |
| `tradingagents_cn/symbols.py` | A 股代码规范化（`.SH/.SZ/.BJ`、Yahoo/Tushare 映射） |
| `tradingagents_cn/calendar.py` | 交易日历（周末 + 可注入节假日） |
| `tradingagents_cn/trading_rules.py` | 涨跌停、整手、T+1、除权参考价 |
| `tradingagents_cn/identity.py` | 公司身份 + `namechange` PIT 名称 + 上市/退市校验 |
| `tradingagents_cn/snapshot.py` | Tushare 版"验证快照"（与行情同源） |
| `tradingagents_cn/cli.py` | 下游 CLI（`analyze`/`batch`，支持 `--market`/`--strict`） |
| `tradingagents_cn/batch.py` | 批量执行（每任务一图，失败隔离） |

### 2.2 Graph

| 文件 | 职责 |
| --- | --- |
| `tradingagents_cn/graph/__init__.py` | 导出 |
| `tradingagents_cn/graph/factory.py` | **唯一**按 Profile 选 graph 类的入口；脏工作区 checkpoint 守卫 |
| `tradingagents_cn/graph/trading_graph.py` | `CnTradingAgentsGraph`：身份解析 + A 股规则注入 + 元数据 |

### 2.3 Web 外壳（`tradingagents_web/`，B4 W1）

| 文件 | 职责 |
| --- | --- |
| `tradingagents_web/__init__.py` | 包说明 |
| `tradingagents_web/__main__.py` | `python -m tradingagents_web`，uvicorn 单 worker |
| `tradingagents_web/app.py` | FastAPI 路由、鉴权、页面、SSE、报告/文件服务 |
| `tradingagents_web/db.py` | SQLite schema（runs/events）、WAL、迁移 |
| `tradingagents_web/jobs.py` | 任务 CRUD、状态迁移、事件序号、崩溃恢复、队位 |
| `tradingagents_web/worker.py` | 单线程队列（1 运行 + 3 排队） |
| `tradingagents_web/runner.py` | 任务执行序列、节点回调映射、job.json、失败分类 |
| `tradingagents_web/errors.py` | 异常 → category/message/action |
| `tradingagents_web/security.py` | 读写 token、CORS、路径白名单 |

### 2.4 数据源

| 文件 | 职责 |
| --- | --- |
| `tradingagents_cn/vendors/__init__.py` | 包说明 |
| `tradingagents_cn/vendors/common.py` | 适配器公共层：`require_ashare`/`require_token`/`adjustment` |
| `tradingagents_cn/vendors/tushare/__init__.py` | Provider 注册表（`PROVIDERS`） |
| `tradingagents_cn/vendors/tushare/client.py` | 惰性鉴权、可注入客户端、限流、端点封装 |
| `tradingagents_cn/vendors/tushare/stock.py` | 日线 + 复权 + `fetch_bars` |
| `tradingagents_cn/vendors/tushare/tdx_indicators.py` | 通达信公式（MA/EMA/RSI/MACD/BOLL/ATR/VWMA/MFI） |
| `tradingagents_cn/vendors/tushare/indicators.py` | 指标口径分发 + 输出渲染 |
| `tradingagents_cn/vendors/tushare/fundamentals.py` | 概况/估值/财务摘要 |
| `tradingagents_cn/vendors/tushare/statements.py` | CAS 三表（前视过滤、亿元、YTD） |
| `tradingagents_cn/vendors/tushare/insider.py` | 高管/股东增减持（按公告日） |
| `tradingagents_cn/vendors/tushare/macro.py` | 中国宏观序列（CPI/PPI/GDP/M2/社融/PMI/SHIBOR；LPR/10Y 显式拒绝） |
| `tradingagents_cn/vendors/xueqiu.py` | 雪球 RSSHub：个股新闻（路由 `get_news`）、帖子/评论/热帖（接口，未接 agent） |
| `tradingagents_cn/vendors/tushare/flows.py` | 资金流/北向/两融/龙虎榜（仅接口） |
| `tradingagents_cn/vendors/tushare/index.py` | 指数行情与成分权重（独立命名空间） |
| `tradingagents_cn/vendors/tushare/calendar.py` | `trade_cal` → 交易日历 |

预留空包（尚无实现，仅占位）：`tradingagents_cn/agents/__init__.py`、`tradingagents_cn/reporting/__init__.py`。

## 3. 测试清单（`tests/downstream/`）

| 文件 | 覆盖 |
| --- | --- |
| `tests/downstream/test_audit_inventory.py` | 本文件与代码同步 |
| `tests/downstream/test_bootstrap.py` | 注册门面、签名、幂等、严格隔离 |
| `tests/downstream/test_registration.py` | 注册与回滚 |
| `tests/downstream/test_config.py` | 配置合并、严格模式、Profile、目录 |
| `tests/downstream/test_market_profiles.py` | 多市场识别/隔离/并发 |
| `tests/downstream/test_contract_behavior.py` | 行为契约：路由、PIT、身份 |
| `tests/downstream/test_entrypoints.py` | 入口不得绕过 Factory（AST） |
| `tests/downstream/test_concurrency.py` | 双链并发隔离 |
| `tests/downstream/test_graph_wiring.py` | 身份注入 12/12、PIT、规则注入、签名一致 |
| `tests/downstream/test_prompt_contracts.py` | **捕获真实 prompt**：身份/规则进入、美股无 A 股规则 |
| `tests/downstream/test_prompt_scenarios.py` | 黄金场景（工具真调用）：无数据哨兵、亏损带符号、涨停带幅度 |
| `tests/downstream/test_macro.py` | 宏观别名/单位/时间窗/不可用拒绝/路由 |
| `tests/downstream/test_xueqiu.py` | 雪球 RSS 解析/窗口/HTML 清洗/路由/拒绝语义 |
| `tests/downstream/test_xueqiu_live.py` | **真实 RSSHub** 2 项（`-m integration`） |
| `tests/downstream/test_web_jobs.py` | 队位、崩溃恢复、事件序号 |
| `tests/downstream/test_web_errors.py` | 错误分类 |
| `tests/downstream/test_web_security.py` | token 比较、路径白名单 |
| `tests/downstream/test_web_runner_worker.py` | 执行序列/产物/失败分类/worker 恢复 |
| `tests/downstream/test_web_api.py` | 鉴权/校验/队列/页面/SSE/文件越权 |
| `tests/downstream/test_checkpoint_behavior.py` | 版本/口径/脏工作区使 checkpoint 失效 |
| `tests/downstream/test_run_metadata.py` | 11 项元数据三处渲染 |
| `tests/downstream/test_snapshot_routing.py` | 快照路由、契约不变、同源一致 |
| `tests/downstream/test_identity_pit.py` | 名称的生效窗口 + 公告日 |
| `tests/downstream/test_insider.py` | 增减持公告日过滤、单位 |
| `tests/downstream/test_statements.py` | 三表前视/单位/口径 |
| `tests/downstream/test_fundamentals.py` | 估值取日、财报前视 |
| `tests/downstream/test_indicators.py` | 指标窗口/错误/表头 |
| `tests/downstream/test_tdx_indicators.py` | 13 个通达信公式逐值对齐 |
| `tests/downstream/test_tushare_vendor.py` | 行情单位/复权/错误映射 |
| `tests/downstream/test_tushare_live.py` | **真实账号** 10 项（`-m integration`） |
| `tests/downstream/test_cache.py` | TTL/LRU/损坏/开关 |
| `tests/downstream/test_pit.py` | 公告日过滤纯函数 |
| `tests/downstream/test_units.py` | 单位换算边界 |
| `tests/downstream/test_symbols.py` | 代码规范化 |
| `tests/downstream/test_calendar.py` | 交易日历 |
| `tests/downstream/test_trading_rules.py` | 涨跌停/整手/参考价 |
| `tests/downstream/test_flows_index_identity.py` | 资金面/指数/身份接口 |
| `tests/downstream/test_upstream_compat.py` | 上游符号/签名/结构（兼容性） |
| `tests/downstream/test_packaging.py` | 打包发现 |

## 4. 配置键与环境变量

| 配置键 | 作用 |
| --- | --- |
| `cn_adjust` | 复权口径（qfq/hfq/none） |
| `cn_allow_dirty_checkpoint` | 开发用：允许脏工作区 checkpoint |
| `cn_calendar_holidays` | 离线日历节假日 |
| `cn_data_schema_version` | 数据结构版本（进 checkpoint 身份） |
| `cn_extension_version` | 扩展版本（进 checkpoint 身份） |
| `cn_formula_version` | 公式版本（进 checkpoint 身份） |
| `cn_include_bj` | 是否纳入北交所 |
| `cn_indicator_flavor` | 指标口径（tdx/stockstats） |
| `cn_market` | 下游市场标识 |
| `cn_rules_version` | 交易规则版本（进 checkpoint 身份） |
| `cn_strict_ashare` | 严格 vendor 策略（仅 CN profile） |

| 环境变量 | 对应 |
| --- | --- |
| `TRADINGAGENTS_CN_ADJUST` | `cn_adjust` |
| `TRADINGAGENTS_CN_INCLUDE_BJ` | `cn_include_bj` |
| `TRADINGAGENTS_CN_INDICATOR_FLAVOR` | `cn_indicator_flavor` |
| `TRADINGAGENTS_CN_MARKET` | `cn_market` |
| `TRADINGAGENTS_CN_STRICT_ASHARE` | `cn_strict_ashare` |

另：`TRADINGAGENTS_CN_CACHE`（off 关闭缓存）、`TRADINGAGENTS_CN_CACHE_DIR`（缓存目录覆盖）、
`TRADINGAGENTS_CN_MIN_INTERVAL`（调用间隔）、`TUSHARE_TOKEN`（数据源凭证）、
`RSSHUB_BASE_URL` / `RSSHUB_TOKEN`（雪球 RSSHub 实例与访问 key，经 `?key=` 传递）。

## 5. 注册到上游的数据方法

全部为 `tushare:` 前缀：`get_stock_data`、`get_indicators`、`get_verified_market_snapshot`、
`get_fundamentals`、`get_balance_sheet`、`get_cashflow`、`get_income_statement`、
`get_insider_transactions`、`get_money_flow`、`get_northbound_holdings`、`get_margin_detail`、`get_top_list`。

## 6. 上游补丁（`upstream-patch:`）

| 文件 | 改动 | 原因 | 台账 |
| --- | --- | --- | --- |
| `tradingagents/dataflows/router.py` | +6 行：注册 `get_verified_market_snapshot` 到 `core_stock_apis`（yfinance 实现） | 快照工具原本直连 Yahoo，绕过 vendor 路由 | D-0022 |
| `tradingagents/agents/tools.py` | 1 行调用改为 `route_to_vendor(...)` | 同上；工具名/Schema/描述/错误语义不变 | D-0022 |
| `tests/test_graph_end_to_end.py` | 2 行：期望的数据路径集合跟随路由 | 路由改动的必然连带 | D-0027 |

## 7. 入口

- `python -m tradingagents_cn.cli analyze --ticker 600519.SH --date 2026-10-30 [--strict] [--market CN]`
- `python -m tradingagents_cn.cli batch --tickers ... --dates ...`
- 程序化：`tradingagents_cn.graph.factory.build_graph(config, symbol=...)`（Profile 自动分流）
- Web：`python -m tradingagents_web --host 0.0.0.0 --port 8501`
  （`TRADINGAGENTS_WEB_TOKEN` 必填；`TRADINGAGENTS_WEB_READ_TOKEN` 只读；`KVIEWER_BASE_URL` 可选）

## 8. 如何复核（可执行）

```bash
uv run pytest -q                                  # 全量（含上游 1412）
uv run pytest -q -m integration tests/downstream/test_tushare_live.py
uv run ruff check .
python scripts/extension_inventory.py --check     # 本文件与代码同步
git diff --stat upstream/main..HEAD -- tradingagents cli tests pyproject.toml
```

## 9. 已知限制（与功能边界）

1. 新闻/公告/社交情绪**未替代**（`docs/DATA_REQUIREMENTS.md` 定义了验收标准）。
2. 中国宏观指标有权限、未封装成接口。
3. 资金面/指数/身份/快照为"仅接口"，未接 agent。
4. A 股专属 Agent（政策/公告/股东行为）未实现，`optional_analysts` 留位。
5. Prompt 本地化未做；B3 只建了评测骨架（`docs/B3_PROMPT_PLAN.md`）。
6. 海外 Profile 的输出级回归待 B3 完整场景集。
7. Provider 日志分目录、凭证分 Profile 未自动化。
