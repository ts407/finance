from __future__ import annotations

from datetime import date
from typing import Any

from standing.optimization.analyse import SensitivityResult
from standing.optimization.log import read_log


def next_cycle_id(as_of: date) -> str:
    """Allocate CYYYYMMDD-NN from existing log cycle_ids for this as_of day."""
    stamp = as_of.isoformat().replace("-", "")
    prefix = f"C{stamp}-"
    seen: set[int] = set()
    for row in read_log():
        cid = str(row.get("cycle_id") or "")
        if cid.startswith(prefix):
            try:
                seen.add(int(cid.split("-")[-1]))
            except ValueError:
                continue
    n = (max(seen) + 1) if seen else 1
    return f"{prefix}{n:02d}"


def prior_reject_summary() -> list[dict[str, Any]]:
    return [
        row
        for row in read_log()
        if row.get("phase") == "loop-vergleich-entscheidung" and row.get("decision") == "reject"
    ]


def default_perturbations(*, fine: bool = False) -> list[tuple[str, dict[str, Any]]]:
    coarse = [
        ("shrinkage.k=15", {"shrinkage.k": 15}),
        ("shrinkage.k=20", {"shrinkage.k": 20}),
        ("sparse_below=8", {"shrinkage.display_badges.sparse_below": 8}),
        ("tilt_max=8", {"social_tilt.tilt_max": 8}),
        ("tilt_max=6", {"social_tilt.tilt_max": 6}),
        ("beta=1.0", {"social_tilt.beta": 1.0}),
    ]
    if not fine:
        return coarse
    return coarse + [
        ("tilt_max=9.5", {"social_tilt.tilt_max": 9.5}),
        ("tilt_max=9", {"social_tilt.tilt_max": 9}),
        ("tilt_max=8.5", {"social_tilt.tilt_max": 8.5}),
        ("beta=1.4", {"social_tilt.beta": 1.4}),
        ("beta=1.3", {"social_tilt.beta": 1.3}),
        ("beta=1.2", {"social_tilt.beta": 1.2}),
        ("dampener=0.40", {"social_tilt.dampener_neg_share_pivot": 0.40}),
        ("source_cap=0.40", {"social_pipeline.source_cap_per_ticker_day": 0.40}),
    ]


