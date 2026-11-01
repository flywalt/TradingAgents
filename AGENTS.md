# AGENTS.md — TradingAgents 下游开发规范

本仓库是 [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) 的
**下游分支（downstream fork）**，目标是在持续跟随官方上游更新的前提下，叠加 A 股研究扩展。

上游是唯一权威来源，下游只做增量。**能不改上游代码，就不改上游代码。**

相关文档：

| 文档 | 内容 |
| --- | --- |
| `docs/ARCHITECTURE.md` | 上游架构、扩展点、建议的下游目录结构 |
| `docs/EXTENSION_POINTS.md` | 扩展点审查报告：哪些能力零改动可实现、哪些必须打补丁 |
| `docs/UPSTREAM_DELTA.md` | 基线记录 + 下游差异台账（每个下游提交都要登记） |
| `docs/UPSTREAM_SYNC.md` | 上游同步（rebase）标准流程与演练记录 |
| `docs/TUSHARE.md` | A 股数据接入：行情/复权/交易日历、单位口径、路由回退、已知限制 |
| `docs/ASHARE_DATA.md` | A 股数据层能力矩阵、价格/指标口径、缓存限流、限制清单 |
| `docs/AGENT_MAP.md` | Agent 层地图：12 个节点的输入/工具/A 股可达性 + B1/B2/B3 批次计划 |
| `docs/WEB_PLAN.md` | Web 界面（B4）：局域网单用户、单 worker、服务端渲染、安全边界 |
| `docs/EXTENSION_ARCHITECTURE.md` | **扩展架构 v2**：L1–L4 手段、关键契约、Checkpoint/版本、补丁登记 |
| `docs/UPSTREAM_CONTRIBUTION_PLAN.md` | 上游贡献备选计划（非近期重点，含触发条件） |

---

## 1. 仓库与 Remote 约定

| 名称 | 指向 | 用途 |
| --- | --- | --- |
| `upstream` | `https://github.com/TauricResearch/TradingAgents.git` | **只读**。官方上游，用于 fetch / rebase |
| `origin` | 自己的 GitHub fork（见 `docs/UPSTREAM_SYNC.md` 第 1 节） | 下游仓库，推送 `main` 与 `feature/*` |

- **禁止** 向 `upstream` 推送（`git push upstream` 一律不允许）。
- **禁止** 未经用户明确同意修改任何远程仓库配置（`git remote add/remove/set-url` 属于本机配置，
  可执行；`git push`、改 GitHub 仓库设置必须经用户确认）。
- 如果 `origin` 仍指向上游地址，说明 fork 尚未建立：**先停下**，按 `docs/UPSTREAM_SYNC.md`
  的"建立 fork"步骤请用户操作，不要自行推送。

## 2. 分支模型

| 分支 | 角色 |
| --- | --- |
| `main` | 稳定下游分支。始终 = 某个上游基线 + 一条线性的下游提交序列 |
| `feature/<slug>` | 功能开发（A 股扩展、数据源、新 agent 等） |
| `fix/<slug>` | 缺陷修复 |
| `chore/<slug>` / `docs/<slug>` | 规范、文档、构建、依赖 |
| `sync/<yyyymmdd>` | 仅用于演练或试运行同步（可随时丢弃） |

规则：

1. 所有改动经 `feature/*`、`fix/*`、`chore/*`、`docs/*` 分支提交，再合入 `main`。
2. `main` 保持**线性**：合入时用 `git merge --no-ff` 或 `git rebase`，禁止把上游历史 merge 成网状。
3. 禁止 `git push --force` 到 `main` / `origin/main`；个人分支如需强推，用 `--force-with-lease`。
4. 上游同步期间产生的备份分支命名为 `backup/pre-sync-<yyyymmdd>`，同步验证通过后删除。

## 3. 下游修改的优先级

按此顺序选择实现方式，**优先靠后的方案必须写明理由**：

1. **配置 / 环境变量**：`config` dict、`TRADINGAGENTS_*` 环境变量、`run_config()` 作用域。
2. **Adapter**：实现上游已有契约（如 vendor 函数签名、`BaseLLMClient`），在自有模块中适配。
3. **依赖注入 / 组合**：构造上游对象时传入自己的实现；包装而非改写。
4. **扩展接口注册**：运行时注册到上游的注册表（如 `VENDOR_METHODS`）。
5. **最小上游补丁**：只改必须改的行，单独一个提交，登记到 `docs/UPSTREAM_DELTA.md`。
6. **上游文件复刻（copy & fork）**：仅当 5 不可行，且必须写明漂移风险与回归测试。

每一条"上游代码修改"都必须满足：

- 有独立 commit，commit message 前缀 `upstream-patch:`；
- 在 `docs/UPSTREAM_DELTA.md` 登记：改了哪个文件、为什么、上游是否已有相关 PR/issue、冲突风险；
- 有对应测试（上游测试或 `tests/downstream/` 下的测试）；
- 补丁尽可能小、局部、无语义重构，便于 rebase 时人工重放。

