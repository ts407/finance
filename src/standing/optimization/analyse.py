from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from standing.config import ScoringConfig, apply_overrides, load_scoring_config
from standing.optimization.paths import BASELINE_DIR, ensure_layout
from standing.pipeline.snapshot import StandingSnapshot, persist_snapshot, run_snapshot
from standing.providers import FixtureMarketProvider, FixtureSocialProvider


@dataclass(frozen=True)
class SensitivityResult:
    label: str
    change: dict[str, Any]
    spearman_final_vs_base: float
    ranking_turnover_vs_baseline: float
    sparse_share: float
    thin_share: float
    ok_share: float
    mean_abs_tilt: float
    tilt_vs_baseline_mae: float


def _badge_shares(standings: pd.DataFrame) -> dict[str, float]:
    counts = standings["social_badge"].value_counts(normalize=True)
    return {
        "sparse_share": float(counts.get("sparse", 0.0)),
        "thin_share": float(counts.get("thin", 0.0)),
        "ok_share": float(counts.get("ok", 0.0)),
    }


def _spearman(a: pd.Series, b: pd.Series) -> float:
    """Spearman rank correlation without requiring scipy."""
    aligned = pd.concat([a, b], axis=1).dropna()
    if len(aligned) < 2:
        return float("nan")
    ra = aligned.iloc[:, 0].rank(method="average")
    rb = aligned.iloc[:, 1].rank(method="average")
    return float(ra.corr(rb, method="pearson"))


def _ranking_turnover(baseline: pd.DataFrame, other: pd.DataFrame) -> float:
    """Fraction of names whose rank by final_standing changed (any delta)."""
    base_rank = baseline.set_index("ticker")["final_standing"].rank(ascending=False, method="average")
    other_rank = other.set_index("ticker")["final_standing"].rank(ascending=False, method="average")
    aligned = pd.concat([base_rank, other_rank], axis=1, keys=["base", "other"]).dropna()
    if aligned.empty:
        return float("nan")
    return float((aligned["base"] != aligned["other"]).mean())


def _with_overrides(cfg: ScoringConfig, overrides: dict[str, Any]) -> ScoringConfig:
    return ScoringConfig(raw=apply_overrides(cfg.raw, overrides), path=cfg.path)


def run_baseline_snapshot(
    *,
    as_of: date,
    cfg: ScoringConfig | None = None,
    history_days: int = 14,
) -> StandingSnapshot:
    cfg = cfg or load_scoring_config()
    return run_snapshot(
        as_of=as_of,
        market=FixtureMarketProvider(),
        social=FixtureSocialProvider(history_days=history_days),
        cfg=cfg,
    )


def diagnose_snapshot(snap: StandingSnapshot) -> dict[str, Any]:
    df = snap.standings
    badges = _badge_shares(df)
    return {
        "as_of": snap.as_of.isoformat(),
        "universe_id": snap.universe_id,
        "methodology_version": snap.methodology_version,
        "score_kind": snap.score_kind,
        "placeholder": snap.placeholder,
        "n_names": int(len(df)),
        "spearman_final_vs_composite": _spearman(df["final_standing"], df["composite_standing"]),
        "mean_abs_tilt": float(df["attention_tilt"].abs().mean()),
        "max_abs_tilt": float(df["attention_tilt"].abs().max()),
        "mean_confidence_c": float(df["confidence_c"].mean()),
        "mean_n": float(df["n"].mean()),
        **badges,
        "low_confidence_sectors": list(snap.meta.get("low_confidence_sectors", [])),
    }


