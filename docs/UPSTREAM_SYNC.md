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

## 6. 演练记录（2026-10-31，已执行）

### 6.0 演练环境

| 项目 | 值 |
| --- | --- |
| 临时工作区 | `/tmp/opencode/sync-drill`（`git worktree`，演练后已删除） |
| 演练分支 | `drill/downstream-on-v0.7.0`（演练后已删除） |
| 基线起点 | tag `v0.7.0` = `e8f5503`（Merge PR #1536）。注意：分支 `origin/v0.7.0` 的 release 提交是 `f802271`，tag 指在它之上 |
| 上游目标 | `upstream/main` = `c454491` (v0.7.1) |
| 上游区间规模 | **22 个提交，37 个文件，+688 / −117** |

### 6.1 演练 1：下游提交落在 `v0.7.0` 基线，rebase 到 `v0.7.1`

| 步骤 | 命令 | 结果 |
| --- | --- | --- |
| 建立临时工作区 | `git worktree add /tmp/opencode/sync-drill -b drill/downstream-on-v0.7.0 v0.7.0` | ✅ 起点 `e8f5503` |
| 模拟下游提交 | `git cherry-pick ffab0e2`（D-0001 文档提交） | ✅ 生成 `e8543cd`，**无冲突** |
| 取上游 | `git fetch upstream --tags` | ✅ 标签/分支全部就绪 |
| 基线前进 | `git rebase upstream/main` | ✅ **成功，0 冲突** → `d4b71ec` |
| 历史检查 | `git log --oneline --graph` | ✅ 线性：`d4b71ec` → `c454491`（上游自身的 merge 提交保留在上游侧） |
| 全量测试 | `.venv/bin/python -m pytest -q` | ✅ **1412 passed, 1 skipped, 1 deselected, 100 subtests**（25.82s） |
| 导入验证 | `python -c "import tradingagents"` | ✅ 解析到**工作区**源码 `/tmp/opencode/sync-drill/tradingagents`，版本 0.7.1 |
| 清理 | `git worktree remove --force` + `git branch -D` | ✅ 临时分支 `drill/downstream-on-v0.7.0`、`drill/conflict-probe` 已删除 |

**为什么 0 冲突（可复现的证据）**：

```bash
# 上游本次改动的文件 ∩ 下游自有文件 = 空集
comm -12 <(git diff --name-only v0.7.0..upstream/main | sort) \
         <(git ls-tree -r --name-only HEAD | grep -E '^(AGENTS.md|docs/)' | sort)
# → 无输出
```

下游提交 100% 是新增文件（`AGENTS.md` + `docs/*.md`），没有一行触碰上游文件，因此 rebase 退化为"前移基点"。

### 6.2 演练 2：冲突场景探测（**仅探测，不产生生产改动**）

为验证"冲突发生时流程仍可用"，在同一个临时 worktree 里用 4 个临时提交探测冲突边界，
探针全部留在演练分支、演练后删除，**从未进入 `main`**：

| 探针 | 下游改动位置 | 上游同区间是否改过该处 | 结果 |
| --- | --- | --- | --- |
| A | `reporting.py` 的 `_SECTIONS` 中插入新章节 | ❌ 未改 `_SECTIONS` | ✅ 自动合并，无冲突 |
| B | `write_report_tree()` 开头的局部赋值行 | ⚠️ 改了同函数的 docstring 尾部 | ✅ 自动合并（改动行距 ≥3 行） |
| C | `reporting.py` 文件末尾追加常量 | ⚠️ 在 `return` 前插入了 14 行 | ✅ 自动合并 |
| D | `date_window.py::as_of()` **被上游重写的那 3 行** | ✅ 重写 | ❌ **CONFLICT (content)**，`UU tradingagents/dataflows/date_window.py` |

探针 D 的冲突现场与解决方式（演练中实际执行）：

```text
<<<<<<< HEAD                       # 上游 v0.7.1 的新实现
    if not trade_date:
        return requested if parsed is None else f"{parsed:%Y-%m-%d}"
    return f"{parsed:%Y-%m-%d}" if parsed is not None and parsed <= _parse(trade_date) else trade_date
=======
    # DRILL PROBE D: downstream re-implements the clamp
    return requested if parsed is not None and parsed <= _parse(trade_date) else trade_date
>>>>>>> eacd880 (upstream-patch: drill probe D)
```

解决策略（与第 3 节"冲突处理策略"一致）：**以上游版本为底，重放下游意图**
（保留上游的 canonical-date 实现，只把下游那行注释意图加回去）→ `git add` → `git rebase --continue`
→ 生成 `e590ef1`；随后 `pytest tests/test_date_boundaries.py` → **2 passed**。

### 6.3 结论与对补丁计划的影响

1. **当前阶段（docs-only）同步零风险**：22 个上游提交、37 个文件的变化全部落在上游自有文件上，
   下游 rebase 无冲突。这正是"先把规范立起来、再动代码"的窗口期。
2. **冲突不是按文件判定，而是按行判定**：同一个文件里，只要下游改的行与上游改的行相隔 ≥3 行，
   git 就能自动合并（探针 B/C）。真正的冲突只发生在**下游改制的行恰好被上游重写**时（探针 D）。
3. **因此"补丁要小、单文件、按文件聚合"是硬要求**：补丁越小、越集中在一处，上游重写该处的概率才可评估；
   大段改写必然长期冲突。
4. **本次上游区间实际触碰了 4 个"补丁候选文件"**：
   `tradingagents/reporting.py`、`tradingagents/agents/tools.py`、`tradingagents/graph/trading_graph.py`、
   `tradingagents/dataflows/date_window.py`。
   其中 `reporting.py`（P4）与 `agents/tools.py`（P5）正是草案补丁的目标 → **打这两个补丁时必须准备 rebase**；
   而 `dataflows/router.py`（P1）、`graph/setup.py` + `graph/analyst_execution.py`（P2）、
   `agents/state.py`、`default_config.py` 本次**未被上游改动** → 补丁落在这几个文件上，冲突概率最低。
5. **首次真同步（fork 建立后）仍应按第 3 节全流程走一遍**：本次演练没有推送、没有打 tag，
   也没有 `origin` 可推（见第 0 节）。

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
