from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from standing.config import ROOT, ScoringConfig, load_scoring_config
from standing.domain.scoring.pipeline import ScoreInputs, score_cross_section
from standing.optimization.analyse import _badge_shares, _ranking_turnover, _spearman
from standing.optimization.forward import forward_return_metrics, summarize_forward_pairs
from standing.optimization.paths import HYPOTHESES_DIR, SHADOW_DIR, ensure_layout
from standing.providers import FixtureMarketProvider, FixtureSocialProvider
from standing.providers.base import FetchCursor
from standing.universe.builder import fetch_and_build


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        return str(path)


def trading_days_ending(end: date, n_days: int) -> list[date]:
    """Return ``n_days`` weekdays ending at ``end`` (inclusive), oldest→newest."""
    if n_days < 1:
        raise ValueError("n_days must be >= 1")
    days: list[date] = []
    cursor = end
    while len(days) < n_days:
        if cursor.weekday() < 5:
            days.append(cursor)
        cursor -= timedelta(days=1)
    return list(reversed(days))


@dataclass(frozen=True)
class DayMetrics:
    as_of: str
    n_names: int
    spearman_final_vs_composite: float
    mean_abs_tilt: float
    max_abs_tilt: float
    mean_confidence_c: float
    mean_n: float
    sparse_share: float
    thin_share: float
    ok_share: float
    ranking_turnover_vs_productive: float
    spearman_final_productive_vs_shadow: float
    mean_abs_final_delta: float


def _metrics_pair(prod: pd.DataFrame, shadow: pd.DataFrame, as_of: date) -> DayMetrics:
    badges = _badge_shares(shadow)
    aligned = prod.set_index("ticker")[["final_standing"]].join(
        shadow.set_index("ticker")[["final_standing"]],
        lsuffix="_prod",
        rsuffix="_shadow",
    )
    return DayMetrics(
        as_of=as_of.isoformat(),
        n_names=int(len(shadow)),
        spearman_final_vs_composite=_spearman(shadow["final_standing"], shadow["composite_standing"]),
        mean_abs_tilt=float(shadow["attention_tilt"].abs().mean()),
        max_abs_tilt=float(shadow["attention_tilt"].abs().max()),
        mean_confidence_c=float(shadow["confidence_c"].mean()),
        mean_n=float(shadow["n"].mean()),
        sparse_share=badges["sparse_share"],
        thin_share=badges["thin_share"],
        ok_share=badges["ok_share"],
        ranking_turnover_vs_productive=_ranking_turnover(prod, shadow),
        spearman_final_productive_vs_shadow=_spearman(
            aligned["final_standing_prod"], aligned["final_standing_shadow"]
        ),
        mean_abs_final_delta=float(
            (aligned["final_standing_prod"] - aligned["final_standing_shadow"]).abs().mean()
        ),
    )


