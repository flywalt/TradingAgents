# B4_INTERACTION_SPEC.md — 上游交互契约与 Web 接入设计

> 目的：先固定"上游怎么被使用、产出什么"，再设计 Web。所有条目均来自代码（`cli/`、`graph/`、`reporting.py`、`memory/`），不是推测。

## 1. 上游的交互流程（CLI 一条命令 = 一次分析）

```
tradingagents [analyze]
  ├─ 缺参数且有终端 → 交互问答：ticker → 资产类型(自动) → 日期 → 分析师(≥1)
  ├─ 缺参数且无终端 → 打印缺失的 TRADINGAGENTS_* 变量后退出
  ├─ 组装 config：环境变量 → 选择结果 → --checkpoint/--no-checkpoint 覆盖
  ├─ 目录：<results_dir>/<ticker>/<date>/ ，内含 reports/ 与 message_tool.log
  ├─ 重建 graph（如需 checkpoint）→ begin_checkpoint() 得 thread_id
  ├─ stream_run(initial_state)：stream_mode=["values","tasks"]
  │    逐节点推送：agent 状态(pending/running/completed)、messages、分析师的报告
  ├─ 成功：记录决策（memory log pending 条目）→ clear_checkpoint_on_success()
  └─ 收尾：rating=run_rating(final_state)（5 档或 REVIEW）
        ├─ REVIEW → 黄字警告"本次不构成仓位，需人工复核"
        └─ 询问/按 flags：是否保存报告、是否全文展示、是否生成 HTML
```

**关键语义**：一次运行是**分钟级**的同步过程；失败时 checkpoint 保留以便续跑；成功才清理。
`REVIEW` 不是第 6 档评级，是"读不出评级"的信号。

## 2. 输入清单（Web 表单要覆盖的）

| 输入 | 上游事实 | Web v1 处理 |
| --- | --- | --- |
| `ticker` | 必填；上游会做代码校验；资产类型自动识别（stock/crypto） | 必填；输入时调用预览接口显示**规范化代码 + 市场 Profile**；歧义（4~5 位纯数字）要求选市场 |
| `date` | 必填；`YYYY-MM-DD`；不得晚于今天 | 日期控件 + 服务端校验 |
| `analysts` | 至少 1 个，子集 `market/social/news/fundamentals` | 多选，默认全选 |
| `portfolio` | 可选 JSON：`cash`、`currency`、`positions[{ticker, quantity, average_price}]`；不提供 ≠ 空仓 | v1 只支持**粘贴/上传 JSON**，不做编辑器；提供 schema 校验错误 |
| `checkpoint` | 三态：flag / env / 默认 | v1 固定按服务端配置（默认开），UI 只提供"强制全新运行"（清本 ticker 检查点） |
| `--clear-checkpoints` | 删除所有检查点 | 提供"清检查点"按钮（明确二次确认） |
| `save/show/html` | 三态，交互式询问 | Web 总是保存；`show` 变成"打开报告页"；`html` 默认开 |
| 模型/供应商/端点 | 环境变量与 prefs；含密钥 | **v1 不暴露**（避免密钥进浏览器）；只暴露 `output_language` 与 `--strict`（CN） |
| 回测参数 | tickers/start/end/every/analysts/asset_type/portfolio/run_id | **v1 不做** |

## 3. 输出清单（Web 要呈现/落盘的）

