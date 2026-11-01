# 外部评审简报：下游补丁与上游同步的工程方案（2026-11-01）

> 用途：交给外部 agent 评审"自定义补丁 + 持续跟随上游"这套方案是否最佳。
> 项目：TauricResearch/TradingAgents（Apache-2.0）的私有下游分支，目标是在其 Agent 框架上做 A 股本地化研究扩展。

## 1. 目标与硬约束

1. 长期跟随上游（当前基线 v0.7.1 / `c454491`），持续 rebase，不 fork 成孤岛。
2. **不破坏性改写上游代码**：优先"不改上游文件"的手段，保证上游更新不会把我们的补丁冲掉。
3. 所有下游改动可追溯、可回滚、有测试。
4. 不为本地化重构上游（不格式化、不搬目录、不换依赖）。

## 2. 现状（已落地，可核验）

- 上游已跟踪文件：**0 修改**（`git diff upstream/main..HEAD -- tradingagents cli pyproject.toml` 为空）。
- 新增文件 19 个，全部在 `tradingagents_cn/**` 与 `tests/downstream/**`（纯新增，rebase 不冲突）。
- 测试：上游 1412 + 下游 207；真实数据 integration 9 个；`ruff` 全绿。
- 已完成的数据层：Tushare 行情/复权/交易日历/三表/概况/资金面/指数、通达信口径 13 指标、公告日前视过滤、单位换算、TTL 缓存+限流、严格模式。

## 3. 我们采用的手段分层（按侵入性递增）

| 层 | 手段 | 改上游文件 | 上游更新后是否自动生效 | 现状 |
| --- | --- | --- | --- | --- |
| L1 | 运行时注册（写入上游 router 的 `VENDOR_METHODS` / `TOOLS_CATEGORIES` 字典） | 否 | 是 | 已大量使用 |
| L2 | 子类覆写上游公开方法（下游包内） | 否 | 是（签名不变时） | 计划使用 |
| L3 | 纯新增文件（下游包 + 下游测试） | 否 | 是 | 已使用 |
| L4a | 上游文件最小补丁（`upstream-patch:` 提交，通常 <30 行） | 是 | 否，需 rebase 重放 | 未使用 |
| L4b | 复刻上游文件到下游再改（copy & fork） | 否 | **否**，且上游修复不再流入 | 未使用 |

同步保障：`backup/pre-sync-*` → `rebase upstream/main` → 全量测试 → `sync/YYYYMMDD` tag；补丁逐条登记在 `docs/UPSTREAM_DELTA.md`；`tests/downstream/test_sync_guard.py` 用测试锁定所依赖的上游符号（方法存在、表结构、状态字段、评级枚举）。已做 `v0.7.0→v0.7.1` 演练：22 提交 / 37 文件，0 冲突；并测出冲突只发生在"我们改的行被上游重写"时。

## 4. 待做的工作与拟用手段

### A. Agent 层接线（不改 prompt、不动上游）

1. **标的身份注入**：上游 `TradingAgentsGraph.resolve_instrument_context()` 用 Yahoo 查公司名/行业，A 股覆盖差。用 **L2**：下游子类覆写该方法，改读 Tushare `stock_basic`。12/12 个 agent 的 prompt 都注入该上下文，一处修改全链路生效。
2. **验证快照换源**：market analyst 的 `get_verified_market_snapshot` 走 Yahoo，与已接入的 Tushare 价格不同源。这项**无法用 L2**（工具元组与 prompt 文本写死在 `market_analyst.py` 闭包内）。两个候选：
   - **L4b**：下游复刻该 analyst（约 80 行）+ 漂移探针（锁定上游文件 hash/关键句）；
   - **L4a**：给上游打约 10 行补丁，让 `TOOLS`/快照工具名可注入。
3. **内部人交易**：`get_insider_transactions` 仍走 Yahoo；用 **L1** 注册 Tushare `stk_holdertrade`（权限已有）。
4. **交易规则进上下文**：涨跌停/T+1/整手/ST/除权参考价由本地 `trading_rules.py` 计算，通过 `instrument_context` 注入（纯下游字符串，**L3**）。

### B. 补 A 股数据源（news / sentiment）

现新闻源是 Yahoo/FRED/Polymarket，情绪源是 StockTwits/Reddit，A 股全空。计划换 AkShare/东财新闻、国内宏观（`cn_cpi`/`shibor`）、股吧/雪球/龙虎榜资金。手段：**L1 + L3**（新增下游 analyst 与工具），不改上游。

### C. Prompt 本地化（最后做）

目标：CAS/YTD/亿元口径、涨跌停/T+1/停牌约束、评级与合规措辞、日期时区。前置条件是先建"脚本化假模型 + 黄金场景"评测，否则无法判断改好还是改坏。候选手段同样是 **L4b（复刻 agent）或 L4a（上游注入点）**。

## 5. 希望外部评审回答的问题

1. L1（运行时改上游字典）+ L2（子类覆写）作为主力手段是否足够稳？有没有更好的"扩展点"形态（例如要求上游提供 entry-point 注册、dependency injection、或把 prompt/tools 参数化）？
2. 当上游没有扩展点时，**L4a（小补丁）与 L4b（复刻）如何取舍**？是否应主动向上游提 PR 把所需扩展点做进去，以此把 L4a/L4b 长期降级为 L1/L2？
3. 同步模型：`main` 保持"上游基线 + 线性下游提交（rebase）"是否优于"下游长期分支 + 定期 merge 上游"或"把上游当依赖（submodule/固定版本包）+ 下游独立仓库"？考虑到我们有 19 个新增文件与未来可能的补丁。
4. 我们的"同步保险丝"（测试锁定上游私有结构，如 `router.VENDOR_METHODS`、`_run_signature`）是否是合理做法，还是有更标准的做法（例如契约测试、接口冻结、min/max 版本约束）？
5. 哪些下游成果值得反哺上游（A 股 vendor 适配器、通达信指标、公告日前视过滤），以降低长期维护成本？反哺的边界应该怎么划？

## 6. 明确的非目标

- 不做多用户/Web 产品（参考过同类 A 股分支 TradingAgents-CN，判定其 8 倍文件量属产品层，不吸收）。
- 不在本阶段重写 12 个 agent 的分析框架；只做数据可达性与 A 股约束。
- 不修改上游的评级契约（5 档 + `REVIEW`）与结构化 schema。
