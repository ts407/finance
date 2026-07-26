"""Seed universe expansion: sector reference + full-universe scoring."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from standing.config import load_scoring_config
from standing.domain.scoring.base import GICS_11
from standing.domain.scoring.pipeline import ScoreInputs, score_cross_section
from standing.providers.edgar.market import EdgarMarketProvider
from standing.providers.factory import build_market_provider
from standing.universe.builder import build_universe
from standing.universe.seeds import load_seed_frame, load_sector_map, load_universe_meta


def test_sector_reference_covers_full_seed_universe():
    seeds = set(load_seed_frame()["ticker"])
    smap = load_sector_map()
    assert seeds, "seed universe should be non-empty"
    # Every seed ticker has a GICS-11 sector, and no stray tickers in the reference.
    assert not (seeds - set(smap)), f"seed tickers missing a sector: {sorted(seeds - set(smap))}"
    assert not (set(smap) - seeds), f"sector rows outside seed universe: {sorted(set(smap) - seeds)}"
    assert set(smap.values()) <= set(GICS_11)


def test_universe_meta_merges_listing_and_sector():
    meta = load_universe_meta()
    # Non-fixture names resolve real sectors, not the IT fallback.
    assert meta["LLY"]["sector"] == "Health Care"
    assert meta["COIN"]["sector"] == "Financials"
    assert meta["RIO"] == {"sector": "Materials", "listing": "ADR"}


def test_edgar_full_universe_expands_ticker_list():
    desk = EdgarMarketProvider()
    full = EdgarMarketProvider(full_universe=True)
    assert len(full._tickers) > len(desk._tickers)
    assert len(full._tickers) == len(load_seed_frame())
    # Real sector resolution wired through the provider meta.
    assert full._meta["NEM"][0] == "Materials"


def test_factory_env_selects_seed_universe(monkeypatch):
    monkeypatch.setenv("STANDING_UNIVERSE", "seed")
    provider = build_market_provider("edgar")
    assert len(provider._tickers) == len(load_seed_frame())


def _synth_full_universe_market(as_of: date, *, seed: int = 11) -> pd.DataFrame:
    """Synthetic financials over the *real* seed universe (real tickers + sectors)."""
    rng = np.random.default_rng(seed)
    rows = []
    for ticker, m in load_universe_meta().items():
        g = rng.normal(0, 1)
        rows.append(
            {
                "ticker": ticker,
                "sector": m["sector"],
                "listing": m["listing"],
                "market_cap": float(rng.uniform(2e9, 3.0e12)),
                "adv_20d": float(rng.uniform(1e7, 5e9)),
                "pe_ttm": float(np.clip(rng.lognormal(3.0, 0.4), 3, 120)),
                "pb": float(np.clip(rng.lognormal(1.0, 0.4), 0.3, 40)),
                "ev_ebitda": float(np.clip(rng.lognormal(2.5, 0.4), 2, 80)),
                "ev_ebit": float(np.clip(rng.lognormal(2.7, 0.4), 3, 100)),
                "ev_sales": float(np.clip(rng.lognormal(1.5, 0.45), 0.4, 30)),
                "roe": float(np.clip(0.1 + 0.12 * g, -0.2, 0.6)),
                "operating_margin": float(np.clip(0.12 + 0.08 * g, -0.1, 0.5)),
                "revenue_growth_yoy": float(np.clip(0.05 + 0.1 * g, -0.3, 0.8)),
                "ret_1m": float(rng.normal(0.01 * g, 0.06)),
                "ret_3m": float(rng.normal(0.03 * g, 0.12)),
                "ret_6m": float(rng.normal(0.05 * g, 0.2)),
                "relative_volume": float(np.clip(rng.lognormal(0.0, 0.35), 0.3, 5.0)),
                "as_of": as_of.isoformat(),
            }
        )
    return pd.DataFrame(rows)


def test_scoring_pipeline_handles_full_universe_and_flags_thin_sectors():
    cfg = load_scoring_config()
    as_of = date(2026, 7, 26)
    market = _synth_full_universe_market(as_of)
    universe = build_universe(market, as_of=as_of, cfg=cfg)

    # The seed universe (full S&P 500 ∪ NDX ∪ ADRs) dwarfs the 54-name fixture desk.
    assert len(universe.members) >= 400
    # Sectors below min_names_per_sector (e.g. Real Estate, Materials) are flagged.
    assert universe.low_confidence_sectors

    scored = score_cross_section(
        ScoreInputs(
            market=universe.members,
            social_daily=pd.DataFrame(columns=["ticker", "date", "source_id", "mention_count"]),
            as_of=pd.Timestamp(as_of),
        ),
        cfg,
    )
    assert len(scored) == len(universe.members)
    assert scored["final_standing"].between(0, 100).all()
    # Every scored row carries a real GICS-11 sector (no IT-fallback contamination).
    assert set(scored["sector"]) <= set(GICS_11)
