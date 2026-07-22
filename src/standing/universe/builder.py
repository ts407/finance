from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd

from standing.config import ScoringConfig, load_rules
from standing.logging_config import get_logger
from standing.providers.base import MarketProvider

log = get_logger("universe")


@dataclass(frozen=True)
class UniverseSnapshot:
    universe_id: str
    methodology_version: str
    as_of: date
    members: pd.DataFrame
    sector_counts: dict[str, int]
    low_confidence_sectors: list[str]
    rules: dict[str, Any]


def apply_admission_rules(market: pd.DataFrame, rules: dict[str, Any]) -> pd.DataFrame:
    df = market.copy()
    df = df[df["market_cap"] >= float(rules["min_market_cap_usd"])]
    df = df[df["adv_20d"] >= float(rules["min_adv_usd_20d"])]
    scope = set(rules.get("scope", ["US", "ADR"]))
    if "listing" in df.columns:
        df = df[df["listing"].isin(scope)]
    return df.reset_index(drop=True)


def build_universe(
    market: pd.DataFrame,
    *,
    as_of: date,
    cfg: ScoringConfig,
    rules: dict[str, Any] | None = None,
) -> UniverseSnapshot:
    rules = rules or load_rules()
    members = apply_admission_rules(market, rules)
    counts = members.groupby("sector").size().to_dict()
    min_names = int(rules.get("min_names_per_sector", cfg.universe["min_names_per_sector"]))
    low = sorted([s for s, n in counts.items() if n < min_names])
    return UniverseSnapshot(
        universe_id=str(rules["universe_id"]),
        methodology_version=str(rules.get("methodology_version", cfg.methodology_version)),
        as_of=as_of,
        members=members,
        sector_counts=counts,
        low_confidence_sectors=low,
        rules=rules,
    )


def fetch_and_build(
    provider: MarketProvider,
    *,
    as_of: date,
    cfg: ScoringConfig,
    rules: dict[str, Any] | None = None,
) -> UniverseSnapshot:
    provider_name = getattr(provider, "name", lambda: "unknown")()
    log.debug("Fetching market universe provider=%s as_of=%s", provider_name, as_of.isoformat())
    market = provider.fetch(as_of)
    universe = build_universe(market, as_of=as_of, cfg=cfg, rules=rules)
    log.info(
        "Universe admitted n=%s sectors=%s low_confidence=%s",
        len(universe.members),
        len(universe.sector_counts),
        len(universe.low_confidence_sectors),
    )
    return universe
