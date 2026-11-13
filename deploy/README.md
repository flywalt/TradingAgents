# 部署：一台 VPS 跑全部（Caddy → UI → 引擎 → RSSHub）

目标拓扑（C 方案：单机整合）：

```
公网 443 ─► Caddy ─► UI 127.0.0.1:8501 ─► 引擎 127.0.0.1:8502
                                          ├─ SQLite（state.db）+ 运行产物
                                          └─► RSSHub 127.0.0.1:1200（雪球/财联社新闻）
```

- **Caddy 是唯一公网入口**，只反代 UI；引擎与 RSSHub 只绑回环，永不出现在任何 site block 里；
- **引擎必须单实例**（`state.db` 唯一写者 + 图改进程级配置）；UI 无状态，可重启；
- 本文以域名 `trade.dafeis.com` 为例；换域名就全局替换该字符串。

| 组件 | 监听 | 内存（实测/估计）| 起法 |
| --- | --- | --- | --- |
| Caddy | `0.0.0.0:80,443` | ~40 MB | `systemctl enable --now caddy` |
| UI | `127.0.0.1:8501` | ~160 MB | `systemctl enable --now tradingagents-ui` |
| 引擎 | `127.0.0.1:8502` | ~210 MB 峰值 | `systemctl enable --now tradingagents-engine` |
| RSSHub | `127.0.0.1:1200` | ~150–300 MB | `docker compose up -d` |

合计峰值 ~0.6–0.8 GB，4c4g 富余很大；磁盘：代码 + venv ≈ 0.5 GB，RSSHub 镜像 ≈ 1 GB，
运行产物每次 ≈ 0.44 MB。

---

## 0. 前置条件

| 项 | 要求 |
| --- | --- |
| DNS | `trade.dafeis.com` 的 **A 记录**指向 VPS 公网 IPv4（有 IPv6 再加 AAAA）；TTL 300 |
| 端口 | 公网可访问 **80**（ACME 校验）与 **443** |
| 系统 | Ubuntu 22.04/24.04 或 Debian 12，Python ≥ 3.11 |
| 时区 | `Asia/Shanghai`（否则「今天」与交易日期差 8 小时）|
| 出站 | 能访问模型服务、`api.tushare.pro`、RSSHub 抓取的目标站点 |

DNS 生效验证：

```bash
dig +short trade.dafeis.com          # 应返回 VPS 的 IP
```

若域名挂在 Cloudflare：先用**灰云（DNS only）**，让 Caddy 直接签 Let's Encrypt；橙云需
Origin CA 证书并确认 SSE 不被缓冲，通网后再考虑。

---

## 1. 系统与依赖

```bash
sudo apt update && sudo apt install -y caddy git python3-venv rsync docker.io
sudo timedatectl set-timezone Asia/Shanghai
# Compose 插件（Ubuntu 24.04 叫 docker-compose-v2，Debian/官方源叫 docker-compose-plugin）
sudo apt install -y docker-compose-v2 || sudo apt install -y docker-compose-plugin
```

---

## 2. 取代码（VPS 上 clone）

业务用独立用户跑，代码放 `/opt/TradingAgents`：

```bash
sudo useradd -r -m -d /opt/TradingAgents tradingagents 2>/dev/null || true
sudo -u tradingagents git clone https://github.com/<你的用户名>/TradingAgents.git /opt/TradingAgents
cd /opt/TradingAgents
sudo -u tradingagents python3 -m venv .venv
sudo -u tradingagents .venv/bin/pip install -e .
```

> 服务必须以**仓库根目录**为工作目录：`tradingagents_web` / `tradingagents_cn` 是仓库内的
> 包，靠 `python -m` 把当前目录加入 `sys.path`。systemd 单元里的 `WorkingDirectory`
> 已经设好，别改。

---

## 3. 环境变量

```bash
cd /opt/TradingAgents
sudo -u tradingagents cp deploy/env.example .env
sudo -u tradingagents vi .env          # 逐项填写
sudo chmod 600 .env
sudo chown tradingagents:tradingagents .env
```

