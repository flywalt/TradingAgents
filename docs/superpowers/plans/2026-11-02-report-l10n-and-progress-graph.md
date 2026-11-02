# 报告本地化 + 进度图 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让报告页在中文运行时全中文，并让运行页用一张实时点亮的拓扑图代替"读时间戳猜进度"。

**Architecture:** 报告在**服务时**转换（`report_page.present()`，磁盘产物不动）；拓扑与坐标算在 **Python**（可测），点亮与动画在**一个静态 JS 文件**里（只管画）。运行页的既有交互（SSE、计时器、重新运行）与图一起搬进同一个静态脚本，页面因此仍然只有一个 `<script>`。

**Tech Stack:** FastAPI + Jinja2 + 内联 SVG + 原生 JS/CSS。无新依赖，无构建步骤。

**Spec:** `docs/superpowers/specs/2026-11-02-report-l10n-and-progress-graph-design.md`

## Global Constraints

- 不改 `tradingagents/`、`tradingagents_cn/`。只改 `tradingagents_web/` 与 `tests/downstream/`。
- 报告本地化**只在服务时**生效：`complete_report.md` / `complete_report.html` 的磁盘内容不变。
- 只替换允许清单里的固定标签；**绝不动报告正文**。
- 无新运行时依赖；无 CDN、无 webfont（LAN 无外网）。
- 每页渲染结果中 `<script` 恰好 1 个（现有测试 `tests/downstream/test_web_api.py::test_each_page_has_exactly_one_script_block` 强制）。
- 中文标签以 `tradingagents_web/labels.py` 为唯一来源；模板与 JS 不得再建一份。
- 颜色语义沿用现有 paper 主题：运行中=琥珀、完成=墨色、失败=红；不引入第四种颜色语言。
- 390px 宽度可读，除表格外不横向滚动；`prefers-reduced-motion: reduce` 时无动效。

## Review Focus

- **英文运行**（`language=English`）的报告必须**完全不变**：一个中文字符都不应出现。
- **未提供评级**的报告（`<h1>` 里没有 `<span class="rating ...">`）：转换函数必须原样返回，不能抛异常。
- **历史旧运行**（`d486cccd…` 这类只有 `node.started`、没有 `node.finished` 的记录）：终态运行时图上不能有节点永远"运行中"。
- **只选部分分析师**（如只勾 `market`）：图上未选的分析师不得出现，且汇合边不能指向不存在的节点。
- **报告 HTML 缺失、只剩 markdown** 的降级路径：走 `text/plain`，不做 HTML 转换。
- **上游改了报告标记**（标签重命名/结构变化）：必须让 `test_web_report_page.py` 先红，而不是页面静默退回英文。
- **页面脚本只剩一个**：图、时间线、计时器、重跑都进同一个静态脚本，任何新增 `<script>` 都会让既有测试红。

---

### Task 1: 标签单一来源

**Files:**
- Create: `tradingagents_web/labels.py`
- Modify: `tradingagents_web/app.py`（`RATING_LABELS = {...}` 整段 ⇒ 改为导入）
- Test: `tests/downstream/test_web_labels.py`

**Interfaces:**
- Produces:
  - `labels.RATING_LABELS: dict[str, str]` — 内核枚举 → 中文
  - `labels.NODE_LABELS: dict[str, str]` — 内核节点英文名 → 中文（13 项，**必须**覆盖 `tradingagents_web.runner.NODE_NAMES` 全部）
  - `labels.ANALYST_NODES: dict[str, str]` — 提交用 analyst key → 内核节点英文名
  - `labels.REPORT_SECTION_LABELS: dict[str, str]` — 上游章节英文名 → 中文（5 个 `_SECTIONS` 标题 + `Downstream run metadata`）

`NODE_LABELS` 的取值（逐字）：

