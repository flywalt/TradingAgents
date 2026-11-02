"""Fuzzy instrument search for the run form: match a code or a name fragment.

The kernel asks for an exact ticker; a person types ``茅台`` or ``6005`` or
half a code remembered off a screen. The exchange's own listing table (tushare
``stock_basic``, cached for a day) is the vocabulary; matching is deliberately
dumb - substring on the code and on the name, prefix ahead of contains - which
is what the reference app's code search does, without a pinyin index.

Best-effort by design: with no data source the answer is an empty list, never
an error - the form still accepts a pasted ticker.
"""

from __future__ import annotations

from tradingagents_cn.cache import cached
from tradingagents_cn.vendors.tushare import client

#: How many suggestions a dropdown can use.
LIMIT = 8


def _listed_table() -> list[dict]:
    """Today's listed A-shares as ``{ts_code, name}`` rows."""
    api = client.get_api()
    frame = cached("stock_basic", "all_listed", 86400,
                   lambda: api.stock_basic(exchange="", list_status="L",
                                           fields="ts_code,name"))
    return frame.to_dict("records")


def suggest(query: str, limit: int = LIMIT) -> list[dict]:
    """Stocks whose code or name contains ``query``, best matches first."""
    query = (query or "").strip()
    if not query:
        return []
    try:
        table = _listed_table()
    except Exception:  # noqa: BLE001 - search is best-effort, never an error
        return []

    needle = query.casefold()
    exact, code_prefix, code_contains, name_prefix, name_contains = [], [], [], [], []
    for row in table:
        code = str(row.get("ts_code") or "")
        name = str(row.get("name") or "").casefold()
        if not code or not name:
            continue
        lowered = code.casefold()
        if lowered.split(".")[0] == needle:
            exact.append(row)
        elif lowered.startswith(needle):
            code_prefix.append(row)
        elif needle in lowered:
            code_contains.append(row)
        elif name.startswith(needle):
            name_prefix.append(row)
        elif needle in name:
            name_contains.append(row)

    ranked = exact + code_prefix + code_contains + name_prefix + name_contains
    return [{"symbol": row["ts_code"], "name": row["name"]}
            for row in ranked[:limit]]