def formulate_hypotheses(
    *,
    cycle_id: str,
    as_of: date,
    baseline: dict[str, Any],
    sensitivity: list[SensitivityResult] | list[dict[str, Any]],
    max_turnover_gate: float = 0.40,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Build shadow-ready + deferred hypothesis specs from baseline + sensitivity.

    Cycle ≥2 learns from prior rejects: prefer finer levers with offline turnover
    strictly below the vergleich ranking-turnover gate.
    """
    from standing.optimization.paths import HYPOTHESES_DIR

    rows: list[dict[str, Any]] = []
    for item in sensitivity:
        if isinstance(item, SensitivityResult):
            rows.append(
                {
                    "label": item.label,
                    "change": item.change,
                    "ranking_turnover_vs_baseline": item.ranking_turnover_vs_baseline,
                    "spearman_final_vs_base": item.spearman_final_vs_base,
                    "mean_abs_tilt": item.mean_abs_tilt,
                    "tilt_vs_baseline_mae": item.tilt_vs_baseline_mae,
                }
            )
        else:
            rows.append(item)

    existing_ids: set[str] = set()
    if HYPOTHESES_DIR.exists():
        for path in HYPOTHESES_DIR.glob("H*.yaml"):
            existing_ids.add(path.stem)
    for row in read_log():
        hid = row.get("hypothesis_id")
        if hid:
            existing_ids.add(str(hid))
        for hid in row.get("hypotheses") or []:
            existing_ids.add(str(hid))
        for hid in row.get("deferred_hypotheses") or []:
            existing_ids.add(str(hid))

    base_spearman = float(baseline["spearman_final_vs_composite"])
    base_tilt = float(baseline["mean_abs_tilt"])

    # Offline selection uses a safety margin: multi-day shadow turnover tends to
    # run ~20% higher than single-day sensitivity on fixtures.
    offline_gate = max_turnover_gate * 0.75
    gated = [
        r
        for r in rows
        if r["ranking_turnover_vs_baseline"] <= offline_gate
        and r["spearman_final_vs_base"] > base_spearman
        and r["mean_abs_tilt"] < base_tilt
        and r["ranking_turnover_vs_baseline"] > 0.05
    ]
    # Prefer higher spearman lift, then lower turnover
    gated.sort(
        key=lambda r: (
            -(r["spearman_final_vs_base"] - base_spearman),
            r["ranking_turnover_vs_baseline"],
        )
    )

    day = as_of.isoformat().replace("-", "")

    def alloc_id(seq_start: int = 1) -> tuple[str, int]:
        seq = seq_start
        while True:
            hid = f"H{day}-{seq:02d}"
            if hid not in existing_ids:
                existing_ids.add(hid)
                return hid, seq + 1
            seq += 1

    seq = 1
    ready: list[dict[str, Any]] = []
    used_paths: set[str] = set()

    for prefer_prefix in ("tilt_max=", "beta="):
        for r in gated:
            if not r["label"].startswith(prefer_prefix):
                continue
            path = next(iter(r["change"]))
            if path in used_paths:
                continue
            hid, seq = alloc_id(seq)
            lift = r["spearman_final_vs_base"] - base_spearman
            ready.append(
                {
                    "hypothesis_id": hid,
                    "basis": (
                        f"Cycle {cycle_id}: prior rejects failed turnover>{max_turnover_gate:.0%} "
                        f"(aggressive tilt_max/beta cuts). Offline {r['label']} stays under "
                        f"safety gate {offline_gate:.0%} "
                        f"(turnover={r['ranking_turnover_vs_baseline']:.1%}) with spearman lift "
                        f"{lift:+.4f} and lower mean|tilt| ({base_tilt:.2f}→{r['mean_abs_tilt']:.2f})."
                    ),
                    "overrides": dict(r["change"]),
                    "prediction": {
                        "metric": "ranking_turnover_vs_baseline",
                        "expected_direction": f"below_{max_turnover_gate:.0%}_gate",
                        "secondary_metric": "spearman_final_vs_composite",
                        "expected_secondary": "increase",
                        "rationale": (
                            f"{r['label']} selected as conservative step after prior overshoot."
                        ),
                    },
                }
            )
            used_paths.add(path)
            break

    if not ready:
        improvers = [
            r
            for r in rows
            if r["spearman_final_vs_base"] > base_spearman and r["mean_abs_tilt"] < base_tilt
        ]
        improvers.sort(key=lambda r: r["ranking_turnover_vs_baseline"])
        for r in improvers[:2]:
            hid, seq = alloc_id(seq)
            ready.append(
                {
                    "hypothesis_id": hid,
                    "basis": (
                        f"Cycle {cycle_id}: fallback candidate {r['label']} "
                        f"(turnover={r['ranking_turnover_vs_baseline']:.1%})."
                    ),
                    "overrides": dict(r["change"]),
                    "prediction": {
                        "metric": "ranking_turnover_vs_baseline",
                        "expected_direction": "minimize",
                        "secondary_metric": "spearman_final_vs_composite",
                        "expected_secondary": "increase",
                        "rationale": r["label"],
                    },
                }
            )

    deferred = [
        {
            "hypothesis_id": "H20260722-01",
            "reason": (
                "shrinkage.k increases remain deferred on fixture mean_n≫k "
                f"(mean_n={float(baseline.get('mean_n', float('nan'))):.0f}); "
                "revisit with sparse live Social."
            ),
            "overrides": {"shrinkage.k": 15},
        }
    ]
    return ready, deferred


def latest_ready_hypothesis_ids() -> list[str]:
    """Return hypothesis IDs from the most recent analyse log entry."""
    for row in reversed(read_log()):
        if row.get("phase") == "loop-analyse-hypothese" and row.get("hypotheses"):
            return list(row["hypotheses"])
    return []
