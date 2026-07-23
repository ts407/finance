from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import yaml

from standing.config import load_scoring_config
from standing.optimization.hypotheses import write_hypothesis
from standing.optimization.shadow import run_shadow_test
from standing.optimization.vergleich import decide_from_shadow, run_vergleich


def _patch_opt_dirs(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "opt"
    mapping = {
        "OPTIMIZATION_ROOT": root,
        "HYPOTHESES_DIR": root / "hypotheses",
        "CONFIGS_DIR": root / "configs",
        "BASELINE_DIR": root / "baseline",
        "SHADOW_DIR": root / "shadow",
        "DECISIONS_DIR": root / "decisions",
        "LOOP_LOG_PATH": root / "loop_log.jsonl",
    }
    for mod in (
        "standing.optimization.paths",
        "standing.optimization.hypotheses",
        "standing.optimization.shadow",
        "standing.optimization.vergleich",
    ):
        for key, value in mapping.items():
            monkeypatch.setattr(f"{mod}.{key}", value, raising=False)


def test_decide_rejects_high_turnover():
    report = {
        "aggregates": {
            "mean_spearman_final_vs_composite_shadow": 0.95,
            "mean_spearman_final_vs_composite_productive": 0.90,
            "mean_ranking_turnover_vs_productive": 0.63,
            "mean_abs_tilt_shadow": 4.0,
            "mean_abs_tilt_productive": 5.0,
        },
        "shadow_daily": [
            {"spearman_final_vs_composite": 0.95, "ranking_turnover_vs_productive": 0.6},
            {"spearman_final_vs_composite": 0.94, "ranking_turnover_vs_productive": 0.65},
        ],
        "productive_daily": [
            {"spearman_final_vs_composite": 0.90},
            {"spearman_final_vs_composite": 0.89},
        ],
    }
    out = decide_from_shadow(report, gap={"productive_turnover_full_vs_gap": 0.5, "shadow_turnover_full_vs_gap": 0.4, "gap_turnover_delta_shadow_minus_prod": -0.1})
    assert out["decision"] == "reject"
    assert out["promote_to_productive"] is False
    assert out["checks"]["turnover_le_max"] is False


def test_run_vergleich_end_to_end(tmp_path: Path, monkeypatch):
    _patch_opt_dirs(monkeypatch, tmp_path)
    hyp_path, _ = write_hypothesis(
        hypothesis_id="H-CMP-01",
        basis="unit",
        overrides={"social_tilt.tilt_max": 8},
        prediction={"metric": "spearman_final_vs_composite", "expected_direction": "increase"},
        cycle_id="C-TEST",
    )
    data = yaml.safe_load(hyp_path.read_text())
    cfg_files = list((tmp_path / "opt" / "configs").glob("H-CMP-01_*.yaml"))
    data["shadow_config"] = str(cfg_files[0])
    hyp_path.write_text(yaml.safe_dump(data, sort_keys=False))

    run_shadow_test(hypothesis_id="H-CMP-01", end_as_of=date(2026, 7, 22), n_days=3)
    out = run_vergleich(hypothesis_id="H-CMP-01")
    assert out["decision"] in {"accept", "reject"}
    assert out["promote_to_productive"] is False
    assert Path(tmp_path / "opt" / "decisions" / "H-CMP-01_decision.json").exists()
    assert load_scoring_config().social_tilt["tilt_max"] == 10
    updated = yaml.safe_load(hyp_path.read_text())
    assert updated["status"].startswith("decision_")
