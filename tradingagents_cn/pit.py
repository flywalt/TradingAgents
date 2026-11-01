"""Point-in-time rules for A-share statements.

A quarterly report is public knowledge only from its announcement date. Serving
a period announced after the run date is lookahead — the one error a backtest
cannot recover from — so this module drops any row whose announcement date is
missing, malformed, or later than the trade date.

``latest_reports`` then picks the version that was current: the same ``end_date``
can appear several times (original filing, corrections), and the newest
announcement wins.
"""

from __future__ import annotations

import pandas as pd

ANNOUNCEMENT_COLUMNS = ("ann_date", "f_ann_date")


def _to_dates(values) -> pd.Series:
    """Parse ``20260825`` / ``2026-08-25`` / ``NaT``-ish values into datetimes."""
    series = pd.Series(values).astype("string").str.strip()
    series = series.str.replace("-", "", regex=False)
    return pd.to_datetime(series, format="%Y%m%d", errors="coerce")


def _as_of(value) -> pd.Timestamp:
    stamp = _to_dates([value]).iloc[0]
    if pd.isna(stamp):
        raise ValueError(f"trade date must be a YYYY-MM-DD or YYYYMMDD value, got {value!r}")
    return stamp


def announced_by(frame: pd.DataFrame, as_of) -> pd.DataFrame:
    """Rows whose report was public on ``as_of``.

    The announcement date is preferred; ``f_ann_date`` (the filing date) stands
    in when it is missing. A row with neither is dropped: an unreadable
    announcement date is not evidence that the report was already out.
    """
    if frame is None or len(frame) == 0:
        return pd.DataFrame() if frame is None else frame.copy()

    cutoff = _as_of(as_of)
    effective = None
    for column in ANNOUNCEMENT_COLUMNS:
        if column not in frame.columns:
            continue
        parsed = _to_dates(frame[column])
        effective = parsed if effective is None else effective.fillna(parsed)

    if effective is None:
        return frame.iloc[0:0].copy()

    keep = effective.notna() & (effective <= cutoff)
    return frame.loc[keep].copy()


def latest_reports(
    frame: pd.DataFrame, periods: int = 4, report_type: str | None = "1"
) -> pd.DataFrame:
    """The newest ``periods`` report periods, consolidated by default, oldest first.

    ``report_type == "1"`` is the consolidated statement (合并报表); A-share
    filings also carry parent-only versions under other codes, which must not
    be mixed into the same column.
    """
    if frame is None or len(frame) == 0:
        return pd.DataFrame() if frame is None else frame.copy()

    work = frame
    if report_type is not None and "report_type" in work.columns:
        work = work[work["report_type"].astype("string").str.strip() == str(report_type)]
    if "end_date" not in work.columns:
        return work.copy()

    work = work.assign(_period=_to_dates(work["end_date"]))
    if "ann_date" in work.columns:
        announced = _to_dates(work["ann_date"])
    else:
        announced = pd.Series(pd.NaT, index=work.index)
    work = work.assign(_announced=announced)

    work = work[work["_period"].notna()]
    work = work.sort_values(["_period", "_announced"], na_position="first")
    work = work.drop_duplicates(subset="_period", keep="last")
    work = work.sort_values("_period").tail(periods)
    return work.drop(columns=["_period", "_announced"]).reset_index(drop=True)
