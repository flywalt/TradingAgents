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
| D-0052 | `feat(web)` 分支 `feature/web-report-l10n-graph` | feat | 报告页服务时本地化（`report_page.present`）+ 运行页拓扑图（`progress_graph.topology` + `static/run-page.js`）+ 中文标签单一来源 `labels.py` | 无 | 无 | 新增 25 项测试，全量 1805 passed |
| D-0053 | `feat(web)` 分支 `feature/web-report-summary` | feat | 中文报告：注入 CJK 排版（ta-cn 样式）+ 核心结论卡（PM 结论摘录置顶，锚点回第五节）；宽屏流程图分析师行动态居中于多头研究员 | 无 | 无 | 新增 10 项测试 |
| D-0054 | `feat(web)` 分支 `feature/graph-v2.1`（已合并） | feat | 运行图 v2：横向阶段流/窄屏脊骨、三线语言（主线/辩论⇄/反馈点线）、分组容器统一边框与等距、固定端口、区域单线交接（一次事件式流动）、卡片三态呼吸；检索 `search.py` 与简称优先为独立提交 | 无 | 无 | 图/检索/布局新增 34 项测试，全量 1846 passed |
| D-0055 | `feat(web)` 分支 `feature/m1-split`（`b9e5bba`…`3cd0739`） | feat | UI 与引擎拆成两个角色进程（`--role ui|engine`）：引擎独占队列/worker/SQLite 并强制回环，UI 出页面并把 `/api` 流式反代给引擎（注入服务令牌、透传 SSE 与 `Last-Event-ID`）；`scripts/serve.sh up\|down\|status` 幂等起停 | 无 | 无 | 新增 6 项测试，全量 1876 passed |
| D-0056 | `feat(deploy)`（`8d3c8f1`、`5687459`、`76eb429`） | feat | Caddy 入口与 HTTPS 感知 cookie（`X-Forwarded-Proto` → `Secure`）；systemd 单元、RSSHub 边车、备份脚本、env 模板；单台 VPS 的上线/迁移手册。Caddy 站点配置不留在仓库（集中配置管理） | 无 | 无 | 新增 2 项测试，全量 1878 passed |
| D-0057 | `chore(deploy)` 分支 `chore/vps-deploy-dafeis` | chore | 公网部署定稿：登录表单改为 POST（口令不进反代访问日志，`GET /login?token=` 保留给局域网）、uvicorn 显式信任回环代理头、UI 单元绑回环、备份 timer、`deploy/README.md` 按 `trade.dafeis.com` 写实（含 Caddyfile） | 无 | 无 | 新增 3 项测试，全量 1881 passed |
| D-0058 | 分支 `chore/vps-deploy`（`3d9562a` `upstream-patch` + 本条 `fix(web)`） | fix | `TRADINGAGENTS_HOME` 环境变量优先于 `~/.tradingagents`：`default_config` 三处默认路径与 web 层 SQLite 兜底（新 `default_db_path()`）跟随单一开关，生产沙箱（vps-deploy，`ReadWritePaths=/srv/<app>/data`）内状态全量归位；特异目录变量仍优先 | `tradingagents/default_config.py`（1 行） | 低：上游极少改该行；**退路**——零补丁可用 `TRADINGAGENTS_RESULTS_DIR`/`_CACHE_DIR`/`_MEMORY_LOG_PATH`/`_WEB_DB` 四变量直配得到同样布局 | `tests/downstream/test_state_home.py` 新增 4 项 |
| D-0059 | 分支 `chore/vps-deploy`（本条 `chore(deploy)`） | chore | 部署收编为 vps-deploy 标准：新增 `deploy/app.toml`（engine 8802 / ui 8801、ta.dafeis.com、`api_paths=["/*"]` 全反代、build 含 requirements-downstream + import 冒烟、备份三路径）；删 `deploy/systemd/` 与 `deploy/backup.sh` 裸机流程；README 重写为标准引用 + 运行手册；env.example 对齐生产 13 键 | `README.md`（末尾 2 行部署注记） | 无 | 清单经 vps-ops parser+validate+render 断言（0 error 0 warning） |
| D-0060 | 分支 `fix/go-endpoint`（本条 `upstream-patch`） | fix | OpenCode Go 订阅端点支持：base_url 指向 `opencode.ai/inference/go/` 时注入`x-opencode-session`（进程级稳定）与 `User-Agent: tradingagents-web/1.0`——缺会话头被 400 拒、端点配成 /inference/openai/v1 会按量计费 402（实测 `billing_source:"go"` 走订阅额度） | `tradingagents/llm_clients/openai_client.py`（约 15 行） | 低：helper 独立函数，上游改动该文件罕见；退路=不用 Go 端点时行为零变化 | `tests/downstream/test_go_endpoint_headers.py` 3 项 |
| D-0061 | 本条 `docs(deploy)` | docs | 上线后运维收口（无代码）：`deploy/README.md` 补三颗令牌职责表（WEB/ENGINE/READ + engine 设令牌后拒收 Web 令牌）、备份与恢复分节（同盘风险 + 整机 ABB 兜底边界）、RSSHub 改为外部实例口径（含 key 轮换处置与自检命令）、验收记录追加 2026-11-17 补测（历史首跑 402 失败、RSSHub 403→200、令牌边界实测）与未闭环两项；`deploy/app.toml` 的 `[[external]]` 指向 `https://rsshub.dafeis.com`（原写"本机 1200 / 无 docker"已过时）；`deploy/env.example` 对齐生产三令牌与外部 RSSHub | 无 | 无 | 不涉及代码；`vps-deploy --dry-run` 渲染结果不变 |
| D-0062 | 本条 `fix(web)` | fix | **缺依赖静默降级**：tushare 1.4.29 元数据漏声明 `six`，干净 venv 里 `import tushare` 抛 `ModuleNotFoundError`，13 处 `get_api()` 全线降级（`/api/preview` 的 `name` 为 null、`/api/search` 空、journal 无告警）。四处收口：① `requirements-downstream.txt` 声明 `six>=1.16`（注释写死原因，禁止"清无用依赖"）；② `deploy/app.toml` build 冒烟加 `import tushare`（缺包在 build 期炸）；③ `create_app` 在 combined/engine 启动时构造一次数据客户端（离线、无取数），失败只 `WARNING` 且带上底层原因，ui 进程不探测；④ `client._build_api` 的错误消息带出原异常并指向 requirements-downstream | 无 | 无 | 新增 `tests/downstream/test_vendor_readiness.py` 3 项 + `test_packaging.py` 2 项（依赖声明与部署冒烟） |
| D-0063 | 本条 `docs(deploy)` | docs | 验收补测（无代码）：P0 修复上线后实测（`preview.name` → 贵州茅台、`search` → 1 条、journal 无 probe 告警）+ **首次成功真实分析**（`d5a9146d…`，600519.SH / 2026-11-13 / 单分析师，14 min 16 s，Hold，报告 67 KB 且含真实数据）+ 内存峰值实测（engine 157.9 M / ui 122.3 M，上限各 400 M）；未闭环改为"多分析师全链路"与"报告语义抽检" | 无 | 无 | 不涉及代码；实测证据见 `deploy/README.md` 补测表 |
| D-0064 | 本条 `fix(web)` | fix | UI 代理两端：① `/api/{path}` 授权按方法分流（GET → `require_read`，其余 → `require_write`）——此前整条路由只认 `require_read`，设了只读令牌即等于给了写权限（生产未设故不可利用）；② 引擎不可达改走统一错误契约（新增 `EngineUnreachableError` / `engine_unreachable` / 502），前端 `body.error.message` 才有话可说，不再是 `{"detail": …}` | 无 | 无 | `test_web_roles.py` 新增 2 项（先红后绿） |
| D-0065 | 本条 `perf(web)` | perf | worker 延迟导入 `runner`：队列里没有任务就不加载分析栈（langgraph + langchain）。实测口径：`import tradingagents_web.worker` 原本连带 runner；但 `app.py` 为身份解析导入 `tradingagents.agents.context` 已拖入 langchain，所以真正的省量是**个位数 M**（实测 145 M → 139 M），不是"几十 M"。收益诚实记录，不为此加深改造 | 无 | 无 | 新增 `tests/downstream/test_web_lazy_stack.py` 3 项（子进程断言导入面 + 默认 execute 仍解析成 runner） |
| D-0066 | 本条 `docs(deploy)` | docs | 运维口径补齐（无代码）：`deploy/README.md` 记 `env_required` 按 provider 写死（换 minimax 要同步改 `app.toml`）、`/api/engine/health` 定位（运维探针，页面不消费）、`api_paths=["/*"]` 的绕行与风险、令牌表改用已修好的授权分流口径；`app.toml` 的 `env_required` 行加同义注释；`docs/UPSTREAM_DELTA.md` 的 D-0059 行补记 `README.md` 为上游文件改动（此前 EXTENSIONS 记了、台账漏了）；验收记录补**报告数字独立复核**（OHLCV/五项指标/百分比逐位对齐，见 README）与"基本面口径未覆盖"的边界说明 | 无 | 无 | 不涉及代码；复核脚本未入仓（一次性核对，证据写进 README） |
| D-0067 | 本条 `fix(web)` | fix | 422 也走统一错误契约：FastAPI 默认的 `{"detail": [...]}` 换成 `error.category=bad_request` + 字段清单 + 下一步动作——前端只读 `body.error.message`，否则"缺了 symbol/date"这种可自解的信息会显示成笼统的"提交失败"（部署后实测 POST 非法载荷曾返回 422 默认体） | 无 | 无 | `test_web_api.py` 新增 1 项（先红后绿） |
| D-0068 | 本条 `feat(web)` | feat | 报告页与流程图的呈现收口（零上游补丁，全部在出站层）：① 剥掉上游 logo 与"TradingAgents powered by Tauric Research" 页脚（`report_page.strip_branding`，`/runs/<id>/report` 与 `/runs/<id>/files/*.html` 两处出口一致；磁盘产物不动）；② 报告在同标签页打开，加 sticky 返回条（`← 返回分析` + 标的名，CSP sandbox 增加 `allow-top-navigation-by-user-activation`，否则链接点不动）；③ 报告纵向节奏收紧（`.page` 上下内距、章节标题上距、核心结论卡内距）+ `@media print` 规则；④ 流程卡卡高 48→40（窄屏 44→40），分组框按 26px 上带/下脚与 24/48 交接节奏重算，13px 标签不再悬在空卡片里 | 无 | 无 | 报告页新增 4 项、API 新增 2 项、图 30 项（含上游 logo/页脚剥离的同步保险丝） |
| D-0069 | 本条 `fix(web)` | fix | 流程图的框随选择收缩：此前输入分组框是四分析师的手调坐标，只选 1 个分析师时画出四格高的空框。改为**按卡片计算**——宽屏输入框随人数居中收缩，窄屏整张图纵向重排（少一张卡就短 56px）；`_groups()` 统一按 26px 上带/下脚贴住成员卡片，左右侧距统一 14px（顺带修掉 risk 框 12px 的偏差、窄屏输入框 12→14）；宽屏 x 轴改为从「14 内距 + 48 阶段间距」推导，避免手写坐标漂移；`_WIDE`/`_NARROW` 里被函数覆盖的 boxes/groups 死配置删掉，单一事实来源 | 无 | 无 | `test_web_progress_graph.py` 新增 5 项（输入框跟随选择、所有框贴卡、窄屏页高随人数线性变化、侧距一致），参数化覆盖 1/2/4 分析师；4 分析师坐标逐值不变（47 项全绿） |
| D-0070 | 本条 `feat(web)` | feat | 统一鉴权门接入（应用侧）：`TRADINGAGENTS_TRUST_FORWARD_AUTH=1` 时，Caddy forward_auth 注入的 `Remote-User` 等同于已登录（仅 ui/combined；engine 仍只认服务令牌），避免 tinyauth 之后再让用户输一遍应用口令；默认关闭，头只有代理场景才可信 | 无 | 无 | `test_web_roles.py` 新增 2 项（信任开启时无口令可进、默认不信任） |
| D-0071 | 本条 `feat(web)` | feat | 应用口令退场：统一鉴权门接管后，`TRADINGAGENTS_WEB_TOKEN` 不再是启动必需项。信任 forward_auth 且未配口令时进入 **gate-only** 模式——不注册 `/login`（303 回首页）、401 不再吐口令表单，身份只来自 Caddy 注入的 `Remote-User`；`env_required` 改为要求 `TRADINGAGENTS_ENGINE_TOKEN`（engine 仍只认服务令牌）。不配口令又不信任 forward_auth 时仍拒绝启动（fail-closed） | 无 | 无 | `test_web_roles.py` 新增 2 项（gate-only 可进且不吐表单、两者皆无则拒启） |
| D-0072 | 本条 `feat(web)` | feat | L2 触发护栏（服务端，不含真实分析）：① **幂等**——同 `(symbol, trade_date, analysts 集合)` 已有 queued/running/succeeded 时返回原 run id（`deduplicated: true`），`force: true` 才新建；② **每日额度**——`TRADINGAGENTS_DAILY_RUN_LIMIT`（默认 0=不限）按**本地日**换算成 UTC 边界计数，超限返回 429 `budget_exhausted`；③ 队列上限仍在额度之后判定（重试不被额度误伤） | 无 | 无 | `test_web_api.py` 新增 4 项（去重、不同分析师不合并、额度 429、force 绕过） |
| D-0073 | 本条 `fix(web)` | fix | 三处界面修正：① **时间按 +08 显示**——新增 `local_clock` 过滤器（库里存 UTC，页面按机器时区渲染），run/history/index 三处不再切 ISO 字符串；事件时间在 JS 里用 `Intl.DateTimeFormat(timeZone: Asia/Shanghai)`；② **状态实时更新**——run 页此前只在 SSE 断开后的轮询里更新状态，打开时是 queued 就一直显示"排队中"；现在 `run.started` 事件到达即切"运行中/已运行"；③ **完成角标**——流程图已完成的节点右上角加绿色实心点（未开工/进行中不显示），与 13px 标签、40px 卡高配套 | 无 | 无 | `test_web_labels.py` 新增 2 项（时区换算、模板不得再切字符串） |
| D-0074 | 本条 `fix(macro)` | fix | 宏观指标名归一化：模型在中文运行里会按 FRED 习惯说 `china_cpi` / `cn_gdp` / `cpi_yoy`，而我们的 A 股 vendor 只认裸名（cpi/gdp/m2…），导致一次宏观查询直接抛 "unknown macro indicator"、该轮宏观数据为空。现在先剥 `china_/chinese_/cn_/zh_` 前缀与 `_yoy/_rate/_index` 后缀再查表；`LPR` 等真正不可用的序列仍**拒绝**而不是拿 FRED 顶替。上游 FRED 描述未改（零上游补丁） | 无 | 无 | `test_macro.py` 新增 6 项（5 个别名 + 归一化后仍拒绝 LPR） |

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
| `render_report` 的标记字面量（`<html lang>`、`<p class="date">`、`<dt>` 标签、`aria-label="Sections"`、`<a class="to-top">`、`<span class="rating "`） | `report_html.py` | Web 层在**服务时**把报告页首本地化，磁盘产物不动 | 页面静默退回英文（不报错） | `tests/downstream/test_web_report_page.py::test_the_markup_we_match_is_still_produced_upstream` |
| `rating.RATINGS_5_TIER` / `REVIEW` | `agents/rating.py` | 全链路评级契约 | 记忆/回测统计口径分裂 | 复用即可，勿改 |
| `_TRADINGAGENTS_HOME`（**私有**模块常量） | `default_config.py:3` | web 层 db 兜底路径跟随 D-0058 的状态归位开关 | 上游改名 → db 静默落回 `~/.tradingagents`（health 仍全绿，备份失真） | `tests/downstream/test_state_home.py::test_default_db_path_follows_home` |

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
