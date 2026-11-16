# TradingAgents P2 上线（vps-deploy 第二应用）实施计划 v2

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 TradingAgents（fork）作为 vps-deploy 标准的第二个应用迁到 df-tc1（`/srv/tradingagents`，双 unit engine/ui，域名 `ta.dafeis.com`），同时把部署工具从 kviewer 仓库抽成独立 `vps-ops` 仓库。

**Architecture:** 三段式：①抽 `vps-ops`（工具独立成仓，VPS **两个** wrapper 改指向）；②fork 按 `AGENTS.md` 下游纪律打最小补丁（`TRADINGAGENTS_HOME` 开关，`upstream-patch:` + 台账登记）+ 在 `chore/vps-deploy` 分支写 `deploy/app.toml` 收编旧 deploy/；③VPS 落地与验收（幂等/发布/回滚/SSE 分层实测/内存与 OOM 连锁）。工具本体冻结（193 测试 + 生产实证 + 审计四波修复）；SSE 缓冲时的排查路径以**去 `encode` 复测**为先（`flush_interval` 对 `text/event-stream` 是空操作，不作首选）。

**Tech Stack:** vps-deploy（Python 3.12 stdlib）、FastAPI/uvicorn（tradingagents_web）、venv + 清华 pypi、Caddy v2、systemd。

**Spec:** `kviewer/docs/superpowers/specs/2026-11-15-vps-deploy-standard-design.md` §13/§13.4；接入标准：`/home/dafei/projects/vps-deploy-standard.md`；本仓规范：`AGENTS.md`（尤其 §1/§2/§3/§6/§7）。

**评审记录:** v1 经独立评审（`docs/superpowers/plans/2026-11-15-p2-vps-migration-review.md`，GO-WITH-FIXES：4 Critical / 10 Important / 7 Minor），本 v2 已全部吸收；关键修正：`api_paths=["/*"]`（站点形态）、`branch="main"`、build 补 `requirements-downstream.txt` + import 冒烟、两个 wrapper 都要改、补丁按 fork 纪律登记、备份加 `data/logs`、`.env` 加 `TZ`、SSE 三层对照实测、venv/Python 预检、OOM 连锁演练。

## Global Constraints

- **分支纪律（本仓 AGENTS.md §2）**：TradingAgents 的所有改动在 `chore/vps-deploy` 分支上做，最后 `git merge --no-ff` 入 `main`；**push / 合并 main 前须用户确认**（§1）。commit 带 `Refs: D-xxxx` 与 `Tests:` 行（§7）。
- **上游补丁纪律（§3/§7）**：改 `tradingagents/` 内文件的提交必须 `upstream-patch:` 前缀 + `docs/UPSTREAM_DELTA.md` 登记（新 D-xxxx）+ 对应测试放 `tests/downstream/` + `docs/EXTENSIONS.md` 同步（`scripts/extension_inventory.py --check` 要过）。
- 测试跑法（§6）：`.venv/bin/python -m pytest -q tests/downstream`（快）；合并前全量 `.venv/bin/python -m pytest -q` 一次并记录数字。
- 端口：**engine 8802、ui 8801**（8800-8899 段内），一律回环。
- 状态目录：**`/srv/tradingagents/data`**，由 `TRADINGAGENTS_HOME` 单开关实现（用户裁定；零补丁替代方案——`TRADINGAGENTS_RESULTS_DIR`/`_CACHE_DIR`/`_MEMORY_LOG_PATH`/`_WEB_DB` 四个变量直配——写进 UPSTREAM_DELTA 作为 rebase 冲突时的退路）。
- **沙箱失效模式是静默跑偏不是 EACCES**：`ProtectSystem=full` 不保护 `/home`，所以验收必须硬性断言 `/home/ubuntu/.tradingagents` **不存在**。
- `.env` = dev 的 11 键 + `TZ=Asia/Shanghai`（日期边界依赖本地时区，不加则北京时间 0–8 点"今天"算成昨天）+ `TRADINGAGENTS_HOME=/srv/tradingagents/data`，共 13 行，权限 600；`env_required` 只列 `TRADINGAGENTS_WEB_TOKEN`、`OPENAI_COMPATIBLE_API_KEY`、`TUSHARE_TOKEN`（`TRADINGAGENTS_ENGINE_TOKEN` 不填，ui 回落 WEB_TOKEN）。
- 备份：`paths = ["data/web/state.db", "data/memory", "data/logs"]`（报告实体在 `data/logs`，不备则恢复后 DB 与报告不一致）；`data/cache` 明确不备；**不打包 `.env`**；cron `0 20 * * *`；keep 7。注意 `run_backup` 对不存在路径直接失败——备份验收必须在跑过真实任务之后。
- RSSHub 本次不上：`[[external]]` 仅登记，警告不阻断；Step 8 顺带验证新闻源降级不阻断主流程（若阻断 → 从 prod `.env` 删 `RSSHUB_*` 两键）。
- 分支名：fork 只有 `main`（实测 `ls-remote`），app.toml 写 `branch = "main"`。
- 仓库 `flywalt/TradingAgents`（大小写与 app 名不符）→ 不用 `--init`，手工 clone。
- pip 一律 `-i https://pypi.tuna.tsinghua.edu.cn/simple`；fork 的 `.venv` 里装 pytest 走官方源（AGENTS.md §6 已知清华镜像 403）。

