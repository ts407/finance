from __future__ import annotations

from datetime import date

import pandas as pd

from standing.optimization.forward import forward_return_metrics, next_weekday, top_decile_mean_return
from standing.providers import FixtureMarketProvider


def test_next_weekday_skips_weekend():
    assert next_weekday(date(2026, 7, 17)) == date(2026, 7, 20)  # Fri -> Mon


def test_top_decile_mean_return():
    scores = pd.Series([10, 9, 8, 7, 6, 5, 4, 3, 2, 1], index=list("abcdefghij"))
    fwd = pd.Series([0.1, 0.2, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, -0.1], index=scores.index)
    # top 10% of 10 = 1 name (score 10) -> 0.1
    assert top_decile_mean_return(scores, fwd, frac=0.1) == 0.1


def test_forward_return_metrics_runs():
    market = FixtureMarketProvider()
    m = market.fetch(date(2026, 7, 22))
    standings = m[["ticker"]].copy()
    standings["final_standing"] = range(len(standings), 0, -1)
    out = forward_return_metrics(standings, as_of=date(2026, 7, 22), market=market)
    assert "spearman_score_vs_forward" in out
    assert out["forward_as_of"] == "2026-07-23"
