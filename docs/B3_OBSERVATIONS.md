# B3_OBSERVATIONS.md — 真实运行观察台账

> 用途：把"看报告时发现的问题"变成**可重复的检查项**。每次真实运行后跑一遍体检脚本，
> 把新发现归档到本文件；某类问题反复出现，才进入下一轮 prompt 改动或呈现层修复。

## 怎么用

```bash
python scripts/report_lint.py ~/.tradingagents/logs/profile-cn/<ticker>/<date>/runs/<run_id>/report
```

- 无模型、无网络、确定性；**永远退出码 0**（这是体检，不是门禁）。
- 检查对象是**呈现层翻译后的页面**（`complete_report.html` 经 `report_page.present`），
  即读者实际看到的内容；没有 HTML 时退回原始 markdown。

## 检查项与归属

| 检查项 | 说明 | 归属 |
| --- | --- | --- |
| `bold label still in English` | 中文页面里残留的英文加粗标签 | 若属内核固定标签（`schemas.py`）→ 呈现层漏译；若属模型自创 → 需 prompt 引导（记入本文件） |
| `intraday path claimed` | 用日线描述盘中路径 | prompt 准确性纪律（B3 第二轮已加规则） |
| `growth figure without a visible source` | 无来源的增长数字 | prompt 准确性纪律 |
| `empty source labelled UNAVAILABLE` | 把"没条目"写成"源坏了" | 数据层语义（已修）或 prompt 纪律 |
| `price basis (复权) never stated` | 全文没有复权口径 | prompt 口径要求（B3 第一轮已加） |

## 已归档观察

### 2026-11-03 · `0f6ea109`（4 分析师，600519.SH）

- 内核固定标签**全部已中文化**（源码枚举生效），残余 5 处均为**模型自创**标签：
  `Mildly Bullish`、`Price stability at the product level`、`RSI`（技术指标名，可接受）。
- 口径：`前复权（qfq）…以 2026-11-03 为锚` 出现；来源+日期在新闻报告 17 处。
- `盘中` 类描述 0 次；`站上/站稳` 7 次但均带日期+收盘价+指标值，属日线支持的事实陈述。

### 2026-11-02 · `d486cccd`（改造前基线）

- 18 处英文加粗标签，含 `FINAL TRANSACTION PROPOSAL`；口径与单位引用明显少于改造后。
- 对照用途：证明"源码枚举"清掉的是**内核词表**这一类，而不是靠人工列表堆出来的。

## 候选（出现两次以上才动手）

| 模式 | 出现次数 | 拟处理 |
| --- | --- | --- |
| 模型自创英文小标题（`Overall Sentiment`、`Mildly Bullish` 等） | 1 次运行 | 待观察：若稳定复现，考虑上下文加一句"小标题用中文"（会改变落盘产物，需评估） |
| 技术指标缩写（`RSI`/`MACD` 等） | 常态 | 不翻译：这是通用缩写，译为中文反而更难读 |
