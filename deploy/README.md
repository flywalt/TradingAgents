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
                          └─► [RSSHub 127.0.0.1:1200 暂未部署：新闻源降级不阻断]
```

- 路径 `/srv/tradingagents`，运行用户 `ubuntu`，venv 由 build 重建；
- 全部运行时状态在 `TRADINGAGENTS_HOME=/srv/tradingagents/data`（`web/state.db`、`memory/`、`logs/`、`cache/`），
  单元沙箱 `ReadWritePaths=data backup`——**别把状态写去别处**（见 D-0058）。

## 环境变量

见 [`env.example`](./env.example)。要点：`env_required` 三项（`TRADINGAGENTS_WEB_TOKEN`、
`OPENAI_COMPATIBLE_API_KEY`、`TUSHARE_TOKEN`）缺失 preflight 直接失败；`TZ=Asia/Shanghai` 必须有
（否则 0–8 点"今天"算昨天）；`TRADINGAGENTS_HOME` 是状态归位的单一开关。

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

## 已知边界（运行手册）

- ui 单元 `Requires=engine`：engine 被 OOM 杀掉时 systemd 会连带停 ui；engine 靠 `Restart=always`
  自愈，**ui 若停在 inactive，跑一次 `vps-deploy tradingagents` 拉起**。
- `limits` 当前 600M 总量（engine/ui 各 300M）。跑大任务若见 `journalctl` 里 `Killed`（OOM），
  把 `app.toml` 的 `limits.memory` 提到 `800M` 重发一次。

## RSSHub（暂缓）

新闻源旁路走 RSSHub（`deploy/rsshub/docker-compose.yml` 留作将来参考）。df-tc1 不装 docker，
`app.toml` 里只登记 `[[external]]` 可达性检查（失败仅警告）。再上时：单独立项，不进本标准。
