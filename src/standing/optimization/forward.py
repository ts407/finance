from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pandas as pd

from standing.optimization.analyse import _spearman
from standing.providers import FixtureMarketProvider


def next_weekday(d: date) -> date:
    cursor = d + timedelta(days=1)
    while cursor.weekday() >= 5:
        cursor += timedelta(days=1)
    return cursor


def top_decile_mean_return(scores: pd.Series, forward: pd.Series, *, frac: float = 0.1) -> float:
    """Mean forward return of the top ``frac`` names by score."""
    aligned = pd.concat([scores, forward], axis=1, keys=["score", "fwd"]).dropna()
    if aligned.empty:
        return float("nan")
    k = max(1, int(len(aligned) * frac))
    top = aligned.nlargest(k, "score")
    return float(top["fwd"].mean())


def forward_return_metrics(
    standings: pd.DataFrame,
    *,
    as_of: date,
    market: FixtureMarketProvider | None = None,
    return_col: str = "ret_1m",
) -> dict[str, float]:
    """
    Score@as_of vs next-weekday market ``return_col`` (synthetic forward proxy).

    Fixture market draws are seeded by as_of, so D+1 returns are independent of
    D cross-section scores — unlike same-day ret_* which also feed Momentum.
    """
    market = market or FixtureMarketProvider()
    fwd_as_of = next_weekday(as_of)
    fwd = market.fetch(fwd_as_of).set_index("ticker")[return_col]
    scored = standings.set_index("ticker")
    aligned_score = scored["final_standing"].reindex(fwd.index)
    spearman = _spearman(aligned_score, fwd)
    hit = top_decile_mean_return(aligned_score, fwd)
    universe_mean = float(fwd.mean())
    return {
        "forward_as_of": fwd_as_of.isoformat(),
        "spearman_score_vs_forward": spearman,
        "top_decile_mean_forward": hit,
        "universe_mean_forward": universe_mean,
        "top_decile_excess_forward": hit - universe_mean,
    }


def summarize_forward_pairs(
    prod_rows: list[dict[str, Any]],
    shadow_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Aggregate daily forward metrics and shadow−productive lifts."""
    if not prod_rows or not shadow_rows:
        return {}
    prod = pd.DataFrame(prod_rows)
    shadow = pd.DataFrame(shadow_rows)
    spearman_lift = (
        shadow["spearman_score_vs_forward"].to_numpy() - prod["spearman_score_vs_forward"].to_numpy()
    )
    excess_lift = (
        shadow["top_decile_excess_forward"].to_numpy() - prod["top_decile_excess_forward"].to_numpy()
    )
    return {
        "n_forward_days": int(len(prod)),
        "mean_spearman_score_vs_forward_productive": float(prod["spearman_score_vs_forward"].mean()),
        "mean_spearman_score_vs_forward_shadow": float(shadow["spearman_score_vs_forward"].mean()),
        "mean_forward_spearman_lift": float(spearman_lift.mean()),
        "daily_forward_spearman_lift": spearman_lift.tolist(),
        "mean_top_decile_excess_productive": float(prod["top_decile_excess_forward"].mean()),
        "mean_top_decile_excess_shadow": float(shadow["top_decile_excess_forward"].mean()),
        "mean_top_decile_excess_lift": float(excess_lift.mean()),
        "daily_top_decile_excess_lift": excess_lift.tolist(),
        "return_col": "ret_1m",
        "note": (
            "Forward proxy = next weekday fixture ret_1m after score date; "
            "not live realized returns."
        ),
    }