## Review Focus

1. **`TRADINGAGENTS_HOME` 未生效 → 状态静默落到 `/home/ubuntu/.tradingagents`**（无报错、health 全绿、备份失真）。钉：Task 2 下游测试 + Task 4 Step 6 的 `test ! -e /home/ubuntu/.tradingagents` 硬断言。
2. **站点形态错**（`/api/*` 之外全 404）。钉：Task 3 Step 2 断言 `handle /*`；Task 4 Step 4 核对渲染 + Step 6 `curl -sI https://ta.dafeis.com/` 非 404。
3. **SSE 双跳被缓冲**（ui→engine httpx 流式 + Caddy `encode` 压缩器行为）。钉：Task 4 Step 9 三层对照（engine 直打 / ui 直打 / 经 Caddy，均带 Bearer）；排查先去 `encode`，`flush_interval` 对 SSE 无效不作首选。
4. **venv/依赖构建失败**（Web 栈不在 pyproject、python3-venv 缺失）。钉：build 含 `-r requirements-downstream.txt` + `import tradingagents_web.app` 冒烟；Task 4 Step 1 预检 venv 探针。
5. **内存与连锁**：300M/unit 过紧 → OOM；且 ui 带 `Requires=engine`，engine 被杀会连带停 ui，自愈与否必须实测。钉：Task 4 Step 8 内存记录 + `systemctl kill -s KILL` 演练；预案 `limits` 提 `800M` 重发。

---

### Task 1: 抽 `vps-ops` 独立仓库（工具与 kviewer 解耦）

**Files:**
- Create: `~/projects/vps-ops/`（= kviewer `ops/` 全量 + `README.md` + `.gitignore`）
- Modify: VPS `/usr/local/bin/vps-deploy` **与 `/usr/local/bin/vps-apps`**；kviewer 仓库（删 `ops/`）；`/home/dafei/projects/vps-deploy-standard.md`、`~/.config/opencode/AGENTS.md`

**Interfaces:**
- Produces: GitHub 仓 `flywalt/vps-ops`（dev 推送；VPS 以 PAT 凭据助手 https 克隆到 `/srv/vps-ops`）；两个 wrapper 均从 `/srv/vps-ops` 取脚本、`PYTHONPATH=/srv/vps-ops`。

- [ ] **Step 1: dev 侧建仓**

```bash
mkdir -p ~/projects/vps-ops && cd ~/projects/vps-ops
cp -r ../kviewer/ops/{vps-deploy,vpsdeploy,tests,pytest.ini} .
printf '__pycache__/\n.pytest_cache/\n*.pyc\n' > .gitignore
git init -b master
```

`README.md`（≤40 行）：是什么；标准文档与 app.toml 指南指到 `/home/dafei/projects/vps-deploy-standard.md`；如何改工具（TDD：`cd ~/projects/vps-ops && python3 -m pytest`）；如何发布（push → VPS `git -C /srv/vps-ops pull` → 自举滞后一轮说明）。

- [ ] **Step 2: 测试全绿 + 建远端 + 推送**

