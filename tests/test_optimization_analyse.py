from __future__ import annotations

from datetime import date
from pathlib import Path

from standing.config import load_scoring_config
from standing.optimization.analyse import _with_overrides, diagnose_snapshot, run_baseline_snapshot
from standing.optimization.hypotheses import write_hypothesis, write_shadow_config
from standing.optimization.log import append_log, latest_entry, read_log
from standing.optimization.paths import ensure_layout


def test_ensure_layout_and_log(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("standing.optimization.paths.OPTIMIZATION_ROOT", tmp_path / "opt")
    monkeypatch.setattr("standing.optimization.paths.HYPOTHESES_DIR", tmp_path / "opt" / "hypotheses")
    monkeypatch.setattr("standing.optimization.paths.CONFIGS_DIR", tmp_path / "opt" / "configs")
    monkeypatch.setattr("standing.optimization.paths.BASELINE_DIR", tmp_path / "opt" / "baseline")
    monkeypatch.setattr("standing.optimization.paths.LOOP_LOG_PATH", tmp_path / "opt" / "loop_log.jsonl")
    monkeypatch.setattr("standing.optimization.log.LOOP_LOG_PATH", tmp_path / "opt" / "loop_log.jsonl")
    monkeypatch.setattr("standing.optimization.hypotheses.CONFIGS_DIR", tmp_path / "opt" / "configs")
    monkeypatch.setattr("standing.optimization.hypotheses.HYPOTHESES_DIR", tmp_path / "opt" / "hypotheses")

    root = ensure_layout()
    assert root.exists()
    assert latest_entry() is None
    append_log({"phase": "test", "decision": "ok"})
    assert latest_entry()["decision"] == "ok"
    assert len(read_log()) == 1


def test_with_overrides_nested_badge():
    cfg = load_scoring_config()
    alt = _with_overrides(cfg, {"shrinkage.display_badges.sparse_below": 8})
    assert alt.shrinkage["display_badges"]["sparse_below"] == 8
    assert cfg.shrinkage["display_badges"]["sparse_below"] == 5


def test_baseline_diagnose_runs():
    snap = run_baseline_snapshot(as_of=date(2026, 7, 22))
    report = diagnose_snapshot(snap)
    assert report["n_names"] > 0
    assert 0.0 <= report["sparse_share"] <= 1.0
    assert "spearman_final_vs_composite" in report


def test_write_hypothesis_isolated(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("standing.optimization.paths.OPTIMIZATION_ROOT", tmp_path / "opt")
    monkeypatch.setattr("standing.optimization.paths.HYPOTHESES_DIR", tmp_path / "opt" / "hypotheses")
    monkeypatch.setattr("standing.optimization.paths.CONFIGS_DIR", tmp_path / "opt" / "configs")
    monkeypatch.setattr("standing.optimization.paths.BASELINE_DIR", tmp_path / "opt" / "baseline")
    monkeypatch.setattr("standing.optimization.paths.LOOP_LOG_PATH", tmp_path / "opt" / "loop_log.jsonl")
    monkeypatch.setattr("standing.optimization.hypotheses.CONFIGS_DIR", tmp_path / "opt" / "configs")
    monkeypatch.setattr("standing.optimization.hypotheses.HYPOTHESES_DIR", tmp_path / "opt" / "hypotheses")

    hyp, cfg_path = write_hypothesis(
        hypothesis_id="H-TEST-01",
        basis="unit test",
        overrides={"shrinkage.k": 15},
        prediction={"metric": "mean_abs_tilt", "expected_direction": "decrease"},
        cycle_id="C-TEST",
    )
    assert hyp.exists()
    assert cfg_path.exists()
    productive = load_scoring_config()
    assert productive.shrinkage["k"] == 10
    shadow = write_shadow_config(hypothesis_id="H-TEST-02", overrides={"social_tilt.tilt_max": 8})
    assert shadow.exists()
    text = shadow.read_text()
    assert "tilt_max: 8" in text
