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
| D-0004 | `8d0ffb6` `feat(tushare)` | feat | Tushare 行情 vendor（`get_stock_data`，含 `cn_adjust` 复权）+ `trade_cal` 交易日历 + `docs/TUSHARE.md` + 16 个离线测试 + 2 个 `integration` 冒烟 | 无 | 无 | 全量 `1538 passed, 1 skipped`；integration 需 `TUSHARE_TOKEN` |
| D-0005 | 本条提交 `test(tushare)` | test/docs | 真实冒烟记录（单位/复权/日历/北交所实测）+ 北交所 integration 用例 + 2 条已知限制 | 无 | 无 | offline `1538 passed`；`-m integration` → **3 passed** |
| D-0006 | `8fd4a77` `feat(data)` | feat | `units.py`（元→亿元/手→股/千元→元）+ `pit.py`（公告日前视过滤、同期取最新公告） | 无 | 无 | 13 passed |
| D-0007 | `4ec11dc` `feat(data)` | feat | `cache.py`（内存+磁盘 TTL、原子写）+ 客户端限流 | 无 | 无 | 9 passed |
| D-0008 | `5fb37c5` `feat(indicators)` | feat | 13 个指标本地计算（同一份 qfq 日线）+ `fetch_bars()` 抽取 | 无 | 无 | 7 passed |
| D-0009 | `b19eb63` `feat(fundamentals)` | feat | 概况/估值/财务摘要（估值按日、财报按公告日） | 无 | 无 | 8 passed |
| D-0010 | `d83adc2` `feat(statements)` | feat | CAS 三表（合并报表、防前视、亿元、YTD 标注） | 无 | 无 | 9 passed |
| D-0011 | `1857fdf` `feat(data)` | feat | 资金面/指数/身份/快照接口 + `register_category()` | 无 | 无 | 10 passed |
| D-0012 | `43dc4a6` `feat(config)` | feat | `cn_strict_ashare` 单 vendor 链 + 三类 vendor 链扩展 | 无 | 无 | 全量 1599 passed |
| D-0013 | `51487e9` `test(data)` | test/docs | 9 个真实接口冒烟 + `docs/ASHARE_DATA.md` | 无 | 无 | `-m integration` → 9 passed |
| D-0014 | `917d1d4` `chore(env)` | chore | uv 管理环境 + `requirements-downstream.txt` + `requirements-lock.txt` + `docs/DEV_ENV.md` | 无 | 无 | `uv run pytest -q` → 1599 passed；integration 9 passed |
| D-0015 | `041b74a` `docs(plan)` | docs | A 股数据层设计文档（含 builder check 裁决）与实施计划 | 无 | 无 | 不涉及代码 |
| D-0016 | `8a03f73` `fix(data)` | fix | reviewer 修复：指数权重数据源、两融单位、f_ann_date 去重、缓存上限、env 优先级、指数/资金流单位 | 无 | 无 | 全量 1606 passed |
| D-0017 | 本条提交 `feat(indicators)` | feat | 通达信口径 13 指标（可切 stockstats）+ `cn_indicator_flavor` + 价格头写明复权锚点 | 无 | 无 | 全量 1619 passed；integration 9 passed |
| D-0018 | `5504440` `docs(research)` | docs | TradingAgents-CN 与上游的对照报告（5 条可借鉴 / 5 条不照搬） | 无 | 无 | 不涉及代码 |
| D-0019 | `67e64b0` `docs(agent)` | docs | `docs/AGENT_MAP.md`：12 个 agent 的输入/工具/A 股可达性 + B1–B4 批次 | 无 | 无 | 不涉及代码 |
| D-0020 | `f30a936` `docs(research)` | docs | 外部评审简报（补丁 vs 上游同步） | 无 | 无 | 不涉及代码 |
| D-0021 | `5009543` `docs(web)` | docs | `docs/WEB_PLAN.md`：局域网单用户、单 worker、服务端渲染 | 无 | 无 | 不涉及代码 |
| D-0022 | `5953058` `upstream-patch(snapshot)` | **上游补丁** | 快照工具改走 `route_to_vendor`：`agents/tools.py` -1/+3、`dataflows/router.py` +6 | `tradingagents/agents/tools.py`、`tradingagents/dataflows/router.py` | 中低：上游重写工具/router 表时需重放 ~9 行 | `test_snapshot_routing.py` + 上游全量 |
| D-0023 | `bc455bb` `feat(snapshot)` | feat | 注册 Tushare 版快照实现（签名对齐 4 个位置参数） | 无 | 无 | 同上 |
| D-0024 | `217b48c` `test(guard)` | test | Sync Guard 拆分 A/B/C + `cn_extension_version` 进入配置与 checkpoint 身份 | 无 | 无 | 38 passed |
| D-0025 | `64e537a` `feat(report)` | feat | 9 项运行元数据写入 md/json/html | 无 | 无 | 3 passed |
| D-0026 | `e1ee43d` `chore(sync)` | chore | 同步治理 v2 + `scripts/sync_upstream.sh` + `docs/UPSTREAM_BASE.md` | 无 | 无 | 脚本语法检查 |
| D-0027 | 本条提交 `upstream-patch(test)` | **上游补丁** | 端到端测试的『实际数据路径』断言跟随快照路由（2 行） | `tests/test_graph_end_to_end.py` | 低：一处集合字面量 | 上游全量 1654 passed |
| D-0028 | `211c690` `refactor(core)` | refactor | P0 修订：`bootstrap()` 与运行配置分离、自建 CLI/Batch、严格模式锁 `tool_vendors`、真实并发隔离测试 | 无 | 无 | 1675 passed |
| D-0029 | `06b7940` `feat(roi)` | feat | P1 修订：`namechange` PIT 名称、快照与行情同源校验、脏工作区禁止 checkpoint、元数据 11 字段 | 无 | 无 | 1675 passed |
| D-0030 | 本条提交 `docs(extension)` | docs | 扩展架构 v2.1 重写（层级按实际侵入性、兼容性表述、并发矩阵、严格模式、入口规则、L4a 取消行数门槛） | 无 | 无 | 不涉及代码 |
| D-0031 | 本条提交 `feat(insider)` | feat | `get_insider_transactions` → Tushare `stk_holdertrade`，按公告日过滤；默认 `tool_vendors` 定向到 `tushare,yfinance` | 无 | 无 | 新增 5 项离线 + 1 项 live |
| D-0032 | 本条提交 `feat(context)` | feat | 交易约束（涨跌停/T+1/整手，ST 不假设）注入 `instrument_context`；新增 `reference_price()` | 无 | 无 | 图接线 12 项 + 规则 14 项 |
| D-0033 | 本条提交 `docs(data)` | docs | `DATA_REQUIREMENTS.md`（news 只要标题+摘要+链接+时间；宏观/情绪/预测市场的替代验收标准） | 无 | 无 | 不涉及代码 |
| D-0034 | 本条提交 `docs(b3)` | docs | `B3_PROMPT_PLAN.md`：评测骨架先行 + TradingAgents-CN prompt 改动核对结论 | 无 | 无 | 不涉及代码 |
| D-0035 | 本条提交 `feat(markets)` | feat | `market.py`：`MarketProfile` + `UPSTREAM_DEFAULT`/`CN_A_SHARE` + 按交易所识别；`apply(profile=)` 与 `build_graph(market=,symbol=)` 分流；A 股规则仅在 CN profile 注入 | 无 | 无 | 新增 12 项多市场测试，全量 1697 passed |
| D-0036 | 本条提交 `docs(markets)` | docs | `MARKET_PROFILES.md`（设计/隔离/目录/10 项测试对照）+ 架构文档 v2.2 多市场节 | 无 | 无 | 不涉及代码 |
| D-0037 | 本条提交 `test(b3)` | test | Prompt 契约评测：记录型脚本模型捕获 12 节点 prompt，验证身份/规则/口径注入与美股隔离 | 无 | 无 | 新增 4 项，全量 1701 passed |
| D-0038 | 本条提交 `docs(audit)` | docs | `EXTENSIONS.md` 可审计清单 + `scripts/extension_inventory.py --check`（模块/测试/配置键/补丁缺失即失败） | 无 | 无 | 清单检查通过 |
| D-0039 | 本条提交 `test(b3)` | test | 黄金场景（工具真调用）：无数据哨兵不被补全、亏损带符号、涨停带板块幅度 | 无 | 无 | 新增 3 项，全量 1707 passed |
| D-0040 | 本条提交 `feat(macro)` | feat | 中国宏观接口（7 个序列，别名/单位/频率/点时窗）；CN profile `macro_data: tushare,fred`；LPR/10Y 显式拒绝 | 无 | 无 | 新增 8 项离线 + 1 live |
| D-0041 | 本条提交 `docs(b4)` | docs | 上游交互契约（交互问答/单次运行/输出物/状态）+ Web v1 表单、状态机、API、安全与验收 | 无 | 无 | 不涉及代码 |
| D-0042 | 本条提交 `docs(b4)` | docs | CN Web 层核对：采纳错误分类/SSE 心跳/合规术语/历史过滤；拒绝 Redis/Mongo/双栈/多 service | 无 | 无 | 不涉及代码 |
| D-0043 | `7865382` `fix(markets)` | fix | spec 自审发现：symbol/market 必须优先于配置里的 profile；CLI/Batch 不再预合并配置 | 无 | 无 | 1717 passed |
| D-0044 | `a048c65` `docs(b4)` | docs | 交互 spec 重写（8 项自审结论 + 13 条决策记录） | 无 | 无 | 不涉及代码 |
| D-0045 | 本条提交 `feat(web)` | feat | Web 外壳 W1：FastAPI + SQLite + 单 worker + SSE + 报告/文件服务 + kviewer 钩子；测试 37 个新增 | 无 | 无 | 全量 1744 passed |
| D-0046 | 本条提交 `feat(xueqiu)` | feat | 雪球 RSSHub：个股新闻接 `get_news`（CN 链 `xueqiu,yfinance`）、帖子/评论/热帖接口；`?key=` 鉴权、窗口过滤、HTML 清洗 | 无 | 无 | 10 项离线 + 2 项 live |
| D-0047 | 本条提交 `feat(cls)` | feat | RSSHub 公共层抽取 + 财联社电报（全市场雷达/公司事件流，按代码提取聚合） | 无 | 无 | 7 项离线 + 2 项 live |
| D-0048 | 本条提交 `feat(agent)` | feat | A 股情绪分析师（雪球评论/帖子/热帖）替换上游美股源；CN 图经 `graph/wiring.py` 重建 | 无 | 无 | 3 项新增，全量 1766 passed |
| D-0049 | 本条提交 `feat(agent)` | feat | 下游新闻分析师：上游四工具 + 预取 CLS 公司事件/雪球公告；CN 图同时替换 news 与 sentiment | 无 | 无 | 3 项新增，全量 1769 passed |
| D-0050 | 本条提交 `fix(agents)` | fix | 空结果标记 `NO_ITEMS`（本地语义）；SSE 子图 namespace 映射修复（Web 本地）；RSS 无历史写入文档 | 无 | 无 | 新增 3 项测试，全量 1772 passed |
| D-0051 | 本条提交 `fix(web)` | fix | 报告路由取 `.html` 兄弟文件（上游 `save_reports` 返回 `.md`）；事件写入加锁（并行分支线程池）；时间线补 `node.finished` 与中文标签；主题改为 paper 浅色 | 无 | 无 | 新增 7 项测试，全量 1779 passed |

十余条下游提交合计新增代码与文档，**0 行上游改动**。下游与上游的唯一耦合是文档里登记的"脆弱耦合"，
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
| `_analyst_graph()` + `DEBATE_PATH_MAP` / `RISK_ANALYSIS_PATH_MAP`（**私有**） | `graph/setup.py` | CN 图重建时复用分析师子图与条件边映射 | 上游改签名/改名 → 下图失败 | `test_upstream_compat` + `test_cn_sentiment_agent` |
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
