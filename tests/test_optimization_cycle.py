from __future__ import annotations

from datetime import date
from pathlib import Path

from standing.optimization.cycle import formulate_hypotheses, is_social_override


def test_social_override_detection():
    assert is_social_override({"social_tilt.tilt_max": 8})
    assert is_social_override({"shrinkage.k": 15})
    assert not is_social_override({"base.winsorize.lower": 0.02})


def test_formulate_track_m_skips_social(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("standing.optimization.paths.HYPOTHESES_DIR", tmp_path / "hyp")
    (tmp_path / "hyp").mkdir()
    log = tmp_path / "loop_log.jsonl"
    log.write_text("")
    monkeypatch.setattr("standing.optimization.log.LOOP_LOG_PATH", log)

    baseline = {
        "spearman_final_vs_composite": 0.92,
        "mean_abs_tilt": 5.7,
        "mean_n": 1200.0,
    }
    sensitivity = [
        {
            "label": "tilt_max=9",
            "change": {"social_tilt.tilt_max": 9},
            "ranking_turnover_vs_baseline": 0.1,
            "spearman_final_vs_base": 0.93,
            "mean_abs_tilt": 5.0,
            "tilt_vs_baseline_mae": 0.5,
        },
        {
            "label": "winsorize_tighter",
            "change": {"base.winsorize.lower": 0.02, "base.winsorize.upper": 0.98},
            "ranking_turnover_vs_baseline": 0.12,
            "spearman_final_vs_base": 0.921,
            "mean_abs_tilt": 5.7,
            "tilt_vs_baseline_mae": 0.0,
        },
        {
            "label": "momentum_weight_up",
            "change": {
                "base.pillar_weights.value": 0.30,
                "base.pillar_weights.quality": 0.30,
                "base.pillar_weights.momentum": 0.40,
            },
            "ranking_turnover_vs_baseline": 0.15,
            "spearman_final_vs_base": 0.91,
            "mean_abs_tilt": 5.7,
            "tilt_vs_baseline_mae": 0.0,
        },
    ]
    ready, deferred = formulate_hypotheses(
        cycle_id="C20260722-04",
        as_of=date(2026, 7, 22),
        baseline=baseline,
        sensitivity=sensitivity,
        track="M",
    )
    # Track M stays market-only and no longer force-defers Social.
    assert all(not is_social_override(h["overrides"]) for h in ready)
    assert ready[0]["overrides"] != {"social_tilt.tilt_max": 9}
    assert deferred == []


def test_formulate_track_s_unlocked_formulates_social(tmp_path: Path, monkeypatch):
    """Track S is unlocked: it formulates Social levers and defers nothing."""
    monkeypatch.setattr("standing.optimization.paths.HYPOTHESES_DIR", tmp_path / "hyp")
    (tmp_path / "hyp").mkdir()
    log = tmp_path / "loop_log.jsonl"
    log.write_text("")
    monkeypatch.setattr("standing.optimization.log.LOOP_LOG_PATH", log)

    sensitivity = [
        {
            "label": "sentiment_weight_up",
            "change": {"social_tilt.sentiment_weight": 0.75},
            "ranking_turnover_vs_baseline": 0.08,
            "spearman_final_vs_base": 0.905,
            "mean_abs_tilt": 3.1,
            "tilt_vs_baseline_mae": 0.4,
        },
        {
            "label": "winsorize_tighter",  # market lever — must be skipped on Track S
            "change": {"base.winsorize.lower": 0.02, "base.winsorize.upper": 0.98},
            "ranking_turnover_vs_baseline": 0.02,
            "spearman_final_vs_base": 0.90,
            "mean_abs_tilt": 3.0,
            "tilt_vs_baseline_mae": 0.0,
        },
    ]
    ready, deferred = formulate_hypotheses(
        cycle_id="C-TEST",
        as_of=date(2026, 7, 22),
        baseline={"spearman_final_vs_composite": 0.9, "mean_abs_tilt": 3.0, "mean_n": 10},
        sensitivity=sensitivity,
        track="S",
    )
    assert ready, "Track S should now formulate Social hypotheses"
    assert all(is_social_override(h["overrides"]) for h in ready)
    assert all(h["prediction"]["track"] == "S" for h in ready)
    assert deferred == []
