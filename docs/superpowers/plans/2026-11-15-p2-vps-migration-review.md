# P2 计划评审（DeepSeek V4.1 Flash, 2026-11-15）

## 方法

读了计划全文、`kviewer/ops/{vps-deploy,vpsdeploy/{config,render,deploy,backup,envfile}.py}`、`vps-deploy-standard.md`、spec §13/§13.4、
TradingAgents 的 `default_config.py` / `tradingagents_web/{__main__,app,runner}.py` / `pyproject.toml` / `requirements-downstream.txt` / `deploy/`。
只读实跑：把 Task 3 的 app.toml 原文喂给 `parse_app_toml`+`validate_app`+`render_site`/`render_unit`/`render_cron`（errors=[], warnings=[]；300M/100% ×2）；
`git ls-remote --heads origin`；`git branch --show-current`；把 `kviewer/ops` 复制到 `/tmp/opencode/vps-ops-check` 跑 `pytest -q`（**193 passed in 14.60s**，计划数字成立）。
未写任何仓库、未连 VPS。

## 结论摘要

- 坏的四处都在「清单渲染结果」这一层，而且**不会以报错过早暴露**：站点把非 `/api/*` 全 404（页面、CSS 都打到不存在的 `dist/`）、分支名 `master` 在 fork 上不存在、build 少装 `requirements-downstream.txt`、`vps-apps` 包装器仍指 `/srv/kviewer/ops`。
- 两条监控判据是错的：`ProtectSystem=full` **不保护** `/home`（所以 TRADINGAGENTS_HOME 失效时是静默跑偏不是 EACCES），SSE 的 `flush_interval -1` 对 `text/event-stream` 被 Caddy 忽略。
- 备份范围窄于 spec §13.4-4：`data/logs`（每份报告实体）不在 `backup.paths`，恢复后 DB 与报告不一致。
- 五项前置形式上都覆盖了，但 #1/#2/#3 的验收判据需要改；#4 缺 Python 版本/venv 前置。

## 发现

### Critical（按计划执行必然翻车）

#### C1 站点只反代 `/api/*`，`/`、`/history`、`/runs/*`、`/login`、`/static/*` 全部 404

- **位置**：Task 3 Step 1 `deploy/app.toml`（`spa = false` + `api_paths = ["/api/*"]`），Task 4 Step 4 的「核对站点」。
- **问题**：实际渲染（逐字跑出来的）是
  ```
  handle /api/* { reverse_proxy 127.0.0.1:8801 }
  handle { root * /srv/tradingagents/dist ; file_server }
  ```
  `spa = false` 时兜底 `handle` **没有** `try_files`（`render.py:307-318`），就是把所有非 API 请求交给 `file_server` 去 `/srv/tradingagents/dist` 找——这个目录在 python runtime 下永远不存在（`plan_files` 只对 `runtime == "static"` 检查它）。
  而 UI 是**服务端渲染的多页应用**：`/`（app.py:484）、`/history`（491）、`/runs/{id}`（500）、`/runs/{id}/report`（511）、`/login`（336）、`/healthz`（343），外加 `app.mount("/static", ...)`（app.py:120）。所以部署会「成功」——health 探测走的是回环 `127.0.0.1:8801/healthz`，不经 Caddy——而上线后打开首页是 404、CSS/JS 也 404。
- **为什么必翻**：`spa = true` 也救不了（`try_files {path} /index.html` 之后还是 `file_server` 打 `dist/`）。工具没有「全部反代给动态应用」的专用开关，唯一表达方式是 `api_paths`。
- **建议修法**：`api_paths = ["/*"]`（已实测：`validate_app` 无 error/warning，渲染成 `handle /* { reverse_proxy 127.0.0.1:8801 }`，`spa = false` 保留以维持「无 try_files」语义）。
  Task 3 Step 2 顺带加一行断言 `assert "handle /*" in render_site(cfg)`；Task 4 Step 4 加「`render_site` 里对 `/`、`/static/*`、`/runs/*` 都命中同一 `handle`」的核对；Step 6 验收加 `curl -sI https://ta.dafeis.com/`（期望 200/401 的登录页，不是 404）与 `curl -sI https://ta.dafeis.com/static/<任一资源>`。