必填项：

| 键 | 说明 |
| --- | --- |
| `TRADINGAGENTS_WEB_TOKEN` | 浏览器登录口令，32+ 随机字符 |
| `TRADINGAGENTS_ENGINE_TOKEN` | UI → 引擎的服务令牌，**必须与上一条不同** |
| `TUSHARE_TOKEN` | A 股行情/财务 |
| `RSSHUB_TOKEN` | 与 RSSHub compose 的 `ACCESS_KEY` 一致，否则新闻 403 |
| `TRADINGAGENTS_LLM_PROVIDER` / `OPENAI_API_KEY` / `OPENAI_BASE_URL` | 模型服务 |

生成令牌：

```bash
python3 -c "import secrets;print('WEB='+secrets.token_urlsafe(32));print('ENGINE='+secrets.token_urlsafe(32))"
```

注意：注释必须单独成行——systemd 的 `EnvironmentFile` 不认行尾注释，会把 `# ...` 当成值。

---

## 4. 两个应用进程

```bash
cd /opt/TradingAgents
# 模板默认 User=tradingagents、WorkingDirectory=/opt/TradingAgents。
# 路径或用户名不同就替换，例如改到 /srv/ta 与用户 stock：
#   sudo sed -i 's#/opt/TradingAgents#/srv/ta#g; s/^User=tradingagents/User=stock/' deploy/systemd/*.service

sudo cp deploy/systemd/tradingagents-engine.service \
        deploy/systemd/tradingagents-ui.service \
        deploy/systemd/tradingagents-backup.service \
        deploy/systemd/tradingagents-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now tradingagents-engine tradingagents-ui
sudo install -d -o tradingagents -g tradingagents /var/backups/tradingagents
sudo systemctl enable --now tradingagents-backup.timer
```

此时**还不通外网**，先在机器上确认两个进程活着：

```bash
systemctl status tradingagents-engine tradingagents-ui --no-pager
curl -fsS http://127.0.0.1:8501/healthz                      # {"ok":true}
curl -s  -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8502/   # 404（引擎不出页面）
```

`curl` 走 UI 需要令牌：

```bash
T=$(sudo grep -oP '^TRADINGAGENTS_WEB_TOKEN=\K.*' /opt/TradingAgents/.env)
curl -fsS -H "Authorization: Bearer $T" http://127.0.0.1:8501/api/runs
```

---

## 5. RSSHub（新闻源）

```bash
cd /opt/TradingAgents
sudo -u tradingagents env RSSHUB_TOKEN="$(sudo grep -oP '^RSSHUB_TOKEN=\K.*' .env)" \
  docker compose -f deploy/rsshub/docker-compose.yml up -d
docker ps --filter name=rsshub
```

自检（带 key 才有内容，缺 key 返回 403 属正常鉴权）：

```bash
curl -s -o /dev/null -w '%{http_code}\n' "http://127.0.0.1:1200/xueqiu/hots?key=$(sudo grep -oP '^RSSHUB_TOKEN=\K.*' /opt/TradingAgents/.env)"
```

---

## 6. Caddy 站点配置

把下面内容写入 `/etc/caddy/Caddyfile`（若由集中配置管理下发，就按同一内容同步过去）：

```caddyfile
{
	email you@example.com          # 换成可收信的地址，Let's Encrypt 到期提醒
	admin off                      # 如需 Admin API 热加载：admin localhost:2019
}

trade.dafeis.com {
	encode zstd gzip

	# 单用户实时页面：不缓存、不泄露实现细节
	header {
		Cache-Control "no-store"
		X-Content-Type-Options "nosniff"
		Referrer-Policy "no-referrer"
		-Server
		# 证书连续自动续期一个月无误后再启用：
		# Strict-Transport-Security "max-age=31536000; includeSubDomains"
	}

	# 只反代 UI。引擎 8502 与 RSSHub 1200 都不在这里出现。
	reverse_proxy 127.0.0.1:8501 {
		flush_interval -1                     # SSE 立即刷出，否则进度条会卡住
		transport http {
			read_timeout 0                     # 长连接：SSE 可持续数分钟
			write_timeout 0
		}
	}

	log {
		output file /var/log/caddy/trade.log {
			roll_size 20MiB
			roll_keep 5
		}
	}
}
```

