"""Access control for a LAN service: one token to write, one to read, path jail.

The stakes are concrete: anything on the LAN that can POST a run spends real
model money. The token is therefore required unless the operator explicitly opts
out for a loopback-only development server.
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path

TOKEN_ENV = "TRADINGAGENTS_WEB_TOKEN"
READ_TOKEN_ENV = "TRADINGAGENTS_WEB_READ_TOKEN"
CORS_ENV = "TRADINGAGENTS_WEB_CORS_ORIGINS"
KVIEWER_ENV = "KVIEWER_BASE_URL"

ALLOWED_SUFFIXES = {".html", ".md", ".json", ".log"}


def configured_token() -> str | None:
    return os.environ.get(TOKEN_ENV) or None


def configured_read_token() -> str | None:
    return os.environ.get(READ_TOKEN_ENV) or None


def cors_origins() -> list[str]:
    raw = os.environ.get(CORS_ENV) or ""
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def kviewer_base() -> str:
    return (os.environ.get(KVIEWER_ENV) or "").rstrip("/")


def token_matches(provided: str | None, expected: str | None) -> bool:
    """Constant-time comparison; an unset token never matches."""
    if not provided or not expected:
        return False
    return secrets.compare_digest(str(provided), str(expected))


def is_inside(base: Path, candidate: Path) -> bool:
    """True when ``candidate`` resolves inside ``base`` (symlinks included)."""
    try:
        base_resolved = Path(base).resolve()
        candidate_resolved = Path(candidate).resolve()
    except OSError:
        return False
    return candidate_resolved == base_resolved or base_resolved in candidate_resolved.parents


def safe_run_file(run_dir: Path, name: str) -> Path | None:
    """A whitelisted artifact inside ``run_dir``, or None for anything else."""
    if not name or "/" in name or "\\" in name or ".." in name:
        return None
    candidate = Path(run_dir) / name
    if Path(name).suffix.lower() not in ALLOWED_SUFFIXES:
        return None
    return candidate if is_inside(run_dir, candidate) and candidate.is_file() else None
