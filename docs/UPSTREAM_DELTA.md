# UPSTREAM_DELTA.md — 上游基线与下游差异台账

本文件有两个作用：

1. **基线记录**：当前 `main` 基于哪个上游提交，测试基线是多少。
2. **差异台账**：每一个下游提交（尤其是触碰上游文件的）都登记在此，供同步时逐条重放与评审。

---

## 1. 上游基线（当前）

| 项目 | 值 |
| --- | --- |
| 上游仓库 | https://github.com/TauricResearch/TradingAgents |
| 版本 | **v0.7.1**（`tradingagents/__init__.py::__version__`） |
| Commit | `c4544913a14ed3df5f1ed7b9e8483270ce20682a` |
| Commit 说明 | `Merge pull request #1613 from TauricResearch/v0.7.1` |
| Commit 时间 | 2026-10-27 01:38:40 -0700 |
| `git describe` | `v0.7.1` |
| 本地历史 | 515 个提交；**完整克隆**（无 `.git/shallow`）；标签 `v0.1.0` … `v0.7.1` |
| 记录日期 | 2026-10-31 |

### 基线验证（2026-10-31 实测）

| 项目 | 结果 |
| --- | --- |
| 工作区状态 | `git status` 干净，无未提交修改 |
| 本地 `main` 与上游 `main` | 一致（`c454491`） |
| 未推送提交 | 无 |
| 解释器 | `.venv/bin/python` = Python 3.13.12 |
| 测试命令 | `.venv/bin/python -m pytest -q` |
| 测试结果 | **1412 passed, 1 skipped, 1 deselected, 100 subtests passed**（33.84s） |
| 跳过原因 | `test_bedrock_provider.py`：未安装可选依赖 `langchain_aws` |
| 备注 | `.venv` 原本未装 `pytest`，本次用 `ensurepip` + `pip install -i https://pypi.org/simple pytest pytest-subtests` 补齐（仅本地环境，不进仓库） |

### 环境注意

- 默认 pip 索引（清华镜像 `pypi.tuna.tsinghua.edu.cn`）返回 **403**，安装需加 `-i https://pypi.org/simple`。
- 系统未安装 `gh` CLI；GitHub 操作需网页或自行安装。

---

## 2. 下游差异台账

**登记规则**（见 `AGENTS.md` 第 7 节）：每个下游提交一行；触碰上游文件的必须写"补丁理由 / 冲突风险"。
"上游文件"= `tradingagents/**`、`cli/**`、`tests/**`、`main.py`、`pyproject.toml`、`README.md`、`CHANGELOG.md`、
`.github/**`、`Dockerfile`、`docker-compose.yml`、`requirements.txt`、`.env.example`。

| 编号 | Commit | 类型 | 内容 | 触碰上游文件 | 冲突风险 | 测试 |
| --- | --- | --- | --- | --- | --- | --- |
| D-0001 | `ffab0e2` `docs(governance)` | docs | 建立 `AGENTS.md` + `docs/` 四份规范（本文件、`UPSTREAM_SYNC.md`、`ARCHITECTURE.md`、`EXTENSION_POINTS.md`） | 无（纯新增 5 个文件） | 无 | 不涉及代码，跑全量测试确认无副作用（1412 passed） |
| D-0002 | `d733340` `docs(sync)` | docs | 回填 rebase 演练结果、冲突探测结论与提交哈希 | 无 | 无 | 同上 |
| D-0003 | `7d626cd` `feat(downstream)` | feat | 下游骨架 `tradingagents_cn/`（注册/配置/代码规范化/交易日历/交易规则/适配器公共层）+ `tests/downstream/` 110 个测试（含**同步保险丝**） | 无 | 无 | 全量 `1522 passed, 1 skipped`；`ruff check .` 全绿 |
| D-0004 | 本条提交 `feat(tushare)` | feat | Tushare 行情 vendor（`get_stock_data`，含 `cn_adjust` 复权）+ `trade_cal` 交易日历 + `docs/TUSHARE.md` + 16 个离线测试 + 2 个 `integration` 冒烟 | 无 | 无 | 全量 `1538 passed, 1 skipped`；integration 需 `TUSHARE_TOKEN` |

四条下游提交合计新增代码与文档，**0 行上游改动**。下游与上游的唯一耦合是文档里登记的"脆弱耦合"，
现在由 `tests/downstream/test_sync_guard.py`（12 组断言）机械锁定。

### 2.1 已实现的下游文件（D-0003）

| 文件 | 作用 |
| --- | --- |
| `tradingagents_cn/register.py` | `activate()` / `register_vendor()` / `reset()`：幂等注册到 `router.VENDOR_METHODS`，可完整回滚 |
| `tradingagents_cn/config.py` | `cn_*` 配置键、有序 vendor 链（`tushare,yfinance`）、`TRADINGAGENTS_CN_*` 环境变量、纯函数合并 |
| `tradingagents_cn/symbols.py` | A 股代码规范化（`.SH/.SZ/.BJ`）、Yahoo/Tushare 双向外形、交易所前缀推断 |
| `tradingagents_cn/calendar.py` | 交易日历（周末 + 可注入节假日），`set_default_calendar()` 供 vendor 安装真实日历 |
| `tradingagents_cn/trading_rules.py` | 涨跌停比例与限价（Decimal 半进位）、整手规则、T+1 交收 |
| `tradingagents_cn/vendors/common.py` | 适配器公共层：`require_ashare` / `require_token` / `adjustment` / `no_rows` |
| `tradingagents_cn/vendors/tushare/` | 行情 vendor：`stock.py`（日线 + `cn_adjust` 复权、手/千元→股/元）、`calendar.py`（`trade_cal` → 交易日历）、`client.py`（惰性鉴权 + 可注入假客户端） |
| `tests/downstream/test_sync_guard.py` | 脆弱耦合保险丝（router 表、错误类型、state key、agent 工厂、图注入点、评级、报告、provider） |

