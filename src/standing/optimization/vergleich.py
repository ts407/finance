from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date as date_cls
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from standing.config import ROOT, ScoringConfig, load_scoring_config
from standing.domain.scoring.pipeline import ScoreInputs, score_cross_section
from standing.optimization.analyse import _ranking_turnover
from standing.optimization.paths import DECISIONS_DIR, HYPOTHESES_DIR, ensure_layout
from standing.optimization.shadow import load_hypothesis
from standing.providers import FixtureMarketProvider, FixtureSocialProvider
from standing.providers.base import FetchCursor
from standing.universe.builder import fetch_and_build


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        return str(path)


def _bootstrap_mean_ci(
    values: np.ndarray,
    *,
    n_boot: int = 2000,
    alpha: float = 0.05,
    seed: int = 42,
) -> dict[str, float]:
    rng = np.random.default_rng(seed)
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if len(values) == 0:
        return {"mean": float("nan"), "ci_low": float("nan"), "ci_high": float("nan"), "n": 0}
    means = np.empty(n_boot, dtype=float)
    n = len(values)
    for i in range(n_boot):
        sample = values[rng.integers(0, n, size=n)]
        means[i] = sample.mean()
    lo, hi = np.quantile(means, [alpha / 2, 1 - alpha / 2])
    return {
        "mean": float(values.mean()),
        "ci_low": float(lo),
        "ci_high": float(hi),
        "n": int(n),
    }


def _social_gap_sensitivity(
    *,
    as_of,
    prod_cfg: ScoringConfig,
    shadow_cfg: ScoringConfig,
) -> dict[str, float]:
    """Compare ranking turnover when social inputs are zeroed (data-gap stress)."""
    market = FixtureMarketProvider()
    social = FixtureSocialProvider(history_days=14)
    universe = fetch_and_build(market, as_of=as_of, cfg=prod_cfg)
    social_df, _ = social.fetch_since(FetchCursor(as_of=as_of))
    tickers = set(universe.members["ticker"])
    social_df = social_df[social_df["ticker"].isin(tickers)].copy()
    empty = social_df.iloc[0:0].copy()

    def _score(cfg: ScoringConfig, social_daily: pd.DataFrame) -> pd.DataFrame:
        return score_cross_section(
            ScoreInputs(
                market=universe.members,
                social_daily=social_daily,
                as_of=pd.Timestamp(as_of),
            ),
            cfg,
        )

    prod_full = _score(prod_cfg, social_df)
    prod_gap = _score(prod_cfg, empty)
    shadow_full = _score(shadow_cfg, social_df)
    shadow_gap = _score(shadow_cfg, empty)
    return {
        "productive_turnover_full_vs_gap": _ranking_turnover(prod_full, prod_gap),
        "shadow_turnover_full_vs_gap": _ranking_turnover(shadow_full, shadow_gap),
        "gap_turnover_delta_shadow_minus_prod": (
            _ranking_turnover(shadow_full, shadow_gap) - _ranking_turnover(prod_full, prod_gap)
        ),
    }


@dataclass(frozen=True)
class DecisionThresholds:
    """
    Gates for accept_candidate (quantitative) vs promote_to_productive (epistemic).

    Primary evidence is forward-return proxy lift (skill criteria), not composite
    alignment. Placeholder configs may accept as candidates but never auto-promote.
    """

    max_mean_ranking_turnover: float = 0.40
    require_tilt_decrease: bool = True
    require_forward_evidence: bool = True
    # Informational composite-alignment floor (not required for accept_candidate)
    min_spearman_lift: float = 0.02
    allow_promote_when_placeholder: bool = False


