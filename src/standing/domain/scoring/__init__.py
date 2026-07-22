"""Pure scoring package — no I/O by design."""

from standing.domain.scoring.base import (
    GICS_11,
    compute_base_standing,
    pillar_percentiles,
    sector_occupancy_flags,
    winsorize_series,
)
from standing.domain.scoring.pipeline import ScoreInputs, ScoreRow, score_cross_section
from standing.domain.scoring.shrinkage import shrink_social
from standing.domain.scoring.social_features import aggregate_mentions, apply_source_cap
from standing.domain.scoring.tilt import attention_tilt, final_standing, hype_dampener

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
