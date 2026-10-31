# ARCHITECTURE.md — 上游架构与下游边界

> 基线：TradingAgents **v0.7.1**（`c454491`）。行号与函数名以该版本为准；上游变动后请以代码为准。
> 扩展点可行性结论见 `docs/EXTENSION_POINTS.md`。

## 1. 一句话概括

`TradingAgentsGraph` 用 LangGraph 编排一组 LLM agent（4 分析师 → 多空辩论 → 研究经理 → 交易员 →
三方风险辩论 → 组合经理），agent 通过 `@tool` 调用数据层；数据层用"方法 → vendor 实现"的路由表
访问行情/基本面/新闻/macro/预测市场；所有产物写入报告树与记忆日志（含事后结算与反思）。

## 2. 模块地图（v0.7.1）

| 路径 | 职责 | 下游是否可直接复用 |
| --- | --- | --- |
| `main.py`, `cli/` | Typer CLI：交互选择、偏好持久化、无头运行、展示、版本检查 | 复用逻辑，入口自建 |
| `tradingagents/graph/trading_graph.py` | 编排入口：LLM 客户端、graph 编译、checkpoint、运行、保存报告 | 需包装/子类 |
| `tradingagents/graph/setup.py` | `GraphSetup.setup_graph()`：**硬编码**节点与边 | 冲突点（见扩展报告） |
| `tradingagents/graph/analyst_execution.py` | `ANALYST_NODE_SPECS` + `build_analyst_execution_plan()`，把 `selected_analysts` 解析成节点规格 | 可读、不可注��� |
| `tradingagents/graph/conditional_logic.py` | 辩论/风险轮次路由（`DEBATE_PATH_MAP` 等） | 可替换实现 |
| `tradingagents/graph/propagation.py` | 初始 state 构造（`create_initial_state`） | 可包装 |
| `tradingagents/graph/checkpointer.py` | 每 ticker 一个 SQLite 的 `SqliteSaver`、`thread_id` 签名 | 可复用 |
| `tradingagents/agents/*` | 各 agent 工厂 `create_xxx(llm) -> node`；prompt 写在工厂闭包内 | 只能整体替换节点 |
| `tradingagents/agents/tools.py` | `@tool` 数据工具，日期由 `InjectedState` 注入并截断到 `trade_date` | 可复用/可并列 |
| `tradingagents/agents/context.py` | 标的身份、输出语言指令、组合上下文 | 可复用 |
| `tradingagents/agents/rating.py` | 5 档评级解析（Buy…Sell / REVIEW） | 必须复用（口径一致） |
| `tradingagents/dataflows/router.py` | `TOOLS_CATEGORIES` + `VENDOR_METHODS` + `route_to_vendor()`：vendor 链、fallback、typed error | 可运行时注册 |
| `tradingagents/dataflows/vendors/*` | 每 vendor 一个模块/包（`yahoo/`, `alpha_vantage/`, `sec_edgar.py`, `fred.py`, `polymarket.py`, …） | 可仿照新增 |
| `tradingagents/dataflows/errors.py` | `NoMarketDataError` / `VendorUnavailableError` / `VendorNotConfiguredError` | **必须复用**（路由靠它决策） |
| `tradingagents/dataflows/config.py` | 进程级 config + `run_config()` ContextVar 作用域 | 必须复用 |
| `tradingagents/default_config.py` | `DEFAULT_CONFIG`、`_ENV_OVERRIDES`、`build_default_config()` | 可扩展 dict |
| `tradingagents/llm_clients/` | `create_llm_client()` 工厂、`OPENAI_COMPATIBLE_PROVIDERS` 注册表、tier 客户端 | 可扩展 |
| `tradingagents/memory/` | 记忆日志、事后结算（settlement）、反思（reflection） | 可复用 |
| `tradingagents/backtest.py` | 网格回测与聚合统计（基于记忆日志，不是撮合器） | 可复用 |
| `tradingagents/portfolio.py` | 组合上下文加载 | 可复用 |
| `tradingagents/reporting.py`, `report_html.py` | 报告树与 HTML 汇总（`_SECTIONS` 硬编码） | 需扩展点 |
| `tests/` | 1400+ 单元测试；`test_layering.py` 强制"只有数据层 import vendor 库" | 必须保持通过 |

## 3. 运行流程

