"""Tongdaxin (通达信) indicator formulas, checked against a reference implementation.

The point of this module is that a reader comparing the report with 同花顺/通达信
sees the same number. The reference implementation below is written directly from
the formula definitions (loops, no pandas shortcuts), so a vectorised mistake
cannot agree with itself.

Formulas:
    MA(X,N)          = rolling simple mean
    EMA(X,N)         = (2*X + (N-1)*Y') / (N+1), seeded with X[0]
    SMA(X,N,1)       = (X + (N-1)*Y') / N, seeded with X[0]   (Wilder)
    RSI              = SMA(MAX(C-LC,0),N,1) / SMA(ABS(C-LC),N,1) * 100
    MACD             = DIF=EMA(C,12)-EMA(C,26); DEA=EMA(DIF,9); HIST=2*(DIF-DEA)
    BOLL             = MA(C,20) ± 2*STD(C,20)  (sample std, ddof=1)
    ATR              = MA(TR,14)              (simple mean, not Wilder)
    VWMA             = SUM(C*V,14)/SUM(V,14)
    MFI              = 100-100/(1+SUM(pos,14)/SUM(neg,14)) on typical price
"""

from __future__ import annotations

import math

import pandas as pd
import pytest

from tradingagents_cn.vendors.tushare.indicators import SUPPORTED_INDICATORS, indicator_series

pytestmark = pytest.mark.unit

SYMBOL = "600519.SH"


def bars(count: int = 80) -> pd.DataFrame:
    """Deterministic, non-monotonic series so RSI/MFI are not degenerate."""
    days = pd.date_range("2026-01-05", periods=count, freq="B")
    closes, highs, lows, volumes = [], [], [], []
    price = 100.0
    for i in range(count):
        move = math.sin(i / 3.0) * 2.0 + (0.4 if i % 7 < 4 else -0.3)
        price = round(price + move, 2)
        closes.append(price)
        highs.append(round(price + 1.5, 2))
        lows.append(round(price - 1.2, 2))
        volumes.append(1000 + (i % 5) * 137)
    return pd.DataFrame(
        {
            "ts_code": [SYMBOL] * count,
            "trade_date": [d.strftime("%Y%m%d") for d in days],
            "open": closes,
            "high": highs,
            "low": lows,
            "close": closes,
            "vol": volumes,
            "amount": [10_000.0] * count,
            "pct_chg": [0.0] * count,
        }
    )


# --- reference implementation (loops, straight from the formulas) ----------


def ref_ma(values, n):
    return [sum(values[max(0, i - n + 1): i + 1]) / len(values[max(0, i - n + 1): i + 1])
            for i in range(len(values))]


def ref_ema(values, n):
    alpha = 2 / (n + 1)
    out = [values[0]]
    for value in values[1:]:
        out.append(out[-1] + alpha * (value - out[-1]))
    return out


def ref_sma(values, n):
    out = [values[0]]
    for value in values[1:]:
        out.append((value + (n - 1) * out[-1]) / n)
    return out


def ref_rsi(closes, n=14):
    up, down = [0.0], [0.0]
    for prev, cur in zip(closes, closes[1:], strict=False):
        diff = cur - prev
        up.append(max(diff, 0.0))
        down.append(max(-diff, 0.0))
    su, sd = ref_sma(up, n), ref_sma(down, n)
    return [100 * u / (u + d) if (u + d) else float("nan") for u, d in zip(su, sd, strict=True)]


def ref_macd(closes):
    short, long = ref_ema(closes, 12), ref_ema(closes, 26)
    dif = [fast - slow for fast, slow in zip(short, long, strict=True)]
    dea = ref_ema(dif, 9)
    return dif, dea, [2 * (d - e) for d, e in zip(dif, dea, strict=True)]


def ref_tr(highs, lows, closes):
    out = [highs[0] - lows[0]]
    for i in range(1, len(closes)):
        prev = closes[i - 1]
        out.append(max(highs[i] - lows[i], abs(prev - highs[i]), abs(prev - lows[i])))
    return out


def ref_atr(highs, lows, closes, n=14):
    return ref_ma(ref_tr(highs, lows, closes), n)


def ref_boll(closes, n=20):
    mid = ref_ma(closes, n)
    upper, lower = [], []
    for i, mean in enumerate(mid):
        window = closes[max(0, i - n + 1): i + 1]
        if len(window) < 2:
            std = float("nan")
        else:
            variance = sum((x - sum(window) / len(window)) ** 2 for x in window) / (len(window) - 1)
            std = math.sqrt(variance)
        upper.append(mean + 2 * std)
        lower.append(mean - 2 * std)
    return mid, upper, lower


def ref_vwma(closes, volumes, n=14):
    out = []
    for i in range(len(closes)):
        start = max(0, i - n + 1)
        num = sum(c * v for c, v in zip(closes[start:i + 1], volumes[start:i + 1], strict=True))
        den = sum(volumes[start:i + 1])
        out.append(num / den)
    return out


