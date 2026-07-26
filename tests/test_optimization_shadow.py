from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
import yaml

from standing.config import load_scoring_config
from standing.optimization.hypotheses import write_hypothesis
from standing.optimization.shadow import run_shadow_test, trading_days_ending


def test_trading_days_ending_skips_weekend():
    # 2026-07-22 is Wednesday
    days = trading_days_ending(date(2026, 7, 22), 5)
    assert len(days) == 5
    assert days[-1] == date(2026, 7, 22)
    assert all(d.weekday() < 5 for d in days)


def test_run_shadow_test(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("standing.optimization.paths.OPTIMIZATION_ROOT", tmp_path / "opt")
    monkeypatch.setattr("standing.optimization.paths.HYPOTHESES_DIR", tmp_path / "opt" / "hypotheses")
    monkeypatch.setattr("standing.optimization.paths.CONFIGS_DIR", tmp_path / "opt" / "configs")
    monkeypatch.setattr("standing.optimization.paths.BASELINE_DIR", tmp_path / "opt" / "baseline")
    monkeypatch.setattr("standing.optimization.paths.SHADOW_DIR", tmp_path / "opt" / "shadow")
    monkeypatch.setattr("standing.optimization.paths.LOOP_LOG_PATH", tmp_path / "opt" / "loop_log.jsonl")
    monkeypatch.setattr("standing.optimization.hypotheses.CONFIGS_DIR", tmp_path / "opt" / "configs")
    monkeypatch.setattr("standing.optimization.hypotheses.HYPOTHESES_DIR", tmp_path / "opt" / "hypotheses")
    monkeypatch.setattr("standing.optimization.shadow.HYPOTHESES_DIR", tmp_path / "opt" / "hypotheses")
    monkeypatch.setattr("standing.optimization.shadow.SHADOW_DIR", tmp_path / "opt" / "shadow")

    hyp_path, _cfg = write_hypothesis(
        hypothesis_id="H-SHADOW-01",
        basis="unit test",
        overrides={"social_tilt.tilt_max": 8},
        prediction={"metric": "mean_abs_tilt", "expected_direction": "decrease"},
        cycle_id="C-TEST",
    )
    # rewrite shadow_config to absolute so loader finds it under tmp
    data = yaml.safe_load(hyp_path.read_text())
    data["shadow_config"] = str(tmp_path / "opt" / "configs" / Path(data["shadow_config"]).name)
    # find actual config file
    cfg_files = list((tmp_path / "opt" / "configs").glob("H-SHADOW-01_*.yaml"))
    assert cfg_files
    data["shadow_config"] = str(cfg_files[0])
    hyp_path.write_text(yaml.safe_dump(data, sort_keys=False))

    summary = run_shadow_test(
        hypothesis_id="H-SHADOW-01",
        end_as_of=date(2026, 7, 22),
        n_days=3,
    )
    assert summary["status"] == "shadow_complete"
    assert summary["window"]["n_trading_days"] == 3
    assert summary["aggregates"]["mean_abs_tilt_shadow"] < summary["aggregates"]["mean_abs_tilt_productive"]
    assert Path(summary["report_path"]).exists() or (tmp_path / "opt" / "shadow" / "H-SHADOW-01").exists()
    updated = yaml.safe_load(hyp_path.read_text())
    assert updated["status"] == "shadow_complete"
    assert updated["handoff"] == "loop-vergleich-entscheidung"
    # productive untouched
    assert load_scoring_config().social_tilt["tilt_max"] == 10


def test_deferred_rejected(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("standing.optimization.paths.HYPOTHESES_DIR", tmp_path / "hyp")
    monkeypatch.setattr("standing.optimization.shadow.HYPOTHESES_DIR", tmp_path / "hyp")
    monkeypatch.setattr("standing.optimization.shadow.SHADOW_DIR", tmp_path / "shadow")
    (tmp_path / "hyp").mkdir(parents=True)
    (tmp_path / "hyp" / "H-DEF.yaml").write_text(
        yaml.safe_dump({"id": "H-DEF", "status": "deferred", "shadow_config": "x.yaml"})
    )
    with pytest.raises(ValueError, match="deferred"):
        run_shadow_test(hypothesis_id="H-DEF", end_as_of=date(2026, 7, 22), n_days=2)