| 输出 | 位置/形态 | Web v1 |
| --- | --- | --- |
| 实时进度 | 节点级：agent 状态、messages | SSE：`node_started` / `node_finished` / `message` |
| 最终评级 | `run_rating(final_state)`：Buy/Overweight/Hold/Underweight/Sell/**REVIEW** | 结果页顶部；REVIEW 显示警告条（不能当静默成功） |
| 报告树 | `reports/1_analysts/… 5_portfolio/`、`complete_report.md` | 列出章节；正文用 HTML 版 |
| HTML 报告 | `reports/complete_report.html` | 直接内嵌/跳转展示 |
| 运行元数据 | `reports/run_metadata.json` + md/html 章节 | 详情页折叠展示（11 字段） |
| 消息/工具日志 | `<ticker>/<date>/message_tool.log` | 仅提供下载，不在页面渲染 |
| 检查点 | `<data_cache_dir>/checkpoints/<TICKER>.db` | 不在 UI 暴露路径，只提供"清除" |
| 记忆条目 | `memory_log_path`：`[date | ticker | rating | pending]` | v1 不做记忆页 |
| CLI 偏好 | `~/.tradingagents/cli_prefs.json` | Web 不使用（避免与 CLI 互相覆盖） |

## 4. Web 设计决定（v1）

### 4.1 表单（单页）

```
标的 [600519.SH      ]  → 预览：CN_A_SHARE · 贵州茅台（Tushare 身份）
日期 [2026-10-30]
分析师 [x] market [x] social [x] news [x] fundamentals
语言   [中文/English]
严格模式 [ ]（仅 CN_A_SHARE 可选；海外标的隐藏）
组合 JSON（可选，折叠）
[开始分析]
```

- **预览接口** `GET /api/preview?symbol=…&market=…`：返回规范化代码、Profile、身份名；
  歧义/冲突返回 400 与可读原因（不猜市场）。
- 严格模式对 `UPSTREAM_DEFAULT` **隐藏并拒绝**（与后端一致）。

### 4.2 状态机

```
queued → running → succeeded | failed
```

- 单 worker 串行；队列上限 3；
- 失败区分：`vendor_unavailable` / `no_data` / `config_error` / `internal`（都在任务页显示原始消息）；
- 不做"取消"（v1）：上游是同步长任务，中断语义需要进程级处理，留到 W3。

### 4.3 API 草案

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/preview` | 代码规范化 + Profile + 身份 |
| POST | `/api/runs` | `{symbol, date, analysts, language, strict, portfolio?}` → `{id}` |
| GET | `/api/runs/{id}` | 状态、评级、错误、报告路径 |
| GET | `/api/runs/{id}/events` | SSE 进度 |
| GET | `/runs/{id}/report` | 报告页（内嵌 HTML） |
| GET | `/runs/{id}/files/{name}` | 白名单下载（`complete_report.md`、`message_tool.log`） |
| POST | `/api/checkpoints/clear` | 清检查点（二次确认在 UI） |

### 4.4 安全（局域网 ≠ 可信）

- 共享 token（`TRADINGAGENTS_WEB_TOKEN`），未带 → 401；cookie 记住；
- 一次分析会真实产生 LLM 费用：队列上限 + 表单"开始"二次确认；
- 报告文件只读白名单 + `safe_ticker_component` 路径校验；
- 绑定 `0.0.0.0` 但文档写明仅内网，不映射公网。

## 5. 与多市场 Profile 的关系

- Web 不在前端写死任何 A 股假设：Profile 由**服务端** `select_profile(symbol, market)` 决定，
  前端只展示结果；
- 结果页显示 `profile`、`extension_version`、`upstream/downstream commit`（来自 `run_metadata.json`）；
- 海外标的的分析走**上游类**，UI 不得显示 A 股约束（前端不生成这些文案，全部来自报告/元数据）。

## 6. v1 明确不做

多用户/权限、回测 UI、记忆页、模型与密钥选择、任务取消、token 级流式输出、报告在线编辑。

## 7. 验收（W1）

1. 手机浏览器打开 → 输入 `600519.SH`，预览显示 `CN_A_SHARE` 与公司名；
2. 开始分析 → 页面显示节点进度 → 完成后显示评级与报告；
3. 输入 `0700.HK` → 预览显示 `UPSTREAM_DEFAULT`，严格模式不可选；
4. 输入 `0700` → 预览报错"无法判定市场，请选择"；
5. 刷新页面后历史任务仍在（SQLite）；
6. 未带 token 的请求返回 401。
