# systemd 单元

| 文件 | 作用 |
| --- | --- |
| `tradingagents-engine.service` | 队列 + worker + SQLite + 产物，`127.0.0.1:8502` |
| `tradingagents-ui.service` | 页面 + `/api` 转发，`127.0.0.1:8501`（由 Caddy 反代）|
| `tradingagents-backup.service` / `.timer` | 每天 03:30 归档结果、`state.db`、`.env` |

安装前把 `User`、`WorkingDirectory`、`ExecStart` 里的 `/opt/TradingAgents` 和
用户 `tradingagents` 换成实际值（`sed -i` 或直接编辑），否则服务起不来。

```bash
sudo cp deploy/systemd/tradingagents-*.service deploy/systemd/tradingagents-*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now tradingagents-engine tradingagents-ui tradingagents-backup.timer
```

备份目录 `/var/backups/tradingagents` 需对该用户可写：

```bash
sudo install -d -o tradingagents -g tradingagents /var/backups/tradingagents
```