```python
{
    "Market Analyst": "市场分析师", "Sentiment Analyst": "情绪分析师",
    "News Analyst": "新闻分析师", "Fundamentals Analyst": "基本面分析师",
    "Memory Log": "记忆检索", "Bull Researcher": "多头研究员",
    "Bear Researcher": "空头研究员", "Research Manager": "研究经理",
    "Trader": "交易员", "Aggressive Analyst": "激进风险分析师",
    "Conservative Analyst": "保守风险分析师", "Neutral Analyst": "中性风险分析师",
    "Portfolio Manager": "组合经理",
}
```

`ANALYST_NODES`：`market→Market Analyst`、`social→Sentiment Analyst`、`news→News Analyst`、
`fundamentals→Fundamentals Analyst`。

- [ ] **Step 1: Write the failing test**

```python
# tests/downstream/test_web_labels.py
import pytest

from tradingagents_web import labels
from tradingagents_web.runner import NODE_NAMES

pytestmark = pytest.mark.unit


def test_every_kernel_node_has_a_chinese_label():
    assert set(labels.NODE_LABELS) == set(NODE_NAMES)
    assert all(label.strip() for label in labels.NODE_LABELS.values())


def test_every_analyst_key_maps_to_a_kernel_node():
    assert set(labels.ANALYST_NODES.values()) <= set(NODE_NAMES)
    assert set(labels.ANALYST_NODES) == {"market", "social", "news", "fundamentals"}


def test_rating_labels_cover_the_kernel_enums():
    assert labels.RATING_LABELS == {
        "Buy": "乐观", "Overweight": "偏乐观", "Hold": "中性",
        "Underweight": "偏审慎", "Sell": "审慎", "REVIEW": "需人工复核",
    }


def test_the_report_sections_have_chinese_names():
    assert labels.REPORT_SECTION_LABELS["Analyst Team Reports"] == "分析师团队报告"
    assert labels.REPORT_SECTION_LABELS["Downstream run metadata"] == "下游运行元数据"
    assert len(labels.REPORT_SECTION_LABELS) == 6
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest -q tests/downstream/test_web_labels.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'tradingagents_web.labels'`

- [ ] **Step 3: Create `tradingagents_web/labels.py`, and make `app.py` import from it**

`app.py` 里 `RATING_LABELS = {...}` 整段删除，改为 `from .labels import RATING_LABELS`（`rating_label`
过滤器与模板用法不变）。

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest -q tests/downstream/test_web_labels.py tests/downstream/test_web_api.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tradingagents_web/labels.py tradingagents_web/app.py tests/downstream/test_web_labels.py
git commit -m "refactor(web): one source for the Chinese node and rating labels"
```

---

### Task 2: 报告 HTML 的呈现本地化

**Files:**
- Create: `tradingagents_web/report_page.py`
- Test: `tests/downstream/test_web_report_page.py`

**Interfaces:**
- Consumes: `labels.RATING_LABELS`, `labels.REPORT_SECTION_LABELS`
- Produces: `report_page.present(html: str, language: str | None) -> str` — 非中文原样返回；中文返回转换后的 HTML

替换清单（逐条精确匹配，**顺序即执行顺序**）：

| 目标 | 原文 | 中文 |
| --- | --- | --- |
| 语言标记 | `<html lang="en">` | `<html lang="zh-CN">` |
| 页签后缀 | `: TradingAgents report</title>` | ` · TradingAgents 研究报告</title>` |
| 日期行前缀 | `>Analysis of ` | `>分析日期 ` |
| 返回顶部 | `<a class="to-top" href="#top">Top</a>` | `<a class="to-top" href="#top">回到顶部</a>` |
| 章节标题 | `<h2>I. Analyst Team Reports</h2>` … | `<h2>一、分析师团队报告</h2>` … |
| 浮层导航章节名 | `<span class="label">Analyst Team Reports</span>` … | `<span class="label">分析师团队报告</span>` … |
| 浮层导航序号 | `<span class="num">I</span>` … | `<span class="num">一</span>` … |
| 元信息标签 | `<dt>Generated</dt>` 等 8 个 | 见下 |
| 评级 | `<span class="rating {tone}">Hold</span>` | `<span class="rating {tone}" title="Hold">中性</span>` |

元信息标签：`Generated→生成时间`、`Deep model→深度模型`、`Quick model→快速模型`、`Analysts→分析师`、
`Debate rounds→辩论轮次`、`Data vendors→数据源`、`Version→版本`、`Memory log→历史记忆`。

章节：`Analyst Team Reports→分析师团队报告`、`Research Team Decision→研究团队结论`、
`Trading Team Plan→交易团队方案`、`Risk Management Team Decision→风险管理团队结论`、
`Portfolio Manager Decision→组合经理决策`、`Downstream run metadata→下游运行元数据`。
序号：`I→一`、`II→二`、`III→三`、`IV→四`、`V→五`。

- [ ] **Step 1: Write the failing tests**

```python
# tests/downstream/test_web_report_page.py
import pytest

