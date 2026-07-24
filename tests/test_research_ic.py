from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from standing.providers.stooq.ohlcv import compute_ohlcv_features, parse_stooq_csv
from standing.research.ic import power_days_80, spearman_ic, summarize_ic_series


def test_compute_ohlcv_features_from_cassette():
    text = Path("tests/cassettes/stooq/aapl.us.csv").read_text()
    df = parse_stooq_csv(text)
    feats = compute_ohlcv_features(df, as_of=date(2026, 7, 10))
    assert feats["last_price"] is not None
    assert feats["ret_1m"] is not None


def test_power_days_formula():
    # T ≈ (2.80 * 0.10 / 0.05)^2 = 5.6^2 = 31.36
    assert abs(power_days_80(0.05, 0.10) - 31.36) < 0.01


def test_summarize_ic_series():
    s = pd.Series([0.05, 0.02, -0.01, 0.04, 0.03, 0.01])
    summary = summarize_ic_series(s, signal="test", horizon_days=21)
    assert summary.n_ic_obs == 6
    assert summary.sigma_ic > 0
    assert summary.power_days_80 > 0


def test_spearman_ic_perfect():
    score = pd.Series([1, 2, 3, 4, 5, 6])
    fwd = pd.Series([0.1, 0.2, 0.3, 0.4, 0.5, 0.6])
    assert abs(spearman_ic(score, fwd) - 1.0) < 1e-9
