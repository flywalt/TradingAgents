# EXTENSION_POINTS.md — 上游扩展点审查报告

> 审查对象：TradingAgents **v0.7.1**（`c454491`），本仓库当前代码。
> 结论分三档：**零改动**（下游包内注册/组合即可）、**需补丁**（必须改上游文件）、**不可扩展**（只能复刻）。
> 本阶段**不实施**任何补丁，只给最小必要补丁草案与理由（见第 8 节）。

## 0. 结论速览

| # | 扩展点 | 本次审查结论 | 主要依据 |
| --- | --- | --- | --- |
| 1 | 数据源（vendor）——复用已有方法 | ✅ **零改动** | `router.VENDOR_METHODS` 是可写 dict，`route_to_vendor` 在调用时查表 |
| 1b | 数据源——新增方法（如北向资金/龙虎榜） | ⚠️ **需补丁**（新 tool 需进上游 `agents/tools.py`） | 工具函数是上游硬编码 `@tool` |
| 2 | 新增/替换分析师 agent | ⚠️ **需补丁**，或用"自建图"绕开（复制约 100 行连线） | `GraphSetup.setup_graph` 内 `analyst_factories` 局部字典 |
| 2b | 替换经理/交易员/组合经理节点 | ❌ **不可注入**（节点名字硬编码） | 同上 |
| 3 | Prompt 覆写 | ⚠️ **无 seam**；可用 `instrument_context` 注入 A 股事实（零改动）+ 自建图替换节点 | prompt 写在工厂闭包内，无模块级常量 |
| 4 | LangGraph 拓扑扩展 | ⚠️ **零改动可行但需自建连线**（复用上游节点工厂） | `__init__` 里 `setup_graph()` 后立即 `compile()` |
| 5 | 状态扩展（新增 state channel） | ✅ **零改动**（自建图用扩展 state） | `AgentState` 可被继承；上游图本身不接受新 state |
| 5b | Checkpoint | ✅ **零改动**（复用工具函数，覆写 `_run_signature`） | `checkpointer.py` 是纯函数；签名通过 `self.` 调用 |
| 6 | 配置 / 环境变量 | ✅ **零改动** | config 是自由 dict，`run_config()` ContextVar 作用域 |
| 6b | 模型供应商 | ✅ **零改动** | `OPENAI_COMPATIBLE_PROVIDERS` 注册表 + `openai_compatible` 通用端点 |
| 6c | 工具注册 | ⚠️ 新工具可给下游 agent 用；不能给上游 analyst 加 | 每个 analyst 的 `TOOLS` 是模块级 tuple |
| 7 | 报告章节 | ❌ **需补丁**（`reporting._SECTIONS` 硬编码） | `reporting.py` 私有常量 |

总原则：**A 股数据接入可以做到零上游改动；A 股 agent/prompt/报告章节需要少量补丁或自建图。**

---

## 1. 数据提供者（Data Provider）

### 现状（代码事实）

`tradingagents/dataflows/router.py`：

- `TOOLS_CATEGORIES`：`category → {description, tools:[方法名]}`，`get_category_for_method()` 反向查表。
- `VENDOR_METHODS`：`method → {vendor_name: callable}`，是**普通模块级 dict**。
- `get_vendor(category, method)`：`tool_vendors[method]` 优先，其次 `data_vendors[category]`，否则 `"default"`。
- `route_to_vendor(method, *args, **kwargs)`：把配置值按 `,` 拆成**有序 vendor 链**；显式配置就**只**用配置里的
  vendor（不静默回退）；`"default"` 才用全部可用 vendor；逐个 `try`，按错误类型决定继续还是记录。
- vendor 实现是**普通函数**（无基类、无 Protocol、无 entry_points），错误必须来自
  `dataflows/errors.py`（`NoMarketDataError` / `VendorUnavailableError` / `VendorNotConfiguredError`）。

### 结论

- **复用已有方法**（`get_stock_data` / `get_fundamentals` / `get_news` / `get_indicators` …）：
  在下游包 import 时（或显式 `activate()`）执行
  `router.VENDOR_METHODS["get_stock_data"]["tushare"] = impl` 即可，**零上游改动**。
  因为查表发生在 `route_to_vendor` 内部，注册时机只要早于第一次工具调用。
