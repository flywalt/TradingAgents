# B4_INTERACTION_SPEC.md — Web 接入规范（自审后修订版）

> 状态：**实现前定稿**。读者是没参与本项目的工程师，照着即可实现。
> 本文所有上游行为均与代码核对过；与代码冲突处以本文「决策记录」（§13）为准，并说明理由。

## 0. 范围

- **做**：局域网单用户 Web；一次分析 = 一个后台任务；表单 → 进度 → 报告 → 历史。
- **不做**：多用户/权限、回测 UI、记忆页、模型/密钥选择、任务取消、token 级流式、报告编辑、**加密/期货等非股票资产**。
- **不改上游**：新增顶层包 `tradingagents_web/`；上游文件零修改；依赖只进 `requirements-downstream.txt`。

## 1. 上游契约（核对后的准确版本）

```
analyze: ticker/date/analysts → config → 目录 → (可选)checkpoint
  → stream_run → 成功: record_decision(记忆) + clear_checkpoint_on_success()
  → rating = run_rating(最终 state)  # 五档 或 REVIEW("读不出"，非第六档)
```

| 输入 | 约束 |
| --- | --- |
| ticker | 必填；**Web v1 只支持股票**（`asset_type="stock"`） |
| date | `YYYY-MM-DD`；上游只校验"≤ 今天"，Web 另加下限 1990-01-01 |
| analysts | ≥1，子集 `market/social/news/fundamentals` |
| portfolio | 可选 `PortfolioContext`（`cash/currency/positions[]`）；**不提供 ≠ 空仓** |
| checkpoint | 服务端配置；Web 注入 thread_id，正文不暴露 |
| 模型/供应商/密钥 | 环境变量；**不进浏览器** |

**产出（上游默认）**：`save_reports()` 不传 `save_path` 时写入
`<results_dir>/reports/<ticker>_<时间戳>/`（`trading_graph.py:288`）。
Web **必须显式传 `save_path`**，否则无法按任务定位。

Web 的运行目录（**本规范定义**）：

```
<results_dir>/<safe_ticker>/<date>/runs/<run_id>/
├── report/                 # save_reports(save_path=...) 的目标
│   ├── 1_analysts/ … 5_portfolio/  complete_report.md/html
│   └── run_metadata.json   # 仅 CN profile（子类写入）
├── job.json                # Web 写入：请求参数 + profile + 版本 + 评级
└── web.log                 # Web 写入：异常堆栈、耗时（不进事件流）
```

- `<results_dir>` 取自 `graph.config["results_dir"]`（**由 factory 按 profile 决定**，Web 不覆盖）；
- 同标的同日期重跑 → **新 run_id 目录**，不覆盖历史（上游 `write_report_tree` 会清理目录内旧文件，
  所以每次运行必须独立目录）；
- `message_tool.log` **不由 Web 产生**（它是 CLI 显示层的产物），不在本规范输出清单内。

## 2. 包结构与依赖

```
tradingagents_web/
├── __main__.py   # python -m tradingagents_web，uvicorn 单 worker
├── app.py        # create_app、路由、鉴权、模板
├── db.py         # SQLite schema + PRAGMA user_version 迁移
├── jobs.py       # CRUD、状态迁移、事件、启动恢复
├── worker.py     # 单线程队列 + 执行循环
├── runner.py     # 任务 → build_graph → 回调/values → 事件 → 保存
├── errors.py     # 异常 → category/message/action
├── security.py   # token、cookie、路径白名单
├── checkpoints.py# 按标的清理检查点（脆弱耦合，见 §8）
├── templates/ static/
```

依赖 `fastapi`、`uvicorn[standard]`、`jinja2`；无 Node；不加 console_script。

## 3. 数据模型（SQLite，单库）

**单库路径**：`TRADINGAGENTS_WEB_DB`，默认 `~/.tradingagents/web/state.db`。
**不放在 `<results_dir>` 下**：results 目录按 profile 分叉，会把历史拆成两个库。

