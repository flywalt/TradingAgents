# AGENT_MAP.md — Agent 层地图（A 股改造用）

> 基线：上游 v0.7.1 + 下游数据层（2026-11-01）。本文件是"决策级地图"：
> **每个 agent 吃什么、吐什么、在 A 股哪里会空转**，不是 prompt 逐字解读。
> 它同时是批次 1 的任务看板。

## 1. 拓扑（上游硬编码，12 个节点）

```
START ─┬─ Market Analyst      ─┐
       ├─ Sentiment Analyst    │  并行；每个分析师是独立子图，
       ├─ News Analyst         │  私有 messages，只回写自己的 report_key
       ├─ Fundamentals Analyst ┤
       └─ Memory Log ──────────┘  并行；结算历史决策 → past_context
                │
                ▼
        Bull ⇄ Bear ──► Research Manager ──► Trader
                │                               │
                ▼                               ▼
     Aggressive ⇄ Conservative ⇄ Neutral ──► Portfolio Manager ──► END
```

## 2. 十二个 agent

| # | Agent（节点名） | 输入 | 数据/工具 | 输出 | A 股现状 |
| --- | --- | --- | --- | --- | --- |
| 1 | Market Analyst | `company_of_interest`、`trade_date`、身份上下文 | `get_stock_data`、`get_indicators`、**`get_verified_market_snapshot`** | `market_report` | ⚠️ 价格/指标已同源，**快照仍走 Yahoo** |
| 2 | Sentiment Analyst | 同上（无工具调用） | **预取**：`get_news` + StockTwits + Reddit | `sentiment_report`（`SentimentReport`） | ❌ 三个源全是美股社区 → 空转 |
| 3 | News Analyst | 同上 | `get_news`、`get_global_news`、**`get_macro_indicators`（FRED）**、**`get_prediction_markets`（Polymarket）** | `news_report` | ❌ 公司新闻覆盖弱；宏观是美国；预测市场是美国/加密 |
| 4 | Fundamentals Analyst | 同上 | `get_fundamentals`、三表、**`get_insider_transactions`** | `fundamentals_report` | ⚠️ 三表/概况已接 Tushare；内部人仍走 Yahoo |
| 5 | Bull Researcher | 4 份报告 + 辩论历史 | 无外部数据 | `investment_debate_state.bull_history` | ⚠️ 只缺 A 股语境 |
| 6 | Bear Researcher | 同上 | 无外部数据 | `...bear_history` | ⚠️ 同上 |
| 7 | Research Manager | 辩论历史 | 无外部数据；结构化 `ResearchPlan` | `investment_plan` | ⚠️ 同上 |
| 8 | Trader | `investment_plan`、`market_report` | 无外部数据；结构化 `TraderProposal` | `trader_investment_plan` | ⚠️ 同上（无 T+1/涨跌停约束） |
| 9-11 | Aggressive / Conservative / Neutral Debator | 交易计划 + 3 份报告 + 风险辩论 | 无外部数据 | `risk_debate_state.*` | ⚠️ 同上 |
| 12 | Portfolio Manager | 风险辩论 + 交易计划 | 无外部数据；结构化 `PortfolioDecision` | `final_trade_decision`（5 档评级 + `REVIEW`） | ⚠️ 同上（合规与评级口径待定） |

**结论**：真正"缺数据"的只有 **news（3）** 和 **sentiment（2）**；market/fundamentals 只差**工具接线**；
5 个下游节点（5-12）不调任何行情 API，缺的是**语境与约束**，属于 prompt 专题。

## 3. 横切层（一次改动影响全部 12 个）

| 机制 | 位置 | 对 A 股的意义 |
| --- | --- | --- |
| `instrument_context` | `agents/context.py::build_instrument_context`，12/12 个节点都注入 | **一处注入，全链路生效**：公司名/行业/板块/涨跌停约束都从这里进 |
| 输出语言指令 | `agents/context.py::get_language_instruction`，12/12 使用 | 已有 `output_language`，中文输出无需改 prompt |
| 结构化输出 | `agents/schemas.py`：`SentimentReport`/`ResearchPlan`/`TraderProposal`/`PortfolioDecision` | 评级枚举是**全链路契约**（报告/记忆/回测），A 股不得自定义 |
| 评级解析 | `agents/rating.py`（5 档 + `REVIEW`） | 同上，只能复用 |
| 工具注入 | 每个 analyst 的模块级 `TOOLS` tuple（上游硬编码） | 换工具 = 换 analyst（下游自有节点）或上游补丁 P5 |