from tradingagents_web import report_page

pytestmark = pytest.mark.unit

SAMPLE = """<!doctype html>
<html lang="en">
<head><title>600519.SH 2026-11-02 Hold: TradingAgents report</title></head>
<body>
<header><h1><span class="ticker">600519.SH</span> <span class="rating level">Hold</span></h1>
<p class="date">Analysis of 2026-11-02</p>
<dl class="run"><div><dt>Generated</dt><dd>2026-11-02 13:22</dd></div>
<div><dt>Debate rounds</dt><dd>1</dd></div></dl></header>
<nav class="contents" aria-label="Sections"><ul><li><a href="#s1"><span class="num">I</span>
<span class="label">Analyst Team Reports</span></a></li></ul></nav>
<main><section id="s1"><h2>I. Analyst Team Reports</h2><h3>Market Analyst</h3>
<p>正文中的 Generated、Analysts 这些词不该被翻译。</p></section>
<section id="s6"><h2>Downstream run metadata</h2></section></main>
<a class="to-top" href="#top">Top</a>
</body>
</html>"""


def test_a_chinese_run_gets_a_chinese_masthead():
    out = report_page.present(SAMPLE, "中文")

    assert '<html lang="zh-CN">' in out
    assert '<p class="date">分析日期 2026-11-02</p>' in out
    assert "<dt>生成时间</dt>" in out
    assert "<dt>辩论轮次</dt>" in out
    assert "<h2>一、分析师团队报告</h2>" in out
    assert "<h2>下游运行元数据</h2>" in out
    assert '<span class="num">一</span>' in out
    assert '<span class="label">分析师团队报告</span>' in out
    assert "回到顶部" in out
    assert "研究报告</title>" in out


def test_the_rating_keeps_its_kernel_word_in_the_tooltip():
    out = report_page.present(SAMPLE, "中文")

    assert '<span class="rating level" title="Hold">中性</span>' in out


def test_the_report_body_is_never_touched():
    out = report_page.present(SAMPLE, "中文")

    assert "正文中的 Generated、Analysts 这些词不该被翻译。" in out
    assert "<h3>Market Analyst</h3>" in out


def test_an_english_run_is_returned_unchanged():
    assert report_page.present(SAMPLE, "English") == SAMPLE
    assert report_page.present(SAMPLE, None) == SAMPLE


def test_a_report_without_a_rating_is_left_alone():
    html = SAMPLE.replace(' <span class="rating level">Hold</span>', "")

    out = report_page.present(html, "中文")
    assert "中性" not in out
    assert '<h1><span class="ticker">600519.SH</span></h1>' in out


