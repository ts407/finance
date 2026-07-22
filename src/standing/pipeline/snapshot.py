from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from standing.config import ScoringConfig, load_scoring_config
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
) -> StandingSnapshot:
    cfg = cfg or load_scoring_config()
    universe: UniverseSnapshot = fetch_and_build(market, as_of=as_of, cfg=cfg, rules=rules)
    social_df, _cursor = social.fetch_since(FetchCursor(as_of=as_of))
    # Restrict social to admitted universe
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

    meta = {
        "sector_counts": universe.sector_counts,
        "low_confidence_sectors": universe.low_confidence_sectors,
        "n_names": len(universe.members),
        "market_provider": getattr(market, "name", lambda: "unknown")(),
        "social_provider": getattr(social, "name", lambda: "unknown")(),
        "social_provider_meta": getattr(social, "metadata", lambda: {})(),
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
    meta_path.write_text(json.dumps(payload, indent=2))
    return csv_path
