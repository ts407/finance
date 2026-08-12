"""Sync filesystem / live Standing snapshots into portfolio SQLite."""

from __future__ import annotations

from typing import Any

from standing.pipeline.snapshot import StandingSnapshot
from standing.portfolio.repository import PortfolioRepository


def sync_standing_snapshot(
    repo: PortfolioRepository,
    snap: StandingSnapshot,
    *,
    universe_version: str | None = None,
    coverage_flags_col: str | None = None,
) -> int:
    """
    Upsert every standing row into scanner_snapshots.

    Returns number of rows written.
    Pillars map: fundamentals←value, momentum←momentum, attention←s_used
    (attention is the shrunk social score used for tilt — closest desk signal).
    """
    version = universe_version or snap.universe_id or "unknown"
    provider_state: dict[str, Any] = {
        "market_provider": snap.meta.get("market_provider"),
        "social_provider": snap.meta.get("social_provider"),
        "market_mode": snap.meta.get("market_mode"),
        "social_mode": snap.meta.get("social_mode"),
        "provider_staleness_utc": snap.meta.get("provider_staleness_utc"),
        "methodology_version": snap.methodology_version,
        "score_kind": snap.score_kind,
    }
    n = 0
    for row in snap.standings.to_dict(orient="records"):
        ticker = str(row["ticker"]).upper()
        coverage: dict[str, Any] = {}
        if coverage_flags_col and coverage_flags_col in row:
            coverage["raw"] = row[coverage_flags_col]
        if "value_coverage" in row:
            coverage["value_coverage"] = row.get("value_coverage")
        if "value_ev_rung" in row:
            coverage["value_ev_rung"] = row.get("value_ev_rung")
        if "sector_low_confidence" in row:
            coverage["sector_low_confidence"] = bool(row.get("sector_low_confidence"))

        score = row.get("final_standing")
        if score is None:
            continue
        repo.upsert_scanner_snapshot(
            as_of=snap.as_of,
            ticker=ticker,
            universe_version=version,
            score=float(score),
            pillar_fundamentals=_opt_float(row.get("value")),
            pillar_momentum=_opt_float(row.get("momentum")),
            pillar_attention=_opt_float(row.get("s_used")),
            coverage_flags=coverage,
            provider_state=provider_state,
        )
        n += 1
    return n


def _opt_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return f
