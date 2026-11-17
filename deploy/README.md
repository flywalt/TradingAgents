# 部署：vps-deploy 标准接管（ta.dafeis.com）

> **本应用的部署已由 [`vps-deploy`](https://github.com/flywalt/vps-ops) 标准接管**（2026-11 起）。
> 自描述清单见同目录 [`app.toml`](./app.toml)；接入标准与字段说明读
> `~/projects/vps-deploy-standard.md`（任何项目会话照它接入）。
> 旧的裸机流程（手工 systemd / Caddy / `apt install caddy` / `useradd` / `/opt/TradingAgents`）已废弃删除。

## 拓扑（渲染结果，勿手改 `/etc` 下文件）

```
公网 443 ─► Caddy（ta.dafeis.com，handle /* 反代）
              └─► ui   127.0.0.1:8801（页面 + /api/* 流式转发，注入服务令牌）
                    └─► engine 127.0.0.1:8802（队列/worker/SQLite 唯一写者，单实例）
                          ├─► api.tushare.pro（行情/财务/日历）
                          ├─► https://opencode.ai/inference/go/openai/v1（LLM，订阅通道）
                          └─► https://rsshub.dafeis.com（外部实例，不在本机；不可达时新闻源降级）
```

- 路径 `/srv/tradingagents`，运行用户 `ubuntu`，venv 由 build 重建；
- 全部运行时状态在 `TRADINGAGENTS_HOME=/srv/tradingagents/data`（`web/state.db`、`memory/`、`logs/`、`cache/`），
  单元沙箱 `ReadWritePaths=data backup`——**别把状态写去别处**（见 D-0058）。

## 环境变量

见 [`env.example`](./env.example)。要点：`env_required` 三项（`TRADINGAGENTS_WEB_TOKEN`、
`OPENAI_COMPATIBLE_API_KEY`、`TUSHARE_TOKEN`）缺失 preflight 直接失败；`TZ=Asia/Shanghai` 必须有
（否则 0–8 点"今天"算昨天）；`TRADINGAGENTS_HOME` 是状态归位的单一开关。

### 三颗令牌各管一段

| 变量 | 角色 | 谁持有 | 生产现状 |
| --- | --- | --- | --- |
| `TRADINGAGENTS_WEB_TOKEN` | 旧的应用口令（历史）；统一鉴权门接管后**已停用** | — | 已从 `.env` 移除，`[auth]` + `TRADINGAGENTS_TRUST_FORWARD_AUTH=1` 取代它 |
| `TRADINGAGENTS_ENGINE_TOKEN` | ui → engine 的服务令牌；engine 只认这一颗 | ui 进程 | 已设（`secrets.token_urlsafe(32)`，600），并列入 `env_required` |
| `TRADINGAGENTS_WEB_READ_TOKEN` | 只读凭据：`require_read` 接口（GET `/api/*`、`/api/engine/health`）可用；**写操作只认 Web 令牌** | 外部只读调用方 | 未设（无消费方；代理已按方法分流，设上即可用） |

- 令牌未设时的回退：`engine` 角色在 `TRADINGAGENTS_ENGINE_TOKEN` 为空时退用 `TRADINGAGENTS_WEB_TOKEN`
  （单机可用，但服务边界消失）；ui 转发同理。
- **统一鉴权门（vps-deploy `[auth]`）**：站点先过 `auth.dafeis.com`（tinyauth，用户名+密码+TOTP），
  未认证 302 回登录页并带回原地址；`/healthz` 免鉴权。认证通过后 Caddy 注入 `Remote-User`，
  设 `TRADINGAGENTS_TRUST_FORWARD_AUTH=1` 时它等同于"已登录"，不再重复要求应用口令（引擎仍只认服务令牌）。
- 授权分流（D-0064）：`/api/{path}` 代理 GET 走 `require_read`、其余方法走 `require_write`；
  引擎不可达返回 502 且带统一错误体（`error.category=engine_unreachable`）。
- `env_required` 是**按当前 provider 写死的**（生产用 openai-compatible）。换 provider（如 minimax）时
  必须同步改 `app.toml` 的 `env_required`，否则 preflight 会拦一个用不到的键、而放行真正缺的那个。

## 日常操作（VPS 上）

```bash
vps-deploy tradingagents        # 发布（幂等：已是最新秒退）
vps-deploy --dry-run tradingagents   # 只看渲染 diff
vps-deploy backup tradingagents # 立即备份一次
vps-apps                        # 全机应用清单
```

- 备份每日 20:00（cron 由工具管理）：`data/web/state.db`（SQLite 在线备份）、`data/memory`、
  `data/logs`（报告实体，不备则恢复后 DB 与报告对不上）；`data/cache` 不备；**不打包 `.env`**。
- **备份对不存在的路径会直接失败**：`memory/`、`logs/` 要跑过一轮真实分析才存在，装好即触发手动备份属预期失败。
- 健康检查 `/healthz` 走回环；**SSE 链路**（`/api/runs/<id>/events`）如需排障，按
  engine 直打 → ui 直打 → 经 Caddy 三层 `curl -N`（带 `Authorization: Bearer <token>`）对照。

## 备份与恢复（含风险边界）

每天 20:00 由 `vps-deploy` 管理的 cron 写 `/srv/tradingagents/backup/`，保留 7 份：

| 产物 | 内容 | 恢复方式 |
| --- | --- | --- |
| `state-YYYYMMDD.db` | `data/web/state.db` 的**在线备份**（SQLite backup API，跑任务时也一致） | 停两个 unit → 覆盖 `data/web/state.db`（先删 `-wal`/`-shm`）→ 起 unit |
| `memory-YYYYMMDD.tar.gz` | `data/memory/`（决策记忆） | 解到 `data/memory/` |
| `logs-YYYYMMDD.tar.gz` | `data/logs/`（每份报告与事件实体） | 解到 `data/logs/` |

`data/cache/` 不备（可重建）；`.env` **故意不打包**（令牌不落备份）。

**风险边界（唯一未闭环项）**：备份目录与数据在同一块盘、同一台机器上——单盘故障或误删
`/srv/tradingagents` 时备份一起没。整机/磁盘级故障由**百度云 ABB 整机备份**兜（定期快照，覆盖
系统盘与数据盘），因此不额外做异地副本；代价是恢复粒度是"整机回滚"，且快照间隔内的写入会丢。
要更细的 RPO 时，先在 `deploy/app.toml` 的 `backup.paths` 之外自行同步一份到异地，再改本节。


## 已知边界（运行手册）

- ui 单元 `Requires=engine`。实测（SIGKILL engine 主进程）：engine `Restart=always` 秒级自愈、
  **ui 全程 active**——快速自愈下 `Requires` 连锁不会造成停站；OOM 路径未实测，若见 ui 停在
  inactive，跑一次 `vps-deploy tradingagents` 拉起。
- `limits` 按终审裁定为 **800M 总量**（engine/ui 各 400M；idle 实测 146M/116M；2026-11-17 单分析师
  真实分析实测 engine 峰值 **157.9 M**、ui **122.3 M**，余量约 2.5×）。仍见 `journalctl` 里 `Killed`
  （OOM）就继续上调。
- `/api/engine/health` 只给运维看（人工 curl / 将来的监控），页面不消费它；它走 `require_read`，
  不带令牌不会暴露引擎细节。
- `api_paths=["/*"]` 与占位 `static_root` 是为绕开工具"静态站点默认假设"的写法：本站所有路径都由
  ui 渲染，必须 catch-all 反代。若将来 vps-deploy 校验 `api_paths` 前缀，这里会第一个失败（已注释）。
- 回滚演练的坏 commit 会短暂经过 `main`——这是拉取式部署的固有形态（工具只从 `origin/main` 取代码），
  bisect 时注意跳过标注 `test(deploy)` 的演练提交。

## RSSHub（外部实例）

新闻源旁路走 **`https://rsshub.dafeis.com`**（不在 df-tc1 上，由 infra 侧单独维护；本机 Caddy 无此站点）。
`app.toml` 的 `[[external]]` 只做可达性提示，失败仅警告、新闻源降级不阻断。

- `RSSHUB_TOKEN` 必须与该实例的 `ACCESS_KEY` 一致，否则所有路由 **403**（代码会归类成
  `VendorNotConfiguredError`，不重试）。
- key 会被轮换：2026-11 就轮换过一次，旧 key 在 `.env` 里留了几天，表现为 `/api/preview` 正常但
  新闻/情绪面全空。轮换后从 infra 侧 `.env`（当前在 `~/projects/eventengine/.env` 的
  `RSSHUB_ACCESS_KEY`）取新值写入 `/srv/tradingagents/.env`，再 `systemctl restart` 两个 unit。
- 自检：`curl "$RSSHUB_BASE_URL/xueqiu/hots?key=$RSSHUB_TOKEN"` 应 200 且返回 `<rss`；
  应用内自检 `.venv/bin/python -c "from tradingagents_cn.vendors import rsshub;
  print(len(rsshub.parse_items(rsshub.fetch('/xueqiu/hots'))))"`。
- 本机 docker 是有的（`/usr/bin/docker`），不在这里起 RSSHub 是**部署归属决定**（避免第二份实例与
  第二处 key），不是能力限制。真要单机自托管时见 `deploy/rsshub/docker-compose.yml`，单独立项。

## 验收记录（2026-11-16，P2 上线）

| 场景 | 实测 | 结果 |
|---|---|---|
| 首次部署（含 venv + pip 全量构建） | 08:01 | exit 0，**66.9 s**，双 unit active+enabled，healthz 200×2，RSSHub 按设计仅警告 |
| 幂等秒退 | 08:02 | **1.7 s** `已是最新` |
| 真实发布（README 一行） | 08:03 | **18.4 s**（venv 已缓存），marker 更新 |
| 回滚演练（engine start 坏旗标） | 08:03 | 健康轮询失败 → 回滚重建+重渲染好单元 → **「已回滚到 7c02d69」exit 1，63.6 s**，ui 全程在线 |
| SSE 三层对照（`/api/runs/<id>/events`，带 Bearer） | 08:05 | engine 直打 / ui 直打 / 经 Caddy 三层均**增量分块到达**——`encode` 不缓冲，无需 `flush_interval` |
| OOM/`Requires` 连锁演练（SIGKILL engine 主进程） | 08:07 | engine `Restart=always` 秒级自愈，**ui 全程 active**，`/api/engine/health` 恢复 `{"online":true}`——连锁下线担忧实测不存在 |
| 状态落位硬断言 | 08:02 | `data/{web,logs,memory,cache}` 就位；`/home/ubuntu/.tradingagents` **不存在**（无泄漏） |
| 备份（`vps-deploy backup`） | 08:07 | `state-*.db`（在线备份）+ `memory-*.tar.gz` + `logs-*.tar.gz` 三件齐，无 `.env` |
| 首页/静态/链路 | 08:02 | `/` 401 登录页（非 404）、`/static/*` 200、`/api/engine/health` `{"online":true}` |

内存峰值（2026-11-17 实测，见下方补测表）：idle engine ~146M / ui ~116M；单分析师真实分析
engine 峰值 **157.9 M**、ui **122.3 M**，上限各 **400M**（余量约 2.5×）。

LLM 后端（2026-11-16 起）：**OpenCode Go 订阅端点** `https://opencode.ai/inference/go/openai/v1`，
模型 `deepseek-v4.1-flash`，D-0060 注入 `x-opencode-session` + 自报 UA（`billing_source=go` 已实测）。
注意别把端点配回 `/inference/openai/v1`——那是按量计费通道。

### 上线后补测（2026-11-17）

| 场景 | 实测 | 结果 |
| --- | --- | --- |
| 首次真实分析（历史记录，`608d07dd…`，600519.SH / 2026-11-13 / 4 分析师） | 2026-11-16 00:05:37 → 00:06:01 | **failed / internal**：`openai.APIStatusError: 402 Insufficient balance ... pay-as-you-go`——即 D-0060 之前的按量计费通道。**这是唯一一次真实运行，尚未成功跑通一轮** |
| RSSHub key 轮换后取数 | 11-17 | 403 → **200**，应用内 `rsshub.parse_items(fetch("/xueqiu/hots"))` 返回 **10 条** |
| 服务令牌边界 | 11-17 | 浏览器令牌直打 engine `/api/runs` → **401 token required**；engine 令牌 → **200**；经 ui 代理登录态 → **200** |
| 重启后健康 | 11-17 | 两 unit `active`、`NRestarts=0`、`/healthz` 200×2 |
| **P0 修复：`six` + 冒烟 + 启动自检**（D-0062） | 11-17 11:01 | 重发布 20.7 s；`six 1.17.0` / `tushare 1.4.29` 可导入；`/api/preview` 的 `name` → **贵州茅台**（原 `null`）；`/api/search?q=茅台` → `[{600519.SH, 贵州茅台}]`（原 `[]`）；journal 无 probe 告警（构建成功即安静） |
| **首次成功的真实分析**（`d5a9146d…`，600519.SH / 2026-11-13 / **单分析师**） | 11-17 03:01:34 → 03:15:50（**14 min 16 s**） | `succeeded`，评级 **Hold**，`complete_report.md` **67 KB**（含 `贵州茅台`、`MA`、`均线`；头部注明 `Data vendors: … tushare,yfinance`）；`/runs/<id>` 200、`/runs/<id>/report` 200（110 KB） |
| 内存峰值（真实分析全程） | 11-17 03:01–03:16 | engine 运行中稳定 **152–156 M**、峰值 **157.9 M**；ui 峰值 **122.3 M**；上限各 400 M——**余量约 2.5×** |
| **报告行情数字独立复核**（不跑应用里的指标实现，直接用 `fetch_bars` + pandas 重算） | 11-17 | 原始日线 open/high/low/close/vol/amount/pct **逐位相同**（1404.00 / 1437.69 / 1394.00 / 1435.26 / 4,177,984 股 / 59.55 亿 / +1.77%）；SMA50 **1323.59**、SMA200 **1327.89**、EMA10 **1420.49**、BOLL 中轨 **1390.25**（上轨 1502.00 与 `ddof=1` 一致）、ATR14 32.84、VWMA **1421.35**（应用口径是 14 日，与报告一致）；"中轨自 10-13 +9.87%" 复算 **+9.87%**；单位与整手换算（143,526 元/手）自洽 |
| 代理授权分流 + 502 契约（D-0064） | 11-17 11:2x | 部署后 GET/POST 带登录态均正常（GET `/api/runs` 200、POST 非法载荷返回引擎的 400 统一错误体）；只读令牌相关行为由单测锁定 |

仍未闭环：

1. **多分析师全链路**（4 分析师 = 并行分支 + 更多 LLM 调用，耗时与峰值都会更高；单分析师 14 分钟说明真实调度是分钟级）。**由人手动触发**，不排自动任务；
2. **基本面口径未跑过**：本次是单分析师（market）运行，报告的 PIT/财报单位/公告日过滤没有被执行到——抽查只覆盖行情与指标；要验这部分必须跑 `fundamentals`（同样由人手动触发）。


