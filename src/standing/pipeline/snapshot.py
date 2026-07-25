from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from standing.config import ScoringConfig, load_rules, load_scoring_config
from standing.domain.scoring.pipeline import ScoreInputs, score_cross_section
from standing.providers.base import FetchCursor, MarketProvider, SocialProvider
from standing.universe.builder import UniverseSnapshot, fetch_and_build


@dataclass(frozen=True)
class StandingSnapshot:
    as_of: date
    universe_id: str
    methodology_version: str
    score_kind: str
    placeholder: bool
    standings: pd.DataFrame
    meta: dict[str, Any]

    def to_records(self) -> list[dict[str, Any]]:
        return self.standings.to_dict(orient="records")


def run_snapshot(
    *,
    as_of: date,
    market: MarketProvider,
    social: SocialProvider,
    cfg: ScoringConfig | None = None,
    rules: dict[str, Any] | None = None,
    market_mode: str | None = None,
    social_mode: str | None = None,
) -> StandingSnapshot:
    cfg = cfg or load_scoring_config()
    rules = rules or load_rules()
    universe: UniverseSnapshot = fetch_and_build(market, as_of=as_of, cfg=cfg, rules=rules)
    social_df, _cursor = social.fetch_since(FetchCursor(as_of=as_of))
    tickers = set(universe.members["ticker"])
    social_df = social_df[social_df["ticker"].isin(tickers)].copy()

    standings = score_cross_section(
        ScoreInputs(
            market=universe.members,
            social_daily=social_df,
            as_of=pd.Timestamp(as_of),
        ),
        cfg,
    )
    standings.insert(0, "universe_id", universe.universe_id)
    standings = standings.sort_values("final_standing", ascending=False).reset_index(drop=True)

    now = datetime.now(timezone.utc).isoformat()
    market_meta = getattr(market, "metadata", lambda: {})()
    social_meta = getattr(social, "metadata", lambda: {})()
    market_fixture = bool(getattr(market, "is_fixture", lambda: False)())
    social_fixture = bool(getattr(social, "is_fixture", lambda: False)())

    coverage = {}
    for col in ("value_coverage", "quality_coverage", "momentum_coverage"):
        if col in standings.columns:
            coverage[col] = float(standings[col].mean(skipna=True))

    meta = {
        "sector_counts": universe.sector_counts,
        "low_confidence_sectors": universe.low_confidence_sectors,
        "n_names": len(universe.members),
        "universe_id": universe.universe_id,
        "universe_as_of": rules.get("universe_as_of"),
        "peer_frame": cfg.base.get("peer_frame"),
        "peer_frame_planned": rules.get("peer_frame_planned"),
        "market_mode": market_mode,
        "social_mode": social_mode,
        "market_provider": getattr(market, "name", lambda: "unknown")(),
        "social_provider": getattr(social, "name", lambda: "unknown")(),
        "market_provider_meta": market_meta,
        "social_provider_meta": social_meta,
        "market_is_fixture": market_fixture,
        "social_is_fixture": social_fixture,
        "provider_staleness_utc": {
            "market": now,
            "social": now,
            "scored": now,
        },
        "coverage_means": coverage,
        "attention_mode": cfg.social_tilt.get("attention_mode"),
        "tilt_max": cfg.social_tilt.get("tilt_max"),
    }
    return StandingSnapshot(
        as_of=as_of,
        universe_id=universe.universe_id,
        methodology_version=cfg.methodology_version,
        score_kind=cfg.score_kind,
        placeholder=cfg.placeholder,
        standings=standings,
        meta=meta,
    )


def persist_snapshot(snapshot: StandingSnapshot, out_dir: Path) -> Path:
    """Legacy flat CSV+meta writer (reports / ad-hoc). Not the immutable day log."""
    import json

    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = snapshot.as_of.isoformat()
    csv_path = out_dir / f"standings_{stamp}.csv"
    meta_path = out_dir / f"standings_{stamp}.meta.json"
    snapshot.standings.to_csv(csv_path, index=False)
    payload = {
        "as_of": snapshot.as_of.isoformat(),
        "universe_id": snapshot.universe_id,
        "methodology_version": snapshot.methodology_version,
        "score_kind": snapshot.score_kind,
        "placeholder": snapshot.placeholder,
        "meta": snapshot.meta,
    }
    meta_path.write_text(json.dumps(payload, indent=2, default=str))
    return csv_path