```
cli/main.py (Typer)
  └─ cli/run.py: run_analysis()
       └─ TradingAgentsGraph(config)          # 选择 analyst、建 LLM 客户端、编译 graph
            ├─ set_config(config)             # 进程级默认，之后每次 run 用 run_config() 作用域
            ├─ GraphSetup.setup_graph(selected_analysts, memory_node)
            └─ propagate(ticker, trade_date, asset_type, portfolio)
                 ├─ Propagator.create_initial_state()          # messages / 各 *_report 槽位 / 辩论 state
                 ├─ with run_config(self.config):              # ContextVar 供工具读取 vendor 配置
                 │    graph.invoke(state)  (可挂 SqliteSaver，按 ticker+date+signature 分线程)
                 └─ save_reports() → reporting.write_report_tree() + report_html
```

图结构（节点名即 state key 的生产者）：

```
START ─┬─ Market Analyst     ─┐
       ├─ Sentiment Analyst   │  (并行；每个分析师是独立子图，
       ├─ News Analyst        │   私有 messages，只回写自己的 report_key)
       ├─ Fundamentals Analyst┤
       └─ Memory Log ─────────┘   (并行：结算历史决策，产出 past_context)
                │
                ▼
        Bull ⇄ Bear  ──► Research Manager ──► Trader
                │                                │
                ▼                                ▼
     Aggressive ⇄ Conservative ⇄ Neutral ──► Portfolio Manager ──► END
                                                   │
                                            final_trade_decision
                                            （rating.py 解析成 5 档评级）
```

## 4. 六个横向层次

1. **配置层**：`default_config.build_default_config()` 把 `TRADINGAGENTS_*` 环境变量折叠进字典；
   `dataflows/config.py` 提供 `set_config()`（一层深合并）与 `run_config()` / `run_config_context()`
   （ContextVar 作用域，LangGraph 会把 context 带进 tool 调用）。配置字典是自由 dict，下游可加自定义键。
2. **数据层**：工具函数 `agents/tools.py` → `route_to_vendor(method, ...)` → 按 category/tool 配置选
   vendor 链 → 逐个尝试 → 全失败时返回 `DATA_UNAVAILABLE` / `NO_DATA_AVAILABLE` 哨兵文本（不抛异常给模型）。
   `route_to_vendor` 会区分 typed error，并用 `as_of()` / `as_of_window()` 把日期截断到 `trade_date`（防前视）。
3. **Agent 层**：每个 agent 是一个闭包节点，内部用 `ChatPromptTemplate` + `take_turn()`（`analysts/turn.py`）
   完成"模型 → 工具 → 报告"的回合，产出 state 中对应 `*_report` 字段。
4. **图编排层**：`setup.py` 显式 `add_node` / `add_edge`，条件边用 `ConditionalLogic` + 完整 path_map。
5. **状态与检查点**：`agents/state.py` 的 `AgentState(MessagesState)` + `InvestDebateState` / `RiskDebateState`；
   checkpoint 存 SQLite（`~/.tradingagents/cache/checkpoints/<TICKER>.db`），线程 ID 含 graph 形状签名。
6. **产出层**：`results_dir/<TICKER>/<date>/` 下的分节 markdown + `complete_report.md` / HTML；
   `memory/trading_memory.md` 记录决策与事后结算，供反思与回测读取。

## 5. 上游已有的 A 股相关能力（避免重复造）

- `dataflows/symbols.py`：`600519.SH → 600519.SS` 等 Yahoo 代码规范化；`.SS`/`.SZ`/`.HK` 映射。
- `default_config.benchmark_map`：`.SS → 000001.SS`、`.SZ → 399001.SZ`，A 股标的自带基准指数。
- `dataflows/date_window.py`：交易日期截断，避免前视偏差。
- Yahoo vendor 能取部分 A 股日线与基本面（覆盖/质量有限，见下）。
- `asset_type` 已是字符串参数（`stock` / `crypto`），可透传自定义值（如 `ashare`），下游可用于分支。

**上游没有的**：A 股交易日历、停牌/涨跌停/T+1/整手约束、中国会计准则财报、龙虎榜/北向资金/融资融券、
涨跌停复盘、公告与政策文本源、A 股专用基准与行业分类。

## 6. 下游边界（硬规则）

