from __future__ import annotations

from datetime import date
from pathlib import Path

from standing.optimization.cycle import formulate_hypotheses, next_cycle_id


def test_next_cycle_id(tmp_path: Path, monkeypatch):
    log = tmp_path / "loop_log.jsonl"
    log.write_text(
        '{"cycle_id":"C20260722-01","phase":"x"}\n'
        '{"cycle_id":"C20260722-01","phase":"y"}\n'
    )
    monkeypatch.setattr("standing.optimization.log.LOOP_LOG_PATH", log)
    assert next_cycle_id(date(2026, 7, 22)) == "C20260722-02"


def test_formulate_prefers_gated_fine_steps(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("standing.optimization.paths.HYPOTHESES_DIR", tmp_path / "hyp")
    (tmp_path / "hyp").mkdir()
    (tmp_path / "hyp" / "H20260722-03.yaml").write_text("id: H20260722-03\n")
    (tmp_path / "hyp" / "H20260722-04.yaml").write_text("id: H20260722-04\n")
    log = tmp_path / "loop_log.jsonl"
    log.write_text(
        '{"phase":"loop-vergleich-entscheidung","decision":"reject","hypothesis_id":"H20260722-03"}\n'
    )
    monkeypatch.setattr("standing.optimization.log.LOOP_LOG_PATH", log)

    baseline = {
        "spearman_final_vs_composite": 0.92,
        "mean_abs_tilt": 5.7,
        "mean_n": 1200.0,
    }
    sensitivity = [
        {
            "label": "tilt_max=8",
            "change": {"social_tilt.tilt_max": 8},
            "ranking_turnover_vs_baseline": 0.52,
            "spearman_final_vs_base": 0.95,
            "mean_abs_tilt": 4.5,
            "tilt_vs_baseline_mae": 1.0,
        },
        {
            "label": "tilt_max=8.5",
            "change": {"social_tilt.tilt_max": 8.5},
            "ranking_turnover_vs_baseline": 0.39,
            "spearman_final_vs_base": 0.941,
            "mean_abs_tilt": 4.87,
            "tilt_vs_baseline_mae": 0.8,
        },
        {
            "label": "tilt_max=9",
            "change": {"social_tilt.tilt_max": 9},
            "ranking_turnover_vs_baseline": 0.28,
            "spearman_final_vs_base": 0.936,
            "mean_abs_tilt": 5.16,
            "tilt_vs_baseline_mae": 0.5,
        },
        {
            "label": "beta=1.3",
            "change": {"social_tilt.beta": 1.3},
            "ranking_turnover_vs_baseline": 0.26,
            "spearman_final_vs_base": 0.933,
            "mean_abs_tilt": 5.25,
            "tilt_vs_baseline_mae": 0.4,
        },
    ]
    ready, deferred = formulate_hypotheses(
        cycle_id="C20260722-02",
        as_of=date(2026, 7, 22),
        baseline=baseline,
        sensitivity=sensitivity,
    )
    assert len(ready) == 2
    assert ready[0]["overrides"] == {"social_tilt.tilt_max": 9}
    assert ready[1]["overrides"] == {"social_tilt.beta": 1.3}
    assert ready[0]["hypothesis_id"] not in {"H20260722-03", "H20260722-04"}
    assert deferred[0]["hypothesis_id"] == "H20260722-01"
