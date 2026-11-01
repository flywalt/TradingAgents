# EXTENSION_ARCHITECTURE.md — 下游扩展架构（v2.1）

> 2026-11-01 第二轮评审后的修订版。**本文档描述代码实际行为**，不是"应该怎样"。
> 任何与实现不符之处，以测试为准并立即修正文档。

## 1. 扩展手段（按实际侵入性排序）

| 层 | 手段 | 实际耦合 | "上游更新后"的真实含义 |
| --- | --- | --- | --- |
| **L3** | 独立下游模块（`tradingagents_cn/**` 新文件） | 最低 | 不会被覆盖；但它对上游 API 的**调用**仍可能失效 |
| **L1** | Vendor / Category 注册 | 中低 | 注册表结构与路由语义不变时继续可用 |
| **L2** | 子类覆写公开方法 | 中 | 方法签名与调用生命周期不变时继续可用 |
| **L4a** | 上游最小补丁 | 高 | 需要 rebase 重放；上游改到同一行就冲突 |
| **L4b** | 复制上游文件 | 最高 | 上游修复不再流入，只剩漂移探针 |

统一表述：**都不需要重新复制上游文件；兼容性由自动测试保障。上游若改变相关接口或调用语义，必须人工审核后再升级。**

原则不是机械排序，而是：**先把独立业务逻辑留在下游（L3），再选择连接上游的最小接口（L1/L2）。**
例：通达信指标是 L3 的计算模块，`register_vendor` 只负责把函数接进路由，计算代码不写进注册层。

## 2. 职责分离（v2.1 的核心修订）

```python
bootstrap()            # 进程级，一次：注册 vendor/category，校验签名/重复/覆盖，幂等
build_graph(config)    # 运行级：规范化本次配置 → ensure_bootstrapped() → CnTradingAgentsGraph
```

- `bootstrap()` **不接收、不读取、不返回运行配置**；`RegistrationReport` 只有 vendors 与幂等标志。
- `build_graph()` 产出一份**新的**配置副本；每个 Graph 的 `self.config` 相互独立。
- 工具调用只在 `run_config()` 上下文内进行（`propagate()` / `stream_run()` 已自带）。
- **禁止**用 `set_config()` 的进程级默认值决定某个任务的数据源。

## 3. 并发契约（实测支撑）

`test_concurrency.py` 用两个会 sleep 的假 vendor 在 20 个并发调用中验证隔离。

| 场景 | 结论 |
| --- | --- |
| 不同 Graph 实例各自 `propagate()` / `stream_run()` | ✅ 可并行（`run_config` ContextVar 隔离） |
| 不同 Graph 的 vendor 链不同 | ✅ 互不串线（已测） |
| 同一 Graph 实例并发多个 checkpoint 任务 | ❌ 不支持：`begin_checkpoint()` 会改 `self.graph` / `_checkpointer_ctx` / `_resuming` |
| 无运行上下文直接调用数据工具 | ❌ 不作为生产路径（会用进程级默认配置） |
| 用 `set_config()` 切换任务间 vendor | ❌ 禁止 |

## 4. 入口：任何研究入口都不得绕过 Factory

| 入口 | 实现 | 保障 |
| --- | --- | --- |
| 下游 CLI | `tradingagents_cn/cli.py`（`analyze` / `batch`） | 调用 `graph.factory.build_graph` |
| 批量 | `tradingagents_cn/batch.py::run_batch`（每任务一个 Graph） | 同上 |
| Web（B4，未开工） | `tradingagents_web/` | 计划同路径 |
| 上游 CLI / `backtest.py` | **不用于生产**：它们直接 `TradingAgentsGraph(...)` | `test_entrypoints.py` 用 AST 扫描禁止下游新增直连 |

## 5. 严格模式（v2.1 修订）

`cn_strict_ashare=True` 同时锁两层，因为上游 `get_vendor()` 里 **`tool_vendors` 优先于 `data_vendors`**：

1. `data_vendors` 的 `core_stock_apis` / `technical_indicators` / `fundamental_data` → `tushare`；
2. `tool_vendors` 的 7 个受管方法（`MANAGED_METHODS`）→ `tushare`；
3. 若用户显式把受管工具配成非 Tushare → **启动即 `ValueError`**，不静默接受。

