"""TTL cache for vendor calls.

A backtest asks the same endpoint for the same window many times, and the
Tushare quota is finite. Two levels, both optional:

* an in-process dict (fast, dies with the process);
* one pickle file per key under ``<data_cache_dir>/cn-tushare`` (survives a run).

Keys are built by the caller and must name everything that changes the answer
(endpoint, symbol, date range, adjustment) — a key that omits the adjustment
would serve 前复权 bars to a 后复权 request, which is worse than no cache.
``TRADINGAGENTS_CN_CACHE=off`` disables both levels.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import pickle
import time
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

T = TypeVar("T")

_MEMORY: dict[tuple[str, str], tuple[float, object]] = {}
_MISS = object()


def enabled() -> bool:
    """Whether caching is on (default) for this process."""
    return os.environ.get("TRADINGAGENTS_CN_CACHE", "").strip().lower() not in {
        "off",
        "0",
        "false",
        "no",
    }


def _root() -> Path:
    override = os.environ.get("TRADINGAGENTS_CN_CACHE_DIR")
    if override:
        base = Path(override)
    else:
        from tradingagents.dataflows.config import get_config

        base = Path(get_config()["data_cache_dir"])
    return base / "cn-tushare"


def _digest(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def cached(namespace: str, key: str, ttl_seconds: int, producer: Callable[[], T]) -> T:
    """``producer()``'s result, reused while it is younger than ``ttl_seconds``."""
    if not enabled():
        return producer()

    digest = _digest(key)
    memory_key = (namespace, digest)
    now = time.time()

    hit = _MEMORY.get(memory_key)
    if hit is not None and now - hit[0] < ttl_seconds:
        return hit[1]

    path = _root() / f"{namespace}-{digest}.pkl"
    try:
        fresh = path.exists() and now - path.stat().st_mtime < ttl_seconds
    except OSError:
        fresh = False
    if fresh:
        try:
            value = pickle.loads(path.read_bytes())
        except Exception:  # noqa: BLE001 - a corrupt or older-format file is a miss
            value = _MISS
        if value is not _MISS:
            _MEMORY[memory_key] = (now, value)
            return value

    value = producer()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(pickle.dumps(value))
        os.replace(tmp, path)  # atomic: a reader never sees a half-written file
    except OSError:
        pass  # an unwritable cache degrades to memory-only, never to a failure
    _MEMORY[memory_key] = (now, value)
    return value


def clear(namespace: str | None = None) -> None:
    """Drop cached entries (all of them, or one namespace) from disk and memory."""
    for memory_key in list(_MEMORY):
        if namespace is None or memory_key[0] == namespace:
            _MEMORY.pop(memory_key, None)

    root = _root()
    if not root.exists():
        return
    pattern = f"{namespace}-*.pkl" if namespace else "*.pkl"
    for path in root.glob(pattern):
        with contextlib.suppress(OSError):
            path.unlink()


def reset_memory_cache() -> None:
    """Forget the in-process layer only (keeps the disk layer)."""
    _MEMORY.clear()
