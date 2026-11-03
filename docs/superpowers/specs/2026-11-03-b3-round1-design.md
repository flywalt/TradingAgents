# B3 第一轮：缺失数据纪律 + 口径引用 + 研究口吻 设计（2026-11-03）

## 为什么

评测骨架与黄金场景已就位（`test_prompt_contracts.py` / `test_prompt_scenarios.py`），按
`B3_PROMPT_PLAN.md` 的顺序，先固化基线，再做第一轮 prompt 改动。真实运行暴露的具体缺口：

1. **语义不一致（数据层措辞）**：`blocks.py` 已区分 `NO_ITEMS`（源应答、窗口内无条目）与
   `UNAVAILABLE`（源失败），但 sentiment agent 内嵌的 `_block/_safe` 副本仍把空结果写成
   `UNAVAILABLE`——同一张图里两个 agent 对模型讲两套语义。
2. **模型不知道两种标记的差别**：prompt 从没向模型解释"NO_ITEMS = 公司安静，不是源坏了"。
3. **口径引用没有要求**：数据表头带了 qfq/锚点日/本年累计/亿元，但 prompt 不要求模型**引用**
   它们，报告里口径时常缺席。
4. **研究口吻未成文**：news 的通用前缀有一句"另一个 agent 决定交易"，但没有"每个事实带来源
   与日期、结论写成观察而非指令"的成文规则。

## 目标 / 非目标

**目标**

- 基线固化为 `docs/B3_BASELINE.md`（脚本化模型下可重复）。
- 只改我们自己的两个文件：`tradingagents_cn/agents/{news,sentiment}_analyst.py`。
- 每条改动先让黄金场景断言 RED，再改文本 GREEN。

**非目标（硬约束不变）**

- 不改上游 12 个 Analyst Prompt，不动 `instrument_context`（C 方案留待本轮之后）。
- 不评"结论对错"，只评"是否按规则使用数据与口径"。
- 不翻译 prompt 全文、不重写结构。

## 改动清单（每条一个 RED→GREEN）

| # | 改动 | 断言 |
| --- | --- | --- |
| 1 | sentiment 的 `_block`：空 → `NO_ITEMS: ...`；`_safe` 失败仍 `UNAVAILABLE`（与 blocks.py 对齐） | 单测：`_block([])` 以 NO_ITEMS 开头；抛错 → UNAVAILABLE |
| 2 | 两个 agent 的 system 文本各加一段**缺失数据纪律**：解释 NO_ITEMS（公司安静）/ UNAVAILABLE（源失败）的行为差异，禁止互换、禁止补全 | 黄金场景：prompt 含 `NO_ITEMS` 与"quiet"释义句、含"missing data"释义句 |
| 3 | news 的 system 文本加**口径引用**规则：引用价格必须带复权口径与锚点日、引用财报必须带期间基准与单位，表头缺失时如实说"未注明" | 黄金场景：prompt 含 qfq/锚点日要求句与"本年累计/亿元"要求句 |
| 4 | 两个 agent 的 system 文本加**研究口吻**规则：每个事实带来源与日期；结论写成有证据的观察，不写成买卖指令 | 黄金场景：prompt 含"with its source and date"与"not as instructions to buy or sell" |

## 基线与回退

`docs/B3_BASELINE.md` 记录：本轮改动前的两段 system 全文、既有断言清单、3 个黄金场景行为。
回退 = revert 本轮两个文件的两个提交；评测套件保证回退后行为与基线一致。

## 验收

- 全量测试绿；黄金场景新增 ≥6 条断言全过。
- `B3_PROMPT_PLAN.md` §5 追加本轮记录。