要点：

- **只反代 8501**。引擎在内网回环，暴露它就等于绕过 UI 的登录页；
- `flush_interval -1` 不能省：进度流（SSE）被缓冲时表现为「卡住」；
- 日志会记录 URI 的查询串，所以**公网请用登录表单（POST）**，不要用
  `https://…/login?token=…` 这种链接（那是本机 `scripts/serve.sh` 打印给局域网的便捷方式）；
- 日志目录不存在时：`sudo install -d -o caddy -g caddy /var/log/caddy`。

应用与校验：

```bash
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl enable --now caddy      # 或 reload
sudo journalctl -u caddy -n 50 --no-pager     # 看证书申请过程
```

首次访问 `https://trade.dafeis.com` 时 Caddy 自动申请证书（需 80/443 可达、DNS 已生效）。

---

## 7. 防火墙

```bash
sudo ufw default deny incoming
sudo ufw allow 22/tcp      # 保留 SSH，按需改端口
sudo ufw allow 80,443/tcp
sudo ufw enable
sudo ufw status verbose
```

不该出现在公网的东西：8501、8502、1200。三条都只绑 `127.0.0.1`，`ufw` 只是第二道保险。

---

## 8. 上线验证（从外部机器）

```bash
# 1) 证书与健康检查
curl -fsS https://trade.dafeis.com/healthz                       # {"ok":true}
curl -s -o /dev/null -w '%{http_code}\n' https://trade.dafeis.com/    # 401（未登录）

# 2) 登录表单（POST，令牌不进日志）
curl -s -D - -o /dev/null -X POST https://trade.dafeis.com/login \
  --data-urlencode "token=$T" | grep -i set-cookie
#   期望：HttpOnly; Secure; SameSite=lax; Max-Age=2592000

# 3) 登录后页面与接口
curl -s -c jar -o /dev/null -X POST https://trade.dafeis.com/login --data-urlencode "token=$T"
curl -s -b jar -o /dev/null -w 'home %{http_code}\n' https://trade.dafeis.com/
curl -s -b jar -o /dev/null -w 'api  %{http_code}\n' https://trade.dafeis.com/api/runs

# 4) 引擎隔离
curl -s -o /dev/null -w '%{http_code}\n' http://<VPS_IP>:8502/   # 连不上 / 000
```

浏览器走一遍：登录 → 新建报告 → 观察进度流（应有逐条进度，不是一次性刷出）→ 打开报告。

---

## 9. 从家用机迁移（停机搬运）

同一时刻**只能有一个引擎**写 `state.db`，所以先停旧的再搬：

```bash
# 家用机
cd ~/projects/TradingAgents && scripts/serve.sh down
rsync -a ~/.tradingagents/ tradingagents@<VPS_IP>:/opt/TradingAgents/../.tradingagents/   # 见下方说明
scp .env tradingagents@<VPS_IP>:/opt/TradingAgents/.env      # 或逐项重填，两边 K 线口径一致

# VPS
sudo chown -R tradingagents:tradingagents /opt/TradingAgents/.tradingagents /opt/TradingAgents/.env
sudo systemctl restart tradingagents-engine tradingagents-ui
```

更稳的做法：VPS 上 `sudo -u tradingagents` 先建好 `~/.tradingagents`，用
`rsync -a ~/.tradingagents/ root@<VPS_IP>:/opt/TradingAgents/.tradingagents/`
（`/opt/TradingAgents` 是 `tradingagents` 用户的家目录，所以 `~` 就是它），再 `chown -R`。

迁移后家用机保持**不发车**（需要时反向搬一次即可）；两台不要同时启动引擎。

---

## 10. 日常运维

