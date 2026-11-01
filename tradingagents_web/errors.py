"""Turn an exception into something a person can act on.

Three layers fail differently and must not be conflated: the model provider
(credentials, quota), the data vendor (unconfigured, unavailable, no data), and
our own validation/config. Each category carries the next step, because "internal
error" tells a user nothing.
"""

from __future__ import annotations

from dataclasses import dataclass

from tradingagents.dataflows.errors import (
    NoMarketDataError,
    VendorNotConfiguredError,
    VendorUnavailableError,
)


@dataclass(frozen=True)
class ErrorInfo:
    category: str
    message: str
    action: str
    http_status: int = 500


class QueueFullError(Exception):
    """More jobs are waiting than the single worker is allowed to hold."""


class ReportWriteError(Exception):
    """The report could not be written to disk."""


def classify(exc: BaseException) -> ErrorInfo:
    if isinstance(exc, QueueFullError):
        return ErrorInfo("queue_full", "已有任务在运行或排队（上限 3）。", "稍后再试。", 409)
    if isinstance(exc, ReportWriteError):
        return ErrorInfo("report_write", "报告写入失败。", "检查磁盘空间与目录权限。")
    if isinstance(exc, VendorNotConfiguredError):
        return ErrorInfo("vendor_unconfigured", "数据源未配置（缺少凭据）。",
                         "在 .env 中配置对应 token 后重启服务。")
    if isinstance(exc, VendorUnavailableError):
        return ErrorInfo("vendor_unavailable", "数据源暂时不可用（网络/限流）。", "稍后重试。")
    if isinstance(exc, NoMarketDataError):
        return ErrorInfo("no_data", "该标的在此区间没有可用数据。", "换日期或确认代码。")

    text = str(exc)
    if isinstance(exc, ValueError):
        if "cannot tell the market" in text:
            return ErrorInfo("symbol_ambiguous", "无法判定市场（代码有歧义）。",
                             "显式指定市场，例如港股请选择 HK。", 400)
        if "contradicts" in text or "is " in text and "but the run identifies" in text:
            return ErrorInfo("symbol_conflict", "市场与代码不一致。", "检查代码后缀与所选市场。", 400)
        if "unknown market" in text or "unknown market profile" in text:
            return ErrorInfo("symbol_invalid", "市场代码无法识别。", "使用 CN/HK/US 等支持的市场。", 400)
        if "cn_strict_ashare" in text:
            return ErrorInfo("strict_not_allowed", "严格模式只适用于 A 股。", "关闭严格模式。", 400)
        return ErrorInfo("bad_request", text or "请求参数不合法。", "修正后重试。", 400)

    if isinstance(exc, RuntimeError) and "uncommitted worktree" in text:
        return ErrorInfo("config_blocked", "开启检查点时工作区有未提交修改。",
                         "提交/清理工作区，或关闭检查点。", 400)
    return ErrorInfo("internal", "未预期的内部错误。", "查看该任务的 web.log。")
