"""Domain layer — scoring is pure (no I/O)."""

from standing.domain.scoring import (
    GICS_11,
    ScoreInputs,
    ScoreRow,
    aggregate_mentions,
    apply_source_cap,
    attention_tilt,
    compute_base_standing,
    final_standing,
    hype_dampener,
    pillar_percentiles,
    score_cross_section,
    sector_occupancy_flags,
    shrink_social,
    winsorize_series,
)

__all__ = [
    "GICS_11",
    "ScoreInputs",
    "ScoreRow",
    "aggregate_mentions",
    "apply_source_cap",
    "attention_tilt",
    "compute_base_standing",
    "final_standing",
    "hype_dampener",
    "pillar_percentiles",
    "score_cross_section",
    "sector_occupancy_flags",
    "shrink_social",
    "winsorize_series",
]
