# DATA_REQUIREMENTS.md — 上游数据需求规格（替代前必须先满足的契约）

> 原则：**先定义消费者要什么，再选数据源**。不做事后平替——源的能力不匹配契约时，
> 宁可显式"数据不可用"，也不要塞入看似可用的劣质数据。
> 本文件只写需求与验收标准，不写选型结论（RSSHub / 东财 / 巨潮 等都是候选，未拍板）。

## 1. `get_news`（公司新闻）

**上游实现**：`dataflows/vendors/yahoo/news.py::get_news_yfinance(ticker, start_date, end_date)`

| 项 | 上游事实 |
| --- | --- |
| 输入 | 标的、起止日期（ISO） |
| 来源 | Yahoo 个股 news feed，空则 Yahoo 搜索（按标的 tag） |
| 条数 | `news_article_limit`，默认 **20** |
| 内容 | **不是正文**：`title`、`summary`（Yahoo 提供的摘要，可为空）、`publisher`、`link`、`pub_date` |
| 渲染 | `### 标题 (source: 来源)` + 摘要 + `Link: …` |
| 时间 | 只保留 `pub_date` 落在 `[start, end]` 的文章（防前视） |
| 缺失语义 | 区分三态：窗口内无新闻 / 源无该标的覆盖（视为 vendor 不可用，尝试下一家）/ 完全无响应 |

**替代源必须满足**：
1. 能按**个股**检索（A 股代码或公司名），不是只有大盘新闻；
2. 每篇有**可解析发布时间**（到日即可，最好到分钟），用于窗口过滤；
3. 每篇至少有标题 + 来源；摘要可选但强烈建议（否则模型只能靠标题推断）；
4. 能在 20 条/标的的量级上稳定翻页或检索；
5. 明确许可/条款（自建 RSSHub 抓取也要看目标站点条款）。

**RSSHub 能力边界**：多数财经路由给 title + link + pubDate，**summary 常缺**；个股粒度路由有限（多为「快讯」「要闻」「个股新闻页」）。若只拿到标题，prompt 质量会明显低于摘要齐全的源——这属于验收项，不是可以忽略的细节。

## 2. `get_global_news`（宏观/全球新闻）

| 项 | 上游事实 |
| --- | --- |
| 输入 | 日期（`curr_date`）、可选 lookback / limit |
| 条数 | `global_news_article_limit` 默认 **10**，窗口 `global_news_lookback_days` 默认 **7 天** |
| 检索 | 配置里的多条 query 分别搜索，合并后**按标题去重**，窗口优先于限额 |
| 内容 | 与公司新闻同字段（title/summary/publisher/link/pub_date） |
| 缺失语义 | 窗口内为空时明确说"没有"，而不是给空报告 |

**替代源必须满足**：多主题（宏观/政策/行业）可检索、去重可靠、时间窗过滤、中文语境（A 股用户关心的是政策与流动性，不是美联储）。

## 3. `get_macro_indicators`（宏观序列）

| 项 | 上游事实 |
| --- | --- |
| 来源 | FRED，按**别名**取序列（`cpi`、`unemployment`、`10y_treasury`、`yield_curve`…）或原始 series id |
| 输出 | 序列标题、单位、频率、最新值、窗口变化、近期观测表 |
| 时间 | 截止 `curr_date` |
| 缺失 | 未配置 key → `VendorNotConfiguredError`（不静默返回空） |

**A 股替代必须满足**：中国宏观口径（CPI/PPI/GDP/社融/M2/LPR/SHIBOR/国债收益率）、**明确单位与频率**、截止日过滤、别名表可扩展。

> 注：我们的 Tushare 账号实测可用 `cn_cpi`（513 行）与 `shibor`（22 行），但**尚未封装**成该接口。

## 4. `get_prediction_markets`（预测市场）

上游用 Polymarket 给"事件概率"（美联储、衰退、选举、地缘、加密）。

**A 股语境下的需求判断**：A 股研究里对应的是**政策/事件概率**，Polymarket 基本不覆盖。
选项（不替用户决定）：① 在 A 股模式返回明确的"不适用"哨兵；② 换成国内事件（如降准概率——但没有权威概率源）；
③ 保留工具但默认不配置 vendor。**不建议**用模型臆造的"概率"填补。

## 5. `sentiment_analyst` 的三路输入

上游在节点内**预取**（无工具调用）：

| 源 | 字段 | 用途 |
| --- | --- | --- |
| `get_news` | 同 §1 | 新闻情绪 |
| StockTwits | 消息文本、点赞、发布时间 | 散户情绪 |
| Reddit | 帖子标题/正文、score、评论数、subreddit、时间 | 社区情绪 |

**共同要求**：按 `screen`（标的）过滤、窗口内（防前视）、去重、限制条数（StockTwits 30 条）。
**A 股替代需要明确的**：股吧/雪球的**文本**是否可合法稳定获取；若拿不到文本，是否接受用"资金面/龙虎榜"作为情绪代理（那是**换语义**，必须显式声明，不能假装是社交情绪）。

## 6. 已解决 / 未解决一览

| 接口 | 状态 |
| --- | --- |
| `get_stock_data` / `get_indicators` / 三表 / 概况 / `get_verified_market_snapshot` | ✅ 已接 Tushare 且同源 |
| `get_insider_transactions` | ✅ `stk_holdertrade`，按公告日过滤 |
| `get_news` / `get_global_news` | ❌ 待替代（本文 §1/§2 为验收标准） |
| `get_macro_indicators` | ✅ 已封装（CN profile：CPI/PPI/GDP/M2/社融/PMI/SHIBOR；LPR/10Y 显式拒绝） |
| `get_prediction_markets` | ⚠️ 语义不适用，待决定（§4） |
| 社交情绪 | ❌ 待替代或改语义（§5） |

## 7. B3 前必须先确认的三件事

1. **新闻只要摘要还是也要正文？** 上游只要摘要。如果要正文，抓取成本、许可风险、token 成本都上一个量级。
2. **社交情绪是否接受"资金面替代"？** 换语义必须写进报告，否则读者会以为是舆情。
3. **宏观指标首批要哪几个？** 建议 CPI / PPI / M2 / 社融 / LPR / SHIBOR / 10Y，按分析师实际引用频率取舍。
