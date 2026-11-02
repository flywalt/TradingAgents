# 报告本地化 + 进度图 设计（2026-11-02）

两件小事，同一份设计：报告页的中文呈现、运行页的节点图。都只动我们的 Web 层。

## 1. 为什么

跑出来的报告正文是中文，页首却是 `Overweight`、`I. Analyst Team Reports`、`Top`、`<html lang="en">`
—— 上游渲染器没有语言概念。运行页只有一列文字事件，用户要读时间戳才能看出哪几个分析师在同时跑、
辩论循环了几轮。图能把这两件事一眼说清。

## 2. 目标 / 非目标

**目标**

- 报告页在 `output_language` 为中文时，页首元信息、章节标题、导航与语言标记都是中文。
- 运行页在进度卡上方画出真实拓扑，节点随事件点亮，交接走线有流动，辩论来回。
- 两者都不改上游文件，不新增依赖，不引入 Node 构建。

**非目标**

- 不翻译报告**正文**（那是模型产物）。
- 不改 `complete_report.md` / `complete_report.html` 磁盘产物：产物是内核的，呈现才是我们的。
- 不做历史回放动画（v1 完成态直接落到终态；重播按钮列为后续）。
- 不改评级枚举：`Buy/Hold/...` 仍是内核词汇，只在展示层附中文。

**反目标**

- 用字符串替换去改正文（只允许替换页首/导航/章节标题这类固定标签）。
- 为了动效引入 JS 框架或 CDN。
- 让上游同步时静默失效：耦合点必须有测试，上游改标记就红。

## 3. 方案（已选）

**本地化：A（Web 层呈现替换）**，大于 B（上游最小补丁）与 C（复刻渲染器）。
产物不动、上游不动；将来上游自带语言支持时，删掉这一层即可。

**图：A（内联 SVG + 两套坐标）**，大于 CSS Grid 连线（坐标计算易错）与服务端 SVG（做不了流动）。

## 4. 怎么做

### 4.1 报告本地化

新模块 `tradingagents_web/report_page.py`：

- `present(html: str, lang: str) -> str`：仅在 `lang` 以中文开头时生效，其余原样返回。
- 替换面（**允许清单**，逐条精确匹配，不做模糊替换）：
  - `<html lang="en">` → `lang="zh-CN"`
  - `<p class="date">Analysis of 2026-11-02</p>` → `分析日期 2026-11-02`
  - `<dt>` 标签：`Generated / Deep model / Quick model / Analysts / Debate rounds / Data vendors / Version / Memory log`
  - `<a class="to-top">Top</a>` → `回到顶部`
  - `<h2>` / 目录里的 5 个章节名（`I. Analyst Team Reports` …），映射到
    `一、分析师团队报告` …；章节序号里的罗马数字换成中文序号，锚点 id 不动。
  - 评级 `<span class="rating ...">Overweight</span>` → 中文名，英文原文进 `title` 属性。
- 在 `app.py` 的报告路由里调用（只对 `.html` 生效；`text/plain` 回退路径不碰）。
- **脆弱耦合**：`tests/downstream/test_web_report_page.py` 断言上游仍产出这些锚点原文；
  上游哪天改了标记，这条测试先红，而不是页面悄悄变英文。登记到 `docs/UPSTREAM_DELTA.md` 的脆弱耦合栏。

### 4.2 进度图

**布局算在 Python，动效在 JS**——布局可测，动画只管画。

新模块 `tradingagents_web/progress_graph.py`：

- `topology(analysts: list[str]) -> dict`：节点、边、两套坐标。
  - 节点：START、所选分析师（未选的**不画**）、`Memory Log`（若启用）、Bull、Bear、
    Research Manager、Trader、Aggressive、Conservative、Neutral、Portfolio Manager、END。
  - 边：`START → 每个起始节点`、`每个分析师 → Bull`（汇合）、`Bull ⇄ Bear`（辩论，双向）、
    `Research Manager → Trader`、`Trader → Aggressive`、`Aggressive ⇄ Conservative ⇄ Neutral`（辩论环）、
    `Portfolio Manager → END`。
  - 两套坐标：`wide`（≥720px，分行：分析师 / 辩论 / 经理 / 交易 / 风险 / 组合）与
    `narrow`（竖排骨架，辩论对横向并排）。
- 布局自检（测试）：节点矩形不重叠、全部落在 viewBox 内、每条边的两端都存在。

`run.html`：

- 进度卡上方加 `<section class="panel panel--graph">`，内嵌一个 `svg`，由 Python 注入的 JSON
  （`data-graph`）渲染；`matchMedia('(min-width: 720px)')` 切换布局。
- 状态机（纯 JS，事件驱动）：`idle → active → done`；`run.failed` 时把在跑的节点标为失败。
- 边状态：`flow`（上游完成、下游开始时的交接，流动虚线）、`debate`（辩论对之间来回动画）。
- 轮次：同名节点重复 `node.started` 即为一轮，图上标 `第 n 轮`。
- `prefers-reduced-motion: reduce`：关闭流动与来回动画，只留静态点亮。
- 无障碍：`<svg role="img" aria-label="…">`，图形不是唯一信息来源（文字日志仍在下方）。

**页面脚本数**：现有测试要求每页 `<script` 恰好一个。本设计把图逻辑放进
`static/progress-graph.js`，页面用**一个** `<script src>` 引入，仍在预算内。

## 5. 约束

- 不碰 `tradingagents/`、`tradingagents_cn/`；只动 `tradingagents_web/` 与 `tests/downstream/`。
- 无新运行时依赖；LAN 无外网，字体仍用系统 CJK 栈。
- 沿用现有 paper 配色与 Console 的语义：琥珀=人的动作，冷蓝=仪器测量。图里
  **运行中=琥珀呼吸、完成=墨色、失败=红**，不新增第四种颜色语言。
- 移动端 390px 可读，不横向滚动。

## 6. 留给实现者的判断

- 图的高度与节点尺寸比例（宽屏偏横向、窄屏偏紧凑）。
- 交接流动的具体时长/缓动（要短，≤600ms，不能拖慢观感）。
- 章节序号用「一、二、三」还是「1 / 2 / 3」——默认中文序号，若与正文编号冲突再退回阿拉伯数字。