## 4. 数据可达性（只列被 4 个分析师真正调用的）

| 工具 | 上游 vendor | A 股现状 | 缺口 | 批次 |
| --- | --- | --- | --- | --- |
| `get_stock_data` | yahoo | ✅ Tushare（qfq） | — | — |
| `get_indicators` | yahoo | ✅ Tushare 日线本地算（通达信口径） | — | — |
| `get_verified_market_snapshot` | yahoo（`vendors/yahoo/snapshot.py`） | ❌ 仍是 Yahoo | 换成 `tradingagents_cn.snapshot` | B1-2 |
| `get_fundamentals` / 三表 | sec_edgar/yahoo | ✅ Tushare | — | — |
| `get_insider_transactions` | yahoo | ❌ | Tushare `stk_holdertrade` 注册 | B1-3 |
| `get_news` / `get_global_news` | yahoo | ⚠️ 覆盖弱 | AkShare/东财（专题） | B2 |
| `get_macro_indicators` | FRED（美国） | ❌ 美国口径 | 国内宏观（`cn_cpi`/`shibor` 已有权限） | B2 |
| `get_prediction_markets` | Polymarket | ❌ 与 A 股无关 | 移出 A 股链或换成本地事件 | B2 |
| StockTwits / Reddit（预取） | 美股社区 | ❌ | 股吧/雪球/龙虎榜资金情绪 | B2 |

## 5. 怎么验证这张图（不是靠读，靠跑）

用上游 `tests/test_graph_end_to_end.py` 的"脚本化假模型"手法，建一个下游测试：

- 用假 LLM 跑完整图，**捕获每个节点收到的 system prompt**；
- 断言 12 个 prompt 里都出现 A 股标的的规范代码与公司名（验证 B1-1）；
- 断言 market 的工具集里没有 Yahoo 快照（验证 B1-2）；
- 断言 prompt 里出现该板块正确的涨跌停幅度与 T+1 说明（验证 B1-4）；
- 断言 news/sentiment 的空数据以"明确不可用"出现，而不是模型自行编造（B2 的前置条件）。

这一步同时是"全面了解"的完成标志：地图上每一行都有一条会失败的测试对应。

## 6. 批次计划

### B1 — 接线（不改上游、不改 prompt）

| ID | 内容 | 验收 |
| --- | --- | --- |
| B1-1 ✅ | 覆写 `resolve_instrument_context`，Tushare 身份 + `namechange` PIT | 12 个 prompt 含公司名/行业；US 回退 Yahoo（D-0029） |
| B1-2 ✅ | 快照改走 vendor 路由（`upstream-patch:` + Tushare 实现） | 快照与行情同源、不越界、严格模式不回落（D-0022/23） |
| B1-3 ✅ | 注册 `get_insider_transactions` → `stk_holdertrade`，按公告日过滤 | A 股命中 Tushare，美股回落 Yahoo（D-0031） |
| B1-4 ✅ | `trading_rules` 约束注入 `instrument_context` + `reference_price()` | 板块幅度/T+1/整手进上下文；参考价有单测（D-0032） |

### B2 — 补 A 股数据源（独立专题：新闻与情绪）

news 三工具换国内源；sentiment 从美股社区换股吧/雪球/资金面。必然新增下游 analyst。

### B4 — Web 界面（局域网单用户，单 worker 串行）

下游新增包 `tradingagents_web/`，只做排队/调用/展示，不改上游。范围与端点见 `docs/WEB_PLAN.md`。

### B3 — prompt 专题（先评测后改）

CAS/YTD/亿元口径、涨跌停/T+1/停牌约束、评级与合规措辞、日期时区。
前置：脚本化回归 + 3~5 个黄金场景（涨停、停牌、亏损财报、ST、除权日）。

## 7. 明确还不知道的（不要假装知道）

- 每个 prompt 的**实际质量**（是否适合 A 股结论）——只能通过 B3 的评测回答；
- 单个 agent 的 token 成本与长上下文退化点；
- news/sentiment 空转对最终评级的影响幅度（需要在 B2 后用对照跑评估）；
- 上游改 prompt 的频率（影响我们"下游自有 analyst"的维护成本）。
