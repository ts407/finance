"""Track S research: calibrate the sentiment attention axis via forward-return IC.

Parallels ``momentum_calibrate`` for Track M. The productive ``sentiment_calibrated``
flag flips true only when the sentiment signal shows forward-return IC that clears the
apparatus gate (n / |mean_ic| / tstat). On synthetic fixtures — and until non-
backfillable live Social density exists — this stays inconclusive, and the flag stays
false. ``apparatus_self_test`` validates the *measuring chain* on a known injected
signal so a null real result means "no signal", not "broken meter".
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from standing.config import ROOT, ScoringConfig, load_scoring_config
from standing.optimization.forward import next_weekday
from standing.pipeline.snapshot import run_snapshot
from standing.providers import FixtureMarketProvider, FixtureSocialProvider
from standing.research.ic import cross_section_ic_timeseries, power_days_80

DEFAULT_REPORT_DIR = ROOT / "artifacts" / "research" / "track_s"

# Apparatus gate — same shape as the Track M momentum check.
MIN_IC_OBS = 12
MIN_ABS_MEAN_IC = 0.01
MIN_TSTAT = 1.5


@dataclass(frozen=True)
class SentimentCalibration:
    n_ic_obs: int
    mean_ic: float
    sigma_ic: float
    tstat: float
    power_days_80: float
    ic_positive_share: float
    passed: bool


def _summ_to_calibration(summary: Any) -> SentimentCalibration:
    passed = bool(
        summary.n_ic_obs >= MIN_IC_OBS
        and abs(summary.mean_ic or 0.0) > MIN_ABS_MEAN_IC
        and (summary.tstat or 0.0) > MIN_TSTAT
    )
    return SentimentCalibration(
        n_ic_obs=int(summary.n_ic_obs),
        mean_ic=float(summary.mean_ic),
        sigma_ic=float(summary.sigma_ic),
        tstat=float(summary.tstat),
        power_days_80=float(summary.power_days_80),
        ic_positive_share=float(summary.ic_positive_share),
        passed=passed,
    )


def build_sentiment_panel(
    *,
    days: list[date],
    cfg: ScoringConfig,
    history_days: int = 14,
) -> pd.DataFrame:
    """
    Panel of (as_of, ticker, sentiment, forward_ret) from the productive pipeline.

    ``sentiment`` is the shrunk sentiment-blended social score (``s_used``) the desk
    actually applies; ``forward_ret`` is the look-ahead-free next-weekday fixture
    ``ret_1m`` (independent of the score-day cross-section).
    """
    market = FixtureMarketProvider()
    rows: list[dict[str, Any]] = []
    for d in days:
        snap = run_snapshot(
            as_of=d,
            market=market,
            social=FixtureSocialProvider(history_days=history_days),
            cfg=cfg,
        )
        fwd = market.fetch(next_weekday(d)).set_index("ticker")["ret_1m"]
        for _, r in snap.standings.iterrows():
            t = r["ticker"]
            if t not in fwd.index:
                continue
            rows.append(
                {"as_of": d.isoformat(), "ticker": t, "sentiment": float(r["s_used"]), "forward_ret": float(fwd.loc[t])}
            )
    return pd.DataFrame(rows)


def apparatus_self_test(*, n_days: int = 24, n_names: int = 60, seed: int = 5) -> SentimentCalibration:
    """
    Validate the IC chain on a synthetic panel with an *injected* sentiment→forward
    signal. A pass means the meter recovers a signal it was given — so a null result
    on real/fixture data is evidence of no signal, not a broken apparatus.
    """
    rng = np.random.default_rng(seed)
    rows: list[dict[str, Any]] = []
    for i in range(n_days):
        d = date(2026, 1, 1).toordinal() + i * 7
        sentiment = rng.uniform(0, 100, size=n_names)
        # forward return leans on sentiment (centered at 50) plus heavy noise.
        forward = 0.02 * (sentiment - 50.0) / 50.0 + rng.normal(0, 0.05, size=n_names)
        for j in range(n_names):
            rows.append(
                {"as_of": date.fromordinal(d).isoformat(), "ticker": f"S{j:03d}", "sentiment": float(sentiment[j]), "forward_ret": float(forward[j])}
            )
    panel = pd.DataFrame(rows)
    _, summary = cross_section_ic_timeseries(
        panel, score_col="sentiment", forward_col="forward_ret", signal_name="sentiment_self_test", horizon_days=21
    )
    return _summ_to_calibration(summary)


def run_sentiment_calibration(
    *,
    days: list[date] | None = None,
    cfg: ScoringConfig | None = None,
    horizon_days: int = 21,
    out_dir: Path | None = None,
) -> dict[str, Any]:
    """Attempt sentiment calibration on the available (fixture) panel; write a report."""
    cfg = cfg or load_scoring_config()
    out = out_dir or DEFAULT_REPORT_DIR
    out.mkdir(parents=True, exist_ok=True)

    if days is None:
        base = date(2026, 7, 24)
        days = [date.fromordinal(base.toordinal() - i) for i in range(20)]
        days = [d for d in days if d.weekday() < 5]

    self_test = apparatus_self_test()
    panel = build_sentiment_panel(days=days, cfg=cfg, history_days=14)
    if panel.empty:
        real = SentimentCalibration(0, float("nan"), float("nan"), float("nan"), float("inf"), float("nan"), False)
    else:
        _, summary = cross_section_ic_timeseries(
            panel, score_col="sentiment", forward_col="forward_ret", signal_name="sentiment_axis", horizon_days=horizon_days
        )
        real = _summ_to_calibration(summary)

    attention_mode = str(cfg.social_tilt.get("attention_mode", "volume_only"))
    # Flip recommendation requires: sentiment axis active, apparatus healthy, real IC passes.
    recommend_flag = bool(attention_mode == "volume_plus_sentiment" and self_test.passed and real.passed)

    report = {
        "track": "S",
        "phase": "sentiment_apparatus_calibration",
        "status": "ok" if real.passed else "weak_or_inconclusive",
        "attention_mode": attention_mode,
        "sentiment_weight": cfg.social_tilt.get("sentiment_weight"),
        "horizon_days": horizon_days,
        "apparatus_self_test": {
            "passed": self_test.passed,
            "mean_ic": self_test.mean_ic,
            "tstat": self_test.tstat,
            "n_ic_obs": self_test.n_ic_obs,
            "rule": f"n_ic_obs>={MIN_IC_OBS} AND |mean_ic|>{MIN_ABS_MEAN_IC} AND tstat>{MIN_TSTAT}",
            "note": "Injected sentiment→forward signal; validates the IC measuring chain.",
        },
        "real_calibration": {
            "passed": real.passed,
            "mean_ic": real.mean_ic,
            "sigma_ic": real.sigma_ic,
            "tstat": real.tstat,
            "n_ic_obs": real.n_ic_obs,
            "power_days_80": real.power_days_80,
            "source": "fixture social sentiment vs next-weekday fixture ret_1m",
        },
        "sentiment_calibrated_current": bool(cfg.social_pipeline.get("sentiment_calibrated", False)),
        "recommend_sentiment_calibrated": recommend_flag,
        "note": (
            "Fixture/synthetic social carries no real forward signal and live Social is "
            "not backfillable, so real IC is expected to be inconclusive. sentiment_calibrated "
            "flips true only when a real panel clears the apparatus gate."
        ),
    }
    report_path = out / "sentiment_calibration.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    try:
        report["report_path"] = str(report_path.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        report["report_path"] = str(report_path)
    return report
