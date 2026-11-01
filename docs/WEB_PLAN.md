# WEB_PLAN.md — Web 界面（B4）

> 状态：已定范围，未开工。开工前置：B1（agent 接线）完成，且外部评审对补丁/同步策略的结论回来。
> 定位：**下游外壳**，不是第二套分析引擎；上游 `cli/` 与 `tradingagents/` 一行不改。

## 1. 已确认的范围（2026-11-01）

| 项 | 决定 |
| --- | --- |
| 形态 | 本地单人，**暴露到局域网**（主机是 Ubuntu，日常用 PC/手机浏览器访问） |
| 并发 | **单 worker 串行**（正确性优先；并发会串 `set_config` 的进程级状态） |
| 前端 | 服务端渲染（Jinja + 少量原生 JS），**不引入 Node/构建链** |
| 存储 | SQLite（任务表 + 报告索引）；不引入 Mongo/Redis |
| 鉴权 | 首版无登录，但**默认带一个共享访问 token**（见 §5） |
| 依赖 | `fastapi`、`uvicorn[standard]`、`jinja2` → 只进 `requirements-downstream.txt` |
| 启动 | `python -m tradingagents_web`（不加 console_script，避免 `pyproject.toml` 补丁） |

## 2. 架构

```
浏览器(PC/手机) ──HTTP/SSE──► FastAPI (tradingagents_web/app.py)
                                 │
                                 ├─ SQLite: runs(id, ticker, date, analysts, status, ...)
                                 ├─ Worker(单线程队列): activate() → TradingAgentsGraph ...
                                 │     └─ 复用 tradingagents.graph 与 tradingagents_cn
                                 └─ 报告: 直接读 results_dir/<ticker>/<date>/ 静态文件
                                        （render_report 已生成完整 HTML）
```

**核心原则**：web 不实现任何分析逻辑。它只做三件事：排队、调用内核、展示产物。
原因：分析逻辑每改一次就要同步两处，是最容易漂移的重复。

## 3. 端点草案

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/` | 表单：标的、日期、分析师、组合（可选） |
| POST | `/runs` | 入队；返回 303 到任务页 |
| GET | `/runs/{id}` | 任务状态 + 进度（服务端刷新或 SSE） |
| GET | `/runs/{id}/events` | SSE：节点级进度（复用 LangGraph 回调） |
| GET | `/runs/{id}/report` | 报告（`complete_report.html`，内嵌或跳转） |
| GET | `/reports` | 历史报告列表（按 ticker/日期） |
| GET | `/healthz` | 健康检查 |

**不做**：多用户、权限矩阵、定时调度、组合下单（这些是产品层，非研究层）。

## 4. 单 worker 的并发安全

- 任务在**一个后台线程**里串行执行；队列是 SQLite 表 + 内存信号量。
- 每次执行用 `run_config(config)` 包住（上游 ContextVar，工具读取该次运行配置）。
- `activate()` 在进程启动时调用一次（注册 vendor），**不放进任务里**（注册是幂等的，但没必要重复）。
- 崩溃恢复：进程重启时把 `running` 状态的任务标为 `failed`（附原因），不自动重跑（避免重复计费）。

## 5. 安全（局域网 ≠ 可信网络）

局域网里任何设备都能触发一次**真实付费 LLM 调用**，所以默认：

1. 访问 token：`TRADINGAGENTS_WEB_TOKEN`（`.env` 里配），未带 token 一律 401；页面用 cookie 记住。
2. 入参白名单：标的过 `tradingagents_cn.symbols.normalize`（或美股走上游规则）、日期必须 ISO 且 ≤ 今天、分析师枚举。
3. 报告路径：只允许 `results_dir` 下、经 `safe_ticker_component` 规范化的路径（复用上游函数）。
4. 队列上限：同时最多 1 个运行 + 排队上限（默认 3），防止误触发批量花费。
5. 绑定地址：`--host 0.0.0.0 --port 8501`（或用户指定），文档写明"仅限内网，勿映射公网"。

## 6. 移动端

- 页面单栏、`viewport` meta、表格横向滚动、报告正文可读字号；
- 不在手机端做图表交互（首版只读报告 + 状态）。

## 7. 里程碑

| 里程碑 | 内容 | 验收 |
| --- | --- | --- |
| W1 | 骨架 + SQLite 任务表 + 单 worker + 跑一次分析 + 看报告 | 手机浏览器发起 600519 分析并读到报告 |
| W2 | SSE 进度 + 历史列表 + 失败原因可读 + 移动端样式 | 断网刷新后能看到历史与当前进度 |
| W3 | 配置面板（模型、分析师、`cn_strict_ashare`、语言）+ 两次运行对比 | 不改代码即可切换模型与严格模式 |
| W4（可选） | 多用户 / 定时任务 | 仅当确有第二用户或每日批量需求 |

预估：W1 ≈ 400–600 行（含模板），W2 ≈ 200–300 行，W3 ≈ 200 行。

## 8. 与上游的关系

- 纯新增包 `tradingagents_web/`（L3），上游更新不会冲突；
- 若上游未来提供官方 Web/UI：**评估替换我们的外壳**，而不是并行维护两套；
- 复用上游资产：`reporting.write_report_tree`、`report_html.render_report`、`symbols.safe_ticker_component`、`graph.TradingAgentsGraph`。