```sql
runs(
  id TEXT PRIMARY KEY, symbol TEXT, market TEXT, profile TEXT,
  trade_date TEXT, analysts TEXT,        -- JSON array
  language TEXT, strict INTEGER,
  portfolio_json TEXT,                   -- 已验证的 JSON；NULL=未提供
  status TEXT,                           -- queued|running|succeeded|failed
  rating TEXT,                           -- 五档|REVIEW|NULL
  error_category TEXT, error_message TEXT,
  run_dir TEXT, report_path TEXT,
  created_at TEXT, started_at TEXT, finished_at TEXT
);
events(id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, seq INTEGER,
       kind TEXT, payload TEXT, created_at TEXT);
CREATE INDEX idx_runs_status ON runs(status, created_at);
CREATE INDEX idx_runs_symbol ON runs(symbol, trade_date);
CREATE UNIQUE INDEX idx_events ON events(run_id, seq);
```

- 启动恢复：`running` → `failed(interrupted)`；`queued` 按 `created_at` 重新入队。
- 事件上限 5,000/任务，超出丢最旧的非状态事件。
- `report_path` 存的是内核 `save_reports()` 的返回值（规范产物 `complete_report.md`）。
  Web 打开报告时必须**优先取同名 `.html` 兄弟文件**（内核同目录写出）；只有 HTML 缺失时才按
  `text/plain` 回退。把 markdown 当成 `text/html` 发出去，浏览器会渲染成一大段无格式文本。
- 事件写入必须可跨线程：LangGraph 的并行分支在线程池中执行，回调会并发写 `events` 表。
  `jobs.append_event()` 在锁内完成「读 seq + 插入 + 提交」，否则会撞 `(run_id, seq)` 唯一索引
  或读到空结果，直接让任务失败。

## 4. 状态机与 worker

```
POST /api/runs → 校验 → INSERT(queued) → put(id) → 202 {id, position}
worker: running(started_at) → execute → succeeded | failed
```

- 并发：1 运行 + 3 排队；满 → `409 queue_full`。
- **不复用 Graph**：每任务 `build_graph()`（与 CLI 一致，避免 checkpoint/配置串扰）。
- 不自动重试；"重新运行"生成新 id。
- 进程退出：`running` 标 `failed(interrupted)`；不自动续跑。

## 5. 执行序列（`runner.py`，与上游一致）

```python
profile = select_profile(symbol=job.symbol, market=job.market)   # 仅用于校验/展示
graph   = build_graph(job_overrides, symbol=job.symbol, market=job.market)
# ↑ 必须传原始 overrides；factory 以 symbol/market 为准选择 profile
config  = graph.config
state   = graph.create_run_state(job.symbol, job.trade_date,
                                 asset_type="stock", portfolio=portfolio)
args    = graph.propagator.get_graph_args(callbacks=[progress])
tid     = graph.begin_checkpoint(job.symbol, job.trade_date, "stock", portfolio) if config["checkpoint_enabled"] else None
if tid: args.setdefault("config", {}).setdefault("configurable", {})["thread_id"] = tid
final = {}
try:
    for _messages, chunk in graph.stream_run(state, **args):
        if isinstance(chunk, dict): final.update(chunk)     # values 是累积 state
        progress.emit_from_callbacks()                       # 见 §5.1
    graph.save_reports(final, job.symbol, save_path=run_dir/"report")   # 先落盘
    graph.record_decision(final, job.trade_date, job.symbol)            # 再写记忆
    graph.clear_checkpoint_on_success(job.symbol, job.trade_date, "stock", portfolio)
finally:
    if tid: graph.end_checkpoint()
rating = run_rating(final)                                   # 五档 or REVIEW
```

