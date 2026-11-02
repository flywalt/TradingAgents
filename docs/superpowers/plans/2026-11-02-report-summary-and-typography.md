# 报告摘要卡 + 中文排版 + 图对称 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 中文报告结论先行、排版顺眼，流程图接线对称——全部在呈现层，上游零改动。

**Architecture:** `report_page.present()` 在服务时注入一段 `ta-cn` 样式与一张"核心结论"卡；
`progress_graph.py` 宽屏分析师行动态居中。磁盘产物与英文报告逐字节不变。

**Tech Stack:** 纯 Python 字符串手术 + CSS 注入；无新依赖。

**Spec:** `docs/superpowers/specs/2026-11-02-report-summary-and-typography-design.md`

## Global Constraints

- 只改 `tradingagents_web/` 与 `tests/downstream/`；`docs/` 仅登记。
- 英文运行的报告输出与上游产物**逐字节一致**（`test_an_english_run_is_returned_unchanged` 锁定）。
- 正文原样：摘要卡是**复制**摘录，第五节本身一个字符不改。
- 注入恰一次（`present()` 幂等），坏结构不抛异常、不注入。
- 新耦合标记并入 `UPSTREAM_MARKERS` 并在守卫测试中对真实渲染断言。

---

### Task 1: 中文排版注入（C）

**Files:**
- Modify: `tradingagents_web/report_page.py`
- Test: `tests/downstream/test_web_report_page.py`

- [ ] **Step 1: RED** — 追加测试：中文输出含 `<style id="ta-cn">` 恰一次、位于 `</head>` 之前、含
  `Noto Serif CJK SC` 与 `body` 行距覆盖；英文输出无 `ta-cn`。
- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: GREEN** — `present()` 中文分支在 `</head>` 前注入样式：覆盖 `--serif`（补
  Noto Serif CJK SC / Source Han Serif SC / Songti SC / SimSun）、`--sans`（补 PingFang SC /
  Noto Sans CJK SC / Microsoft YaHei）、`body` 为 `17px/1.85`。已含 `ta-cn` 则跳过（幂等）。
- [ ] **Step 4: 运行确认通过；Commit** `feat(web): set the chinese report in type that can read it`

### Task 2: 核心结论卡（A）

**Files:**
- Modify: `tradingagents_web/report_page.py`
- Test: `tests/downstream/test_web_report_page.py`（夹具 `_upstream_report` 补组合经理一节）

- [ ] **Step 1: RED** — 追加测试：
  - SAMPLE 含 PM 节时，中文输出在 `</header>` 后有 `<section class="ta-summary"`，含摘录文本与
    `href="#s5"`（锚点取真实节号）、"阅读完整结论"；
  - 无 PM 节（现 SAMPLE）→ 无卡、不抛异常；
  - 第五节正文完整保留；`present(present(x)) == present(x)`。
- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: GREEN** — 锚 `<h3 id="sN-1">Portfolio Manager</h3>`：回溯最近 `<section id="sM">`
  取节号；取 h3 后至 `</section>` 的正文，摘前两个 `<p>…</p>`（无则前 500 字符）；卡含标题
  "核心结论"、摘录、锚点链接，样式进 `ta-cn` 块（`--wash` 底、`--accent` 左线）。
- [ ] **Step 4: 运行确认通过；Commit** `feat(web): lead the chinese report with the decision`

### Task 3: 宽屏分析师行动态居中（图对称）

**Files:**
- Modify: `tradingagents_web/progress_graph.py`
- Test: `tests/downstream/test_web_progress_graph.py`

- [ ] **Step 1: RED** — 追加测试：n∈{1,2,4} 时宽屏分析师组中心与 bull 中心偏差 ≤1。
- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: GREEN** — 宽屏 `analyst_x` 改为按 `start = bull中心 − 组宽/2` 计算；memory 跟行尾。
- [ ] **Step 4: 全部几何测试通过；Commit** `fix(web): centre the analyst row on the debate entry`

### Task 4: 守卫、文档、上线

- [ ] `UPSTREAM_MARKERS` 增 `</head>`、`</header>`、`<h3 id="s`、`Portfolio Manager</h3>`、
  `--serif:`、`--sans:`；守卫夹具补 PM 节并逐一断言于真实渲染。
- [ ] `docs/UPSTREAM_DELTA.md` 脆弱耦合栏补摘要卡/排版耦合；登记 D-0053；`docs/B4_INTERACTION_SPEC.md`
  §9.1 增摘要卡与排版两行。
- [ ] 全量 `pytest -q` + `ruff` + inventory；重启 8501；浏览器核验中文报告页首；merge 回 main 并推送。
