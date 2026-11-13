# 部署：Caddy + UI + 引擎

Caddy 只做入口（TLS/HTTP2/日志）；UI 出页面并把 `/api` 转给引擎；引擎只监听回环、
独占 SQLite 与队列。三者可以放在一台机器，也可以分开放（见下方拓扑）。

> Caddy 的站点配置**不在本仓库**：由集中配置管理（单一来源），本仓库只保留
> systemd 单元、RSSHub 边车、备份脚本与环境模板。

## 1. 三种拓扑

| 拓扑 | 在哪跑 | 优点 | 注意 |
| --- | --- | --- | --- |
| **A. 全在本机**（现在） | Caddy + UI + engine 同一台 | 数据不出门、零成本 | 需要局域网证书（`caddy trust`） |
| **B. UI 上 VPS，引擎留家里** | Caddy+UI 在 VPS；engine 在家 | 外网随时看页面，重计算留在家里 | UI→engine 要隧道（WireGuard/Tailscale/Cloudflare Tunnel）；engine **绝不**直接暴露公网 |
| **C. 全在 VPS** | 三者都在 VPS | 运维最简单、一处备份 | RSSHub 需可达（同机 docker 或隧道回内网）；数据与 key 都在云端 |

无论哪种：**engine 单实例**（SQLite 单写者 + 图改进程级配置），UI 可以多副本。

## 2. 起步（以 A/C 为例）

```bash
# 1) 代码与依赖
sudo useradd -r -m -d /opt/TradingAgents tradingagents   # 若用独立用户
sudo -u tradingagents git clone <repo> /opt/TradingAgents
cd /opt/TradingAgents && python3 -m venv .venv && .venv/bin/pip install -e .

# 2) 环境变量（不要提交进仓库）
cat > .env <<'ENV'
TRADINGAGENTS_WEB_TOKEN=<用户口令，长随机串>
TRADINGAGENTS_ENGINE_TOKEN=<服务令牌，另一条长随机串>
TRADINGAGENTS_OUTPUT_LANGUAGE=中文
ENV
chmod 600 .env

# 3) 两个进程
sudo cp deploy/systemd/tradingagents-*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now tradingagents-engine tradingagents-ui

# 4) Caddy：站点配置由集中配置管理下发，不在此仓库
sudo systemctl reload caddy
```

生成令牌：

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

## 3. Caddy 关注点

- **只反代 UI**（8501）。引擎 8502 只监听 `127.0.0.1`，不要出现在任何 site block 里。
- **SSE**：`flush_interval -1`，否则进度条会被缓冲成"卡住"。
- **不缓存**：`Cache-Control: no-store`——页面和历史都是实时的。
- **HSTS** 只在证书能自动续期后再开（模板里已给，第一次上线可先注释）。
- 局域网（A）用 `tls internal`，手机需导入一次根证书：`caddy trust` 或在设备的证书设置里安装
  `~/.local/share/caddy/pki/authorities/local/root.crt`。

## 4. 防火墙与暴露面

| 端口 | 允许来源 | 说明 |
| --- | --- | --- |
| 80 | 公网 | 仅 ACME 挑战（Caddy 自动重定向到 443）|
| 443 | 公网 | Caddy |
| 8501 | 仅 127.0.0.1 | UI |
| 8502 | 仅 127.0.0.1 | 引擎 |

```bash
sudo ufw default deny incoming && sudo ufw allow 80,443/tcp && sudo ufw enable
```

## 5. 验证

```bash
curl -fsS https://<域名>/healthz                     # {"ok":true}
curl -fsS -o /dev/null -w '%{http_code}\n' https://<域名>/   # 401（未登录）
curl -fsS -N -b <cookie> https://<域名>/api/runs/<id>/events | head -2   # SSE 有帧
curl -fsS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8502/        # 404（引擎不出页面）
```

## 6. 最终整合方案（C）：一台北京 VPS 跑全部

