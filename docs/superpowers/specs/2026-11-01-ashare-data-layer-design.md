# A 股数据层设计（第二阶段）

日期：2026-11-01
状态：待批准
范围：仅数据层；不改 agent、不改 prompt、不改上游代码

---

## 1. 意图与背景

第一阶段已经打通"行情 + 复权 + 交易日历"（`docs/TUSHARE.md`）。但当前 A 股报告仍然残缺且**口径分裂**：

- `get_indicators` 走 Yahoo，用美股口径的价格算指标，而 `get_stock_data` 已经是 Tushare；
- `get_fundamentals` / 三表走 SEC EDGAR 或 Yahoo，A 股要么空、要么是美股口径（美元、US GAAP）；
- 公司身份（名称/行业）走 yfinance，A 股覆盖不全。

本阶段目标：**让 market analyst 和 fundamentals analyst 在 A 股上拿到同一套、可信、无前视、单位正确的数据**，
并且所有数据能力都可离线测试、可在上游更新后自动回归。

新闻/公告（Tushare 无权限）与情绪数据（A 股股吧/雪球）**不在本阶段** —— 它们的方法论和 prompt 强绑定，
放到下一个"新闻与情绪专题"。

## 2. 目标

1. 技术指标：用 Tushare 日线在本地计算，覆盖 market analyst 需要的全部 12 个指标。
2. 财报：利润表 / 资产负债表 / 现金流量表，中国会计准则，**按公告日做前视过滤**。
3. 公司概况与估值：名称、行业、地区、上市日期、PE/PB/市值/换手（按分析日取值）。
4. 指数与行业：基准指数日线、指数权重/成分（供后续上下文与基准使用）。
5. 资金面**只做数据接口**（资金流、北向持股、融资融券、龙虎榜），注册进 router 但**不接 agent**。
6. 数据访问加一层进程内 + 磁盘缓存与限流，避免回测触发 Tushare 频率限制。
7. uv 管理环境 + 锁文件，替换 pip 管理方式。

## 3. 非目标

- ❌ 不做新闻/公告（无权限）、不做股吧/雪球情绪。
- ❌ 不新增分析师、不改任何 prompt、不改图结构。
- ❌ 不修改上游任何文件（继续零上游补丁）。
- ❌ 不做 `limit_list_d`（涨跌停名单，无权限）；涨跌停价仍由本地 `trading_rules.py` 计算。
- ❌ 不做财务数据的"同比/环比"智能分析（只给结构化数值，解读交给模型）。

## 4. 约束

1. **单位**：Tushare 财报字段单位是**元**，行情 `vol` 是手、`amount` 是千元。输出必须显式声明单位，
   金额统一换算成**亿元（保留 2 位）并在头部写明**，行情仍按股/元。
2. **前视禁止**：财报必须满足 `ann_date <= trade_date`（缺 `ann_date` 时用 `f_ann_date`）；
   估值必须取 `trade_date` 当日或之前最近一个交易日。上游已有"point-in-time"测试哲学，本层必须对齐。
3. **报表口径**：只取合并报表（`report_type == '1'`），同 `end_date` 多版本时取最新公告的一份。
4. **错误语义**：非 A 股 → `NoMarketDataError`；无 token / 无权限 → `VendorNotConfiguredError`；
   网络/限流 → `VendorUnavailableError`；空结果 → `NoMarketDataError`。路由靠类型决策，不能自己发明异常。
5. **测试必须离线**：所有单测用注入的假客户端；真实调用只出现在 `-m integration`。
6. **报表期间语义**：A 股利润表/现金流量表是**年初至今累计（YTD）**，本层原样保留并在表头标注，
   不自行去累计；跨季比较由读者（模型）按标注处理。

## 5. 方案选择（已在对话中确认）

| 方案 | 内容 | 取舍 | 结论 |
| --- | --- | --- | --- |
| A 决策闭环 | 行情+指标+三表+概况+指数，资金面仅接口 | 无抓取依赖，market/fundamentals 完整 | **采纳** |
| B A+新闻/公告 | 增加 AkShare 抓取 | 能补 news analyst，但接口脆弱、测试靠快照 | 推迟到新闻专题 |
| C 最小补齐 | 指标+三表+概况 | 最快，但资金面/指数缺失 | 未采纳 |