- **新增方法**（如 `get_northbound_flow`、`get_limit_up_pool`）：`TOOLS_CATEGORIES` 可运行时补（普通 dict），
  但**工具函数**必须写在 `agents/tools.py` 供 analyst 使用 → 属于上游补丁（见 8 节 P1/P5）。

### 风险（实测得出，必须防）

1. `"default"` 语义 = **全部已注册 vendor**。注册 `tushare` 后，若配置仍为 `default`，美股请求也可能落到 A 股 vendor。
   → 下游配置必须**显式**写 vendor 链（`data_vendors` / `tool_vendors`），并把这条写成测试。
2. vendor 函数签名/顺序必须与 `VENDOR_METHODS` 中现有实现一致（位置参数），否则 fallback 时参数错位。
3. `tests/test_layering.py` 只扫描 `tradingagents/` 和 `cli/`，**不覆盖** `tradingagents_cn/`。
   → 下游需自带等价测试（vendor SDK 只允许出现在 `tradingagents_cn/vendors/`）。
4. 依赖 `router.VENDOR_METHODS` 这一**私有结构**（无公开注册 API）属于脆弱耦合，需登记 + 冒烟测试。

---

## 2. Agent 的注册与扩展

### 现状

- `tradingagents/agents/<role>/<name>.py`：每个 agent 一个 `create_xxx(llm) -> node(state) -> dict` 工厂，
  节点只回写自己负责的 state key。
- `agents/__init__.py`：显式 import/`__all__` 导出，无插件发现机制。
- `graph/analyst_execution.py`：`ANALYST_NODE_SPECS`（key → `AnalystNodeSpec(key, agent_node, report_key, tools)`），
  `build_analyst_execution_plan()` 对未知 key **直接抛 `ValueError`**。
- `graph/setup.py`：`setup_graph()` 内**局部字典** `analyst_factories = {"market": lambda: ..., ...}`，
  以及硬编码的 `workflow.add_node("Bull Researcher", ...)` 等 8 个非分析师节点。
- `graph/trading_graph.py.__init__`：`self.graph_setup = GraphSetup(...)`、`self.workflow = self.graph_setup.setup_graph(selected_analysts, memory_node=self._memory_step)`，随后立刻 `compile()`。

### 结论

| 需求 | 可行性 |
| --- | --- |
| 替换某个分析师的**实现**（保留节点名/报告字段） | ❌ 工厂字典在函数内，不可注入 |
| **新增**分析师（新 key、新节点、新报告字段） | ❌ `build_analyst_execution_plan` 硬校验 + 工厂字典固定 |
| 新增/替换 经理、交易员、风险辩论、组合经理 | ❌ 节点名字符串硬编码在图里 |
| 复用上游全部节点，自己**重新连线** | ✅ 可行：`create_*` 工厂都是公开 API（`tradingagents.agents.__all__`） |

推荐路径（零改动）：下游 `tradingagents_cn/graph/trading_graph_cn.py` 继承 `TradingAgentsGraph`，
在 `__init__` 末尾用 `self.quick_thinking_llm` / `self.deep_thinking_llm` / `self.conditional_logic`
自行 `StateGraph` 连线并覆盖 `self.workflow` / `self.graph`（**不复制** LLM/记忆/checkpoint/报告逻辑）。
代价：连线逻辑（约 100 行）与上游 `setup_graph` 并行维护，上游改拓扑时必须跟进。
→ 用下游冒烟测试锁定：节点集合、边、每条 path_map 全覆盖（参考上游 `tests/test_graph_end_to_end.py` 的脚本化假模型做法）。

**建议补丁 P2**（见 8 节）：让 `GraphSetup`/`TradingAgentsGraph` 接受可注入的 node 工厂与额外分析师规格，
把"复制连线"降级为"注册"，这是本报告中**收益最高的一条**。

---

## 3. Prompt 的管理方式

### 现状

- Prompt **不是数据**，而是每个 agent 工厂闭包里的局部变量 `system_message`，再经
  `ChatPromptTemplate.from_messages(...).partial(system_message=..., tool_names=..., current_date=..., instrument_context=...)` 拼装。
