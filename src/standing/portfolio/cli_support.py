"""Shared helpers for portfolio CLI commands."""

from __future__ import annotations

import re
from pathlib import Path

from standing.config import default_portfolio_db
from standing.portfolio.db import connect, migrate
from standing.portfolio.repository import PortfolioRepository

_HORIZON_RE = re.compile(
    r"^\s*(\d+)\s*([dwmyDWMY])?\s*$"
)


def parse_horizon(value: str | int) -> int:
    """
    Parse a horizon into calendar days.

    Accepts plain integers (days) or suffixes: d/w/m/y
    (month ≈ 30d, year ≈ 365d). Example: ``12M`` → 360.
    """
    if isinstance(value, int):
        if value <= 0:
            raise ValueError("horizon must be positive")
        return value
    text = str(value).strip()
    if text.isdigit():
        days = int(text)
        if days <= 0:
            raise ValueError("horizon must be positive")
        return days
    m = _HORIZON_RE.match(text)
    if not m:
        raise ValueError(
            f"Invalid horizon '{value}' — use days (e.g. 90) or Nd/Nw/Nm/Ny (e.g. 12M)"
        )
    n = int(m.group(1))
    unit = (m.group(2) or "d").lower()
    mult = {"d": 1, "w": 7, "m": 30, "y": 365}[unit]
    days = n * mult
    if days <= 0:
        raise ValueError("horizon must be positive")
    return days


def open_repository(db_path: Path | str | None = None) -> PortfolioRepository:
    """Connect, migrate, and return a repository bound to the DB path."""
    if db_path is None or str(db_path).strip() == "":
        path = default_portfolio_db()
    else:
        path = Path(db_path).expanduser()
    conn = connect(path)
    migrate(conn)
    return PortfolioRepository(conn)


def drift_bucket(drift: float | None) -> str:
    """
    Score-drift colour bucket (percentile points).

    green: drift > -5 · yellow: -15..-5 · red: < -15
    """
    if drift is None:
        return "n/a"
    if drift < -15:
        return "red"
    if drift <= -5:
        return "yellow"
    return "green"