理由：权限已覆盖"价格—财报—资金面"主线；新闻属另一个方法论专题，混进来会把数据层变脆。

## 6. 数据映射（Tushare → 上游方法）

| 上游 router 方法 | 上游现状 | 本层实现 | Tushare 接口 |
| --- | --- | --- | --- |
| `get_stock_data` | Yahoo | ✅ 已完成（D-0004） | `daily` / `pro_bar` |
| `get_indicators` | Yahoo + stockstats | **新增** 本地计算 | `daily`（复用已取行情） |
| `get_fundamentals` | SEC/Yahoo | **新增** 概况+估值+财务摘要 | `stock_basic` + `daily_basic` + `fina_indicator` |
| `get_income_statement` | SEC EDGAR | **新增** 利润表 | `income` |
| `get_balance_sheet` | SEC EDGAR | **新增** 资产负债表 | `balancesheet` |
| `get_cashflow` | SEC EDGAR | **新增** 现金流量表 | `cashflow` |
| `get_news` / `get_global_news` / `get_insider_transactions` | Yahoo | **不动**（A 股无源） | — |
| `get_macro_indicators` | FRED | **不动**（后续中国宏观专题） | — |
| 新增 `get_northbound_holdings` | — | 新方法，仅接口 | `hk_hold` |
| 新增 `get_margin_detail` | — | 新方法，仅接口 | `margin_detail` |
| 新增 `get_money_flow` | — | 新方法，仅接口 | `moneyflow` |
| 新增 `get_top_list` | — | 新方法，仅接口 | `top_list` |
| 新增 `get_index_daily` | — | 新方法，仅接口 | `index_daily` |

## 7. 模块设计

```
tradingagents_cn/
├── units.py                  # 元→亿元、手→股、千元→元；显式舍入
├── pit.py                    # 公告日过滤（point-in-time），报表去重取最新
├── cache.py                  # 进程内 LRU + 磁盘缓存（data_cache_dir/cn-tushare），TTL 分级
├── identity.py               # stock_basic → 名称/行业/地区/市场/上市日（供 context 注入使用）
└── vendors/tushare/
    ├── client.py             # 已有：鉴权 + 可注入假客户端（新增 cache 包装）
    ├── stock.py              # 已有：日线 + 复权
    ├── indicators.py         # 指标：sma/ema/macd/rsi/boll/atr/vwma，基于日线本地算
    ├── fundamentals.py       # 概况 + 估值 + 财务指标摘要
    ├── statements.py         # 三表（合并报表、前视过滤、亿元）
    ├── flows.py              # 资金流/北向/两融/龙虎榜（仅数据接口）
    ├── index.py              # 指数日线/权重/成分
    └── calendar.py           # 已有：trade_cal
```

### 关键实现要点

1. **指标**（`indicators.py`）
   - 入口签名对齐上游：`get_stock_stats_indicators_window(symbol, indicator, as_of_date, look_back_days)`。
   - 用上游 `get_indicators` 支持的 **13** 个名字（`close_50_sma`、`close_200_sma`、`close_10_ema`、`macd`、
     `macds`、`macdh`、`rsi`、`boll`、`boll_ub`、`boll_lb`、`atr`、`vwma`、`mfi`），未知指标名抛 `ValueError`
     （与上游一致：模型传错名字时给回错误文本，不是崩溃）。
   - 计算复用 `stockstats`（已在依赖里），数据来自本地 `get_stock_data` 的同一份 qfq 序列 → 口径一致。
   - 输出：指标表（日期 + 指标列）+ 头部声明"复权口径 + 数据来源"。
2. **三表**（`statements.py`）
   - `freq` 支持 `annual` / `quarterly`；取最近 4 期；`end_date` 去重取最新 `ann_date`。
   - 前视：只保留 `ann_date <= trade_date`（回退 `f_ann_date`），**必须有对应单测**。
   - 单位：元 → 亿元（2 位小数），负值/缺失按原样呈现，不补零不猜测。
   - 只展示分析师真正会用到的 15~20 个字段（不是全字段倾倒），字段中文标签 + 英文 key。