def test_the_markup_we_match_is_still_produced_upstream():
    """Fragile coupling: if upstream renames its markup this fails at sync time."""
    from tradingagents import reporting

    headings = [heading for heading, _folder, _agents in reporting._SECTIONS]
    assert headings == [
        "I. Analyst Team Reports", "II. Research Team Decision",
        "III. Trading Team Plan", "IV. Risk Management Team Decision",
        "V. Portfolio Manager Decision",
    ]
    for marker in ('<html lang="en">', '<p class="date">Analysis of ',
                   '<a class="to-top" href="#top">Top</a>', '<dt>Generated</dt>',
                   '<span class="rating ', 'aria-label="Sections"'):
        assert marker in report_page.UPSTREAM_MARKERS, marker
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest -q tests/downstream/test_web_report_page.py`
Expected: FAIL — `ModuleNotFoundError` / 缺 `present`

- [ ] **Step 3: Implement `present()`**

`UPSTREAM_MARKERS` 是模块级字符串常量，逐条列出本模块依赖的上游标记（与上面测试同字面量）。
`present()`：非中文（`language` 为 `None` 或不以 `中文` / `zh` 开头）⇒ 原样返回；否则按表顺序
`str.replace`，评级用 `re.sub(r'<span class="rating ([a-z]+)">([A-Za-z]+)</span>', ...)` 加 `title`。
每个替换都带标签字面量，正文里的裸词不会被误改。

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest -q tests/downstream/test_web_report_page.py`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add tradingagents_web/report_page.py tests/downstream/test_web_report_page.py
git commit -m "feat(web): present the report in the run's language, without touching the artifact"
```

---

### Task 3: 接到报告路由

**Files:**
- Modify: `tradingagents_web/app.py`（`report()` 路由，约 343-360 行；`from . import db, jobs, security` 一行加 `report_page`；`fastapi.responses` 导入加 `Response`）
- Test: `tests/downstream/test_web_api.py`（追加两个用例）

**Interfaces:**
- Consumes: `report_page.present(html, language)`

- [ ] **Step 1: Write the failing tests**

```python
def test_the_report_page_follows_the_run_language(client, tmp_path):
    report_dir = tmp_path / "report"
    report_dir.mkdir()
    (report_dir / "complete_report.html").write_text(
        '<!doctype html><html lang="en"><body><p class="date">Analysis of 2026-11-02</p>'
        '<a class="to-top" href="#top">Top</a></body></html>', encoding="utf-8")

    conn = db.connect(tmp_path / "state.db")
    try:
        run_id = jobs.create(conn, symbol="600519.SH", market="CN", profile="CN_A_SHARE",
                             trade_date="2026-10-30", analysts=["market"], language="中文",
                             strict=False, portfolio_json=None)
        jobs.finish(conn, run_id, rating="Hold", run_dir=str(tmp_path),
                    report_path=str(report_dir / "complete_report.md"))
    finally:
        conn.close()

    response = client.get(f"/runs/{run_id}/report", headers=AUTH)

    assert response.status_code == 200
    assert '<html lang="zh-CN">' in response.text
    assert "回到顶部" in response.text
    assert response.headers["content-type"].startswith("text/html")


def test_an_english_report_is_served_as_written(client, tmp_path):
    report_dir = tmp_path / "report"
    report_dir.mkdir()
    (report_dir / "complete_report.html").write_text(
        '<!doctype html><html lang="en"><body><a class="to-top" href="#top">Top</a>'
        '</body></html>', encoding="utf-8")

    conn = db.connect(tmp_path / "state.db")
    try:
        run_id = jobs.create(conn, symbol="AAPL", market="US", profile="UPSTREAM_DEFAULT",
                             trade_date="2026-10-30", analysts=["market"], language="English",
                             strict=False, portfolio_json=None)
        jobs.finish(conn, run_id, rating="Hold", run_dir=str(tmp_path),
                    report_path=str(report_dir / "complete_report.md"))
    finally:
        conn.close()

    response = client.get(f"/runs/{run_id}/report", headers=AUTH)

    assert '<html lang="en">' in response.text
    assert response.text.count("回到顶部") == 0
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest -q tests/downstream/test_web_api.py -k report`
Expected: FAIL — 中文断言不成立

- [ ] **Step 3: Wire it in**

`report()` 里，取到 `served, media_type` 之后：`media_type == "text/html"` 时读文件、过 `present()`，
用 `Response(content=..., media_type="text/html", headers=...)` 返回（保留
`Content-Security-Policy` 与 `X-Content-Type-Options`）；`text/plain` 分支继续用 `FileResponse`。

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/bin/python -m pytest -q tests/downstream/test_web_api.py`
Expected: PASS (17 passed)