> 目前**没有任何上游代码修改**（无 `upstream-patch:` 提交）。这是有意的：本阶段的结论是
> "数据层扩展零改动可行，agent/prompt/报告补丁暂缓"（见 `docs/EXTENSION_POINTS.md` 第 8 节）。

### 待实施的上游补丁（草案，未实施）

| 编号 | 目标文件 | 目的 | 状态 |
| --- | --- | --- | --- |
| P1 | `tradingagents/dataflows/router.py` | 公开 `register_vendor()` 注册函数 | 草案 |
| P2 | `graph/analyst_execution.py`, `graph/setup.py`, `graph/trading_graph.py` | 可注入分析师规格/节点工厂 | 草案 |
| P3 | `agents/analysts/*.py` 等 | prompt 提升为模块级常量 | 暂缓 |
| P4 | `tradingagents/reporting.py` | 报告章节表可扩展 | 草案 |
| P5 | `agents/tools.py` | 新工具进上游 analyst | 暂缓 |

---

## 3. 脆弱耦合清单

下游会依赖的上游"非正式 API"。每次同步后必须确认这些仍成立（下游 `tests/downstream/test_sync_guard.py` 负责锁定）。

| 耦合点 | 位置（v0.7.1） | 为什么必须依赖 | 破坏时症状 | 保险措施 |
| --- | --- | --- | --- | --- |
| `VENDOR_METHODS` / `TOOLS_CATEGORIES` 结构 | `dataflows/router.py` | 唯一的 vendor 注册点（无公开 API） | A 股数据全部落到 `NO_DATA_AVAILABLE` | 冒烟测试：注册后 `route_to_vendor` 能命中 |
| vendor 函数位置参数签名 | 同上 | fallback 链按位置传参 | 参数错位、静默返回错误数据 | 契约测试：每方法对假数据断言 |
| `dataflows/errors.py` 错误类型语义 | `dataflows/errors.py` | router 靠类型决定"换下一家/放弃" | fallback 失效或异常冒到模型 | 测试：适配器抛正确类型 |
| `AgentState` 字段名 | `agents/state.py` | A 股上下文注入与分析产物读取 | 报告字段为空、agent 拿不到上下文 | 冒烟测试断言 key 集合 |
| `AnalystNodeSpec` / `ANALYST_NODE_SPECS` | `graph/analyst_execution.py` | 自建图复用分析师规格 | 自建图无法生成节点 | 同上 |
| `create_*` 工厂签名 `(llm) -> node(state) -> dict` | `agents/**` | 自建图直接复用节点 | 图编译期 TypeError | 图冒烟测试 |
| `TradingAgentsGraph.resolve_instrument_context` | `graph/trading_graph.py:117` | 唯一的横切 prompt 注入缝 | A 股事实注入失效 | 测试覆写后 prompt 含关键字 |
| `TradingAgentsGraph._run_signature`（**私有**） | `graph/trading_graph.py:140` | checkpoint 线程 ID 需含下游配置 | resume 命中旧形状检查点 | 测试：配置变 → ID 变 |
| `_SECTIONS` 报告结构 | `reporting.py` | 若自建 writer 需对齐 | 报告缺失/格式分裂 | 报告渲染测试 |
| `rating.RATINGS_5_TIER` / `REVIEW` | `agents/rating.py` | 全链路评级契约 | 记忆/回测统计口径分裂 | 复用即可，勿改 |

---

## 4. 同步记录流水

| 日期 | 动作 | 从 | 到 | 结果 |
| --- | --- | --- | --- | --- |
| 2026-10-31 | 建立基线、添加 `upstream` remote、演练 rebase | `v0.7.0` (`e8f5503`) | `v0.7.1` (`c454491`) | ✅ 0 冲突，1412 passed。详见 `docs/UPSTREAM_SYNC.md` 第 6 节 |

### 4.1 上游区间风险提示（v0.7.0 → v0.7.1，22 提交 / 37 文件）

- 上游**本次改动**了补丁候选文件：`tradingagents/reporting.py`（P4）、`tradingagents/agents/tools.py`（P5）、
  `tradingagents/graph/trading_graph.py`、`tradingagents/dataflows/date_window.py`。
- 上游**本次未改动**：`dataflows/router.py`（P1）、`graph/setup.py`、`graph/analyst_execution.py`、
  `agents/state.py`、`default_config.py`（P2 相关）。→ 补丁优先落在这些文件，冲突概率最低。
- 实测结论：冲突按**行**判定，同一文件内相隔 ≥3 行的改动可自动合并；只有下游改制的行被上游重写时才冲突。