```
上游代码（唯读）                    下游代码（可写）
tradingagents/**, cli/**, tests/**,  tradingagents_cn/**
pyproject.toml, README.md, ...
        │                                  │
        └───────── 只通过公开 API 调用 ◄───┘
```

1. 下游只 import 上游的**公开符号**；需要上游内部细节时，先登记为"脆弱耦合"并加测试。
2. 下游不得在 import 时产生副作用（注册动作必须显式调用 `tradingagents_cn.register.activate()`）。
3. 下游不得修改上游模块的全局状态（除注册表注册），尤其不得改 `DEFAULT_CONFIG` 原对象。
4. 上游文件补丁上限：一个文件一个补丁提交，改动尽量 < 30 行；超过则重新设计。

## 7. 建议的 A 股扩展目录结构

```
tradingagents_cn/
├── __init__.py
├── register.py            # activate(config=None)：幂等注册 vendor / agent 规格 / 报告章节
├── config.py              # 下游默认配置（deep-merge 进 run_config），env 前缀 TRADINGAGENTS_CN_
├── symbols.py             # A 股代码规范化（600519.SH/.SZ/.BJ → 内部统一 ID + 上游 Yahoo 映射）
├── calendar.py            # 交易日历、是否交易日、下一交易日、停牌查询
├── trading_rules.py       # 涨跌停价、ST/创业板/科创板/北交所 幅度、T+1、整手、复权口径
├── vendors/
│   ├── __init__.py
│   ├── common.py          # 限流、重试、缓存、错误映射到上游 typed error
│   ├── tushare/
│   │   ├── __init__.py    # 与 router 方法同名同签名的适配函数
│   │   ├── stock.py       # 日线/复权/停牌/涨跌停
│   │   ├── fundamentals.py# CAS 财报（含单位换算）
│   │   └── flows.py       # 资金流/北向/龙虎榜/融资融券
│   └── akshare/           # 备选/补充源（fallback 链的第二家）
├── agents/
│   ├── __init__.py
│   ├── ashare_context.py  # A 股上下文注入（涨跌停状态、停牌、行业、T+1）
│   ├── ashare_analyst.py  # 下游自有分析师（自带 tools 与 prompt）
│   └── prompts/           # prompt 作为数据文件（可版本化、可 i18n、可 A/B）
├── graph/
│   ├── state.py           # 扩展 AgentState（下游 channel）
│   ├── setup.py           # 复用上游节点 + 追加下游节点/边
│   └── graph.py           # 下游编排入口（复用上游 checkpoint/memory/reporting）
├── reporting/
│   └── sections.py        # 下游报告章节与术语（如资金面、龙虎榜、涨停原因）
└── cli.py                 # `python -m tradingagents_cn`（暂不加 console_scripts，避免改 pyproject）

tests/downstream/
├── conftest.py            # 离线 fixture（假 vendor、假 LLM），禁止真实网络
├── test_registration.py   # activate() 幂等 + 不污染上游默认配置
├── test_vendor_contract.py# 适配函数签名/错误类型与上游 router 契约一致
├── test_symbols.py        # 代码规范化、市场识别
├── test_calendar.py       # 交易日历/停牌/涨跌停/T+1
└── test_sync_guard.py     # 上游耦合冒烟：被依赖的上游符号仍存在且语义未变
```

要点：

- **一个 vendor 一个包**，函数签名与 `router.VENDOR_METHODS` 的方法签名严格一致，错误必须是
  `tradingagents.dataflows.errors` 里的类型，否则 router 的 fallback 判定会失效。
- **prompt 与代码分离**：A 股术语（"标的""涨停"）与输出语言需要频繁调整，放数据文件比改闭包稳。
- **`test_sync_guard.py` 是同步保险丝**：上游改坏任何被依赖的符号，同步当天就能发现。
- 首选 vendor 链写成 `tushare,akshare,yahoo` 之类的有序回退，通过 `data_vendors` / `tool_vendors` 配置，
  不写死在代码里。

## 8. 下游不可覆盖的部分

- `agents/rating.py` 的 5 档评级口径 → 必须复用，否则记忆日志/回测/报告口径分裂。
- `dataflows/errors.py` 的错误类型语义 → 必须复用，否则 fallback 失效。
- `run_config()` 的作用域语义 → 必须复用，否则并发跑多标的多配置时会串配置。
- 检查点的 `thread_id(ticker, date, signature)` 生成规则 → 若下游改图形状，必须在 signature 中体现。