- [ ] **Step 5: Commit**

```bash
git add tradingagents_web/app.py tests/downstream/test_web_api.py
git commit -m "feat(web): serve the report in the run's language"
```

---

### Task 4: 拓扑与坐标（纯 Python）

**Files:**
- Create: `tradingagents_web/progress_graph.py`
- Test: `tests/downstream/test_web_progress_graph.py`

**Interfaces:**
- Consumes: `labels.ANALYST_NODES`, `labels.NODE_LABELS`
- Produces: `progress_graph.topology(analysts: list[str]) -> dict`，形状：

```python
{
  "wide":   {"viewBox": "0 0 960 640",
             "nodes": [{"id": "bull", "label": "多头研究员", "kernel": "Bull Researcher",
                        "x": 280, "y": 168, "w": 150, "h": 48}, ...],
             "edges": [{"from": "analyst-market", "to": "bull", "kind": "flow",
                        "d": "M 115 96 V 132 H 355 V 168"}, ...]},
  "narrow": {"viewBox": "0 0 360 680", "nodes": [...], "edges": [...]},
}
```

`kind` ∈ `flow`（交接）、`debate`（双向来回）、`bypass`（记忆检索旁路）。
节点 id：`analyst-market`/`analyst-social`/`analyst-news`/`analyst-fundamentals`、`memory`、`bull`、
`bear`、`research-manager`、`trader`、`risk-aggressive`/`risk-conservative`/`risk-neutral`、`portfolio`。

宽屏（`w=150, h=48`，viewBox `0 0 960 640`）：

| id | x | y |
| --- | --- | --- |
| analyst-market | 40 | 48 |
| analyst-social | 216 | 48 |
| analyst-news | 392 | 48 |
| analyst-fundamentals | 568 | 48 |
| memory | 760 | 48 |
| bull | 280 | 168 |
| bear | 530 | 168 |
| research-manager | 405 | 272 |
| trader | 405 | 368 |
| risk-aggressive | 150 | 464 |
| risk-conservative | 405 | 464 |
| risk-neutral | 660 | 464 |
| portfolio | 405 | 560 |

窄屏（viewBox `0 0 360 680`；分析师与 `memory` 用 `w=240, x=60`；辩论对 `w=150`；风险三节点 `w=100`；
其余 `w=240, x=60`）：

| id | x | y | w |
| --- | --- | --- | --- |
| analyst-market | 60 | 24 | 240 |
| analyst-social | 60 | 84 | 240 |
| analyst-news | 60 | 144 | 240 |
| analyst-fundamentals | 60 | 204 | 240 |
| memory | 60 | 264 | 240 |
| bull | 20 | 340 | 150 |
| bear | 190 | 340 | 150 |
| research-manager | 60 | 408 | 240 |
| trader | 60 | 472 | 240 |
| risk-aggressive | 20 | 540 | 100 |
| risk-conservative | 130 | 540 | 100 |
| risk-neutral | 240 | 540 | 100 |
| portfolio | 60 | 616 | 240 |

窄屏 `h=44`；宽屏 `h=48`。

边（两套布局同一套语义，`d` 由矩形算）：

- 每个起始节点（所选分析师 + `memory`）→ `bull`，`kind="flow"`。
- `bull` ⇄ `bear`：同排水平线，`kind="debate"`。
- `bull` → `research-manager`、`bear` → `research-manager`：辩论出环，`kind="flow"`。
- `research-manager` → `trader` → `risk-aggressive`：`kind="flow"`。
- `risk-aggressive` → `risk-conservative` → `risk-neutral` → `risk-aggressive`：三段 `kind="debate"`。
- `risk-neutral` → `portfolio`：`kind="flow"`。
- `memory` → `portfolio`：`kind="bypass"`，沿画布留白绕行。

- [ ] **Step 1: Write the failing tests**