## 4. 目录约定

- **上游代码**（`tradingagents/`、`cli/`、`tests/`、`main.py`、`pyproject.toml`、`README.md` 等）
  视为"外部依赖源码"，不做风格化重排、不重命名、不搬移。
- **下游代码**放在独立顶层包，不要塞进 `tradingagents/`：

```
tradingagents_cn/      # A 股扩展（自有 vendor / agent / graph / 交易日历 / CLI）
tests/downstream/      # 下游测试（pytest marker: downstream）
docs/                  # 下游文档（本套规范）
```

- 下游测试必须自包含：不得依赖真实网络、真实 API key；网络类测试标记 `integration`。
- 下游代码只能通过**公开 API** 访问上游（`tradingagents.*` 的模块级函数/类）；
  依赖上游私有细节（下划线开头的内部状态、硬编码常量）必须在 `docs/UPSTREAM_DELTA.md`
  的"脆弱耦合"栏登记，并附一条测试以便在同步时第一时间发现破坏。

## 5. A 股领域的硬约束（写代码前先读）

- 一个交易日 = 09:30–11:30 / 13:00–15:00（北京时间），**必须**用交易日历判断，不要用自然日。
- T+1 交收、涨跌停（主板 10%、创业板/科创板 20%、ST 5%）、最小 100 股整手、停牌。
- 财报口径为中国会计准则（CAS），**不能**把 SEC EDGAR / 美式字段直接套到 A 股；
  单位是人民币元/万元/亿元，需显式换算，不要沿用上游美股单位假设。
- 复权方式（前复权/后复权/不复权）必须显式声明；跨复权口径比较价格视为 bug。
- 数据源（Tushare/AkShare/交易所官网等）均有速率限制与授权条款，token 只放 `.env`，
  不写入仓库、不写入日志、不写入报告。

## 6. 测试与验证

```bash
# 上游全量测试（默认排除 integration）
.venv/bin/python -m pytest -q

# 只跑下游测试
.venv/bin/python -m pytest -q tests/downstream

# 上游 + 下游，含联网测试（需要 key，慎用）
.venv/bin/python -m pytest -q -m "not integration"

# 代码风格（上游 ruff 配置：line-length 100，py311）
.venv/bin/python -m ruff check .
```

- 提交前**必须**跑一次全量测试，并在 commit message 或 PR 描述里贴结果
  （例如 `pytest: 1412 passed, 1 skipped`）。
- 新增下游功能必须新增测试；修改上游补丁必须有覆盖该补丁的测试。
- 测试失败时不允许 `-k` 跳过或 `xfail` 掩盖，除非写明原因并登记为已知问题。
- 本仓库 `.venv` 已是可用环境（Python 3.13 + 已装运行依赖）；若缺 `pytest`，用
  `.venv/bin/python -m ensurepip --upgrade` 后 `pip install -i https://pypi.org/simple "pytest>=8.0" "pytest-subtests>=0.13"`
  （默认的清华镜像可能返回 403）。

## 7. 提交规范

```
<type>(<scope>): <subject>

<body: 为什么改、怎么改、影响面>

Refs: D-0003            # 下游台账编号（docs/UPSTREAM_DELTA.md）
Tests: pytest -q → 1420 passed, 1 skipped
```

- `type`: `feat` / `fix` / `docs` / `chore` / `test` / `refactor` / `upstream-patch`。
- 一个提交只做一件事；下游改动不要和上游补丁混在同一提交里。
- 每个下游提交必须在 `docs/UPSTREAM_DELTA.md` 登记（编号 `D-xxxx`），包含 commit hash、
  触碰的上游文件（如有）、rebuild 冲突风险。

## 8. 上游同步

标准流程见 `docs/UPSTREAM_SYNC.md`。要点：

1. `git fetch upstream --tags`；
2. 先建备份分支 `backup/pre-sync-<date>`；
3. `git rebase upstream/main`，冲突优先保留上游语义，再重放下游 hunk；
4. 跑全量测试（下游测试是同步的"冒烟闸门"）；
5. 打 tag `sync/YYYYMMDD`，更新 `docs/UPSTREAM_DELTA.md` 的基线章节。

## 9. 明确禁止

- ❌ 直接 `git merge upstream/main` 污染 `main` 的线性历史。
- ❌ 为了"跑起来"就地改上游代码而不登记、不测试。
- ❌ 大规模重构上游（格式化、重命名、搬目录、换依赖版本）。
- ❌ 提交 `.env`、token、API key、真实持仓/交易记录。
- ❌ 覆盖、删除、reset 用户已有的未提交工作。
- ❌ 在没有明确需求时启动 A 股功能开发（本阶段只做工程基础）。