def decide_from_shadow(
    shadow_report: dict[str, Any],
    *,
    thresholds: DecisionThresholds | None = None,
    gap: dict[str, float] | None = None,
) -> dict[str, Any]:
    thresholds = thresholds or DecisionThresholds()
    agg = shadow_report["aggregates"]
    daily = pd.DataFrame(shadow_report["shadow_daily"])
    prod_daily = pd.DataFrame(shadow_report["productive_daily"])
    forward = shadow_report.get("forward") or {}

    spearman_lift = (
        float(agg["mean_spearman_final_vs_composite_shadow"])
        - float(agg["mean_spearman_final_vs_composite_productive"])
    )
    daily_lift = (
        daily["spearman_final_vs_composite"].to_numpy()
        - prod_daily["spearman_final_vs_composite"].to_numpy()
    )
    lift_ci = _bootstrap_mean_ci(daily_lift)
    turnover_ci = _bootstrap_mean_ci(daily["ranking_turnover_vs_productive"].to_numpy())
    tilt_delta = float(agg["mean_abs_tilt_shadow"]) - float(agg["mean_abs_tilt_productive"])

    # Track M (no Social change): tilt is unchanged — do not require tilt decrease.
    change = shadow_report.get("change") or []
    social_change = False
    for c in change:
        if isinstance(c, dict) and str(c.get("path", "")).startswith(
            ("social_tilt.", "shrinkage.", "social_pipeline.")
        ):
            social_change = True
            break
    require_tilt = thresholds.require_tilt_decrease and social_change

    fwd_spearman_lifts = np.asarray(
        forward.get("daily_forward_spearman_lift")
        or (
            [agg.get("mean_forward_spearman_lift", float("nan"))]
            if "mean_forward_spearman_lift" in agg
            else []
        ),
        dtype=float,
    )
    fwd_excess_lifts = np.asarray(
        forward.get("daily_top_decile_excess_lift")
        or (
            [agg.get("mean_top_decile_excess_lift", float("nan"))]
            if "mean_top_decile_excess_lift" in agg
            else []
        ),
        dtype=float,
    )
    fwd_spearman_ci = _bootstrap_mean_ci(fwd_spearman_lifts, seed=43)
    fwd_excess_ci = _bootstrap_mean_ci(fwd_excess_lifts, seed=44)
    forward_evidence = (fwd_spearman_ci["ci_low"] > 0) or (fwd_excess_ci["ci_low"] > 0)

    prod_cfg = load_scoring_config()
    checks = {
        "turnover_le_max": float(agg["mean_ranking_turnover_vs_productive"])
        <= thresholds.max_mean_ranking_turnover,
        "tilt_decreased": (tilt_delta < 0) if require_tilt else True,
        "forward_evidence": forward_evidence if thresholds.require_forward_evidence else True,
        "spearman_lift_ge_min": spearman_lift >= thresholds.min_spearman_lift,
        "lift_ci_excludes_zero": lift_ci["ci_low"] > 0,
        "track_m_social_unchanged": not social_change,
    }
    if gap is not None:
        checks["social_gap_not_worse"] = gap["shadow_turnover_full_vs_gap"] <= (
            gap["productive_turnover_full_vs_gap"] + 1e-9
        )

    candidate_keys = ["turnover_le_max", "tilt_decreased", "forward_evidence"]
    if gap is not None:
        candidate_keys.append("social_gap_not_worse")
    accept_candidate = all(checks[k] for k in candidate_keys)

    promote_ok = accept_candidate and (
        thresholds.allow_promote_when_placeholder or not prod_cfg.placeholder
    )
    checks["placeholder_allows_promote"] = not prod_cfg.placeholder or thresholds.allow_promote_when_placeholder
    checks["accept_candidate"] = accept_candidate

    if promote_ok:
        decision = "accept"
    elif accept_candidate:
        decision = "accept_candidate"
    else:
        decision = "reject"

    from standing.desk.ledger import summarize_diary_for_vergleich

    diary_summary = summarize_diary_for_vergleich()

    rationale_parts = []
    if accept_candidate and prod_cfg.placeholder:
        rationale_parts.append(
            "Quantitative gates passed as accept_candidate; productive promote blocked "
            "while placeholder=true."
        )
    elif prod_cfg.placeholder and not accept_candidate:
        rationale_parts.append(
            "Productive config remains placeholder=true — auto-promotion blocked by epistemic lock."
        )
    if not checks["turnover_le_max"]:
        rationale_parts.append(
            f"Ranking turnover {agg['mean_ranking_turnover_vs_productive']:.1%} "
            f"exceeds max {thresholds.max_mean_ranking_turnover:.0%}."
        )
    if thresholds.require_forward_evidence:
        rationale_parts.append(
            "Forward-return proxy (next-weekday fixture ret_1m): "
            f"spearman_lift={fwd_spearman_ci['mean']:+.4f} "
            f"CI[{fwd_spearman_ci['ci_low']:+.4f},{fwd_spearman_ci['ci_high']:+.4f}]; "
            f"top_decile_excess_lift={fwd_excess_ci['mean']:+.4f} "
            f"CI[{fwd_excess_ci['ci_low']:+.4f},{fwd_excess_ci['ci_high']:+.4f}]; "
            f"evidence={'yes' if forward_evidence else 'no'}."
        )
    rationale_parts.append(
        f"Composite-alignment spearman lift {spearman_lift:+.4f} is informational only "
        f"(threshold {thresholds.min_spearman_lift:.2f}, "
        f"{'met' if checks['spearman_lift_ge_min'] else 'not met'})."
    )
    if gap is not None:
        rationale_parts.append(
            "Social-gap turnover: "
            f"prod={gap['productive_turnover_full_vs_gap']:.1%}, "
            f"shadow={gap['shadow_turnover_full_vs_gap']:.1%}."
        )
    rationale_parts.append(
        "No trading-journal entries available; qualitative diary reference skipped."
        if diary_summary["n_entries"] == 0
        else (
            "Diary qualitative reference (not score-input): "
            f"n_entries={diary_summary['n_entries']} n_tickers={diary_summary['n_tickers']}"
            + (
                f" latest={diary_summary['latest_utc']}."
                if diary_summary.get("latest_utc")
                else "."
            )
        )
    )

    return {
        "decision": decision,
        "accepted": accept_candidate,
        "accept_candidate": accept_candidate,
        "checks": checks,
        "thresholds": {
            "max_mean_ranking_turnover": thresholds.max_mean_ranking_turnover,
            "require_tilt_decrease": thresholds.require_tilt_decrease,
            "require_forward_evidence": thresholds.require_forward_evidence,
            "min_spearman_lift": thresholds.min_spearman_lift,
            "allow_promote_when_placeholder": thresholds.allow_promote_when_placeholder,
        },
        "metrics": {
            "spearman_lift": spearman_lift,
            "spearman_lift_bootstrap": lift_ci,
            "ranking_turnover": float(agg["mean_ranking_turnover_vs_productive"]),
            "ranking_turnover_bootstrap": turnover_ci,
            "tilt_delta": tilt_delta,
            "forward_spearman_lift_bootstrap": fwd_spearman_ci,
            "top_decile_excess_lift_bootstrap": fwd_excess_ci,
            "forward": forward,
            "social_gap": gap,
        },
        "rationale": " ".join(rationale_parts),
        "promote_to_productive": bool(promote_ok),
        "diary_qualitative": diary_summary,
    }