def _score_shared(
    *,
    as_of: date,
    prod_cfg: ScoringConfig,
    shadow_cfg: ScoringConfig,
    market: FixtureMarketProvider,
    social: FixtureSocialProvider,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Fetch market+social once; score with both configs on identical inputs."""
    universe = fetch_and_build(market, as_of=as_of, cfg=prod_cfg)
    social_df, _ = social.fetch_since(FetchCursor(as_of=as_of))
    tickers = set(universe.members["ticker"])
    social_df = social_df[social_df["ticker"].isin(tickers)].copy()
    inputs = ScoreInputs(
        market=universe.members,
        social_daily=social_df,
        as_of=pd.Timestamp(as_of),
    )
    prod = score_cross_section(inputs, prod_cfg)
    shadow = score_cross_section(inputs, shadow_cfg)
    prod = prod.sort_values("final_standing", ascending=False).reset_index(drop=True)
    shadow = shadow.sort_values("final_standing", ascending=False).reset_index(drop=True)

    capture = prod[
        [
            "ticker",
            "sector",
            "value",
            "quality",
            "momentum",
            "composite_standing",
            "s_obs",
            "s_used",
            "n",
            "confidence_c",
            "neg_share",
            "attention_tilt",
            "final_standing",
            "social_badge",
            "methodology_version",
            "as_of",
        ]
    ].copy()
    capture = capture.rename(
        columns={
            "attention_tilt": "prod_attention_tilt",
            "final_standing": "prod_final_standing",
            "composite_standing": "prod_composite_standing",
            "methodology_version": "prod_methodology_version",
        }
    )
    shadow_cols = shadow.set_index("ticker")[
        ["attention_tilt", "final_standing", "composite_standing", "methodology_version"]
    ].rename(
        columns={
            "attention_tilt": "shadow_attention_tilt",
            "final_standing": "shadow_final_standing",
            "composite_standing": "shadow_composite_standing",
            "methodology_version": "shadow_methodology_version",
        }
    )
    capture = capture.join(shadow_cols, on="ticker")
    capture.insert(0, "config_pair", "productive_vs_shadow")
    return prod, shadow, capture


def load_hypothesis(hypothesis_id: str) -> dict[str, Any]:
    path = HYPOTHESES_DIR / f"{hypothesis_id}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Hypothesis not found: {path}")
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Invalid hypothesis file: {path}")
    return data


def run_shadow_test(
    *,
    hypothesis_id: str,
    end_as_of: date,
    n_days: int = 7,
    history_days: int = 14,
    productive_config: Path | None = None,
) -> dict[str, Any]:
    """
    Run productive + shadow configs in parallel over ``n_days`` trading days.

    Never writes to productive scoring.yaml.
    """
    ensure_layout()
    hyp = load_hypothesis(hypothesis_id)
    if hyp.get("status") == "deferred":
        raise ValueError(f"Hypothesis {hypothesis_id} is deferred; not eligible for shadow test")

    shadow_cfg_path = Path(hyp["shadow_config"])
    if not shadow_cfg_path.is_absolute():
        shadow_cfg_path = ROOT / shadow_cfg_path
    shadow_cfg = load_scoring_config(shadow_cfg_path)
    prod_cfg = load_scoring_config(productive_config)

    days = trading_days_ending(end_as_of, n_days)
    market = FixtureMarketProvider()
    social = FixtureSocialProvider(history_days=history_days)

    day_rows: list[dict[str, Any]] = []
    capture_frames: list[pd.DataFrame] = []
    prod_metrics_rows: list[dict[str, Any]] = []
    prod_forward_rows: list[dict[str, Any]] = []
    shadow_forward_rows: list[dict[str, Any]] = []

    for d in days:
        prod, shadow, capture = _score_shared(
            as_of=d,
            prod_cfg=prod_cfg,
            shadow_cfg=shadow_cfg,
            market=market,
            social=social,
        )
        day_rows.append(asdict(_metrics_pair(prod, shadow, d)))
        prod_badges = _badge_shares(prod)
        prod_metrics_rows.append(
            {
                "as_of": d.isoformat(),
                "n_names": int(len(prod)),
                "spearman_final_vs_composite": _spearman(
                    prod["final_standing"], prod["composite_standing"]
                ),
                "mean_abs_tilt": float(prod["attention_tilt"].abs().mean()),
                "mean_confidence_c": float(prod["confidence_c"].mean()),
                **prod_badges,
            }
        )
        prod_fwd = forward_return_metrics(prod, as_of=d, market=market)
        shadow_fwd = forward_return_metrics(shadow, as_of=d, market=market)
        prod_forward_rows.append({"as_of": d.isoformat(), **prod_fwd})
        shadow_forward_rows.append({"as_of": d.isoformat(), **shadow_fwd})
        capture.insert(1, "hypothesis_id", hypothesis_id)
        capture_frames.append(capture)

    shadow_df = pd.DataFrame(day_rows)
    prod_df = pd.DataFrame(prod_metrics_rows)
    forward_summary = summarize_forward_pairs(prod_forward_rows, shadow_forward_rows)

    out_dir = SHADOW_DIR / hypothesis_id
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = f"{days[0].isoformat()}_{days[-1].isoformat()}"
    report_path = out_dir / f"shadow_report_{stamp}.json"
    capture_path = out_dir / f"capture_{stamp}.csv"
    daily_path = out_dir / f"daily_metrics_{stamp}.csv"

    summary = {
        "phase": "loop-live-test-shadow",
        "hypothesis_id": hypothesis_id,
        "cycle_id": hyp.get("cycle_id"),
        "status": "shadow_complete",
        "window": {
            "n_trading_days": n_days,
            "start": days[0].isoformat(),
            "end": days[-1].isoformat(),
            "dates": [d.isoformat() for d in days],
            "data_source": "fixture_shared_fetch",
            "note": (
                "Fixtures stand in for live data; productive and shadow scored on "
                "identical market+social fetches per day. Forward proxy uses next "
                "weekday fixture ret_1m."
            ),
        },
        "productive_config": _rel(prod_cfg.path),
        "shadow_config": hyp["shadow_config"],
        "change": hyp.get("change"),
        "prediction": hyp.get("prediction"),
        "productive_daily": prod_metrics_rows,
        "shadow_daily": day_rows,
        "productive_forward_daily": prod_forward_rows,
        "shadow_forward_daily": shadow_forward_rows,
        "forward": forward_summary,
        "aggregates": {
            "mean_ranking_turnover_vs_productive": float(
                shadow_df["ranking_turnover_vs_productive"].mean()
            ),
            "mean_spearman_final_vs_composite_shadow": float(
                shadow_df["spearman_final_vs_composite"].mean()
            ),
            "mean_spearman_final_vs_composite_productive": float(
                prod_df["spearman_final_vs_composite"].mean()
            ),
            "mean_abs_tilt_shadow": float(shadow_df["mean_abs_tilt"].mean()),
            "mean_abs_tilt_productive": float(prod_df["mean_abs_tilt"].mean()),
            "mean_abs_final_delta": float(shadow_df["mean_abs_final_delta"].mean()),
            "mean_spearman_final_productive_vs_shadow": float(
                shadow_df["spearman_final_productive_vs_shadow"].mean()
            ),
            "mean_forward_spearman_lift": float(
                forward_summary.get("mean_forward_spearman_lift", float("nan"))
            ),
            "mean_top_decile_excess_lift": float(
                forward_summary.get("mean_top_decile_excess_lift", float("nan"))
            ),
        },
        "report_path": _rel(report_path),
        "capture_path": _rel(capture_path),
        "daily_metrics_path": _rel(daily_path),
        "handoff": "loop-vergleich-entscheidung",
        "productive_config_unchanged": True,
    }

    report_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    pd.concat(capture_frames, ignore_index=True).to_csv(capture_path, index=False)
    shadow_df.to_csv(daily_path, index=False)

    hyp["status"] = "shadow_complete"
    hyp["shadow_report"] = _rel(report_path)
    hyp["shadow_capture"] = _rel(capture_path)
    hyp["handoff"] = "loop-vergleich-entscheidung"
    hyp_path = HYPOTHESES_DIR / f"{hypothesis_id}.yaml"
    with hyp_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(hyp, f, sort_keys=False, allow_unicode=True)

    return summary