#### C2 `branch = "master"`，但 fork 只有 `main`

- **位置**：Task 3 Step 1 `branch = "master"`；Global Constraints 与 Task 2 Step 5「push fork 的 master」。
- **问题**：`git ls-remote --heads origin` 实测只有 `refs/heads/main`（外加 v0.x tag 分支），本地分支也是 `main`。
  `Deployer.fetch()`（deploy.py:318-336）执行 `git fetch --depth 1 origin master` 且 `check=True` → `CommandFailed` → 首次部署在第 2 步就 exit 1（还没到 build）。
- **为什么必翻**：这不是「回滚」而是「根本没跑起来」，而计划里所有验收都假定首次部署能过。
- **建议修法**：`branch = "main"`；同步 Global Constraints；Task 2 Step 5 改成 "push fork 的 `main`"（注意本仓 AGENTS.md §2 把 `main` 定为稳定下游分支——推 `main` 需要用户确认，或改走 `sync/`/tag 后由用户合并；这条要在计划里写明，别让执行者自行 push）。

#### C3 `pip install -e .` 装不出 `fastapi/uvicorn/jinja2/httpx/tushare`

- **位置**：Task 3 Step 1 的 `build`。
- **问题**：`pyproject.toml` 的 dependencies 里**没有** Web 栈：`requirements-downstream.txt` 明确写着「Not in upstream's pyproject.toml on purpose」，内含 `tushare`、`fastapi>=0.115`、`uvicorn[standard]>=0.30`、`jinja2`、`httpx`。
  `pip install -e .` 之后 `ExecStart=/srv/tradingagents/.venv/bin/python -m tradingagents_web` 直接 `ModuleNotFoundError: uvicorn` → 两 unit 都起不来 → 健康失败 → `cleanup_first_deploy()` → exit 1。
- **为什么必翻**：计划的 build 只跑了一条 pip；`requirements-lock.txt` 也不在 build 里，锁文件形同虚设。
- **建议修法**：
  ```toml
  build = [
    "python3 -m venv .venv",
    ".venv/bin/pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements-downstream.txt",
    ".venv/bin/pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -e .",
    ".venv/bin/python -c 'import tradingagents_web.app'",
  ]
  ```
  最后一条把「缺依赖」从健康检查阶段提前到 build 阶段（错误信息可读、且首次部署会走 build 失败分支而不是半部署）。若更想「一个清单说完」，可把 Web 栈加进 `pyproject.toml` 的 optional-dependencies——但那是上游文件，要按 AGENTS.md §3/§7 走 `upstream-patch:` 登记（见 I3）。

#### C4 Task 1 只改 `/usr/local/bin/vps-deploy`，`vps-apps` 仍指向 `/srv/kviewer/ops`

- **位置**：Task 1 Step 3 / Step 4。
- **问题**：`kviewer/docs/vps-deployment.md:41` 写明 `/usr/local/bin/vps-apps` 是「与 vps-deploy 同款、复制到临时文件执行、`PYTHONPATH=/srv/kviewer/ops` 必须保留」的第二个包装器。
  Step 4 `git rm -r ops/` + `vps-deploy kviewer` 之后 `/srv/kviewer/ops` 被 reset 掉 → `vps-apps` 立刻 `ImportError`。而 Task 4 的 Step 1（预检）、Step 5、Step 6 全都要用 `vps-apps`。
