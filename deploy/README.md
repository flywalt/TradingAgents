# 部署：Caddy + UI + 引擎

Caddy 只做入口（TLS/HTTP2/日志）；UI 出页面并把 `/api` 转给引擎；引擎只监听回环、
独占 SQLite 与队列。三者可以放在一台机器，也可以分开放（见下方拓扑）。

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

# 4) Caddy
sudo cp deploy/caddy/Caddyfile.vps /etc/caddy/Caddyfile   # 或 .lan
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

## 6. 回滚

停 Caddy 的 site block 或 `systemctl stop caddy`，UI/引擎仍在回环上；本机可随时退回
`combined` 单进程：`python -m tradingagents_web`（8501）。数据只在 `~/.tradingagents`，
与前端/入口无关。
