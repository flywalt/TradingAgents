# 上游贡献计划（备选，非近期重点）

> 用户已明确：**推动上游迭代暂不作为主要考虑事项**。本文件只把"值得反哺的东西"按优先级固化，
> 避免以后每次都要重新论证；真正提 PR 前需要单独排期。

## 1. 原则

- 只反哺**通用能力**：任何 A 股专有规则（涨跌停/T+1/ST/整手）、中国数据源细节、下游 web 产品，一律不提交。
- 每个 PR 必须能被上游独立接受：无中国业务逻辑、无新依赖、有测试、默认行为不变。
- 反哺的收益是**消灭我们自己的 L4a 补丁与脆弱耦合**，不是为了"做好人"。

## 2. 顺序（依赖从前到后）

### P-1 Vendor Registry 注册扩展接口（收益最高）

- 现状：下游直接写 `VENDOR_METHODS` / `TOOLS_CATEGORIES`（`bootstrap.py` 封装）。
- 提议：`register_vendor(method, vendor, impl, category=None)` + `register_category()`，带幂等与签名校验。
- 收益：把我们的 `bootstrap` 从"私有结构耦合"降级为"公开 API 调用"。
- 风险：上游可能有自己的插件设想，需先讨论形态（entry-point vs 显式函数）。

### P-2 Instrument Identity Resolver 注入接口

- 现状：`resolve_instrument_context()` 硬编码 Yahoo；我们靠子类覆写。
- 提议：构造函数接受 `identity_resolver: Callable[[str, str], dict]`，默认仍是 Yahoo。
- 收益：L2 子类覆写 → 配置注入，减少签名漂移风险。

### P-3 Tool Override / Tool Factory

- 现状：分析师模块级 `TOOLS` 元组与 prompt 文本写死；我们因此打了 snapshot 路由补丁。
- 提议：`create_market_analyst(llm, tools=TOOLS)` 之类的最小参数化（不改 prompt 文本）。
- 收益：让"换一个工具实现"不需要 patch 或复刻 analyst。

### P-4 Snapshot Vendor Routing（我们已打补丁）

- 提议：把 `get_verified_market_snapshot` 接入 `route_to_vendor`，Yahoo 作为默认 vendor。
- 现状：我们已有等价实现（`upstream-patch:`），上游合并后可直接删除补丁。

### P-5 通用 PIT 数据契约

- 提议：把"公告日过滤"抽象成 vendor 层可选契约（例如报表帧必须带 `ann_date`，router 负责按 `trade_date` 过滤）。
- 收益：下游不用各自实现前视防护；上游也受益（SEC 财报同样有 filing date）。

### P-6 通用技术指标计算

- 提议：把指标计算从 Yahoo 取数中拆出来，接受任意 OHLCV 帧；可选提供通达信口径作为第二 flavor。
- 收益：任何数据源都能复用同一套指标；我们的 `tdx_indicators.py` 有变成上游模块的可能。
- 注意：只提"指标算法"，不提 A 股规则。

### P-7 可选 Tushare Provider（最后）

- 提议：作为可选 extra 的通用 provider（仅 OHLCV + 报表），不含 A 股交易规则。
- 收益：上游多一个数据源；我们少维护一个适配器。
- 前提：P-1 已被接受，否则该 provider 无处注册。

## 3. 不做

- 不提交涨跌停/T+1/整手/ST 规则（A 股专有，且我们自己的 `trading_rules.py` 更完整）。
- 不提交中文 prompt 改写（属产品定位差异）。
- 不提交 web/多用户/调度（CN 分支的路线，不是上游的）。
- 不为"减少冲突"而把下游代码整体上游化——那会把维护责任转移给一个我们不控制节奏的项目。

## 4. 触发条件

只有满足其一才启动：

1. 某个 L4a 补丁在上游连续两个 release 都需要手工重放；
2. 上游明确表示欢迎该类扩展（issue 讨论有正面回应）；
3. 我们有稳定的第二使用者（不是自用）。

否则保持现状：L4a 补丁 + 台账 + 同步演练已经足够便宜。
