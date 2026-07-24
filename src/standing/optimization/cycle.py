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


SOCIAL_PATH_PREFIXES = (
    "social_tilt.",
    "shrinkage.",
    "social_pipeline.",
)

TRACK_M_PERTURBATIONS = [
    ("winsorize_tighter", {"base.winsorize.lower": 0.02, "base.winsorize.upper": 0.98}),
    ("winsorize_looser", {"base.winsorize.lower": 0.005, "base.winsorize.upper": 0.995}),
    ("momentum_weight_up", {"base.pillar_weights.value": 0.30, "base.pillar_weights.quality": 0.30, "base.pillar_weights.momentum": 0.40}),
    ("value_weight_up", {"base.pillar_weights.value": 0.40, "base.pillar_weights.quality": 0.30, "base.pillar_weights.momentum": 0.30}),
    ("quality_weight_up", {"base.pillar_weights.value": 0.30, "base.pillar_weights.quality": 0.40, "base.pillar_weights.momentum": 0.30}),
    ("min_cap_2e9", {"universe.min_market_cap_usd": 2.0e9}),
    ("min_adv_1e7", {"universe.min_adv_usd_20d": 1.0e7}),
]


def is_social_override(overrides: dict[str, Any]) -> bool:
    return any(
        any(path.startswith(prefix) for prefix in SOCIAL_PATH_PREFIXES)
        for path in overrides
    )


def default_perturbations(*, fine: bool = False, track: str = "M") -> list[tuple[str, dict[str, Any]]]:
    """
    Sensitivity grid for the active track.

    Track S (Social) returns an empty grid — Social hypotheses are locked.
    Track M uses V/Q/M / universe / winsorize levers only.
    """
    if track.upper() == "S":
        return []
    return list(TRACK_M_PERTURBATIONS)


def formulate_hypotheses(
    *,
    cycle_id: str,
    as_of: date,
    baseline: dict[str, Any],
    sensitivity: list[SensitivityResult] | list[dict[str, Any]],
    max_turnover_gate: float = 0.40,
    track: str = "M",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Build shadow-ready + deferred hypothesis specs from baseline + sensitivity.

    Track M only: Social overrides are rejected. Prefer market levers under the
    offline turnover safety margin.
    """
    from standing.optimization.paths import HYPOTHESES_DIR

    if track.upper() == "S":
        return [], [
            {
                "hypothesis_id": "H-SOCIAL-LOCKED",
                "reason": (
                    "Track S locked: no Social score hypotheses until live density "
                    "feasibility (n distribution / sparse_share) exists."
                ),
                "overrides": {},
            }
        ]

    rows: list[dict[str, Any]] = []
    for item in sensitivity:
        if isinstance(item, SensitivityResult):
            change = item.change
            if is_social_override(change):
                continue
            rows.append(
                {
                    "label": item.label,
                    "change": change,
                    "ranking_turnover_vs_baseline": item.ranking_turnover_vs_baseline,
                    "spearman_final_vs_base": item.spearman_final_vs_base,
                    "mean_abs_tilt": item.mean_abs_tilt,
                    "tilt_vs_baseline_mae": item.tilt_vs_baseline_mae,
                }
            )
        else:
            if is_social_override(item.get("change") or {}):
                continue
            rows.append(item)

    existing_ids: set[str] = set()
    tested_overrides: set[tuple[str, str]] = set()
    if HYPOTHESES_DIR.exists():
        import yaml

        for path in HYPOTHESES_DIR.glob("H*.yaml"):
            existing_ids.add(path.stem)
            try:
                data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            except Exception:
                continue
            for change in data.get("change") or []:
                if isinstance(change, dict) and "path" in change:
                    tested_overrides.add((str(change["path"]), repr(change.get("to"))))
    for row in read_log():
        hid = row.get("hypothesis_id")
        if hid:
            existing_ids.add(str(hid))
        for hid in row.get("hypotheses") or []:
            existing_ids.add(str(hid))
        for hid in row.get("deferred_hypotheses") or []:
            existing_ids.add(str(hid))

    base_spearman = float(baseline["spearman_final_vs_composite"])

    # Offline selection uses a safety margin vs multi-day shadow turnover.
    offline_gate = max_turnover_gate * 0.75
    gated = [
        r
        for r in rows
        if r["ranking_turnover_vs_baseline"] <= offline_gate
        and not any((p, repr(v)) in tested_overrides for p, v in r["change"].items())
    ]
    # Prefer modest turnover (stable) then larger composite shift as secondary
    gated.sort(
        key=lambda r: (
            r["ranking_turnover_vs_baseline"],
            -abs(r["spearman_final_vs_base"] - base_spearman),
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
    used_labels: set[str] = set()

    # Track M: take up to two lowest-turnover untested market levers
    for r in gated:
        if r["label"] in used_labels:
            continue
        if is_social_override(r["change"]):
            continue
        hid, seq = alloc_id(seq)
        ready.append(
            {
                "hypothesis_id": hid,
                "basis": (
                    f"Track M cycle {cycle_id}: Social locked. Offline {r['label']} "
                    f"turnover={r['ranking_turnover_vs_baseline']:.1%} under safety gate "
                    f"{offline_gate:.0%}. Evaluate with forward-return apparatus "
                    f"(see standing track-m-calibrate / σ_IC)."
                ),
                "overrides": dict(r["change"]),
                "prediction": {
                    "metric": "mean_forward_spearman_lift",
                    "expected_direction": "non_negative_with_ci",
                    "secondary_metric": "ranking_turnover_vs_baseline",
                    "expected_secondary": f"below_{max_turnover_gate:.0%}_gate",
                    "rationale": f"{r['label']} — Track M market lever (no Social).",
                    "track": "M",
                },
            }
        )
        used_labels.add(r["label"])
        if len(ready) >= 2:
            break

    if not ready:
        # Fallback: any untested non-social row, lowest turnover
        candidates = [
            r
            for r in rows
            if not is_social_override(r["change"])
            and not any((p, repr(v)) in tested_overrides for p, v in r["change"].items())
        ]
        candidates.sort(key=lambda r: r["ranking_turnover_vs_baseline"])
        for r in candidates[:2]:
            hid, seq = alloc_id(seq)
            ready.append(
                {
                    "hypothesis_id": hid,
                    "basis": (
                        f"Track M cycle {cycle_id}: fallback {r['label']} "
                        f"(turnover={r['ranking_turnover_vs_baseline']:.1%})."
                    ),
                    "overrides": dict(r["change"]),
                    "prediction": {
                        "metric": "mean_forward_spearman_lift",
                        "expected_direction": "non_negative_with_ci",
                        "secondary_metric": "ranking_turnover_vs_baseline",
                        "expected_secondary": "observe",
                        "rationale": r["label"],
                        "track": "M",
                    },
                }
            )

    deferred = [
        {
            "hypothesis_id": "H-SOCIAL-LOCKED",
            "reason": (
                "Track S locked: no Social score hypotheses until live Social density "
                "feasibility exists (no backfill). Prior k/tilt/beta Social shadows stay archived."
            ),
            "overrides": {},
        }
    ]
    return ready, deferred


def latest_ready_hypothesis_ids() -> list[str]:
    """Return hypothesis IDs from the most recent analyse log entry."""
    for row in reversed(read_log()):
        if row.get("phase") == "loop-analyse-hypothese" and row.get("hypotheses"):
            return list(row["hypotheses"])
    return []