Run: `cd ~/projects/vps-ops && python3 -m pytest -q` → Expected: 193 passed。
建远端：优先 `gh repo create flywalt/vps-ops --private`（先 `gh auth status` 确认）；否则**请用户网页建仓**。`git remote add origin git@github.com:flywalt/vps-ops.git && git push -u origin master`（推送前向用户确认一次）。

- [ ] **Step 3: VPS 切换两个 wrapper**

先备份：`sudo cp -a /usr/local/bin/vps-deploy /usr/local/bin/vps-deploy.bak-preops && sudo cp -a /usr/local/bin/vps-apps /usr/local/bin/vps-apps.bak-preops`。
克隆：`git clone https://github.com/flywalt/vps-ops.git /srv/vps-ops`（凭据助手走 `~/.config/git-deploy/token`，同 kviewer）；`git -C /srv/vps-ops fetch --dry-run` 验证私仓可拉。
重写 `/usr/local/bin/vps-deploy`（`cp /srv/vps-ops/vps-deploy "$tmp"; PYTHONPATH=/srv/vps-ops exec python3 …`）；**`vps-apps` 一并重写**（同样从 `/srv/vps-ops` 取，不再依赖旧路径）。
兜底扫描：`sudo grep -l "srv/kviewer/ops" /usr/local/bin/*` → 除 `.bak-preops` 外应为空。
验证：`vps-apps` 出 kviewer 一行；`vps-deploy kviewer` 幂等秒退（marker 不变）。

- [ ] **Step 4: kviewer 退位为消费者**

kviewer 仓库：`git rm -r ops/`；`docs/vps-deployment.md`、`docs/infra-inventory.md` 中 ops/ 路径表述改 vps-ops → push。VPS `vps-deploy kviewer` 一次（树与远端一致，`/srv/kviewer/ops` 消失）→ **再跑一次 `vps-apps` 验证无 ImportError**。
同步改 `/home/dafei/projects/vps-deploy-standard.md` 与 `~/.config/opencode/AGENTS.md` 的工具位置表述 → `~/projects/vps-ops`（VPS `/srv/vps-ops`）。

- [ ] **Step 5: 提交推送**（vps-ops、kviewer 各自）

---

### Task 2: fork 补丁——`TRADINGAGENTS_HOME` 环境开关（按下游纪律）

**Files:**
- Create: `chore/vps-deploy` 分支
- Modify: `tradingagents/default_config.py:3`；`tradingagents_web/app.py:94`（db 兜底抽成 `default_db_path() -> Path` 并跟随开关）
- Test/docs: `tests/downstream/test_state_home.py`；`docs/UPSTREAM_DELTA.md`（新 D-xxxx）；`docs/EXTENSIONS.md`（同步该测试行，过 `scripts/extension_inventory.py --check`）

**Interfaces:**
- Produces: `TRADINGAGENTS_HOME` 优先于 `~/.tradingagents`（default_config 与 web db 兜底一致跟随）。

- [ ] **Step 1: 建分支 + 写失败测试（`tests/downstream/test_state_home.py`）**

```python
import importlib
from pathlib import Path

def test_tradingagents_home_env_overrides_default(monkeypatch, tmp_path):
    monkeypatch.setenv("TRADINGAGENTS_HOME", str(tmp_path))
    import tradingagents.default_config as dc
    cfg = importlib.reload(dc).build_default_config()
    assert cfg["results_dir"].startswith(str(tmp_path))
    assert cfg["data_cache_dir"].startswith(str(tmp_path))
    assert cfg["memory_log_path"].startswith(str(tmp_path))
    assert importlib.reload(dc).DEFAULT_CONFIG["results_dir"] == cfg["results_dir"]

def test_default_db_path_follows_home(monkeypatch, tmp_path):
    monkeypatch.setenv("TRADINGAGENTS_HOME", str(tmp_path))
    monkeypatch.delenv("TRADINGAGENTS_WEB_DB", raising=False)
    from tradingagents_web.app import default_db_path
    assert default_db_path() == Path(tmp_path) / "web" / "state.db"
```

（`build_default_config` / `DEFAULT_CONFIG` 是 `default_config.py` 的真实导出；`TRADINGAGENTS_WEB_DB` 是 app.py:93 既有 env 覆盖。）

- [ ] **Step 2: 红灯** — Run: `.venv/bin/python -m pytest -q tests/downstream/test_state_home.py` → Expected: FAIL（`AttributeError: default_db_path` / 路径在 `~` 下）。