3. **概况+估值**（`fundamentals.py`）
   - `stock_basic`：名称、行业、地区、市场、上市日期。
   - `daily_basic`：取 `trade_date` 当日或之前最近交易日的 PE/PB/PS/总市值/流通市值/换手率/量比。
   - 财务摘要：`fina_indicator` 最近一期（前视过滤）：EPS、ROE、毛利率、净利率、资产负债率等。
4. **资金面**（`flows.py`）
   - 4 个新方法注册到新类别 `cn_capital_flows`（需要通过 `register_category()` 创建，见下）。
   - 只做数据接口 + 测试，**不新增 tool、不接 agent**。
5. **`register.py` 扩展**：新增 `register_category(name, description)`，让新方法有归属类别；
   `reset()` 同步撤销新建类别。
6. **缓存**（`cache.py`）
   - key = `(接口名, 排序后的参数, 复权口径)`；分级 TTL：日线/资金流 1h，财报/概况 24h，指数权重 24h。
   - 内存 LRU（进程内）+ 磁盘 pickle（`data_cache_dir/cn-tushare/`），可用 `TRADINGAGENTS_CN_CACHE=off` 关闭。
   - 缓存命中/落盘都要有测试（用临时目录，不碰用户缓存）。
7. **限流**：客户端侧最小间隔（可配置，默认 0.15s/次，约 400 次/分）——2000 积分档的安全值。

## 8. 测试策略

| 层 | 内容 |
| --- | --- |
| 单元（离线，默认跑） | 指标数值（手工算的 SMA/RSI 对照）、前视过滤、报表去重、单位换算、错误映射、缓存命中与 TTL、注册与回滚 |
| 集成（`-m integration`，需 token） | 每个新接口真实取一次：三表有数据、指标与直接 computed 一致、估值字段非空、资金面/指数可用 |
| 同步保险丝 | 现有 `test_sync_guard.py` 继续跑；如新依赖上游符号（如 `get_indicators` 的指标名集合），加入其中 |

## 9. uv 迁移（方案 2）

1. 安装 uv（官方脚本或 `pip install uv`），确认版本。
2. 备份现有环境：`mv .venv .venv-pip-backup`（验证通过前不删）。
3. `uv venv .venv --python 3.13` → `uv pip install -e ".[dev]"`。
4. 下游依赖单独清单 `requirements-downstream.txt`（`tushare`，**不写进上游 pyproject**）。
5. 生成锁文件 `requirements-lock.txt`（`uv pip freeze`）。
6. 验证：`uv run pytest -q` 全绿、`uv run ruff check .` 全绿、`-m integration` 全绿。
7. 失败即回滚：`rm -rf .venv && mv .venv-pip-backup .venv`。
8. 文档：`docs/DEV_ENV.md`（uv 用法、与 pip 的差异、锁文件更新流程、回滚步骤）。

## 10. 风险与已知缺口

1. **`get_verified_market_snapshot` 仍走 Yahoo**：market analyst 会同时拿到 Tushare 指标与 Yahoo 快照 → 仍有口径分裂。
   修复属于 agent 层（替换工具/下游分析师），本阶段只提供 `snapshot` 数据接口变体，不接线。
2. **sentiment/news 两个分析师在 A 股空转**：本阶段不解决，文档写明。
3. **Tushare 字段口径差异**：`n_income`（含少数股东）vs `n_income_attr_p`（归母），不同接口单位是元/万元不一 ——
   逐个字段写进测试，不靠"看起来对"。
4. **复权序列随时间变化**：qfq 会因新除权事件变化，缓存 TTL 到期后同一日期的指标值可能变；文档提示固定口径与日期。
5. **北交所日历不可用**（BSE 返回 0 行）：沿用 SSE 日历。
6. **uv 重建环境可能升级上游依赖版本**：先用现有 freeze 做约束再装，测试不过即回滚。

## 11. 我替你做的取舍（不同意请说）

1. 三表只展示核心字段（15~20 个，中文标签 + 英文 key），不倾倒全字段。
2. 金额统一 **亿元（2 位小数）**，行情保持股/元；头部写明换算关系。
3. `requirements-downstream.txt` + `requirements-lock.txt` 放仓库根目录。

