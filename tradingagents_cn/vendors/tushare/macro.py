"""China macro series for the news analyst.

The upstream macro tool reads FRED, which for an A-share run describes the US
economy — the wrong policy backdrop entirely. This serves the Chinese series the
account can actually reach, with the alias table, unit and frequency stated.

Unavailable series (LPR, China government 10Y) are refused loudly rather than
silently answered from FRED: a US rate under a China heading is worse than no
number.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd

from tradingagents.dataflows.errors import VendorError, VendorUnavailableError
from tradingagents_cn.cache import cached
from tradingagents_cn.vendors.common import no_rows
from tradingagents_cn.vendors.tushare import client

_TTL_SECONDS = 24 * 60 * 60

#: alias -> (endpoint, value column, label, unit, frequency)
ALIASES: dict[str, tuple[str, str, str, str, str]] = {
    "cpi": ("cn_cpi", "nt_yoy", "CPI 同比", "%", "monthly"),
    "ppi": ("cn_ppi", "ppi_yoy", "PPI 同比", "%", "monthly"),
    "gdp": ("cn_gdp", "gdp_yoy", "GDP 同比", "%", "quarterly"),
    "m2": ("cn_m", "m2_yoy", "M2 同比", "%", "monthly"),
    "social_financing": ("sf_month", "inc_month", "社融当月增量", "亿元", "monthly"),
    "pmi": ("cn_pmi", "pmi010000", "制造业 PMI", "点", "monthly"),
    "shibor": ("shibor", "3m", "SHIBOR 3M", "%", "daily"),
}

#: Series an A-share run commonly asks for that this account cannot serve.
UNAVAILABLE = {
    "lpr": "LPR 贷款市场报价利率（Tushare 无该接口权限）",
    "10y_treasury": "中国 10 年期国债收益率（yc_cb 无接口权限）",
    "yield_curve": "中国国债收益率曲线（无接口权限）",
}


def get_macro_indicators(
    indicator: str, curr_date: str, look_back_days: int | None = None
) -> str:
    """A Chinese macro series up to ``curr_date``, rendered as a short report."""
    alias = str(indicator).strip().lower()
    if alias in UNAVAILABLE:
        raise ValueError(
            f"{indicator!r} is not available for A-share runs: {UNAVAILABLE[alias]}. "
            f"Supported: {', '.join(sorted(ALIASES))}"
        )
    if alias not in ALIASES:
        raise ValueError(
            f"unknown macro indicator {indicator!r}; supported: {', '.join(sorted(ALIASES))}"
        )

    endpoint, column, label, unit, frequency = ALIASES[alias]
    as_of = _iso(curr_date)
    days = int(look_back_days) if look_back_days else (365 if frequency != "daily" else 90)
    start = (date.fromisoformat(as_of) - timedelta(days=days)).isoformat()

    frame = _fetch(endpoint, alias, start, as_of, frequency)
    frame = _in_window(frame, as_of, frequency)
    if frame is None or len(frame) == 0 or column not in frame.columns:
        raise no_rows(alias, alias, f"no {endpoint} rows up to {as_of}")

    values = pd.to_numeric(frame[column], errors="coerce").dropna()
    if len(values) == 0:
        raise no_rows(alias, alias, f"{column} is empty up to {as_of}")

    latest = float(values.iloc[-1])
    change = latest - float(values.iloc[0]) if len(values) > 1 else None
    period = _period(frame.iloc[-1])

    lines = [
        f"# 宏观指标: {label} ({alias})",
        f"# 来源: tushare ({endpoint}); 单位: {unit}; 频率: {frequency}; 截止: {as_of}",
        f"# 最新 ({period}): {latest:.2f} {unit}",
    ]
    if change is not None:
        lines.append(f"# 窗口变化: {change:+.2f} {unit}（自 {_period(frame.iloc[0])}）")
    lines += ["", "period,value", *[f"{_period(row)},{float(row[column]):.2f}"
                                    for _, row in frame.iterrows()
                                    if pd.notna(pd.to_numeric(row[column], errors="coerce"))]]
    return "\n".join(lines) + "\n"


def _fetch(endpoint: str, alias: str, start: str, as_of: str, frequency: str):
    call = getattr(client.get_api(), endpoint)
    if frequency == "daily":
        kwargs = {"start_date": start.replace("-", ""), "end_date": as_of.replace("-", "")}
    elif frequency == "quarterly":
        kwargs = {"start_q": _quarter(start), "end_q": _quarter(as_of)}
    else:
        kwargs = {"start_m": start[:7].replace("-", ""), "end_m": as_of[:7].replace("-", "")}

    try:
        return cached(endpoint, f"{alias}|{start}|{as_of}", _TTL_SECONDS, lambda: call(**kwargs))
    except VendorError:
        raise
    except Exception as exc:  # network, throttling, quota
        raise VendorUnavailableError(f"tushare {endpoint} unavailable: {exc}") from exc


def _in_window(frame, as_of: str, frequency: str):
    """Drop observations after the run date (month/quarter prefixes compare as text)."""
    if frame is None or len(frame) == 0:
        return frame
    data = frame.copy()
    if frequency == "daily":
        data["_k"] = data["date"].astype(str).str.replace("-", "", regex=False)
        limit = as_of.replace("-", "")
    elif frequency == "quarterly":
        data["_k"] = data["quarter"].astype(str)
        limit = _quarter(as_of)
    else:
        data["_k"] = data["month"].astype(str)
        limit = as_of[:7].replace("-", "")
    data = data[data["_k"] <= limit]
    return data.sort_values("_k").reset_index(drop=True)


def _quarter(iso_date: str) -> str:
    month = int(iso_date[5:7])
    return f"{iso_date[:4]}Q{(month - 1) // 3 + 1}"


def _period(row) -> str:
    for key in ("month", "quarter", "date"):
        if key in row and pd.notna(row[key]):
            return str(row[key])
    return "?"


def _iso(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"expected a YYYY-MM-DD date, got {value!r}")
    return datetime.strptime(value.strip(), "%Y-%m-%d").strftime("%Y-%m-%d")