- 跨 agent 的公共片段只有两个函数：`agents/context.py::get_language_instruction()`（输出语言）与
  `build_instrument_context()` / `get_instrument_context_from_state()`（标的身份）。
- 无模板目录、无 Jinja、无 versioning、无按市场/资产类型分支的 prompt 选择器。
- 上游有测试**锁死**了 prompt 的部分性质：`tests/test_prompt_integrity.py`（brief 必须是字符串、不得要求交易结论）、
  `tests/test_i18n_coverage.py`、`tests/test_news_analyst_prompt.py`。改写 prompt 文本会撞测试。

### 结论

- **直接覆写上游 prompt 文本 = 禁止**（会与上游 prompt 修复脱钩，且撞上游测试）。
- 可行的**零改动**注入点：`TradingAgentsGraph.resolve_instrument_context()`（`graph/trading_graph.py:117`）
  是一个**公开方法**，被 `create_run_state()` 调用，结果作为 `instrument_context` 传进每个 agent 的 prompt。
  → 下游子类覆写它，即可给**所有** agent 注入 A 股事实（市场、复权口径、停牌、T+1、行业、交易日历），
  这是当前唯一的"横切 prompt 注入缝"。
- 下游**自有** agent 的 prompt 放 `tradingagents_cn/agents/prompts/`（数据文件），不碰上游。
- 若确需改上游 agent 的**指令本身**（不只是补充事实）：必须（a）自建节点复刻 prompt，或（b）打补丁 P3。

---

## 4. LangGraph 工作流的扩展方式

### 现状

- `setup_graph()` 返回**未编译**的 `StateGraph`；`TradingAgentsGraph` 拿到后立即 `compile()`（`__init__` 内两行相邻）。
- 分析师是**独立子图**（`_analyst_graph`）：`StateGraph(AgentState, output_schema=<只含 report_key 的 TypedDict>)`，
  内部私有 messages + `ToolNode`，超出 `max_tool_rounds` 强制"wrap_up"收尾。
- 条件边统一用 `ConditionalLogic` + **完整 path_map**（`DEBATE_PATH_MAP` / `RISK_ANALYSIS_PATH_MAP`），避免缺 key 崩溃。
- 递归上限校验：`2 * max_tool_rounds + 2 >= max_recur_limit` 直接 `ValueError`。

### 结论

- LangGraph 侧技术上允许在 `compile()` 前任意加节点/边，但上游把"构建"和"编译"写死在 `__init__`，
  **没有钩子**。可选：
  1. 子类覆写 `__init__`（要复制约 70 行配置/LLM/记忆初始化）——不推荐。
  2. 先调用上游 `__init__`，再**重建** workflow 覆盖 `self.workflow` / `self.graph`——推荐（见第 2 节）。
- 若目标只是**增加 A 股数据能力**而不增加 agent，则完全不必动拓扑：注册 vendor 即可。
- 加节点后必须重新核对 `max_recur_limit` 与 `max_tool_rounds` 的关系，否则长跑会在递归上限处失败。

---

## 5. 状态管理与 Checkpoint

### 现状

- `agents/state.py`：`AgentState(MessagesState)` + `InvestDebateState` / `RiskDebateState`（纯 TypedDict，无 reducer 定制）。
- `Propagator.create_initial_state()` 一次填满所有 key（含 debate 子状态）。
- `ConditionalLogic` 只读 `investment_debate_state.count`、`risk_debate_state.latest_speaker` 等。
- `graph/checkpointer.py`：`sqlite3` + `SqliteSaver.setup()`，路径 `<cache>/checkpoints/<TICKER>.db`；
  `thread_id(ticker, date, signature)`；`checkpoint_step()` / `clear_checkpoint()` 为纯函数。
- `TradingAgentsGraph._run_signature()`（`trading_graph.py:140`）把影响**图形状**的配置折叠进线程 ID
  （analysts、轮次、模型、asset_type、portfolio…），通过 `self.` 调用（`begin_checkpoint` / `clear_checkpoint_on_success`）。

### 结论

- **新增 state channel**：`class CnState(AgentState)` 加重叠键即可，但必须用在**下游自建图**上（上游图固定用 `AgentState`）。
  零上游改动。
