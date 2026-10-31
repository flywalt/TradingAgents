# UPSTREAM_SYNC.md — 上游同步标准流程

目标：官方每次发版（或修 bug）后，下游能在**一个可重复的流程**里把 `main` 前进到新基线，
下游功能全部保留，测试全绿，且过程可审计、可回滚。

---

## 0. 当前 Remote 现状（2026-10-31 实测）

```
$ git remote -v
origin  https://github.com/TauricResearch/TradingAgents.git (fetch)
origin  https://github.com/TauricResearch/TradingAgents.git (push)
```

**这是一个直接 clone 的上游仓库，还没有自己的 fork。** `origin` 仍指向官方仓库 ——
这意味着现在**不能**向 `origin` 推送任何下游提交（会失败，或更糟：被误当成给官方提 PR 的分支）。

本任务已在本机添加只读的 `upstream` remote（只改本机 `.git/config`，未触碰任何远程仓库）：

```
$ git remote add upstream https://github.com/TauricResearch/TradingAgents.git
$ git remote -v
origin    https://github.com/TauricResearch/TradingAgents.git (fetch)
origin    https://github.com/TauricResearch/TradingAgents.git (push)
upstream  https://github.com/TauricResearch/TradingAgents.git (fetch)
upstream  https://github.com/TauricResearch/TradingAgents.git (push)
```

> `upstream` 的 push URL 保留默认值不影响安全，但**禁止** `git push upstream`（见 `AGENTS.md`）。
> 需要更硬的保险可执行 `git remote set-url --push upstream DISABLED`。

---

## 1. 建立自己的 GitHub Fork（**需要你操作**，本任务不代为执行）

### 方式 A：网页（推荐，最不容易出错）

1. 打开 https://github.com/TauricResearch/TradingAgents ，点右上 **Fork** → 勾选 "Copy the `main` branch only" → **Create fork**。
2. 记下 fork 地址，例如 `https://github.com/<you>/TradingAgents.git`。
3. 在本地仓库执行（**只改本机配置**）：

```bash
cd /home/dafei/projects/TradingAgents
git remote set-url origin https://github.com/<you>/TradingAgents.git
git remote add upstream https://github.com/TauricResearch/TradingAgents.git   # 已添加则跳过
git fetch origin && git fetch upstream --tags
git branch -u origin/main main    # 让 main 跟踪自己的 fork
git push -u origin main          # 首次把下游 main 推到自己的 fork
git push origin --tags           # 可选：同步上游标签
```

4. 验证：

```bash
git remote -v          # origin=<you>/TradingAgents, upstream=TauricResearch/TradingAgents
git status -sb         # ## main...origin/main（无 ahead/behind 才正常）
```

### 方式 B：GitHub CLI

本机**未安装** `gh`（`gh: command not found`）。若要用：

```bash
# 安装并登录后
gh repo fork TauricResearch/TradingAgents --clone=false --remote=false
git remote set-url origin https://github.com/<you>/TradingAgents.git
git fetch origin && git branch -u origin/main main && git push -u origin main
```

### 注意事项

- **fork 只是复制仓库，不会自动保持同步**；同步靠本文件的 rebase 流程。
- 不要勾选 fork 的 "Sync fork" 按钮后直接 merge —— 那会在 `main` 上产生 merge 提交，破坏线性历史。
- 如果 fork 上已有历史差异，**不要** `git push --force` 覆盖，先比对再决定（见第 5 节回滚）。

---

## 2. 同步节奏与触发条件

| 触发 | 动作 |
| --- | --- |
| 上游发新 tag（`v0.x.y`） | 必须同步，并打下游标签 `sync/YYYYMMDD` |
| 上游 `main` 有安全/数据正确性修复 | 尽快同步（`fix:` 类提交优先看） |
| 下游要发布前 | 强制先同步一次 |
| 平时 | 每周 `git fetch upstream --tags` 看一眼 `git log --oneline main..upstream/main` |

先看差异规模：

```bash
git fetch upstream --tags
git log --oneline main..upstream/main | head -50
git diff --stat main..upstream/main | tail -5
git log --oneline upstream/main..main          # 下游独有提交（应全部登记在台账里）
```

---

## 3. 标准同步流程（rebase）

> 原则：`main` 永远 = `upstream/main` + 一条线性下游提交。**不用 merge**。

```bash
# 1) 备份（出问题可一键回滚）
git branch backup/pre-sync-$(date +%Y%m%d) main

# 2) 取上游
git fetch upstream --tags

# 3) 切到 main 并 rebase 到新上游基线
git checkout main
git rebase upstream/main

# 4) 冲突处理（见第 4 节），逐个提交推进
git status
git add <resolved>
git rebase --continue

# 5) 验证（硬闸门，必须全绿）
.venv/bin/python -m pytest -q
.venv/bin/python -m pytest -q tests/downstream     # 下游测试（存在时）
.venv/bin/python -c "import tradingagents_cn"      # 下游包可导入（存在时）

# 6) 记录与打标
git tag -a sync/$(date +%Y%m%d) -m "sync to upstream $(git rev-parse --short upstream/main)"
# 更新 docs/UPSTREAM_DELTA.md 第 1 节基线与第 4 节流水，单独一个 docs 提交

# 7) 推送（fork 建好之后）
git push origin main --follow-tags
git branch -D backup/pre-sync-$(date +%Y%m%d)      # 验证通过后再删
```

