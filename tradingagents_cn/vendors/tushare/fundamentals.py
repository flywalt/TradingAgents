"""Company profile, valuation and a financial summary for an A-share run.

Replaces what the US pipeline reads from Yahoo/SEC with the Chinese filings:

* profile from ``stock_basic`` (name, industry, area, board, listing date) —
  without it the model tends to invent an industry from the chart;
* valuation from ``daily_basic`` as of the run's session, market cap converted
  from 万元 to 亿元;
* summary from ``fina_indicator``, but only the report that had been announced
  by the run date.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd

from tradingagents.dataflows.errors import VendorError, VendorUnavailableError
from tradingagents_cn.cache import cached
from tradingagents_cn.pit import announced_by, latest_reports
from tradingagents_cn.units import to_yi
from tradingagents_cn.vendors.common import no_rows, require_ashare
from tradingagents_cn.vendors.tushare import client

_TTL_SECONDS = 24 * 60 * 60
_VALUATION_LOOKBACK_DAYS = 10
_SUMMARY_LOOKBACK_DAYS = 3 * 365

_PROFILE_FIELDS = "ts_code,name,area,industry,market,list_date"


def get_fundamentals(ticker: str, curr_date: str) -> str:
    """Profile + valuation + financial summary, as of ``curr_date``."""
    canonical = require_ashare(ticker)
    as_of = _iso(curr_date)

    profile = _profile(canonical)
    valuation = _valuation(canonical, as_of)
    summary = _summary(canonical, as_of)

    lines = [
        f"# Fundamentals for {canonical} ({profile['name']}) as of {as_of}",
        "# Vendor: tushare; market cap in 亿元; ratios in %",
        "",
        "## Profile",
        f"- Name: {profile['name']}",
        f"- Industry: {profile['industry']}",
        f"- Area: {profile['area']}",
        f"- Market: {profile['market']}",
        f"- Listed: {_iso_or_empty(profile['list_date'])}",
        "",
        f"## Valuation ({valuation.get('trade_date') or 'no session found'})",
        f"- PE (TTM): {_number(valuation.get('pe_ttm'))}",
        f"- PB: {_number(valuation.get('pb'))}",
        f"- PS (TTM): {_number(valuation.get('ps_ttm'))}",
        f"- Total market cap: {_wan_to_yi(valuation.get('total_mv'))} 亿元",
        f"- Float market cap: {_wan_to_yi(valuation.get('circ_mv'))} 亿元",
        f"- Turnover rate: {_number(valuation.get('turnover_rate'))} %",
        f"- Volume ratio: {_number(valuation.get('volume_ratio'))}",
    ]

    if summary is None:
        lines += ["", "## Financial summary", "- No report had been announced by this date."]
    else:
        lines += [
            "",
            f"## Financial summary ({_iso_or_empty(summary.get('end_date'))}, "
            f"announced {_iso_or_empty(summary.get('ann_date'))})",
            f"- EPS: {_number(summary.get('eps'))}",
            f"- ROE: {_number(summary.get('roe'))} %",
            f"- Gross margin: {_number(summary.get('grossprofit_margin'))} %",
            f"- Net margin: {_number(summary.get('netprofit_margin'))} %",
            f"- Debt to assets: {_number(summary.get('debt_to_assets'))} %",
        ]
    return "\n".join(lines) + "\n"


def _profile(canonical: str) -> dict:
    frame = _fetch(
        "stock_basic",
        f"{canonical}",
        lambda: client.get_api().stock_basic(ts_code=canonical, fields=_PROFILE_FIELDS),
    )
    if frame is None or len(frame) == 0:
        raise no_rows(canonical, canonical, "no profile row for this symbol")
    row = frame.iloc[0].to_dict()
    return {
        "name": str(row.get("name") or "").strip() or canonical,
        "industry": str(row.get("industry") or "").strip(),
        "area": str(row.get("area") or "").strip(),
        "market": str(row.get("market") or "").strip(),
        "list_date": row.get("list_date"),
    }


def _valuation(canonical: str, as_of: str) -> dict:
    start = (date.fromisoformat(as_of) - timedelta(days=_VALUATION_LOOKBACK_DAYS)).isoformat()
    frame = _fetch(
        "daily_basic",
        f"{canonical}|{start}|{as_of}",
        lambda: client.get_api().daily_basic(
            ts_code=canonical, start_date=_compact(start), end_date=_compact(as_of)
        ),
    )
    if frame is None or len(frame) == 0:
        return {}
    data = frame.copy()
    data["trade_date"] = data["trade_date"].astype(str)
    data = data[data["trade_date"] <= _compact(as_of)]
    if len(data) == 0:
        return {}
    return data.sort_values("trade_date").iloc[-1].to_dict()


def _summary(canonical: str, as_of: str):
    start = (date.fromisoformat(as_of) - timedelta(days=_SUMMARY_LOOKBACK_DAYS)).isoformat()
    frame = _fetch(
        "fina_indicator",
        f"{canonical}|{start}|{as_of}",
        lambda: client.get_api().fina_indicator(
            ts_code=canonical, start_date=_compact(start), end_date=_compact(as_of)
        ),
    )
    if frame is None or len(frame) == 0:
        return None
    visible = announced_by(frame, as_of)
    if len(visible) == 0:
        return None
    latest = latest_reports(visible, periods=1, report_type=None)
    return latest.iloc[-1].to_dict() if len(latest) else None


def _fetch(namespace: str, key: str, producer):
    """Cached call with the router's error taxonomy applied."""
    try:
        return cached(namespace, key, _TTL_SECONDS, producer)
    except VendorError:
        raise
    except Exception as exc:  # network, throttling, quota
        raise VendorUnavailableError(f"tushare fundamentals unavailable: {exc}") from exc


def _number(value) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        return ""
    return f"{float(value):.2f}"


def _wan_to_yi(value) -> str:
    """``万元`` -> ``亿元`` (Tushare serves market cap in 万元)."""
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        return ""
    return to_yi(float(value) * 10_000)


def _iso_or_empty(value) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if len(text) != 8 or not text.isdigit():
        return text
    return f"{text[:4]}-{text[4:6]}-{text[6:]}"


def _iso(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"expected a YYYY-MM-DD date, got {value!r}")
    return datetime.strptime(value.strip(), "%Y-%m-%d").strftime("%Y-%m-%d")


def _compact(iso_date: str) -> str:
    return iso_date.replace("-", "")
