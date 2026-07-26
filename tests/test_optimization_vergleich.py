from __future__ import annotations

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
            "mean_forward_spearman_lift": 0.05,
            "mean_top_decile_excess_lift": 0.01,
        },
        "shadow_daily": [
            {"spearman_final_vs_composite": 0.95, "ranking_turnover_vs_productive": 0.6},
            {"spearman_final_vs_composite": 0.94, "ranking_turnover_vs_productive": 0.65},
        ],
        "productive_daily": [
            {"spearman_final_vs_composite": 0.90},
            {"spearman_final_vs_composite": 0.89},
        ],
        "forward": {
            "daily_forward_spearman_lift": [0.05, 0.04],
            "daily_top_decile_excess_lift": [0.01, 0.02],
        },
    }
    out = decide_from_shadow(
        report,
        gap={
            "productive_turnover_full_vs_gap": 0.5,
            "shadow_turnover_full_vs_gap": 0.4,
            "gap_turnover_delta_shadow_minus_prod": -0.1,
        },
    )
    assert out["decision"] == "reject"
    assert out["accept_candidate"] is False
    assert out["promote_to_productive"] is False
    assert out["checks"]["turnover_le_max"] is False


def test_decide_accept_candidate_without_promote():
    report = {
        "aggregates": {
            "mean_spearman_final_vs_composite_shadow": 0.93,
            "mean_spearman_final_vs_composite_productive": 0.91,
            "mean_ranking_turnover_vs_productive": 0.25,
            "mean_abs_tilt_shadow": 5.0,
            "mean_abs_tilt_productive": 5.7,
        },
        "shadow_daily": [
            {"spearman_final_vs_composite": 0.93, "ranking_turnover_vs_productive": 0.2},
            {"spearman_final_vs_composite": 0.94, "ranking_turnover_vs_productive": 0.3},
            {"spearman_final_vs_composite": 0.92, "ranking_turnover_vs_productive": 0.25},
        ],
        "productive_daily": [
            {"spearman_final_vs_composite": 0.91},
            {"spearman_final_vs_composite": 0.90},
            {"spearman_final_vs_composite": 0.91},
        ],
        "forward": {
            "daily_forward_spearman_lift": [0.08, 0.06, 0.07],
            "daily_top_decile_excess_lift": [0.01, 0.02, 0.015],
        },
    }
    out = decide_from_shadow(
        report,
        gap={
            "productive_turnover_full_vs_gap": 0.5,
            "shadow_turnover_full_vs_gap": 0.4,
            "gap_turnover_delta_shadow_minus_prod": -0.1,
        },
    )
    assert out["accept_candidate"] is True
    assert out["decision"] == "accept_candidate"
    assert out["promote_to_productive"] is False


def test_run_vergleich_end_to_end(tmp_path: Path, monkeypatch):
    _patch_opt_dirs(monkeypatch, tmp_path)
    hyp_path, _ = write_hypothesis(
        hypothesis_id="H-CMP-01",
        basis="unit",
        overrides={"social_tilt.tilt_max": 3},
        prediction={"metric": "spearman_final_vs_composite", "expected_direction": "increase"},
        cycle_id="C-TEST",
    )
    data = yaml.safe_load(hyp_path.read_text())
    cfg_files = list((tmp_path / "opt" / "configs").glob("H-CMP-01_*.yaml"))
    data["shadow_config"] = str(cfg_files[0])
    hyp_path.write_text(yaml.safe_dump(data, sort_keys=False))

    run_shadow_test(hypothesis_id="H-CMP-01", end_as_of=date(2026, 7, 22), n_days=3)
    out = run_vergleich(hypothesis_id="H-CMP-01")
    assert out["decision"] in {"accept", "accept_candidate", "reject"}
    assert out["promote_to_productive"] is False
    assert "forward_spearman_lift_bootstrap" in out["metrics"]
    assert Path(tmp_path / "opt" / "decisions" / "H-CMP-01_decision.json").exists()
    assert load_scoring_config().social_tilt["tilt_max"] == 5
    updated = yaml.safe_load(hyp_path.read_text())
    assert updated["status"].startswith("decision_")