| 事项 | 做法 |
| --- | --- |
| 升级 | `cd /opt/TradingAgents && sudo -u tradingagents git pull && sudo -u tradingagents .venv/bin/pip install -e . && sudo systemctl restart tradingagents-engine tradingagents-ui` |
| 备份 | `tradingagents-backup.timer`（每天 03:30）→ `/var/backups/tradingagents/*.tar.gz`，保留 14 天；手动：`deploy/backup.sh [目标目录]` |
| 恢复 | 停两个服务 → `tar -xzf 归档 -C /` （归档内是 `home/…/.tradingagents` 与 `.env` 的相对路径，按需调整）→ 起服务 |
| 日志 | `journalctl -u tradingagents-engine -f`、`journalctl -u tradingagents-ui -f`；Caddy 在 `/var/log/caddy/trade.log` |
| 换令牌 | 改 `.env` 两处 → `systemctl restart tradingagents-engine tradingagents-ui` → 浏览器重新用表单登录 |
| 磁盘 | `du -sh /opt/TradingAgents/.tradingagents/*`；产物每次 ~0.44 MB，按需清理旧 run 目录 |
| 看门狗 | 单元已是 `Restart=always`；要更主动可加 `curl -f http://127.0.0.1:8501/healthz` 的 timer |

备份内容只包含无法重建的四类：`~/.tradingagents`（结果、`state.db`、memory）、`.env`。
代码与 `.venv` 不入档。

---

## 11. 排障对照表

| 现象 | 原因与处理 |
| --- | --- |
| 浏览器 401 反复出现 | 没登录或 cookie 被清；用 `/login` 表单登录。API 客户端用 `Authorization: Bearer` |
| 登录后立刻掉线 | 访问域名与 cookie 不一致（换了域名/端口）；清 cookie 重登 |
| `Set-Cookie` 里没有 `Secure` | 请求不是 HTTPS（Caddy 没生效），或反代没传 `X-Forwarded-Proto`（默认会传） |
| 证书签不下来 | 80 端口被占/防火墙拦、DNS 未生效、Cloudflare 橙云未配 Origin CA；`journalctl -u caddy` 看 ACME 报错 |
| 进度条卡住不动 | Caddy 少了 `flush_interval -1`，或中间还有一层缓冲代理 |
| 页面 200 但接口 502 | 引擎没起 / 挂了：`systemctl status tradingagents-engine`，`/api/engine/health` 返回 `{"online":false}` |
| 报告里新闻为空（`NO_ITEMS`）| RSSHub 不可达或 key 不一致；先 curl 一次 RSSHub 路由；RSS 源本身没有历史，历史日期天然为空 |
| 提交任务报 502 | 同「接口 502」；UI 只转发，不执行 |
| 报错「time zone / 日期不对」| `timedatectl set-timezone Asia/Shanghai`，并确认服务已重启 |
| 引擎 500，日志 `database is locked` | 起了两个引擎（例如旧机器还在跑）：只允许一个写者 |
| 服务起不来，日志 `ModuleNotFoundError` | `WorkingDirectory` 不在仓库根目录，`python -m` 找不到仓库内的包 |

---

## 12. 回滚

```bash
sudo systemctl stop caddy                    # 先断外网入口
sudo systemctl stop tradingagents-ui tradingagents-engine
# 回到单进程形态（不需要 Caddy，浏览器直连 8501）
cd /opt/TradingAgents && sudo -u tradingagents .venv/bin/python -m tradingagents_web --host 0.0.0.0 --port 8501
```

数据只在 `~/.tradingagents`，与前端、入口、Caddy 无关；把该目录搬回家用机即可完全复原。

---

## 附：本机（家用机）与 VPS 的差异

| 项 | 家用机 | VPS |
| --- | --- | --- |
| 起停 | `scripts/serve.sh up\|down\|status`（按需，无守护）| systemd 常驻，`Restart=always` |
| 入口 | 直连 `http://<内网IP>:8501` | Caddy + 域名 + 自动 HTTPS |
| UI 监听 | `0.0.0.0:8501` | `127.0.0.1:8501`（只有 Caddy 能到）|
| 登录 | `?token=` 链接方便（`serve.sh` 会打印）| 用表单（POST），避免令牌进访问日志 |