- [ ] **Step 3: 实现两处**

`default_config.py:3` → `_TRADINGAGENTS_HOME = os.getenv("TRADINGAGENTS_HOME") or os.path.join(os.path.expanduser("~"), ".tradingagents")`。
`app.py` db 兜底抽 `def default_db_path() -> Path: return Path(_TRADINGAGENTS_HOME) / "web" / "state.db"`，原 `… or Path.home()/…` 处调用之。

- [ ] **Step 4: 绿灯 + 台账** — Run 同 Step 2 → PASS；`scripts/extension_inventory.py --check` 过。
`docs/UPSTREAM_DELTA.md` 新增条目（D-xxxx）：改了哪两处、为什么（沙箱内状态归位）、上游无相关 PR、冲突风险低（两行）；**退路写明**：零补丁可用四个 env 直配（`TRADINGAGENTS_RESULTS_DIR/_CACHE_DIR/_MEMORY_LOG_PATH/_WEB_DB`）。

- [ ] **Step 5: 提交（两个，不混合）**

```bash
git commit -m "upstream-patch: TRADINGAGENTS_HOME 环境变量优先于 ~/.tradingagents

Refs: D-xxxx
Tests: pytest -q tests/downstream/test_state_home.py → 2 passed"
```

（deploy/ 相关改动留给 Task 3，另起 commit。）

---

### Task 3: `deploy/app.toml` 与 deploy/ 目录收编（同在 `chore/vps-deploy`）

**Files:**
- Create: `deploy/app.toml`
- Delete: `deploy/systemd/`、`deploy/backup.sh`
- Modify: `deploy/README.md`（重写，删除 `/opt`、`useradd`、`ufw`、`apt install caddy` 等裸机文案）、`deploy/env.example`；`deploy/rsshub/` 保留

**Interfaces:**
- Consumes: Task 1 的 vps-ops（dev 校验用其 parser/renderer）。
- Produces: 标准 manifest，Task 4 消费。

- [ ] **Step 1: 写 `deploy/app.toml`（逐字）**

```toml
name = "tradingagents"
runtime = "python"
repo = "https://github.com/flywalt/TradingAgents.git"
branch = "main"                      # fork 只有 main（master 不存在）

build = [
  "python3 -m venv .venv",
  ".venv/bin/pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements-downstream.txt",
  ".venv/bin/pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -e .",
  ".venv/bin/python -c 'import tradingagents_web.app'",   # 缺依赖在 build 期暴露，不留给健康检查
]

domain = "ta.dafeis.com"
spa = false                           # 服务端渲染多页应用：无 dist，全部请求反代给 ui
api_paths = ["/*"]                    # /、/history、/runs/*、/static/* 都是动态页，catch-all 必须反代而非 file_server
static_root = "dist"                  # 占位：handle /* 在前，此 root 永不命中（见上行注释）

env_required = ["TRADINGAGENTS_WEB_TOKEN", "OPENAI_COMPATIBLE_API_KEY", "TUSHARE_TOKEN"]
limits = { memory = "600M", cpu = "200%" }

backup = { paths = ["data/web/state.db", "data/memory", "data/logs"], keep = 7, cron = "0 20 * * *" }

[[units]]
name = "engine"
start = "-m tradingagents_web --role engine --host 127.0.0.1 --port 8802"
port = 8802
health = "/healthz"

[[units]]
name = "ui"
start = "-m tradingagents_web --role ui --host 127.0.0.1 --port 8801 --engine http://127.0.0.1:8802"
port = 8801
health = "/healthz"
public = true
depends_on = ["engine"]

[[external]]
name = "rsshub"
url = "http://127.0.0.1:1200"
note = "新闻源旁路，缺了降级不阻断；本次不部署（df-tc1 无 docker）"
```

- [ ] **Step 2: dev 侧校验（校验 + 渲染断言）**