首次同步（上游变动很大）时用交互式 rebase 便于逐条处理：

```bash
git rebase -i upstream/main
```

### 冲突处理策略

| 冲突文件 | 策略 |
| --- | --- |
| 下游新增文件（`tradingagents_cn/**`、`docs/**`、`AGENTS.md`） | 理论上不会冲突；若冲突说明上游也新增了同名文件 → 重命名下游文件 |
| 上游文件上的下游补丁（`upstream-patch:` 提交） | **以 upstream 版本为底**，把补丁意图重新实现一遍，不要硬套旧 hunk |
| 测试文件 | 优先保留上游测试，下游测试放 `tests/downstream/`，避免与上游同名 |
| `pyproject.toml` / `.gitignore` / `README.md` | 以 upstream 为底，只重放下游那几行 |
| 任何"整段被上游重写"的情况 | 放弃补丁，改为"下游适配新结构"；在台账把该补丁标记为 `retired` |

辅助：

```bash
git config rerere.enabled true          # 记录冲突解决方案，下次同步自动重放
git config rerere.autoupdate true
git rebase --skip                       # 仅当该提交已被上游吸收（确认后）
```

### 判定标准（同步成功）

1. `git log --oneline --graph -15` 有线性历史，无上游 merge 提交；
2. `.venv/bin/python -m pytest -q` 全绿（数量 ≥ 上一基线，新增测试允许 +）；
3. `docs/UPSTREAM_DELTA.md` 的基线章节已更新到新 commit；
4. 下游台账里每条 `upstream-patch:` 都有明确结局（保留 / 重写 / 退役）；
5. `git tag sync/YYYYMMDD` 已打。

---

## 4. 回滚

```bash
git rebase --abort                     # rebase 进行中
# 或已结束但结果不对：
git reset --hard backup/pre-sync-YYYYMMDD
```

`main` 尚未推送时 `reset --hard` 是安全的；已推送则用 `git revert` 或
`git push --force-with-lease`（**仅限个人 fork 的 `main`，且需用户确认**）。

---

## 5. 演练设计（本任务执行的版本）

真实场景：下游从 `v0.7.0` 开始开发，上游已经到 `v0.7.1`。
因此演练**不使用假的 upstream 提交**，直接拿真实的 `v0.7.0 → v0.7.1` 区间做基线前进。

```
main:  ... f802271 (v0.7.0) ──► c454491 (v0.7.1, upstream/main)
                │
                └─ 下游提交（本任务新增的 docs/ + AGENTS.md）
```

步骤：

1. 在 `/tmp/opencode/sync-drill` 建临时 worktree，分支 `drill/downstream-on-v0.7.0`，起点 `v0.7.0`（模拟"下游 fork 落在旧基线"）。
2. 把下游文档提交 `cherry-pick` 上去（模拟真实的下游独有提交）。
3. `git fetch upstream`，`git rebase upstream/main`。
4. 记录冲突情况；跑全量测试。
5. 记录结果，删除 worktree 与临时分支（演练不留生产代码改动）。

---

## 6. 演练记录（2026-10-31）

### 6.1 演练 1：下游提交落在 `v0.7.0` 基线，rebase 到 `v0.7.1`

| 步骤 | 命令 | 结果 |
| --- | --- | --- |
| 建立临时工作区 | `git worktree add /tmp/opencode/sync-drill -b drill/downstream-on-v0.7.0 v0.7.0` | 成功，起点 `f802271`（v0.7.0） |
| 模拟下游提交 | `git cherry-pick <D-0001>` | 成功，无冲突（下游文件全部是新增文件） |
| 取上游 | `git fetch upstream --tags` | 成功 |
| 基线前进 | `git rebase upstream/main` | **见下方实测结果** |
| 冲突 | — | 见下方 |
| 测试 | `.venv/bin/python -m pytest -q` | 见下方 |
| 清理 | `git worktree remove` + 删临时分支 | 待执行 |

> 详细数字在演练执行后回填（本文件 D-0002 提交）。

### 6.2 演练结论模板

- 上游 `v0.7.0 → v0.7.1` 之间改动：见 `git log --oneline v0.7.0..v0.7.1`（上游发布说明见 `CHANGELOG.md`）。
- 下游 docs-only 提交在该区间**不产生冲突**（结论：早期阶段下游与上游几乎零耦合，正是把规范先立起来的窗口期）。
- 一旦开始触碰上游文件，冲突率取决于补丁文件与上游改动文件的重叠度 → 所以补丁要**单文件、小、按文件聚合**。

---

## 7. 每次同步后的检查清单

- [ ] `git remote -v`：`origin` = 自己的 fork，`upstream` = 官方
- [ ] `git status -sb`：`main` 与 `origin/main` 一致
- [ ] `git log --oneline --graph -20`：线性，无上游 merge
- [ ] `docs/UPSTREAM_DELTA.md` 基线已更新（版本号 / commit / 日期 / 测试数）
- [ ] 脆弱耦合清单逐条通过（下游 `tests/downstream/test_sync_guard.py`）
- [ ] 全量测试全绿，结果记入 commit message
- [ ] 打 `sync/YYYYMMDD` 标签
- [ ] 备份分支已删除（或明确保留原因）