- **为什么必翻**：这不是「残留文档」而是日常驱动命令直接挂；且它发生在 Task 4 之前，执行者会在预检那一步卡住却不知道该改包装器。
- **建议修法**：Step 3 改成「重写**两个**包装器」并加发现步骤：`sudo grep -l "srv/kviewer/ops" /usr/local/bin/*`（实测已知需改：`vps-deploy`、`vps-apps`；`kviewer-backup` 是指向 `/srv/kviewer/deploy/backup-db.sh` 的软链，spec 不动 `deploy/`，安全）；改前 `sudo cp -a /usr/local/bin/{vps-deploy,vps-apps}{,.bak-preops}` 留一步回退。Step 4 完成后再跑一次 `vps-apps` 验证「kviewer 一行 + 无 ImportError」。

### Important（会造成返工或验收误导）

#### I1 Review Focus #1 的失效机制写错了：`ProtectSystem=full` 不保护 `/home`

- **位置**：Review Focus #1「进程在沙箱内写 `~`（ProtectSystem 拒绝）→ 500/OOM」；Task 4 Step 6。
- **问题**：渲染出的单元是 `ProtectSystem=full`（`render.py:220`），systemd 语义是 `/usr`、`/boot`、`/etc` 只读；**`/home` 仍可写**（那是 `strict`）。所以 `TRADINGAGENTS_HOME` 一旦没生效，`~/.tradingagents` 会被正常创建、health 全绿、日志里**永远不会出现 PermissionError**——状态静默落在 `data/` 之外，备份拿不到，换机即丢历史。
- **为什么重要**：按计划的判据（「journalctl 无 PermissionError」）会得到「通过」，而实际是最坏的一种失败（看起来正常）。
- **建议修法**：Step 6 保留 `ls data/`（`web/ state.db`、`memory/`，跑过一轮后 `logs/`），并加两条硬判据：`sudo test ! -e /home/ubuntu/.tradingagents && echo OK`、`sudo find /home/ubuntu -maxdepth 3 -name '.tradingagents' -o -name 'chatgpt-auth.json'`。Review Focus #1 的措辞改成「静默落到 `~`，备份失真」，删掉「ProtectSystem 拒绝 → 500/OOM」。

#### I2 Task 2 的测试片段引用了不存在的导出

- **位置**：Task 2 Step 1 的 `TRADE_CONFIG_DEFAULTS` / `get_defaults()`。
- **问题**：`default_config.py` 的真实导出是 `build_default_config()`（:77）与模块级 `DEFAULT_CONFIG`（:209），另有 `_TRADINGAGENTS_HOME`、`_apply_env_overrides`。两个候选名都不存在 → 表达式走 else 分支 → `AttributeError: module ... has no attribute 'get_defaults'`。Step 2 的「Expected: FAIL」会变成「测试自己炸了」，红的不是被测行为。
- **为什么重要**：这是标准 TDD 的红灯，红灯不可信的话后面绿了也没意义；而且计划自称「逐字」，执行者大概率照抄。
- **建议修法**：`cfg = importlib.reload(dc).build_default_config()`；再加一条 `assert importlib.reload(dc).DEFAULT_CONFIG["results_dir"] == cfg["results_dir"]`。另外**补一条真覆盖 app.py:94 的测试**：把 db 兜底抽成 `def default_db_path() -> Path` 再断言，并在测试里 `monkeypatch.delenv("TRADINGAGENTS_WEB_DB")`——这条路径才是 UI 起不来的那个。

#### I3 这是「改上游文件」的补丁，但没有按本仓规矩登记