```bash
cd ~/projects/vps-ops && python3 - <<'EOF'
import sys; sys.path.insert(0,'.')
from pathlib import Path
from vpsdeploy.config import parse_app_toml, validate_app
from vpsdeploy.render import render_site, render_unit, render_cron, split_limits
cfg = parse_app_toml(Path('../TradingAgents/deploy/app.toml').read_text())
env = {'TRADINGAGENTS_WEB_TOKEN':'x','OPENAI_COMPATIBLE_API_KEY':'x','TUSHARE_TOKEN':'x'}
ps = validate_app(cfg, env=env, port_owner={8787:('kviewer','app')})
assert not [p for p in ps if p.level=='error'], [p.message for p in ps]
site = render_site(cfg)
assert 'handle /*' in site and 'reverse_proxy 127.0.0.1:8801' in site
ui = render_unit(cfg, cfg.units[1], exec_start='x', memory='300M', cpu='100%')
assert 'MemoryMax=300M' in ui.split('MemoryMax')[1][:8] + 'MemoryMax' or 'MemoryMax=300M' in ui
assert 'Requires=tradingagents-engine.service' in ui
assert render_cron(cfg).startswith('0 20 * * *')
assert split_limits('600M','200%',2) == [('300M','100%'),('300M','100%')]
print('manifest + rendering OK')
EOF
```

Expected: `manifest + rendering OK`。

- [ ] **Step 3: deploy/ 收编**

删 `deploy/systemd/`、`deploy/backup.sh`；`deploy/README.md` 重写：走 vps-deploy 标准（指 `/home/dafei/projects/vps-deploy-standard.md`）+ 应用特有说明（env 键位表 = 11 + `TZ` + `TRADINGAGENTS_HOME`，`ENGINE_TOKEN` 回落说明；双 unit 拓扑与 8801/8802；备份含 `data/logs`、`data/cache` 不备、**路径不存在时备份会失败**的运维注记；OOM/`Requires` 连锁的运行手册；RSSHub 何时再上）。`deploy/env.example` 改成同样的 13 键表。

- [ ] **Step 4: 提交**（`chore(deploy): 收编为 vps-deploy 标准…`，`Refs: D-xxxx`，`Tests:` 行贴 Step 2 输出与 `.venv/bin/python -m pytest -q tests/downstream` 结果）

---

### Task 4: VPS 落地与验收

**Files:** 无代码改动（失败回 Task 2/3）

- [ ] **Step 1: 预检（含 Python 侧）** — `df -h /`（余量 >15G）、`free -m`；`python3 -V`（≥3.11）；`python3 -m venv /tmp/venvprobe && ls /tmp/venvprobe/bin/pip && rm -rf /tmp/venvprobe`（缺则 `sudo apt install -y python3-venv`，人工系统动作）；`timedatectl`（确认时区，`TZ` 由 `.env` 兜底）；`vps-apps` 确认 kviewer 正常。
- [ ] **Step 2: 手工 clone** — `git clone https://github.com/flywalt/TradingAgents.git /srv/tradingagents`（大小写不符，不走 `--init`）。
- [ ] **Step 3: `.env`** — dev 11 键 + `TZ=Asia/Shanghai` + `TRADINGAGENTS_HOME=/srv/tradingagents/data`，`chmod 600`。
- [ ] **Step 4: dry-run** — `vps-deploy --dry-run tradingagents`：核对两 unit ExecStart（`.venv/bin/python -m …`、8802/8801、ui 带 `--engine`）、**站点 `handle /* { reverse_proxy 127.0.0.1:8801 }`（`/`、`/static/*`、`/runs/*` 全走它）**、cron `0 20 * * *`。
- [ ] **Step 5: 首次部署** — `time vps-deploy tradingagents`（build 四条，venv+pip 预计数分钟，上限 1800 s；耗时记录注明"含 build"）。Expected: exit 0，两 unit 健康；`vps-apps` 两行；`systemctl is-enabled tradingagents-{engine,ui}` 均 enabled。
- [ ] **Step 6: 落位与入口检查（Review Focus #1/#2）** — `ls /srv/tradingagents/data/`（`web/`、跑过任务后有 `memory/ logs/`）；**`sudo test ! -e /home/ubuntu/.tradingagents && echo HOME-OK`**；`sudo find /home/ubuntu -maxdepth 3 \( -name '.tradingagents' -o -name 'chatgpt-auth.json' \)` 为空；`curl -sI https://ta.dafeis.com/` 非 404（200/401 登录页）；带 token `curl -s https://ta.dafeis.com/api/engine/health -H "Authorization: Bearer $TRADINGAGENTS_WEB_TOKEN"` → `{"online":true}`（ui→engine 链路运行时判据）。
- [ ] **Step 7: 验收三连** — 幂等秒退（<5 s；build 重跑 venv+pip 属正常，耗时另记）→ dev 改一行 README → 合并 `chore/vps-deploy` 入 main（**经用户确认**）→ push → 真实发布（marker 更新）→ 回滚演练（坏 start → 已回滚 exit 1 → 恢复重发；耗时含 build，与 kviewer 79 s 不可比）。
- [ ] **Step 8: 真实任务 + 内存 + OOM 连锁（Review Focus #5）** — 跑一次真实分析；记录 `systemctl show tradingagents-{engine,ui} -p MemoryCurrent`；观察 RSSHub 降级是否阻断（阻断则从 prod `.env` 删 `RSSHUB_*`）；`sudo systemctl kill -s KILL tradingagents-engine` → 30 s 后 `is-active` 两单元——ui 若未自愈，写进 deploy/README 运行手册（已知边界，本计划不改工具）；任一内存逼近 300M 或 OOM → `limits` 提 `800M` 重发一次。
- [ ] **Step 9: SSE 三层对照（Review Focus #3，均带 `Authorization: Bearer $TOKEN`，否则 401 会伪装成"不分块"）** — 同一 run 的 `/api/runs/<id>/events`：① `curl -N http://127.0.0.1:8802/...`（engine 直打）② `...:8801/...`（ui 直打）③ `https://ta.dafeis.com/...`（经 Caddy）。仅 ③ 卡而 ② 正常时，**先临时去掉站点 `encode` 复测**（压缩器 flush 行为），确认后再谈模板变更；`flush_interval -1` 对 `text/event-stream` 无效，只作最后手段并注明。
- [ ] **Step 10: 备份验证（须在 Step 8 之后）** — `vps-deploy backup tradingagents` → `/srv/tradingagents/backup/` 出现 `state-YYYYMMDD.db`、`memory-*.tar.gz`、`logs-*.tar.gz`，无 `.env`。

