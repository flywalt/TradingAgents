"""Tongdaxin (通达信) indicator definitions.

A-share readers compare numbers with 同花顺/通达信, so the defaults here are the
formulas those tools use, not the Wikipedia/stockstats ones. Two differences are
material and never converge:

* MACD's histogram is ``2*(DIF-DEA)`` in 通达信, while stockstats serves
  ``DIF-DEA``;
* ATR is ``MA(TR,N)`` (simple mean), while stockstats uses Wilder smoothing.

EMA/RSI differ only in how the recursion is seeded (通达信 seeds with the first
value), so they converge on long series; BOLL already matches (sample std).

Every formula is checked against a loop-based reference implementation in
``tests/downstream/test_tdx_indicators.py``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

TDX_FLAVOR = "tdx"
STOCKSTATS_FLAVOR = "stockstats"
FLAVORS = (TDX_FLAVOR, STOCKSTATS_FLAVOR)

_RSI_WINDOW = 14
_ATR_WINDOW = 14
_VWMA_WINDOW = 14
_MFI_WINDOW = 14
_BOLL_WINDOW = 20


def compute(name: str, bars: pd.DataFrame) -> pd.Series:
    """The 通达信 series for one of upstream's indicator names."""
    close = pd.to_numeric(bars["close"], errors="coerce")
    high = pd.to_numeric(bars["high"], errors="coerce")
    low = pd.to_numeric(bars["low"], errors="coerce")
    volume = pd.to_numeric(bars["vol"], errors="coerce")

    if name == "close_50_sma":
        return ma(close, 50)
    if name == "close_200_sma":
        return ma(close, 200)
    if name == "close_10_ema":
        return ema(close, 10)
    if name in ("macd", "macds", "macdh"):
        dif, dea = _macd_lines(close)
        if name == "macd":
            return dif
        if name == "macds":
            return dea
        return 2 * (dif - dea)
    if name == "rsi":
        return _rsi(close, _RSI_WINDOW)
    if name in ("boll", "boll_ub", "boll_lb"):
        mid, upper, lower = _boll(close, _BOLL_WINDOW)
        return {"boll": mid, "boll_ub": upper, "boll_lb": lower}[name]
    if name == "atr":
        return ma(_true_range(high, low, close), _ATR_WINDOW)
    if name == "vwma":
        return _vwma(close, volume, _VWMA_WINDOW)
    if name == "mfi":
        return _mfi(high, low, close, volume, _MFI_WINDOW)
    raise ValueError(f"no 通达信 formula for indicator {name!r}")


def ma(series: pd.Series, window: int) -> pd.Series:
    """``MA(X,N)``: rolling simple mean (partial windows allowed; callers blank them)."""
    return series.rolling(window, min_periods=1).mean()


def ema(series: pd.Series, window: int) -> pd.Series:
    """``EMA(X,N)``: ``(2*X + (N-1)*Y')/(N+1)``, seeded with the first value."""
    return series.ewm(span=window, adjust=False).mean()


def wilder(series: pd.Series, window: int) -> pd.Series:
    """``SMA(X,N,1)``: ``(X + (N-1)*Y')/N``, seeded with the first value."""
    return series.ewm(alpha=1.0 / window, adjust=False).mean()


def _macd_lines(close: pd.Series) -> tuple[pd.Series, pd.Series]:
    dif = ema(close, 12) - ema(close, 26)
    return dif, ema(dif, 9)


def _rsi(close: pd.Series, window: int) -> pd.Series:
    diff = close.diff().fillna(0.0)
    up = wilder(diff.clip(lower=0.0), window)
    down = wilder((-diff).clip(lower=0.0), window)
    total = up + down
    rsi = 100 * up / total
    return rsi.where(total != 0, np.nan)


def _true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    ranges = pd.concat(
        [
            high - low,
            (prev_close - high).abs(),
            (prev_close - low).abs(),
        ],
        axis=1,
    )
    tr = ranges.max(axis=1)
    if len(tr):
        tr.iloc[0] = high.iloc[0] - low.iloc[0]
    return tr


def _boll(close: pd.Series, window: int) -> tuple[pd.Series, pd.Series, pd.Series]:
    mid = ma(close, window)
    std = close.rolling(window, min_periods=2).std(ddof=1)
    return mid, mid + 2 * std, mid - 2 * std


def _vwma(close: pd.Series, volume: pd.Series, window: int) -> pd.Series:
    value = (close * volume).rolling(window, min_periods=1).sum()
    traded = volume.rolling(window, min_periods=1).sum()
    return (value / traded).where(traded != 0, np.nan)


def _mfi(
    high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series, window: int
) -> pd.Series:
    typical = (high + low + close) / 3
    flow = typical * volume
    delta = typical.diff()
    positive = flow.where(delta > 0, 0.0).rolling(window, min_periods=1).sum()
    negative = flow.where(delta < 0, 0.0).rolling(window, min_periods=1).sum()
    ratio = positive / negative
    mfi = 100 - 100 / (1 + ratio)
    mfi = mfi.where(negative != 0, np.where(positive > 0, 100.0, np.nan))
    return mfi