拓扑：`Caddy(443) → UI(8501, loopback) → engine(8502, loopback) → RSSHub(1200, loopback)`。
RSSHub 只有引擎会访问，所以只绑回环；公网只开 80/443。

### 6.1 进程与端口

| 组件 | 起法 | 监听 | 内存（实测/估计）|
| --- | --- | --- | --- |
| Caddy | `systemctl enable --now caddy` | 0.0.0.0:80/443 | ~40 MB |
| UI | `systemctl enable --now tradingagents-ui` | 127.0.0.1:8501 | ~160 MB |
| engine | `systemctl enable --now tradingagents-engine` | 127.0.0.1:8502 | ~210 MB 峰值 |
| RSSHub | `docker compose -f deploy/rsshub/docker-compose.yml up -d` | 127.0.0.1:1200 | ~150–300 MB |

合计峰值约 0.6–0.8 GB；4c4g 富余很大，磁盘 20–40 GB 足够（代码+venv 约 0.5 GB，
RSSHub 镜像约 1 GB，运行产物每天几 MB）。

### 6.2 一次性上线清单

```bash
# 0) 系统
sudo apt update && sudo apt install -y caddy git python3-venv docker.io docker-compose-plugin rsync
sudo timedatectl set-timezone Asia/Shanghai

# 1) 代码（用独立用户跑业务）
sudo useradd -r -m -d /opt/TradingAgents tradingagents
sudo -u tradingagents git clone <repo> /opt/TradingAgents
cd /opt/TradingAgents && sudo -u tradingagents python3 -m venv .venv
sudo -u tradingagents .venv/bin/pip install -e .

# 2) 密钥
sudo -u tradingagents cp deploy/env.example .env && sudo -u tradingagents vi .env
sudo chmod 600 .env
#   两份不同的令牌：WEB（浏览器）与 ENGINE（UI→引擎）
#   RSSHUB_TOKEN 与 RSSHub 的 ACCESS_KEY 必须一致

# 3) 服务
sudo cp deploy/systemd/tradingagents-*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now tradingagents-engine tradingagents-ui

# 4) RSSHub
sudo -u tradingagents env $(grep RSSHUB_TOKEN .env | xargs) \
  docker compose -f deploy/rsshub/docker-compose.yml up -d

# 5) 入口：域名 A 记录先指向这台机器的 IP；Caddy 站点配置由集中配置管理下发

# 6) 防火墙
sudo ufw default deny incoming && sudo ufw allow 80,443/tcp && sudo ufw enable
```

### 6.3 从本地迁移（停机搬运，避免 SQLite 双写）

```bash
# 本机：先停，保证状态一致
scripts/serve.sh down
rsync -a ~/.tradingagents/ root@vps:/home/tradingagents/.tradingagents/   # 以实际业务用户为准
scp .env root@vps:/opt/TradingAgents/.env
# VPS：起服务、验证、再把 DNS 切过去
```

迁移后可以继续用两台：**同一时刻只能有一个 engine** 写 `state.db`；家用机作为冷备，
需要时再反向搬一次。

### 6.4 日常运维

| 事项 | 做法 |
| --- | --- |
| 备份 | `deploy/backup.sh`（结果 + state.db + .env，保留 14 天），挂 cron 03:30 |
| 日志 | journald（两个服务）+ Caddy 自带滚动；`journalctl -u tradingagents-engine -f` |
| 升级 | `git pull && .venv/bin/pip install -e . && systemctl restart tradingagents-{engine,ui}` |
| 换令牌 | 改 `.env` 两处 → `systemctl restart` 两个服务，浏览器重新登录 |
| 磁盘告警 | `du -sh ~/.tradingagents/logs`；产物按需清理（每次约 0.44 MB）|

## 7. 回滚

停 Caddy 的 site block 或 `systemctl stop caddy`，UI/引擎仍在回环上；本机可随时退回
`combined` 单进程：`python -m tradingagents_web`（8501）。数据只在 `~/.tradingagents`，
与前端/入口无关。
