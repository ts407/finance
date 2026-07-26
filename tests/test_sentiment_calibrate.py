"""Track S sentiment calibration apparatus + flag gate."""

from __future__ import annotations

from datetime import date

from standing.config import load_scoring_config
from standing.research.sentiment_calibrate import (
    apparatus_self_test,
    build_sentiment_panel,
    run_sentiment_calibration,
)


def test_apparatus_self_test_recovers_injected_signal():
    # The IC chain must detect a signal it was explicitly given.
    cal = apparatus_self_test()
    assert cal.passed
    assert cal.mean_ic > 0.0
    assert cal.n_ic_obs >= 12


def test_sentiment_panel_has_expected_columns():
    cfg = load_scoring_config()
    days = [date(2026, 7, 22), date(2026, 7, 23)]
    panel = build_sentiment_panel(days=days, cfg=cfg)
    assert not panel.empty
    assert set(["as_of", "ticker", "sentiment", "forward_ret"]).issubset(panel.columns)


def test_calibration_gate_blocks_flag_on_fixture(tmp_path):
    # Fixture social carries no real forward signal → real calibration must not pass,
    # so the flag flip stays blocked even though the apparatus self-test passes.
    report = run_sentiment_calibration(out_dir=tmp_path)
    assert report["apparatus_self_test"]["passed"] is True
    assert report["real_calibration"]["passed"] is False
    assert report["recommend_sentiment_calibrated"] is False