- **位置**：Task 2 Step 3/5（改 `tradingagents/default_config.py`，提交前缀 `fix(config):`，测试落在 `tests/test_state_home.py`），Task 5 未提 `docs/UPSTREAM_DELTA.md` / `docs/EXTENSIONS.md`。
- **问题**：AGENTS.md §3/§7 要求改上游代码必须是独立 commit、前缀 `upstream-patch:`、登记到 `docs/UPSTREAM_DELTA.md`（D-xxxx，含冲突风险）、并有对应下游测试（下游测试按 §4 放 `tests/downstream/`）。`scripts/extension_inventory.py` 扫描的是 `tests/downstream/test_*.py` 与 `tradingagents_web/`、`tradingagents_cn/`——放在 `tests/` 根目录的新测试**不在审计面内**（而一旦挪进 `tests/downstream/`，`--check` 又会要求 `docs/EXTENSIONS.md` 同步该行）。
- **为什么重要**：不登记的话，下一次 `rebase upstream/main` 会把它当成意外冲突处理；也会被仓库自己的同步脚本/审查拦下，形成返工。
- **建议修法**：Task 2 拆成 (a) `upstream-patch: TRADINGAGENTS_HOME……` 提交 + `docs/UPSTREAM_DELTA.md` 新增一行 + `docs/EXTENSIONS.md` 增补；测试挪到 `tests/downstream/test_state_home.py` 并同步 EXTENSIONS.md。另注：**零补丁路线是存在的**——`TRADINGAGENTS_RESULTS_DIR`/`CACHE_DIR`/`MEMORY_LOG_PATH` 已在 :84-86 生效，`TRADINGAGENTS_WEB_DB` 已在 app.py:93 生效，四个变量写进 `.env` 即可得到同样的目录布局。用户裁定要 `TRADINGAGENTS_HOME` 这个单一开关，那就保留补丁，但把这条事实写进计划（万一 rebase 冲突，替代方案现成）。

#### I4 `.env` 里没有 `TZ`，而唯一设置时区的地方是 Task 3 要删的 README

- **位置**：Task 4 Step 3（「抄 11 键」）；被删的 `deploy/README.md` 里的 `sudo timedatectl set-timezone Asia/Shanghai`。
- **问题**：dev `.env` 实测 11 键里**不含 TZ**；渲染的单元也没有 `TZ=`。`app.py:257`（`trade_date <= date.today()`）与 `app.py:489`（首页 today）都吃进程本地时区。df-tc1 若是 UTC（云镜像默认），北京时间 00:00–08:00 期间「今天」是昨天 → 用户在早盘前跑当日分析会被 `date must be between … and today` 拒掉。
- **为什么重要**：这是每天 8 小时窗口的确定性功能缺陷，且症状（日期校验报错）完全不指向时区。
- **建议修法**：`.env` 加 `TZ=Asia/Shanghai`（变 12 键，计划里说明为什么多这一行）；Task 4 Step 1 预检加 `timedatectl`（或 `date`）确认机器时区，需要时作为「人工一次性系统动作」显式写出（vps-deploy 不管这个）。

#### I5 备份范围与状态实际落点不一致：报告实体在 `data/logs` 却没备

- **位置**：Task 3 `backup.paths = ["data/web/state.db", "data/memory"]`；Task 4 Step 10。
- **问题**：`results_dir` 现在是 `$TRADINGAGENTS_HOME/logs` = `/srv/tradingagents/data/logs`，`runner.py:183` 把每次运行的 `runs/<run_id>/`（report.md/html、`job.json`、`web.log`）写在这里，`state.db` 只记 `report_path`。恢复后 DB 说「有报告」，磁盘上没有 → `/runs/{id}/report`、`/runs/{id}/files/*` 全 404。spec §13.4-4 的原话是「backup.paths 只列 `~/.tradingagents` 与 `data/`」，本计划把它收窄了却没有交代。
- **为什么重要**：备份的可用性只能在「恢复演练」里暴露，而计划的 Step 10 只验「文件出现了」，会给出虚假的安心。
- **建议修法**：二选一并写进计划：(a) `paths = ["data/web/state.db", "data/memory", "data/logs"]`（接受 tarball 变大，每份运行 ~0.44 MB，可接受）；(b) 明确「报告不进备份，恢复后仅保留 DB 元数据」，并把这句写进 `deploy/README.md` 与 Task 4 Step 10 的验收。`data/cache` 是纯缓存，明确写「不备」。

#### I6 `vps-deploy backup` 遇到不存在的路径直接失败（首次/cron 会踩）