```python
# tests/downstream/test_web_progress_graph.py
import pytest

from tradingagents_web import progress_graph

pytestmark = pytest.mark.unit

ALL = ["market", "social", "news", "fundamentals"]


def _boxes(layout):
    return {n["id"]: n for n in layout["nodes"]}


@pytest.mark.parametrize("width", ["wide", "narrow"])
def test_the_layout_draws_every_core_node(width):
    ids = set(_boxes(progress_graph.topology(ALL)[width]))

    assert {"bull", "bear", "research-manager", "trader", "portfolio"} <= ids
    assert {"analyst-market", "analyst-social", "analyst-news", "analyst-fundamentals"} <= ids
    assert {"risk-aggressive", "risk-conservative", "risk-neutral", "memory"} <= ids


@pytest.mark.parametrize("width", ["wide", "narrow"])
def test_only_the_selected_analysts_are_drawn(width):
    layout = progress_graph.topology(["market"])[width]
    ids = set(_boxes(layout))

    assert "analyst-market" in ids
    assert not {"analyst-social", "analyst-news", "analyst-fundamentals"} & ids
    assert all(e["from"] in ids and e["to"] in ids for e in layout["edges"])


@pytest.mark.parametrize("width", ["wide", "narrow"])
def test_no_two_nodes_overlap(width):
    boxes = list(_boxes(progress_graph.topology(ALL)[width]).values())

    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            separated = (a["x"] + a["w"] <= b["x"] or b["x"] + b["w"] <= a["x"]
                         or a["y"] + a["h"] <= b["y"] or b["y"] + b["h"] <= a["y"])
            assert separated, (a["id"], b["id"])


@pytest.mark.parametrize("width", ["wide", "narrow"])
def test_every_node_fits_inside_the_viewbox(width):
    layout = progress_graph.topology(ALL)[width]
    _, _, width_px, height_px = (int(v) for v in layout["viewBox"].split())

    for node in layout["nodes"]:
        assert node["x"] >= 0 and node["y"] >= 0
        assert node["x"] + node["w"] <= width_px
        assert node["y"] + node["h"] <= height_px


@pytest.mark.parametrize("width", ["wide", "narrow"])
def test_every_edge_is_a_path_between_two_known_nodes(width):
    layout = progress_graph.topology(ALL)[width]
    ids = set(_boxes(layout))

    for edge in layout["edges"]:
        assert edge["from"] in ids and edge["to"] in ids
        assert edge["d"].startswith("M ")
        assert edge["kind"] in {"flow", "debate", "bypass"}


@pytest.mark.parametrize("width", ["wide", "narrow"])
def test_the_debate_pairs_are_marked_as_debates(width):
    layout = progress_graph.topology(ALL)[width]
    pairs = {(e["from"], e["to"]) for e in layout["edges"] if e["kind"] == "debate"}

    assert ("bull", "bear") in pairs
    assert ("risk-aggressive", "risk-conservative") in pairs
    assert ("risk-conservative", "risk-neutral") in pairs
    assert ("risk-neutral", "risk-aggressive") in pairs


def test_every_node_carries_its_kernel_name_and_chinese_label():
    bull = _boxes(progress_graph.topology(ALL)["wide"])["bull"]

    assert bull["kernel"] == "Bull Researcher"
    assert bull["label"] == "多头研究员"
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest -q tests/downstream/test_web_progress_graph.py`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement `topology()`**

