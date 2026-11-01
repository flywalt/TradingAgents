# EXTENSION_ARCHITECTURE.md — 下游扩展架构（v2）

> 2026-11-01 整改后的正式扩展机制。此前的 `docs/EXTENSION_POINTS.md` 是**上游能力审查报告**，
> 本文件是**我们自己的契约**：哪一层用来扩什么、失效时谁报警。

## 1. 四层手段（按侵入性递增，默认从上层解决）

| 层 | 手段 | 改上游文件 | 上游更新后 | 注册/入口 | 适用 |
| --- | --- | --- | --- | --- | --- |
| L1 | **Vendor / 类别注册** | 否 | 自动生效 | `bootstrap.register_vendor()` / `register_category()` | 新增数据源、覆盖某个数据方法 |
| L2 | **子类覆写公开方法** | 否 | 自动生效（签名不变） | `TradingAgentsGraph` 子类 + `graph.factory.build_graph()` | 身份解析、报告元数据、保存行为 |
| L3 | **纯新增下游文件** | 否 | 完全独立 | `tradingagents_cn/**`、`tests/downstream/**` | 规则计算、缓存、指标、CLI/web 外壳 |
| L4a | **上游最小补丁** | 是 | 需 rebase 重放 | `upstream-patch:` 提交 + `docs/UPSTREAM_DELTA.md` | 上游没有扩展点、且不值得复刻时 |
| L4b | **复刻上游文件** | 否 | **不自动生效**，上游修复不再流入 | 禁止用于 prompt/agent；仅限极端情况并加漂移探针 | 不推荐 |

判定顺序：先问 L1 能不能做 → 再问 L2 → 再问 L3 → 只有"上游缺扩展点且改动可控制在 10 行内"才用 L4a。

## 2. 关键契约（谁负责什么）

| 组件 | 文件 | 契约 | 失效信号 |
| --- | --- | --- | --- |
| 注册门面 | `tradingagents_cn/bootstrap.py` | 唯一写上游注册表的地方；签名/重复/覆盖校验；`bootstrap()` 幂等；`ensure_bootstrapped()` | `test_bootstrap.py` |
| 图工厂 | `tradingagents_cn/graph/factory.py` | 所有入口（CLI/批处理/web/notebook）必须走 `build_graph()` | `test_graph_wiring.py` |
| 身份解析 | `CnTradingAgentsGraph.resolve_instrument_context()` | 与上游 v0.7.1 签名完全一致；复用 `build_instrument_context`；历史日期只给名称 | 签名相等测试 + PIT 测试 |
| 快照路由 | `upstream-patch`（`router.py` + `tools.py`） | 工具名/Schema/描述/错误语义不变，只换数据来源 | `test_snapshot_routing.py` |
| 运行元数据 | `tradingagents_cn/runmeta.py` | 9 个字段，写入 md/json/html 三处 | `test_run_metadata.py` |
| 版本与 Checkpoint | `_version.py` → `cn_extension_version` | 扩展版本进入运行配置，因此进入 checkpoint 身份 | `test_checkpoint_behavior.py` |
| 同步保险丝 | `tests/downstream/test_upstream_compat.py`（B）/ `test_contract_behavior.py`（A）/ `test_checkpoint_behavior.py`（C） | B=符号与签名；A=行为；C=Checkpoint 失效 | 三个文件本身就是信号 |

## 3. 数据流与配置

```
bootstrap(config)                    # 注册 vendor + 合并配置（不联网）
   └─ build_graph(config)            # CnTradingAgentsGraph，ensure_bootstrapped()
        └─ propagate(ticker, date)   # 每次运行 run_config(self.config) 作用域
             ├─ resolve_instrument_context()  → Tushare stock_basic（PIT 检查）
             ├─ 工具 → route_to_vendor(method) → data_vendors 链（tushare|yfinance）
             ├─ 指标 → 本地计算（tdx | stockstats）
             └─ save_reports() → 报告树 + run_metadata.{json,md,html}
```

**并发语义**：vendor *实现*是进程级、无状态的；**选哪家 vendor 是每次运行决定的**（`run_config` 的 ContextVar）。
所以多图并行不会串 vendor；会串的是 `set_config()` 的进程级默认值，因此多任务要串行或每任务一个进程。

## 4. 严格模式

`cn_strict_ashare=True` 把 `core_stock_apis` / `technical_indicators` / `fundamental_data` 的链改为单 vendor。
效果：Tushare 失败时返回 `DATA_UNAVAILABLE` 哨兵，而不是静默换到 Yahoo 的另一套价格口径。
`test_snapshot_routing.py` 与 `test_bootstrap.py` 各有一条测试锁住"绝不回落"。

## 5. Checkpoint 与版本

- 上游把**运行配置**哈希进 checkpoint 线程 ID；
- 因此 `cn_extension_version`、`cn_indicator_flavor`、`cn_adjust`、vendor 链变化都会让旧 checkpoint 失效；
- 测试只用公开的 `checkpoint_scope()`，不断言私有字符串。

## 6. 上游补丁登记

| 补丁 | 文件 | 行数 | 冲突风险 | 删除条件 |
| --- | --- | --- | --- | --- |
| Snapshot Vendor Routing | `tradingagents/dataflows/router.py`、`tradingagents/agents/tools.py` | ~9 行 | 中低（上游重写工具或注册表时） | 上游合并等价能力后，同步时删除并改用其接口 |

补丁必须满足：单文件为主、无语义重构、工具契约不变、有下游测试、登记 `docs/UPSTREAM_DELTA.md`。

## 7. 新增能力的检查清单

1. 能否只靠 L1 注册？→ 能，走 `bootstrap`。
2. 需要改上游行为但方法可覆写？→ L2 + 工厂。
3. 只是新计算/新来源？→ L3。
4. 必须改上游文件？→ 写最小 `upstream-patch:`、登记、加测试、在 `docs/UPSTREAM_CONTRIBUTION_PLAN.md` 记一条"未来反哺"。
5. 绝不复制 Analyst 文件或 prompt 文本来绕开扩展点。