- **位置**：Task 4 Step 10；`backup.paths` 含 `data/memory`。
- **问题**：`run_backup` 对目录走 `tarfile.add`（backup.py:80-88），路径不存在抛 `FileNotFoundError`；`vps-deploy` 把它归到 `(OSError, RuntimeError, sqlite3.Error)` → exit 1。`data/memory` 只在第一次记录决策（`TradingMemoryLog.__init__` 的 mkdir）后才存在，`data/logs` 只在跑过一轮后存在。
- **为什么重要**：20:00 的 cron 在「装好但还没跑过任务」的窗口里会每天失败一次；Step 10 的成败取决于 Step 8 是否先跑过——这条顺序依赖现在没写。
- **建议修法**：Step 10 前注明「必须先完成 Step 8 的真实分析」（否则 `data/memory` 不存在）；或把 `paths` 换成一定存在的 `data/`（一次 tar 全状态，见 I5(a)），并把「路径缺失即失败」写进 `deploy/README.md` 的运维说明。

#### I7 SSE 的 contingency 瞄错了靶：`flush_interval -1` 对 `text/event-stream` 被忽略

- **位置**：Task 4 Step 9；Review Focus #2。
- **问题**：Caddy 官方文档（reverse_proxy 的 Streaming 节）：`flush_interval` 默认不做周期 flush，且 **「This option is ignored and responses are flushed immediately if … `Content-Type: text/event-stream`」**——`app.py:449` 的 `events` 正是 `media_type="text/event-stream"`，还会每 10 s 发 `: ping`。也就是说 Step 9 里那个「唯一允许的工具改动」对这条流**是空操作**（而且 `-1` 的副作用是客户端早断时不再取消后端请求）。真正可疑的是 (a) UI→engine 那一跳（`httpx` `aiter_raw`，已经是流式，但值得分层验证）和 (b) 站点里的 `encode zstd gzip`。
- **为什么重要**：按计划走，如果真观察到卡顿，改工具+重发两个应用一圈（含 kviewer 回归）之后问题还在，白付一次「工具变更」成本。
- **建议修法**：Step 9 改成三层对照 + 带鉴权：`/api/runs/{id}/events` 有 `require_read`（app.py:449），`curl -N` 必须带 `-H "Authorization: Bearer $TOKEN"`，否则只会拿到 401，测出来的「不分块」是假的。
  1. 直打 engine：`curl -N -H ... http://127.0.0.1:8802/api/runs/<id>/events`
  2. 直打 ui：`... http://127.0.0.1:8801/api/runs/<id>/events`
  3. 经 Caddy：`... https://ta.dafeis.com/api/runs/<id>/events`
  只有 3 慢而 2 正常时，先临时把站点里的 `encode` 去掉复测（`encode` 有 `minimum_length` 与压缩器 flush 行为），确认是压缩器再谈模板变更；`flush_interval` 留作最后手段（并在变更说明里写清「对 SSE 无效，加它是为了其它长响应」）。

#### I8 Task 4 预检缺 Python 侧前置（首部署最可能的 build 失败点）

- **位置**：Task 4 Step 1。
- **问题**：`pyproject.toml` 要求 `requires-python >= 3.11`；`python3 -m venv` 需要 `python3-venv`（Debian/Ubuntu 不带）。df-tc1 目前只跑过 Node 应用（kviewer），这两项从未被验证。缺失时表现为 build 失败 → `cleanup_first_deploy` → exit 1，报错信息指向 pip 而不是「装 python3-venv」。
- **为什么重要**：这是首次 Python 部署唯一的环境类前置，漏了会在最贵的阶段（clone+build 后）失败。
- **建议修法**：Step 1 加 `python3 -V`（≥3.11）、`python3 -m venv /tmp/venvprobe && ls /tmp/venvprobe/bin/pip && rm -rf /tmp/venvprobe`、`timedatectl`；缺 `python3-venv` 时 `sudo apt install -y python3-venv`（系统动作，人工执行，写进预检而不是 build）。