---

### Task 5: 文档收口与合并

**Files:**
- Modify: `/home/dafei/projects/vps-deploy-standard.md`（第二应用实例、vps-ops 位置）、`kviewer/docs/{vps-deployment,infra-inventory}.md`（vps-ops 引用、8801/8802、ta.dafeis.com）、`TradingAgents/deploy/README.md`（验收数据：幂等/发布/回滚/SSE 三层/内存/OOM 演练）、`docs/UPSTREAM_DELTA.md`、`~/.config/opencode/AGENTS.md`

- [ ] **Step 1:** 逐文件更新（上表）；TradingAgents 侧验收数据含各步实测耗时（注明含 build）。
- [ ] **Step 2:** 死链检查 `grep -rn "kviewer/ops" ~/projects/vps-deploy-standard.md ~/projects/kviewer/docs ~/.config/opencode/AGENTS.md` → 仅历史语境命中。
- [ ] **Step 3:** `chore/vps-deploy` 全量测试一次（`.venv/bin/python -m pytest -q`，数字写进 merge commit）；**经用户确认后** `git merge --no-ff` 入 `main` 并 push；vps-ops / kviewer 各自提交推送。

---

## Self-Review（v2）

**Spec §13.4 对照:** 1→Task 3 Step 3（裸机文案一并清除）；2→模板固定 + Step 4 核对；3→Task 3 Step 1 + `TZ` 补充；4→backup.paths 三路径 + Step 10（Step 8 之后）；5→Task 4 Step 9 三层对照（flush contingency 降级为最后手段）。全覆盖。
**Review Focus ↔ 钉子:** #1→Task 2 测试 + Step 6 硬断言；#2→Task 3 Step 2 断言 + Step 4/6；#3→Step 9；#4→build 四条 + Step 1 预检；#5→Step 8。
**评审吸收:** C1–C4、I1–I10、M1–M7 全部落位（关键：api_paths=/*、branch=main、requirements-downstream、双 wrapper、fork 纪律、TZ、data/logs、SSE 三层带鉴权、venv 预检、OOM 演练、.gitignore、私仓 PAT、env.example 13 键表、耗时口径、渲染断言、app.toml 注释、RSSHub 键处理）。
**类型一致:** 8802 engine / 8801 ui / ta.dafeis.com / /srv/tradingagents/data / branch main 全文一致。