def ref_mfi(highs, lows, closes, volumes, n=14):
    typ = [(high + low + close) / 3 for high, low, close in zip(highs, lows, closes, strict=True)]
    pos, neg = [0.0], [0.0]
    for i in range(1, len(typ)):
        flow = typ[i] * volumes[i]
        delta = typ[i] - typ[i - 1]
        pos.append(flow if delta > 0 else 0.0)
        neg.append(flow if delta < 0 else 0.0)
    out = []
    for i in range(len(typ)):
        window = slice(max(0, i - n + 1), i + 1)
        p, m = sum(pos[window]), sum(neg[window])
        out.append(100 - 100 / (1 + p / m) if m else (100.0 if p else float("nan")))
    return out


def _assert_series(actual: pd.Series, expected: list[float], first: int) -> None:
    for i in range(first, len(expected)):
        assert actual.iloc[i] == pytest.approx(expected[i], rel=1e-9, abs=1e-9), f"row {i}"


# --- the 13 names, one formula at a time ----------------------------------


def test_ma_indicators_match_the_reference():
    frame = bars()
    _assert_series(indicator_series(frame, "close_50_sma", "tdx"),
                   ref_ma(frame["close"].tolist(), 50), 49)
    _assert_series(indicator_series(frame, "close_200_sma", "tdx"),
                   ref_ma(frame["close"].tolist(), 200), 199)


def test_ema_seeds_with_the_first_close():
    frame = bars()
    _assert_series(indicator_series(frame, "close_10_ema", "tdx"),
                   ref_ema(frame["close"].tolist(), 10), 9)


def test_rsi_uses_wilder_smoothing_on_max_and_abs():
    frame = bars()
    _assert_series(indicator_series(frame, "rsi", "tdx"),
                   ref_rsi(frame["close"].tolist(), 14), 14)


def test_macd_histogram_is_doubled_like_tongdaxin():
    frame = bars()
    dif, dea, hist = ref_macd(frame["close"].tolist())
    _assert_series(indicator_series(frame, "macd", "tdx"), dif, 34)
    _assert_series(indicator_series(frame, "macds", "tdx"), dea, 34)
    _assert_series(indicator_series(frame, "macdh", "tdx"), hist, 34)


def test_atr_is_a_simple_mean_of_true_range_not_wilder():
    frame = bars()
    _assert_series(indicator_series(frame, "atr", "tdx"),
                   ref_atr(frame["high"].tolist(), frame["low"].tolist(),
                           frame["close"].tolist(), 14), 14)


def test_boll_uses_the_sample_standard_deviation():
    frame = bars()
    mid, upper, lower = ref_boll(frame["close"].tolist(), 20)
    _assert_series(indicator_series(frame, "boll", "tdx"), mid, 19)
    _assert_series(indicator_series(frame, "boll_ub", "tdx"), upper, 19)
    _assert_series(indicator_series(frame, "boll_lb", "tdx"), lower, 19)


def test_vwma_weights_close_by_volume():
    frame = bars()
    _assert_series(indicator_series(frame, "vwma", "tdx"),
                   ref_vwma(frame["close"].tolist(), frame["vol"].tolist(), 14), 14)


def test_mfi_is_computed_on_typical_price():
    frame = bars()
    _assert_series(indicator_series(frame, "mfi", "tdx"),
                   ref_mfi(frame["high"].tolist(), frame["low"].tolist(),
                           frame["close"].tolist(), frame["vol"].tolist(), 14), 14)


def test_every_supported_name_has_a_tdx_formula():
    frame = bars(260)          # enough history for close_200_sma
    for name in SUPPORTED_INDICATORS:
        series = indicator_series(frame, name, "tdx")
        assert len(series) == len(frame), name
        assert series.notna().any(), name


# --- flavour selection -----------------------------------------------------


def test_the_two_flavours_disagree_where_the_formulas_differ():
    frame = bars()
    dif = indicator_series(frame, "macd", "tdx")
    dea = indicator_series(frame, "macds", "tdx")
    tdx_hist = indicator_series(frame, "macdh", "tdx")
    stock_hist = indicator_series(frame, "macdh", "stockstats")

    # 通达信 doubles the histogram; stockstats serves DIF-DEA (and a different
    # EMA seeding, so the values differ beyond the factor of two).
    assert tdx_hist.iloc[-1] == pytest.approx(2 * (dif.iloc[-1] - dea.iloc[-1]), rel=1e-9)
    assert not tdx_hist.equals(stock_hist)


def test_the_configured_flavour_is_used_by_default():
    from tradingagents.dataflows.config import run_config

    frame = bars()
    with run_config({"cn_indicator_flavor": "stockstats"}):
        configured = indicator_series(frame, "macdh")
    assert configured.iloc[-1] == pytest.approx(
        indicator_series(frame, "macdh", "stockstats").iloc[-1]
    )