#### I9 Review Focus #3（ui→engine 代理）没有运行时判据

- **位置**：Review Focus #3 → Task 4 Step 4（dry-run）+ 工具既有测试。
- **问题**：dry-run 只证明「渲染出来的 ExecStart 文本对」，不证明这条链路通。UI 其实**自带**一条现成的探针端点：`/api/engine/health`（app.py:192，返回 `{"online": true/false}`）。
- **为什么重要**：502 是这套拓扑最常见的运行时故障，而目前没有一步会主动打它；等用户打开页面才发现。
- **建议修法**：Step 6 或 Step 7 加 `curl -s https://ta.dafeis.com/api/engine/health -H "Authorization: Bearer $TOKEN"` → 期望 `{"online":true}`；再补一条「engine 停掉时它返回 `{"online":false}`」的反向验证（可选）。

#### I10 OOM 与 `Requires=` 的连锁没验：engine 被杀可能连带停掉 ui 且不自愈

- **位置**：Task 4 Step 8（Review Focus #5）。
- **问题**：渲染的 ui 单元带 `Requires=tradingagents-engine.service`（`render.py:185-187`）。engine 被 OOM-kill（300M 硬上限正是本计划的担忧）→ `Requires` 会传播 stop 到 ui；engine 靠 `Restart=always` 自己回来，但 ui 是否被重新拉起**必须实测**（`Requires=` 与 `PartOf=` 的传播方向不同）。若 ui 停在 inactive，整站 502 且没有任何自动机制恢复，只有再跑一次 `vps-deploy`。
- **为什么重要**：把「内存紧」这个已知风险升级成「一次 OOM = 全站下线」，而 Step 8 只观察 MemoryCurrent，看不到这一层。
- **建议修法**：Step 8 加一步演练：`sudo systemctl kill -s KILL tradingagents-engine` → 30 s 后 `systemctl is-active tradingagents-{engine,ui}`。若 ui 未自愈，写进 `deploy/README.md` 的运行手册（「engine 崩溃后执行 `vps-deploy tradingagents`」），并在计划里注明这是工具模板的已知边界（本计划不改工具）。

### Minor（打磨）

- **M1 Task 1 Step 1 会提交 `__pycache__`**：`kviewer/ops` 下已有 `__pycache__/`、`.pytest_cache/`（我复制到 /tmp 跑 193 passed 时也带过去了），新仓没有 `.gitignore`，`git add -A` 会把 `.pyc` 永久入库。先写 `.gitignore`（`__pycache__/`、`.pytest_cache/`、`*.pyc`）再 `git add`。
- **M2 `gh repo create --private` 与 VPS 的 HTTPS clone 可能不匹配**：计划假设「走既有 github 代理配置」，但私仓 HTTPS 需要凭据。Step 3 的「验证」里加一条 `git -C /srv/vps-ops fetch --dry-run`（或 `ls-remote`），别只验证 `vps-deploy kviewer` 秒退。
- **M3 `deploy/env.example` 的「与 11 键对齐」是模糊指令**：现在文件里是 13 键，且缺 dev `.env` 真在用的 `TRADINGAGENTS_QUICK_THINK_LLM` / `TRADINGAGENTS_DEEP_THINK_LLM` / `MINIMAX_CN_API_KEY`，多了 `TRADINGAGENTS_ENGINE_TOKEN`/`TRADINGAGENTS_WEB_READ_TOKEN`/`TRADINGAGENTS_LLM_PROVIDER` 的组合说明。建议直接列出目标键表（11 + `TRADINGAGENTS_HOME` + `TZ`），并说明 `TRADINGAGENTS_ENGINE_TOKEN` 不填时 ui 会用 `TRADINGAGENTS_WEB_TOKEN` 转发（app.py:184），避免执行者把旧注释「两个令牌必须不同」当成硬约束。
- **M4 发布/回滚耗时基线要重记**：每次 deploy 与 rollback 都重跑 venv+pip（build 两条命令），回滚演练的耗时不会接近 kviewer 的 79 s；Step 5/7 记录数字时注明「含 build」，否则以后没人知道哪些时间是 venv 的。
- **M5 Task 3 Step 2 只验 `validate_app`，没验渲染**：加三条断言（`handle /*`、`MemoryMax=300M`、`Requires=tradingagents-engine.service`）——C1 这类问题正是「校验通过但渲染不对」。
- **M6 `spa = false` + `static_root="dist"` 的死代码要留注释**：渲染出的 `root * /srv/tradingagents/dist` 永远命不中（`handle /*` 在前），下一个人看站点文件会困惑。在 app.toml 里加一行注释说明「无 dist，页面由 ui 动态渲染，故 `api_paths = ["/*"]`」。
- **M7 Global Constraints 的「`.env` 11 键」与 I4 冲突**：改成「11 键 + `TZ` + `TRADINGAGENTS_HOME`」（13 行），并说明 `RSSHUB_BASE_URL`/`RSSHUB_TOKEN` 保留但旁路不可达（Step 8 的真实分析会顺带验证新闻降级是否真的「不阻断」——若它把整轮跑挂，应改成从 prod `.env` 里删掉这两个键）。