- **顺序偏离 CLI**：CLI 先记忆后报告；Web 先报告后记忆——报告写失败时不应留下"有决策无报告"的记忆条目。
- `portfolio` 必须同时传给 `create_run_state` / `begin_checkpoint` / `clear_checkpoint_on_success`
  （它的 fingerprint 参与 checkpoint 签名）。
- 脏工作区 + `checkpoint_enabled` → `build_graph` 抛 `RuntimeError` → `config_blocked`（见 §10）。
- `report_write` 失败：`failed(report_write)`，评级仍写入 DB。

### 5.1 进度事件来源（**回调，不靠 tasks**）

上游 `stream_run` 只在子图**完成后**产出 task chunk，且顶层 task 被丢弃（`trading_graph.py:418-436`），
因此节点开始/结束**只能**来自 callback：

- `on_chain_start/end` 读 `metadata["langgraph_node"]`；
- 只映射**上游节点词表**（`graph/setup.py`）：`Market Analyst`、`Sentiment Analyst`、`News Analyst`、
  `Fundamentals Analyst`、`Memory Log`、`Bull Researcher`、`Bear Researcher`、`Research Manager`、
  `Trader`、`Aggressive Analyst`、`Conservative Analyst`、`Neutral Analyst`、`Portfolio Manager`；
- 子图内的 `agent` / `tools` / `wrap_up` 不单列，归属到其父分析师（由 `langgraph_checkpoint_ns` 前缀判定）；
- 其余节点（模型、工具）忽略。

事件：

| 事件 | 触发 | payload |
| --- | --- | --- |
| `run.started` | worker 开始 | `{symbol, date, profile}` |
| `node.started/finished` | 回调 | `{node}` |
| `report.ready` | `values` 首次出现 truthy 的 `*_report` / `investment_plan` / `trader_investment_plan` / `final_trade_decision` | `{key}` |
| `run.finished` | 成功 | `{rating, report_url, final: true}` |
| `run.failed` | 异常 | `{category, message, final: true}` |

**v1 不推 message 文本**：来源里的 agent 归属已被上游丢弃，且推送 prompt 内容有泄漏风险。

## 6. HTTP API