- **Checkpoint**：直接复用 `get_checkpointer` / `thread_id` / `checkpoint_step`；下游配置若改变图形状，
  必须覆写 `_run_signature()` 把下游配置折进去，否则 resume 会拿旧形状的检查点。
  ⚠️ `_run_signature` 是**下划线私有方法**（脆弱耦合），覆写需登记 + 测试（签名变化 → 线程 ID 必须变化）。
- **记忆/报告 hook**：`_memory_step()`、`save_reports()` 都是公开/半公开方法，可被子类覆写（零改动）。

---

## 6. 配置、模型供应商与工具注册

### 配置

- `default_config.build_default_config()`：默认 dict + `_ENV_OVERRIDES`（`TRADINGAGENTS_*` → key，类型按默认值强转）。
  新增环境变量需改 `_ENV_OVERRIDES`（上游文件），但下游可自行读 `os.environ`（如 `TRADINGAGENTS_CN_*`）后并入 config。
- `dataflows/config.py`：`set_config()` 一层深合并（`data_vendors` 局部更新不会丢其他键）、
  `run_config()` / `run_config_context()` 用 ContextVar 做**每次 run 的作用域**，LangGraph 会把 context 带进 tool 调用。
- config 是自由 dict → 下游键（如 `cn_calendar`, `cn_limit_pct`）可直接放入，**零改动**。

### 模型供应商

- `llm_clients/factory.create_llm_client()`：anthropic / google / azure / bedrock 走原生分支，
  其余查 `OPENAI_COMPATIBLE_PROVIDERS`（`ProviderSpec`：base_url、base_url_env、key 可选、chat_class、Responses API 开关…）。
- 该注册表是**普通 dict**，可运行时注册；`ProviderSpec` 是 dataclass。
- 已有国内/兼容供应商：`deepseek`、`qwen`、`qwen-cn`、`glm`、`glm-cn`、`kimi`、`minimax(-cn)`，以及通用 `openai_compatible`（自定义 base_url）。
- 结论：A 股研究**不需要新增供应商**；新增 OpenAI 兼容端点也可零改动（注册表项或 `openai_compatible + base_url`）。
  仅当需要**非 OpenAI 协议**时才会碰到 `factory.py` — 一般用不着。

### 工具注册

- 工具是上游 `agents/tools.py` 里的 LangChain `@tool` 函数，参数用 `Annotated[..., InjectedState("...")]`
  从 state 取值（`company_of_interest`、`trade_date`），日期经 `as_of()` / `as_of_window()` 截断到 `trade_date`（防前视）。
- 每个 analyst 的 `TOOLS` 是**模块级 tuple**（如 `market_analyst.TOOLS`），`AnalystNodeSpec.tools` 引用它。
- 结论：给**已有** analyst 加工具 = 不可能（需改上游模块）；给**下游自有** analyst 配任意工具 = 零改动
  （自己的 `ToolNode` + 自己的 tuple，复用上游 `InjectedState` 约定即可）。

---

## 7. 其它值得注意的约束

1. **分层测试**：`tests/test_layering.py` 只允许数据层 import vendor SDK（当前只查 `yfinance`）。
   下游要做等价约束，否则 A 股 vendor SDK 会长进 agent 层。
2. **报告结构**：`reporting.py::_SECTIONS`（私有模块级 tuple）决定报告分节与文件名；`report_html.py` 消费它。
   下游要加"资金面 / 龙虎榜 / 涨停原因"等章节 → 需补丁 P4 或下游自带 writer。
3. **评级口径**：`agents/rating.py` 的 5 档 + `REVIEW` 是全链路契约（报告、记忆、回测），下游只能复用。
4. **回测/结算**：`backtest.py` 明确"不是撮合器"，基于记忆日志结算 alpha；A 股基准已可通过
   `benchmark_ticker` / `benchmark_map`（`.SS/.SZ`）配置，**零改动**。
5. **CLI**：`cli/main.py` 是上游 Typer 应用（`project.scripts: tradingagents`）。下游入口优先用
   `python -m tradingagents_cn`，避免改 `pyproject.toml`；确需 console script 再加一行（登记为补丁）。
6. **测试作为契约**：`tests/test_graph_end_to_end.py` 用脚本化假模型跑全图——这是下游验证"自建图未破坏上游语义"
   的最佳模板，下游应复制其模式（不复制文件）。

---