## 12. Builder check 结论（6 项已裁决）

一个独立 builder 读完设计后提了 6 个会改变计划的疑问，逐条裁决如下（含理由，便于日后复盘）。

| # | 疑问 | 裁决 | 理由 |
| --- | --- | --- | --- |
| 1 | 利润表/现金流是**年初至今累计**还是单季？ | **原样保留累计值**，表头显式写"本年累计（YTD）"，并在文档注明"跨季不可直接相减" | A 股报表口径就是累计，自行去累计会在缺期/调整时算错；误读风险靠显式标注消除。单季推算留到 prompt 专题按需再加 |
| 2 | 指数代码（`000300.SH`、`000001.SH`）能否走股票 `normalize()`？ | **不能**。`index.py` 用独立的指数命名空间：必须带显式交易所后缀（`.SH`/`.SZ`/`.CSI`），不复用股票规则 | `000001` 同时是平安银行(SZ)与上证指数(SH)，股票规则一旦放宽会改变股票路由。指数接口只接受显式后缀 |
| 3 | 指标/财报类别失败时是否回退 Yahoo？ | 默认链 `tushare,yfinance`（保住美股），另提供 `cn_strict_ashare=True` 切换成 `tushare` 单链 | 无法按标的选 vendor；严格模式给"宁缺毋滥"的用户。两种模式都要有测试，输出头部始终写明 vendor 与复权口径 |
| 4 | 银行/保险/券商的报表字段不同，要不要按行业选字段？ | 本阶段**通用字段集 + 空值安全渲染 + 行业提示**；行业字段映射列为后续 | 通用字段（营业总收入、净利润、总资产等）对金融股仍有意义；行业级字段集是独立工作量，先记录缺口 |
| 5 | 北向持股 `hk_hold` 2024-08-19 后不再逐日披露 | 保留为**历史接口**，文档写明截止日；integration 测试固定在 2023 年区间；十大活跃股列为后续 | 逐日持股确实停了；假装能取近况比明确标注更糟 |
| 6 | `identity.py` 与 snapshot 变体是否要接线？ | 本阶段**只提供可调用函数 + 单测**，不接线（不覆写 `resolve_instrument_context`） | 接线属于 agent 层，与"本阶段不改 agent"冲突；先交付可测的数据接口，专题里再接 |

另外修正一处：上游指标是 **13 个**（含 `mfi`），设计文档已按 13 个写。


---

## 13. 口径裁决（2026-11-01 二轮，取代前文的三轨草案）

用户质疑"三轨是否过度设计"，并用两个事实复核：

1. **上游美股**：`auto_adjust=True, actions=False` —— 除权由 Yahoo 在供数时折进价格，
   项目对涨跌停/T+1/整手毫无概念，所以只要一个口径。**A 股的额外复杂度来自"涨跌停要用交易所
   除权参考价"，不是"除权"本身。**
2. **TradingAgents-CN 分支**：`adj` 参数默认 qfq，组合里另存不复权成交价，技术指标**仍用
   stockstats**，没有除权参考价机制、没有 as-of。

### 裁决

| 议题 | 决定 | 理由 |
| --- | --- | --- |
| 价格口径 | **单轨 qfq**；`cn_adjust` 保留切换；涨跌停/除权参考价等接 agent 时再加一个小函数 | 上游与 CN 分支都只有一个口径；三轨是为未启用的功能付架构成本 |
| as-of | **不新增配置**：保持"锚点=分析日"（Tushare 以区间末为锚，实测），输出头写明 anchor，加测试 | 历史 run 天然 point-in-time；显式配置只会增加概念 |
| 指标算法 | **完整通达信口径**（13 个），`cn_indicator_flavor` 可切 `stockstats` | 用户要求与国内软件可对照；差异最大的是 MACD 柱 ×2 与 ATR 用 MA(TR) |

### 代价

- 通达信口径多约 150 行公式 + 11 组逐值对齐测试；
- 不复权因子快照 → Tushare 修订因子后历史数字不可逐位复现（已列为限制）；
- 除权日的涨跌停仍要等交易规则接线时才正确。