## 五项前置对照（§13.4 逐条：计划是否真覆盖）

| §13.4 | 计划落点 | 覆盖度 | 备注 |
|---|---|---|---|
| 1. `deploy/` 折叠（删 systemd/*/README、`apt/ufw/useradd//opt` 文案） | Task 3 Step 3（删 `deploy/systemd/`、`deploy/backup.sh`，重写 README） | ✅ 真覆盖 | 重写时要确认新 README 不再出现 `/opt/TradingAgents`、`useradd`、`ufw`、`apt install caddy`（§13.2-3 的原义）；`deploy/rsshub/` 保留与 `[[external]]` 一致 |
| 2. 路径 `/opt/...`→`/srv/tradingagents`、用户 `tradingagents`→`ubuntu` | Global Constraints + 渲染模板（实测 `User=ubuntu`、`WorkingDirectory=/srv/tradingagents`） | ✅ 真覆盖 | 无需额外动作，模板固定 |
| 3. `env_required` 只列「缺失会挂」的三个 | Task 3 Step 1，实测 dev `.env` 三键齐备 | ✅ 真覆盖 | 但需补 `TZ`（I4）；`TRADINGAGENTS_ENGINE_TOKEN` 不列是对的（ui 回落到 WEB_TOKEN） |
| 4. 备份不打包 `.env`，`backup.paths` 收 `~/.tradingagents` 与 `data/` | Task 3 `backup.paths` + Task 4 Step 10 | ⚠️ 部分覆盖 | `.env` 确实没进 paths（✅）；但范围收窄到 `state.db`+`memory`，丢了 `data/logs`（I5）、且不存在的路径会让备份失败（I6） |
| 5. SSE 经 Caddy 实测，不符再配 `flush_interval -1` | Task 4 Step 9 | ⚠️ 部分覆盖 | 实测步骤有，但缺鉴权（401 会被误读成「不分块」），且 contingency 选错靶（I7） |

Review Focus 映射：#1→Task 2 测试（红灯不可信，I2）+ Step 6（判据错，I1）；#2→Step 9（I7）；#3→Step 4（缺运行时判据，I9）；#4→Step 5（缺 Python 前置，I8；build recipe 本身错，C3）；#5→Step 8（缺 OOM 连锁验证，I10）。

## 总评

**GO-WITH-FIXES** —— 计划的结构、边界和「工具冻结、只改 app.toml」的取舍都对，但 4 个 Critical 全在「清单/包装器的一行内容」上（`api_paths`、`branch`、build 命令、第二个 wrapper），改完即可执行；Important 里 I1/I2/I7 不只是措辞问题，是验收会给出绿灯的错误判据，必须一起改。