## 8. 最小必要补丁草案（**未实施**，等待批准）

按"收益/风险"排序。所有补丁都遵守：单文件、< 30 行、不改语义、可被上游自行采纳。

### P1 — `dataflows/router.py`：公开 vendor 注册函数

```python
def register_vendor(method: str, vendor: str, impl, category: str | None = None) -> None:
    """Register a vendor implementation for a router method (idempotent)."""
    if method in VENDOR_METHODS:
        VENDOR_METHODS[method][vendor] = impl
    else:
        if category is None or category not in TOOLS_CATEGORIES:
            raise ValueError(f"unknown method {method!r}; pass a known category")
        VENDOR_METHODS[method] = {vendor: impl}
        TOOLS_CATEGORIES[category]["tools"].append(method)
```

- **理由**：现在下游必须直接改 `VENDOR_METHODS` 私有 dict，无校验、无幂等保护、文档无处挂。
- **风险**：极低（仅新增函数）。
- **替代**：不补丁也能跑（dict 赋值），但会一直带着"私有结构耦合"负债。

### P2 — `graph/analyst_execution.py` + `graph/setup.py`：可注入分析师规格与节点工厂

- `AnalystNodeSpec` 增加 `factory: Callable[[Any], Callable] | None = None`；
  `setup_graph(selected_analysts, memory_node=None, extra_specs=None, node_factories=None)`：
  `analyst_factories` 先取 `node_factories` 覆盖项，再回落到内置四家；遍历 `ANALYST_NODE_SPECS + extra_specs`。
- **理由**：这是 A 股新增分析师（行业/政策/资金面）的唯一干净入口；否则下游要复制 100 行连线，上游一改拓扑就漂移。
- **风险**：中低。触及核心文件，但是**向后兼容的默认参数**；上游 `test_graph_end_to_end` 可回归。
- **配套**：`TradingAgentsGraph.__init__` 增加 `graph_setup_cls` 或 `analyst_specs` 透传（+3 行）。

### P3 — 各 agent：把 prompt 提升为模块级常量（可选）

- 把闭包内的 `system_message` 提为 `SYSTEM_MESSAGE`（含 f-string 片段拆成 `SYSTEM_MESSAGE_TEMPLATE`），工厂内引用。
- **理由**：让下游能"覆写文本而不复刻节点"。
- **风险**：中。上游有 prompt 相关测试（`test_prompt_integrity` 用 AST 找 `system_message` 赋值）会受影响，
  需同步调整测试 → 这正是"改上游文件就必须连同测试一起改"的例子。
- **建议**：**暂不做**。先用 `instrument_context` 注入 + 下游自有 agent，等确实需要改上游指令时再打。

### P4 — `reporting.py`：章节表可扩展

- `write_report_tree(..., sections=None)`，默认 `_SECTIONS`；`report_html` 同步接受。
- **理由**：A 股报告需要额外章节，否则下游只能另写 writer，导致两套报告格式与 HTML 渲染分裂。
- **风险**：低（默认参数）。

### P5 — `agents/tools.py`：工具模块化（可选，暂缓）

- 仅为"让上游 analyst 用上新工具"才需要。若下游分析师自带工具，则**不需要**。
- **建议**：暂不做，靠 P2 + 下游自有 agent 覆盖。

### 不做的事情

- ❌ 不引入插件系统/entry_points（上游风格是"显式注册 + 测试锁定"，引入框架会与上游差距越来越大）。
- ❌ 不改 `route_to_vendor` 的 fallback 语义（会破坏上游行为契约与测试）。
- ❌ 不改 `AgentState` 的结构（下游继承即可）。
- ❌ 不重构 `cli/`（下游自建入口更便宜）。

---

## 9. 给后续任务的建议顺序

1. 先只做**数据层**（vendor 注册 + 交易日历 + 复权口径），用现有 4 个分析师跑通 A 股标的 → 验证不碰上游也能产出报告。
2. 再决定是否需要 P1（把注册变公开 API）——如果只有 2~3 个 vendor，直接 dict 注册也够。
3. 需要新增 A 股专属分析师时，评估 P2；在此之前先用"自建图"验证想法。
4. P3/P4 等真正出现"必须改上游指令/报告结构"的需求再打，避免过早背补丁。