除 `/healthz` 外均需鉴权。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/preview?symbol=&market=` | 200 `{symbol, market, profile, name}`；400 `{error}` |
| POST | `/api/runs` | 202 `{id, position}`；400/409 |
| GET | `/api/runs/{id}` | 状态、评级、错误、报告 URL |
| GET | `/api/runs` | 过滤 `symbol/status/rating` + 分页 |
| GET | `/api/runs/{id}/events` | SSE（`Last-Event-ID` 补发） |
| POST | `/api/runs/{id}/rerun` | 202 新 id |
| POST | `/api/checkpoints/clear` | `{symbol}` → `{cleared}`（见 §8） |

页面：`/`、`/runs/{id}`、`/history`、`/runs/{id}/report`、`/runs/{id}/files/{name}`。

### 6.1 校验（服务端权威）

| 字段 | 规则 | category |
| --- | --- | --- |
| symbol | 非空 ≤20、无路径字符；`select_profile` 成功 | `symbol_ambiguous`/`symbol_conflict`/`symbol_invalid` |
| date | ISO，`1990-01-01 ≤ date ≤ 今天`（下限是 Web 规则） | `bad_date` |
| analysts | 非空、子集 | `no_analysts`/`unknown_analyst` |
| language | `English`/`中文` | `bad_language` |
| strict | 仅 `profile=CN_A_SHARE` | `strict_not_allowed` |
| portfolio | `PortfolioContext.model_validate`；`null` 与 `{}` 语义不同 | `portfolio_invalid` |
| asset | v1 仅股票；crypto/期货 → 400 | `unsupported_asset` |

## 7. SSE

- 每条 `id: <seq>`、`retry: 3000`；`data:` 单行 JSON `{seq, kind, at, ...}`。
- 心跳 `: ping` 每 10s（不占 seq）。
- 重连带 `Last-Event-ID` → 从 SQLite 补发 `seq > id`。
- 结束发 `final: true` 后关流；30s 空闲关流。

## 8. 安全

1. `TRADINGAGENTS_WEB_TOKEN` 缺失 → 拒绝启动（`--dev-no-token` 仅允许 127.0.0.1）。
2. `compare_digest`；`HttpOnly; SameSite=Lax` cookie；失败 401。
3. 状态变更仅 POST；带 `X-Requested-With: fetch`。
4. 文件访问：`resolve()` 必须在 `run_dir` 内，扩展名 ∈ `{.html,.md,.json,.log}`；
   报告 HTML 以 `Content-Security-Policy: sandbox; default-src 'none'; style-src 'unsafe-inline'` 返回。
5. 日志脱敏：token/key/请求头不入库、不落日志。

**检查点清理（脆弱耦合）**：上游没有"按标的清理"的公开 API（`clear_checkpoint` 需要 ticker+date+签名，
签名是整份配置的哈希）。Web 的 `checkpoints.py` 自行构造
`<data_cache_dir>/checkpoints/<safe_ticker>.db`（含 `-wal/-shm`）删除，并：
- 在 `docs/UPSTREAM_DELTA.md` 脆弱耦合表登记；
- 由 `tests/downstream/test_web_checkpoints.py` 锁定路径规则。

## 9. 页面（移动优先，服务端渲染）

| 页面 | 内容 |
| --- | --- |
| `/` | 表单（symbol+预览、date、analysts、语言、strict 仅 CN、portfolio 折叠）+ 最近 10 条 |
| `/runs/{id}` | 状态、**流程图**、节点时间线、评级 / REVIEW 警告、报告入口、错误卡片（category+action） |
| `/runs/{id}/report` | 沙箱内 HTML（按运行语言呈现）；上方显示 profile、版本、`job.json` 摘要 |
| `/history` | 过滤 + 分页 |

合规展示：`Buy/Overweight/Hold/Underweight/Sell` → **乐观/中性/审慎**，固定"仅供研究，不构成投资建议"。
只改展示，不改报告正文。

### 9.1 报告呈现层（本地化）

报告在**服务时**本地化，磁盘产物保持内核原样：

- 内核 `save_reports()` 返回 `complete_report.md`，并在同目录写 `complete_report.html`；路由优先发 HTML
  兄弟文件，只有 markdown 时才按 `text/plain` 发（绝不把 markdown 谎称 `text/html`）。
- `tradingagents_web/report_page.py::present(html, language)` 在 `language` 为中文时，按**允许清单**
  替换固定标签（`<html lang>`、`Analysis of …`、7 个 `<dt>`、`Top`、5 个章节标题与序号、评级中文名）。
  正文一个字不动；英文运行原样返回。
- 与上游标记的耦合登记在 `docs/UPSTREAM_DELTA.md` 的脆弱耦合栏，由
  `test_the_markup_we_match_is_still_produced_upstream` 在同步时先报错。

### 9.2 流程图（拓扑与点亮）

- 拓扑与两套坐标由 `tradingagents_web/progress_graph.py::topology(analysts)` 计算（宽屏/窄屏各一套），
  因此"节点不重叠、都在画布内、边两端存在、未选分析师不画"可以写成测试。
- 边语义：`flow`（交接）、`debate`（双向来回）、`bypass`（记忆检索旁路）。
- 画面由 `static/run-page.js` 驱动：`node.started → active`、`node.finished → done`、`run.failed → failed`；
  上游完成而下游开始时交接边流动；辩论对之间来回；同名节点重复开始即"第 n 轮"。
- **事件仍是唯一事实来源**：图只反映 `events` 表。历史记录若只有 `node.started` 没有 `node.finished`
  （`node.finished` 的修复之前产生的运行），终态一律按 `done` 呈现，不留永远"运行中"的节点。
- 运行页脚本集中在 `static/run-page.js`，页面仍只有一个 `<script>`（`test_each_page_has_exactly_one_script_block`）。

## 10. 错误分类

| category | 消息要点 | 下一步 |
| --- | --- | --- |
| `symbol_*` / `bad_date` / `no_analysts` / `unknown_analyst` / `bad_language` / `portfolio_invalid` / `unsupported_asset` | 输入错误 | 修正后重试 |
| `strict_not_allowed` | 严格模式仅 A 股 | 关闭 strict |
| `queue_full` | 队列已满（1 跑 + 3 排） | 稍后 |
| `config_blocked` | 检查点开启但工作区有未提交修改 / profile 冲突 | 清理工作区或关检查点 |
| `llm_auth` / `llm_quota` | 模型凭证/限流 | 检查 `.env`；稍后 |
| `vendor_unconfigured` / `vendor_unavailable` / `no_data` | 数据源未配置 / 暂不可用 / 无数据 | 配置 token；换日期或标的 |
| `report_write` | 磁盘/权限 | 检查目录 |
| `interrupted` | 服务重启 | 重新运行 |
| `internal` | 未预期 | 看 `web.log` |

## 11. 配置与隔离

- Web **不预合并配置**：把原始 overrides 交给 `build_graph(overrides, symbol=…, market=…)`，
  由 factory 决定 profile、vendor 链与 `results_dir`（CN → `profile-cn`）；
- 浏览器只能覆盖 `language`、`strict`；
- 单库固定路径；运行目录按 profile 落在各自 `results_dir` 下；
- 与 CLI 一致：不共享 Graph、不共享进程级默认配置。

## 12. 测试计划（离线）

| 层 | 用例 |
| --- | --- |
| 校验 | 每个 category 至少 1 例（`0700` 歧义、`US+600519.SS` 冲突、strict on US、crypto 拒绝） |
| 鉴权 | 无/错 token 401；cookie；`--dev-no-token` 仅 127.0.0.1 |
| 任务 | 入队→running→succeeded（假 Graph）；失败分类；队列满 409；rerun 新 id |
| 恢复 | `running→failed(interrupted)`；`queued` 重排 |
| SSE | seq 顺序、`Last-Event-ID` 补发、心跳、结束关闭 |
| 安全 | 路径穿越拒绝；CSP 头；日志无 token |
| 视图 | 首页/详情/历史 200；REVIEW 警告；合规术语 |
| 检查点 | 按 symbol 删除 `*.db/-wal/-shm`（脆弱耦合测试） |
| 隔离 | CN 与默认 profile 的 `run_dir` 在不同 results 根下 |
| 回归 | 预合并配置 + 非 CN symbol 不得被误判（factory 优先级） |

验收：手机浏览器完成 `600519.SH`；`0700.HK` 显示默认 profile 且无 strict；`0700` 报歧义；
刷新后历史仍在；无 token 401。

## 13. 决策记录（含自审修订）

| # | 决策 | 理由 |
| --- | --- | --- |
| 1 | Web 传**原始 overrides**；`build_graph` 以 symbol/market 覆盖配置里的 profile；同时修复 factory 优先级与 CLI/Batch 的同类缺陷 | 预合并的 CN 配置会让 `0700.HK`/`AAPL` 直接抛错（自审实测） |
| 2 | 每次运行独立 `run_dir`（含 run_id），显式 `save_path` | 上游默认时间戳目录不可按任务定位；复用目录会被 `write_report_tree` 清理 |
| 3 | 节点事件用 **callback**（`langgraph_node`），不用 `tasks` | `stream_run` 不产顶层 task，子图 task 仅在完成后出现 |
| 4 | 执行序列：stream → 合并 values → 保存报告 → 写记忆 → 清检查点；`finally` 关检查点 | 报告失败不应留下记忆条目；检查点必须成对释放 |
| 5 | v1 **不推 message 文本** | 上游已丢弃 agent 归属；推送 prompt 有泄漏风险 |
| 6 | 检查点清理按 symbol 删 DB，登记脆弱耦合 + 测试 | 上游无按标的清理 API |
| 7 | v1 仅股票；portfolio 透传到 state/checkpoint | `create_run_state` 有 `asset_type/portfolio` 参数，不传会静默丢失 |
| 8 | **单库**固定路径；运行目录按 profile 分离 | 库放 results 下会被 profile 分叉成两个历史 |
| 9 | 模型/密钥不进浏览器；无取消；无回测 | 范围控制；中断/重试需进程级设计 |
| 10 | 报告 HTML 用 CSP sandbox 返回 | 报告含模型输出，禁止脚本执行 |

## 14. 参考 TradingAgents-CN

采纳：错误分类器、SSE 心跳/重连、合规术语、历史过滤、排队可见性。
拒绝：Redis 队列、强制 MongoDB、SSE+WebSocket 双栈、三套 analysis service、Vue 构建、用户体系。


## 15. 与 kviewer 的长期对接（本阶段只埋钩子，不实现）

结论：**两个服务、一份契约**，不合并代码库。kviewer 负责"看"（K 线/资金面/自选），
本项目负责"判断"（研究/评级/记忆），持仓账本属于第三块，不塞进分析服务。

### 15.1 已核对的兼容点（kviewer 源码）

| 点 | kviewer 事实 | 我们的对齐方式 |
| --- | --- | --- |
| 符号格式 | `^\d{6}\.(SH|SZ|BJ)$`（`src/validation.ts`） | DB/API 一律 `600519.SH`（与我们的 `normalize` 一致） |
| 复权锚点 | qfq = `raw × f_row / f_base`，**base = 返回序列最后一行**（`kline.pure.ts`） | 链接必须带 `end=分析日`；否则历史报告与图上价格在除权后不一致 |
| 指标口径 | 前端算通达信 MA/MACD/KDJ | 我们 Python 算 13 个 TDX 指标 → 可做交叉校验 |
| 存储策略 | D1 存原始价+因子，读时现算 | 证明"自算复权"可行；未来审计级复现可参考 |

### 15.2 W1 必须埋的五个钩子（低成本、不可后补的）

| # | 钩子 | 实现 |
| --- | --- | --- |
| H1 | **稳定 URL** | `/runs/{id}` 与 `/runs/{id}/report` 永久不变，供外部长期链接 |
| H2 | **符号规范化** | DB `symbol` 与 API 一律 `<code>.<exchange>`；另存 `display_name` |
| H3 | **锚点入元数据** | `job.json` 必含 `data_as_of`（分析日）与 `qfq_anchor`（=分析日），跨系统展示有据 |
| H4 | **只读凭据与 CORS** | `TRADINGAGENTS_WEB_READ_TOKEN`（只读 `/api/runs*`）+ `TRADINGAGENTS_WEB_CORS_ORIGINS`（逗号分隔白名单） |
| H5 | **链接模板** | `KVIEWER_BASE_URL`（空=不显示）；生成 `#/kline?symbol=<symbol>&start=<报告起始>&end=<分析日>` |

### 15.3 不在本阶段做

- kviewer 反向调用我们的 API：Cloudflare Worker **不能直连局域网**，需要 Tunnel + 只读 token，
  属于独立工程（W2 以后）。
- 持仓/盈亏账本：第三块产品，独立建模与测试，不并入分析服务。
- 以 kviewer 作为数据源：当前 Tushare 直连更简单；仅在 Tushare 不可用时再评估。

### 15.4 验收补充

W1 额外断言：H3 的 `job.json` 含 `data_as_of`/`qfq_anchor`；H4 的只读 token 能读 `/api/runs` 但不能写；
H5 在配置了 `KVIEWER_BASE_URL` 时报告页出现正确 `end=分析日` 的链接。
