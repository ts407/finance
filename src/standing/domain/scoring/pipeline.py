from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from standing.config import ScoringConfig
from standing.domain.scoring.base import (
    compute_base_standing,
    pillar_percentiles,
    sector_occupancy_flags,
)
from standing.domain.scoring.shrinkage import shrink_social
from standing.domain.scoring.social_features import (
    aggregate_mentions,
    apply_source_cap,
    blend_sentiment,
)
from standing.domain.scoring.tilt import attention_tilt, final_standing


@dataclass(frozen=True)
class ScoreInputs:
    market: pd.DataFrame
    social_daily: pd.DataFrame
    as_of: pd.Timestamp


@dataclass(frozen=True)
class ScoreRow:
    ticker: str
    sector: str
    value: float
    quality: float
    momentum: float
    momentum_global: float
    composite_standing: float
    s_obs: float
    s_used: float
    n: float
    confidence_c: float
    neg_share: float
    attention_tilt: float
    final_standing: float
    sector_low_confidence: bool
    social_badge: str


def _badge(n: float, sparse_below: float, ok_at: float) -> str:
    if n < sparse_below:
        return "sparse"
    if n >= ok_at:
        return "ok"
    return "thin"


def _cell_float(val: Any) -> float:
    if val is None:
        return float("nan")
    try:
        if pd.isna(val):
            return float("nan")
    except (TypeError, ValueError):
        pass
    try:
        number = float(val)
    except (TypeError, ValueError):
        return float("nan")
    return number


def _cell_str(val: Any) -> str:
    """Serialize a dataframe cell for CSV/API string fields (never ``\"nan\"``)."""
    if val is None or (isinstance(val, float) and np.isnan(val)) or pd.isna(val):
        return ""
    text = str(val)
    return "" if text.lower() == "nan" else text


def score_cross_section(inputs: ScoreInputs, cfg: ScoringConfig) -> pd.DataFrame:
    """
    Single score-generation process for a cross-section snapshot.

    Base = weighted V/Q/M; Social → shrinkage → tanh tilt (+ dampener) → Final.
    No renorm / floor alternate path.
    """
    market = inputs.market.copy()
    wins = cfg.base["winsorize"]
    peer_frame = str(cfg.base.get("peer_frame", "sector"))
    pillars = pillar_percentiles(
        market,
        winsorize=(float(wins["lower"]), float(wins["upper"])),
        peer_frame=peer_frame,
    )
    weights = {k: float(v) for k, v in cfg.base["pillar_weights"].items()}
    base = compute_base_standing(pillars, weights=weights)
    low_conf = sector_occupancy_flags(
        market, min_names=int(cfg.universe["min_names_per_sector"])
    )

    capped = apply_source_cap(
        inputs.social_daily,
        cap=float(cfg.social_pipeline["source_cap_per_ticker_day"]),
    )
    social = aggregate_mentions(capped, as_of=inputs.as_of)
    social = social.set_index("ticker")

    # Align social to market universe (missing social → n=0 → shrink to prior)
    tickers = market["ticker"].tolist()
    s_obs = np.full(len(tickers), 50.0)
    n = np.zeros(len(tickers))
    neg = np.full(len(tickers), 0.5)
    for i, t in enumerate(tickers):
        if t in social.index:
            s_obs[i] = float(social.loc[t, "s_obs"])
            n[i] = float(social.loc[t, "n"])
            neg[i] = float(social.loc[t, "neg_share"])

    # Attention axis. volume_only: loudness → score, negativity only dampens (one-sided).
    # volume_plus_sentiment: loudness is amplitude, sentiment is sign (symmetric).
    attention_mode = str(cfg.social_tilt.get("attention_mode", "volume_only"))
    s_obs_effective = s_obs
    sentiment_axis = attention_mode == "volume_plus_sentiment"
    if sentiment_axis:
        s_obs_effective = blend_sentiment(
            s_obs, neg, weight=float(cfg.social_tilt.get("sentiment_weight", 1.0))
        )

    s_used, c = shrink_social(
        s_obs_effective,
        n,
        k=float(cfg.shrinkage["k"]),
        prior=float(cfg.shrinkage["prior"]),
    )
    # In sentiment mode polarity already carries negativity symmetrically; skip the
    # one-sided hype dampener to avoid penalizing negative names twice.
    tilt = attention_tilt(
        s_used,
        tilt_max=float(cfg.social_tilt["tilt_max"]),
        beta=float(cfg.social_tilt["beta"]),
        neg_share=None if sentiment_axis else neg,
        dampener_pivot=float(cfg.social_tilt["dampener_neg_share_pivot"]),
    )
    final = final_standing(base.to_numpy(), tilt)

    badges = cfg.shrinkage["display_badges"]
    price_col = "last_price" if "last_price" in market.columns else ("price" if "price" in market.columns else None)

    rows: list[dict[str, Any]] = []
    for i, t in enumerate(tickers):
        last_price = _cell_float(market.iloc[i][price_col]) if price_col else float("nan")
        rows.append(
            {
                "ticker": t,
                "sector": market.iloc[i]["sector"],
                "last_price": last_price,
                "value": float(pillars.iloc[i]["value"]),
                "quality": float(pillars.iloc[i]["quality"]),
                "momentum": float(pillars.iloc[i]["momentum"]),
                "momentum_global": float(pillars.iloc[i]["momentum_global"]),
                "composite_standing": float(base.iloc[i]),
                "size_bucket": _cell_str(pillars.iloc[i].get("size_bucket", "")),
                "peer_group": _cell_str(pillars.iloc[i].get("peer_group", "")),
                "value_n_metrics": int(pillars.iloc[i].get("value_n_metrics", 0)),
                "value_coverage": float(pillars.iloc[i].get("value_coverage", np.nan)),
                "value_confidence": float(pillars.iloc[i].get("value_confidence", np.nan)),
                "value_pe_rung": _cell_str(pillars.iloc[i].get("value_pe_rung", "")),
                "value_ev_rung": _cell_str(pillars.iloc[i].get("value_ev_rung", "")),
                "value_metric_set": _cell_str(pillars.iloc[i].get("value_metric_set", "")),
                "quality_n_metrics": int(pillars.iloc[i].get("quality_n_metrics", 0)),
                "quality_coverage": float(pillars.iloc[i].get("quality_coverage", np.nan)),
                "momentum_n_metrics": int(pillars.iloc[i].get("momentum_n_metrics", 0)),
                "momentum_coverage": float(pillars.iloc[i].get("momentum_coverage", np.nan)),
                "s_obs": float(s_obs[i]),
                "s_used": float(s_used[i]),
                "n": float(n[i]),
                "confidence_c": float(c[i]),
                "neg_share": float(neg[i]),
                "attention_tilt": float(tilt[i]),
                "final_standing": float(final[i]),
                "sector_low_confidence": bool(low_conf.iloc[i]),
                "social_badge": _badge(
                    float(n[i]),
                    float(badges["sparse_below"]),
                    float(badges["ok_at"]),
                ),
                "score_kind": cfg.score_kind,
                "methodology_version": cfg.methodology_version,
                "as_of": inputs.as_of.isoformat(),
            }
        )
    return pd.DataFrame(rows)
