from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from standing.config import load_scoring_config
from standing.domain.scoring.base import compute_base_standing, pillar_percentiles
from standing.domain.scoring.social_features import apply_source_cap
from standing.pipeline.snapshot import run_snapshot
from standing.providers import FetchCursor, FixtureMarketProvider, FixtureSocialProvider
from standing.universe.builder import build_universe


def test_pillar_percentiles_sector_relative():
    df = pd.DataFrame(
        {
            "ticker": ["A", "B", "C", "D"],
            "sector": ["Energy", "Energy", "Utilities", "Utilities"],
            "pe_ttm": [10.0, 20.0, 10.0, 20.0],
            "pb": [1.0, 2.0, 1.0, 2.0],
            "ev_ebitda": [5.0, 10.0, 5.0, 10.0],
            "roe": [0.2, 0.1, 0.2, 0.1],
            "operating_margin": [0.3, 0.1, 0.3, 0.1],
            "revenue_growth_yoy": [0.2, 0.0, 0.2, 0.0],
            "ret_1m": [0.1, -0.1, 0.1, -0.1],
            "ret_3m": [0.2, -0.2, 0.2, -0.2],
            "ret_6m": [0.3, -0.3, 0.3, -0.3],
            "relative_volume": [2.0, 0.5, 2.0, 0.5],
        }
    )
    pillars = pillar_percentiles(df, winsorize=(0.0, 1.0))
    # Cheaper name in each sector gets higher value
    assert pillars.loc[0, "value"] > pillars.loc[1, "value"]
    assert pillars.loc[2, "value"] > pillars.loc[3, "value"]
    base = compute_base_standing(pillars)
    assert base.notna().all()


def test_source_cap_limits_share():
    daily = pd.DataFrame(
        {
            "date": ["2026-07-01", "2026-07-01"],
            "ticker": ["AAA", "AAA"],
            "source_id": ["reddit_wsb", "stocktwits"],
            "mention_count": [90, 10],
            "neg_share": [0.7, 0.2],
            "upvotes": [100, 5],
        }
    )
    capped = apply_source_cap(daily, cap=0.50)
    # Cap is vs original ticker-day total (100): WSB downsampled to 50
    wsb = capped.loc[capped["source_id"] == "reddit_wsb"].iloc[0]
    st = capped.loc[capped["source_id"] == "stocktwits"].iloc[0]
    assert float(wsb["source_share"]) == 0.9
    assert float(wsb["mention_count_capped"]) == 50.0
    assert float(wsb["cap_headroom"]) == 0.0
    assert float(st["mention_count_capped"]) == 10.0
    assert float(st["cap_headroom"]) == pytest.approx(0.40)


def test_fixture_snapshot_runs():
    cfg = load_scoring_config()
    snap = run_snapshot(
        as_of=date(2026, 7, 22),
        market=FixtureMarketProvider(),
        social=FixtureSocialProvider(history_days=14),
        cfg=cfg,
        market_mode="fixture",
        social_mode="fixture",
    )
    assert snap.score_kind == "editorial_descriptive"
    assert snap.placeholder is True
    assert len(snap.standings) > 0
    assert set(["composite_standing", "attention_tilt", "final_standing"]).issubset(
        snap.standings.columns
    )
    assert "value_coverage" in snap.standings.columns
    assert "size_bucket" in snap.standings.columns
    assert snap.meta["social_is_fixture"] is True
    assert snap.meta["universe_as_of"]
    # Final equals clip(base+tilt)
    recomputed = np.clip(
        snap.standings["composite_standing"] + snap.standings["attention_tilt"], 0, 100
    )
    assert np.allclose(snap.standings["final_standing"], recomputed)
    # Low confidence expected on tiny fixture sectors vs min_names=30
    assert snap.meta["low_confidence_sectors"]


def test_providers_share_contract():
    as_of = date(2026, 7, 22)
    m = FixtureMarketProvider().fetch(as_of)
    s, cursor = FixtureSocialProvider().fetch_since(FetchCursor(as_of=as_of))
    assert "ticker" in m.columns and "sector" in m.columns
    assert {"date", "ticker", "source_id", "mention_count", "neg_share"}.issubset(s.columns)
    assert cursor.as_of == as_of


def test_universe_admission():
    cfg = load_scoring_config()
    market = FixtureMarketProvider().fetch(date(2026, 7, 22))
    # Force one name below ADV gate
    market.loc[market.index[0], "adv_20d"] = 100.0
    uni = build_universe(market, as_of=date(2026, 7, 22), cfg=cfg)
    assert market.iloc[0]["ticker"] not in set(uni.members["ticker"])