按两张坐标表建 `nodes`；`_edge(src, dst, kind)` 算 `d`：垂直交接 `M cx1 (y1+h) V … H cx2 V y2`，
同排水平 `M (x1+w) cy H x2`，`bypass` 沿 viewBox 留白 12px 绕行。未选中的分析师不进 `nodes`、
不产生边。标签取自 `labels.NODE_LABELS[node_kernel]`。

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/bin/python -m pytest -q tests/downstream/test_web_progress_graph.py`
Expected: PASS (15 passed)

- [ ] **Step 5: Commit**

```bash
git add tradingagents_web/progress_graph.py tests/downstream/test_web_progress_graph.py
git commit -m "feat(web): compute the run topology and both layouts in Python"
```

---

### Task 5: 运行页画图（含把页面脚本收拢成一个静态文件）

**Files:**
- Create: `tradingagents_web/static/run-page.js`
- Modify: `tradingagents_web/templates/run.html`（加图；内联脚本整体搬走；只留一个 `<script src>`）
- Modify: `tradingagents_web/static/app.css`（图与动画样式，追加到末尾）
- Modify: `tradingagents_web/app.py::run_page()`（传 `graph=progress_graph.topology(json.loads(job["analysts"]))`）
- Test: `tests/downstream/test_web_api.py`（追加用例）

**Interfaces:**
- Consumes: `progress_graph.topology()`、`labels.NODE_LABELS`
- Produces: `run-page.js` 读 `<main id="main" data-run-id data-terminal>` 与
  `<svg id="progress-graph" data-graph='…'>`，自行挂载图、SSE/轮询、计时器、重新运行

`run.html` 需要的新上下文（`app.py::run_page` 里补齐）：`graph`（拓扑 dict）。JS 需要的运行信息走
`data-` 属性，不再用模板内联变量。

- [ ] **Step 1: Write the failing test**

```python
def test_the_run_page_draws_the_graph_for_the_selected_analysts(client, tmp_path):
    conn = db.connect(tmp_path / "state.db")
    try:
        run_id = jobs.create(conn, symbol="600519.SH", market="CN", profile="CN_A_SHARE",
                             trade_date="2026-10-30", analysts=["market"], language="中文",
                             strict=False, portfolio_json=None)
    finally:
        conn.close()

    page = client.get(f"/runs/{run_id}", headers=AUTH)

    assert page.status_code == 200
    assert "panel panel--graph" in page.text
    assert 'role="img"' in page.text
    assert "多头研究员" in page.text            # label reaches the page from Python
    assert "情绪分析师" not in page.text        # that analyst was not selected
    assert page.text.count("<script") == 1
    assert "/static/run-page.js" in page.text
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest -q tests/downstream/test_web_api.py -k graph`
Expected: FAIL — 找不到 `panel--graph`

- [ ] **Step 3: Build it**

`run.html`

- `<main id="main" class="container" …>`：在 `app.py` 的 `run_page()` 里改为传
  `graph`，模板给 `<body>`/`<main>` 加 `data-run-id="{{ run.id }}"` 与
  `data-terminal="{{ (run.status in ('succeeded', 'failed')) | tojson }}"`。
- 进度卡**之前**插：

```html
<section class="panel panel--graph" aria-labelledby="graph-title">
  <div class="panel__head">
    <h2 id="graph-title">流程</h2>
    <p class="graph__legend"><span class="graph__key graph__key--run">运行中</span>
      <span class="graph__key graph__key--done">已完成</span>
      <span class="graph__key graph__key--flow">交接</span></p>
  </div>
  <svg id="progress-graph" class="graph" role="img"
       aria-label="{{ run.symbol }} 分析流程：分析、研究、交易、风险、组合五个阶段"
       data-graph="{{ graph | tojson }}"></svg>
  <p class="hint">图上只表流程；逐条事件仍在下方“进度”中。</p>