def run_sensitivity(
    baseline: StandingSnapshot,
    *,
    cfg: ScoringConfig,
    history_days: int = 14,
    perturbations: list[tuple[str, dict[str, Any]]] | None = None,
) -> list[SensitivityResult]:
    """Re-score with isolated config perturbations on identical fixture inputs."""
    if perturbations is None:
        perturbations = [
            ("shrinkage.k=15", {"shrinkage.k": 15}),
            ("shrinkage.k=20", {"shrinkage.k": 20}),
            ("sparse_below=8", {"shrinkage.display_badges.sparse_below": 8}),
            ("tilt_max=8", {"social_tilt.tilt_max": 8}),
            ("tilt_max=6", {"social_tilt.tilt_max": 6}),
            ("beta=1.0", {"social_tilt.beta": 1.0}),
        ]

    results: list[SensitivityResult] = []
    base_df = baseline.standings
    for label, overrides in perturbations:
        alt_cfg = _with_overrides(cfg, overrides)
        alt = run_baseline_snapshot(as_of=baseline.as_of, cfg=alt_cfg, history_days=history_days)
        badges = _badge_shares(alt.standings)
        aligned = base_df.set_index("ticker")[["attention_tilt"]].join(
            alt.standings.set_index("ticker")[["attention_tilt"]],
            lsuffix="_base",
            rsuffix="_alt",
        )
        results.append(
            SensitivityResult(
                label=label,
                change=overrides,
                spearman_final_vs_base=_spearman(
                    alt.standings["final_standing"], alt.standings["composite_standing"]
                ),
                ranking_turnover_vs_baseline=_ranking_turnover(base_df, alt.standings),
                sparse_share=badges["sparse_share"],
                thin_share=badges["thin_share"],
                ok_share=badges["ok_share"],
                mean_abs_tilt=float(alt.standings["attention_tilt"].abs().mean()),
                tilt_vs_baseline_mae=float(
                    (aligned["attention_tilt_base"] - aligned["attention_tilt_alt"]).abs().mean()
                ),
            )
        )
    return results


def write_baseline_report(
    *,
    as_of: date,
    history_days: int = 14,
    out_dir: Path | None = None,
    cycle_id: str | None = None,
    fine_sensitivity: bool = False,
    track: str = "M",
) -> dict[str, Any]:
    """
    Run baseline + sensitivity diagnostics and persist under artifacts/optimization.
    Does not modify productive config/scoring.yaml.

    ``track`` selects the sensitivity grid: "M" (market levers) or "S" (Social levers).
    """
    from standing.optimization.cycle import default_perturbations, next_cycle_id

    ensure_layout()
    cfg = load_scoring_config()
    snap = run_baseline_snapshot(as_of=as_of, cfg=cfg, history_days=history_days)
    target = out_dir or BASELINE_DIR
    target.mkdir(parents=True, exist_ok=True)
    csv_path = persist_snapshot(snap, target)

    diagnosis = diagnose_snapshot(snap)
    sensitivity = run_sensitivity(
        snap,
        cfg=cfg,
        history_days=history_days,
        perturbations=default_perturbations(fine=fine_sensitivity, track=track),
    )
    cid = cycle_id or next_cycle_id(as_of)

    config_snapshot = {
        "path": str(cfg.path),
        "methodology_version": cfg.methodology_version,
        "score_kind": cfg.score_kind,
        "placeholder": cfg.placeholder,
        "base": cfg.base,
        "social_tilt": cfg.social_tilt,
        "shrinkage": cfg.shrinkage,
        "social_pipeline": cfg.social_pipeline,
    }

    report = {
        "phase": "loop-analyse-hypothese",
        "cycle_id": cid,
        "productive_config": config_snapshot,
        "baseline": diagnosis,
        "sensitivity": [asdict(row) for row in sensitivity],
        "snapshot_csv": str(csv_path),
        "notes": [
            "No forward-return performance log exists yet; this is a baseline/diagnose cycle.",
            "Social is a bounded tilt, not a fourth pillar weight.",
            "All scoring parameters remain placeholder=true (fixture calibration).",
        ],
    }

    report_path = target / f"baseline_report_{as_of.isoformat()}_{cid}.json"
    # Keep stable latest alias for tooling that expects the as_of filename
    latest_alias = target / f"baseline_report_{as_of.isoformat()}.json"
    # Store portable relative paths in the JSON payload
    from standing.config import ROOT as _ROOT

    def _rel(p: Path) -> str:
        try:
            return str(p.resolve().relative_to(_ROOT.resolve()))
        except ValueError:
            return str(p)

    if isinstance(config_snapshot.get("path"), str):
        try:
            config_snapshot["path"] = _rel(Path(config_snapshot["path"]))
        except Exception:
            config_snapshot["path"] = "config/scoring.yaml"

    report["snapshot_csv"] = _rel(csv_path)
    payload = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    report_path.write_text(payload, encoding="utf-8")
    latest_alias.write_text(payload, encoding="utf-8")

    config_yaml_path = target / f"config_snapshot_{as_of.isoformat()}.yaml"
    with config_yaml_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(cfg.raw, f, sort_keys=False, allow_unicode=True)

    report["report_path"] = _rel(report_path)
    report["config_snapshot_path"] = _rel(config_yaml_path)
    return report