def run_vergleich(
    *,
    hypothesis_id: str,
    shadow_report_path: Path | None = None,
) -> dict[str, Any]:
    ensure_layout()
    hyp = load_hypothesis(hypothesis_id)
    report_path = shadow_report_path
    if report_path is None:
        if not hyp.get("shadow_report"):
            raise FileNotFoundError(f"No shadow_report on hypothesis {hypothesis_id}")
        report_path = Path(hyp["shadow_report"])
        if not report_path.is_absolute():
            report_path = ROOT / report_path
    shadow_report = json.loads(report_path.read_text(encoding="utf-8"))

    shadow_cfg_path = Path(hyp["shadow_config"])
    if not shadow_cfg_path.is_absolute():
        shadow_cfg_path = ROOT / shadow_cfg_path
    prod_cfg = load_scoring_config()
    shadow_cfg = load_scoring_config(shadow_cfg_path)

    end = shadow_report["window"]["end"]
    end_as_of = date_cls.fromisoformat(end)
    gap = _social_gap_sensitivity(as_of=end_as_of, prod_cfg=prod_cfg, shadow_cfg=shadow_cfg)
    verdict = decide_from_shadow(shadow_report, gap=gap)

    out = {
        "phase": "loop-vergleich-entscheidung",
        "hypothesis_id": hypothesis_id,
        "cycle_id": hyp.get("cycle_id") or shadow_report.get("cycle_id"),
        "shadow_report": _rel(report_path),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        **verdict,
        "next_phase": "loop-analyse-hypothese",
        "productive_config_unchanged": not verdict["promote_to_productive"],
    }

    out_dir = DECISIONS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    decision_path = out_dir / f"{hypothesis_id}_decision.json"
    decision_path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    out["decision_path"] = _rel(decision_path)

    hyp["status"] = f"decision_{verdict['decision']}"
    hyp["decision_path"] = out["decision_path"]
    hyp["handoff"] = "loop-analyse-hypothese"
    hyp_path = HYPOTHESES_DIR / f"{hypothesis_id}.yaml"
    with hyp_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(hyp, f, sort_keys=False, allow_unicode=True)

    decision_path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out