错误语义（与上游路由器一致）：

| 情况 | 结果 |
| --- | --- |
| 供应商不可用（网络/限流/未配置） | `VendorUnavailableError` → `DATA_UNAVAILABLE` 哨兵 |
| 供应商正常但无该标的/该期数据 | `NoMarketDataError` → `NO_DATA_AVAILABLE` 哨兵 |
| 代码、Schema、单位、配置错误 | **直接抛异常**，禁止伪装成"数据缺失" |

## 6. 身份解析的 PIT 契约

`resolve_instrument_context()` 只做身份与上下文，不承担交易状态。

- 上市前 / 退市后 → 不提供身份（回退到 ticker-only）；
- 历史日期的名称：Tushare **`namechange`**，必须同时满足
  `ann_date ≤ trade_date` 且 `start_date ≤ trade_date ≤ end_date（空视为至今）`；
  只有生效窗口、没有公告日 → 不使用；
- 拿不到可信历史名称 → 用今天的名称，但由上游 `build_instrument_context` 标注"当前名称"；
- 行业/ST/停牌等易变状态**不**用当前值填充（上游历史分支已只给名称）。

## 7. Checkpoint 身份与版本纪律

上游把 `self.config`（除输出路径/重试项）哈希进 thread id。因此运行配置里的：

- `cn_extension_version`（包版本）
- `cn_formula_version` / `cn_rules_version` / `cn_data_schema_version`
- `cn_indicator_flavor` / `cn_adjust` / vendor 链

任一变化都会让旧 checkpoint 失效（`test_checkpoint_behavior.py` 用公开 `checkpoint_scope()` 验证）。

**版本纪律**：改动会影响历史结果的逻辑时，必须 bump 对应版本；忘 bump 的兜底是 `worktree_dirty`：
`checkpoint_enabled` + 工作区不干净 → **拒绝构建**（`cn_allow_dirty_checkpoint=True` 仅供开发）。

## 8. 运行元数据（11 字段，单一来源）

`runmeta.collect()` 是唯一来源，`attach()` 把它渲染到 `run_metadata.json`、`complete_report.md`、`complete_report.html`。

`upstream_commit`、`downstream_commit`、`worktree_dirty`、`extension_version`、`data_provider`、
`provider_revision`、`financial_formula_version`、`market_rules_version`、`data_as_of`、
`data_retrieved_at`、`dataset_snapshot_id`。

- 字段白名单，**不含**任何 token / endpoint / 环境变量；
- `dataset_snapshot_id` 是"数据切片身份"（provider + 版本 + 日期 + 标的 + 复权），**不是全量内容哈希**；
- 已知限制：`data_provider` 记录的是**配置链**，尚未记录"这一次实际由哪家服务"（严格模式下二者等价）。

## 9. L4a 补丁准入（取消行数门槛）

准入条件：不存在可用的 L1/L2/L3 路径，且补丁满足——
最小语义改动、影响面可解释、有回滚路径、有行为测试、登记 `UPSTREAM_DELTA.md`。
**行数只作审查参考，不作门槛。**

现有补丁：

| 补丁 | 文件 | 性质 |
| --- | --- | --- |
| Snapshot Vendor Routing | `dataflows/router.py`、`agents/tools.py` | 把直接调用改为通用路由，工具契约不变 |
| 端到端测试断言 | `tests/test_graph_end_to_end.py` | 随路由更新"实际数据路径"集合（2 行） |

上游合并等价能力后：同步时删除补丁、改用上游接口。

## 10. 快照语义（事实核验工具）

`get_verified_market_snapshot` 被上游用于核对精确数字，因此 Tushare 实现必须与行情工具**同源同口径**：

- 与 `get_stock_data` 同一份 qfq 日线，同一复权锚点；
- 只取 `trade_date` 当日或之前（`fetch_bars` 在适配器层再裁一次，防供应商忽略 `end_date`）；
- 指标序列与快照价格来自同一序列；
- 无数据 → 显式哨兵，不返回空表让模型自行发挥。

`test_snapshot_routing.py` 断言：同源收盘价一致、日期不越过 `trade_date`、严格模式不回落。