</section>
```

- 把原来的内联 `<script>…</script>` 整块删掉，换成
  `<script src="/static/run-page.js?v=1" defer></script>`（全页仍只有一个 `<script`）。

`run-page.js`（一个文件，顺序：读取 DOM 数据 → 建图 → 事件处理 → 计时器 → 重新运行）

- 布局选择：`matchMedia('(min-width: 720px)')`，切换时整体重绘（保留当前状态）。
- 状态：`idle | active | done | failed`；`node.started → active`、`node.finished → done`、
  `run.failed → active 的节点变 failed`。
- 边：目标刚变 active 时给上游边加 `is-flowing`，目标 done 时移除；辩论边在两端点交替 active 时加
  `is-debate`，并在中点写 `第 n 轮`（同名节点重复 `node.started` 即一轮）。
- 终态运行：同步重放全部事件（无定时动画）；**只有 `node.started` 而没有 `node.finished` 的历史记录，
  重放结束时按 `done` 呈现**。
- 时间线：沿用现有行为（事件文案用 `graph` 里 `kernel → label` 推导，不再硬编码 `nodeLabels`；
  找不到时回退内核英文名）；SSE 断线仍降级为 5 秒轮询并在终态 `location.reload()`。

`app.css` 追加：`.graph`（`width: 100%; height: auto`，由 viewBox 定比例）、`.graph__legend`、
`.node` 的四态（`rect` 描边/填充）、`.edge`（`stroke: var(--color-rule-2)`）、
`.edge.is-flowing`（`stroke-dasharray: 5 5; animation: flow 600ms linear infinite; color: var(--color-cool)`）、
`.edge.is-debate`（双向 `flow-reverse`）、以及
`@media (prefers-reduced-motion: reduce) { .edge { animation: none !important; } }`。
运行中节点用琥珀（`--color-accent`）描边，完成用墨色（`--color-ink`），失败用 `--color-bad`。

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest -q tests/downstream/test_web_api.py`
Expected: PASS (18 passed)

- [ ] **Step 5: Verify by eye**

重启 8502（`--db /tmp/opencode/paper.db`），用 playwright 打开
`http://127.0.0.1:8502/runs/9694b098daf3486f99c0d8aff4c3c364`（10 条事件的已完成运行）与
390px 宽度，确认：宽/窄两套布局完整、节点不重叠、无横向滚动、终态无节点停在"运行中"。
再发一个只勾 `market` 的任务，看它跑的过程中节点依次点亮。

- [ ] **Step 6: Commit**

```bash
git add tradingagents_web/templates/run.html tradingagents_web/static/run-page.js \
        tradingagents_web/static/app.css tradingagents_web/app.py tests/downstream/test_web_api.py
git commit -m "feat(web): draw the run as a live graph"
```

---

### Task 6: 文档、全量验证、上线

**Files:**
- Modify: `docs/B4_INTERACTION_SPEC.md`
- Modify: `docs/EXTENSIONS.md`
- Modify: `docs/UPSTREAM_DELTA.md`
- Modify: `tradingagents_web/templates/base.html`（`app.css?v=5`）

- [ ] **Step 1: 文档**

`B4_INTERACTION_SPEC.md` 加一节：报告在**服务时**本地化（磁盘产物不变）；进度图拓扑由
`progress_graph.topology()` 生成，事件仍是唯一事实来源；历史记录缺 `node.finished` 时按完成呈现；
运行页脚本集中在 `static/run-page.js`（一页一个 script 的约束因此仍成立）。
`EXTENSIONS.md` 的归属表补一行：报告呈现层与进度图属于"我们的呈现层"。
`UPSTREAM_DELTA.md` 的脆弱耦合栏加：`report_page.py` 依赖 `report_html.render_report` 的标记
（`<html lang>`、`<p class="date">`、`<dt>` 标签、`aria-label="Sections"`、`<a class="to-top">`），
由 `test_the_markup_we_match_is_still_produced_upstream` 守；并登记新条目 D-0052。

- [ ] **Step 2: 全量验证**

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check .
.venv/bin/python scripts/extension_inventory.py --check
```
Expected: 全绿；清单显示模块数与测试文件数增加（labels / report_page / progress_graph 三个模块）。

- [ ] **Step 3: 上线并确认**

重启 `0.0.0.0:8501`；`curl` 确认：报告返回 `content-type: text/html` 且含 `lang="zh-CN"`，
运行页含 `panel--graph` 与 `/static/run-page.js`，首页引用 `app.css?v=5`。

- [ ] **Step 4: Commit & push**

```bash
git add docs tradingagents_web/templates/base.html
git commit -m "docs(web): record the report presentation layer and the run graph"
git push origin main
```
