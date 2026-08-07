from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from standing.config import load_scoring_config
from standing.domain.scoring.base import pillar_percentiles
from standing.domain.scoring.peer_buckets import assign_size_bucket, peer_group_key
from standing.domain.scoring.value_metrics import (
    resolve_ev_multiple,
    resolve_pe_multiple,
    value_metric_frame,
)
from standing.pipeline.snapshot import run_snapshot
from standing.pipeline.store import SnapshotExistsError, load_immutable, persist_immutable
from standing.providers import FixtureMarketProvider, FixtureSocialProvider


def _toy_market() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ticker": ["A", "B", "C", "D", "E", "F"],
            "sector": [
                "Energy",
                "Energy",
                "Financials",
                "Financials",
                "Information Technology",
                "Information Technology",
            ],
            "market_cap": [5e9, 15e9, 8e9, 250e9, 3e9, 400e9],
            "pe_ttm": [10.0, 20.0, 12.0, 18.0, None, 25.0],
            "pe_forward": [9.0, None, 11.0, 16.0, 22.0, None],
            "pb": [1.0, 2.0, 0.8, 1.5, 3.0, 4.0],
            "ev_ebitda": [None, 10.0, 8.0, 9.0, None, None],
            "ev_ebit": [6.0, None, 7.0, 8.0, None, 12.0],
            "ev_sales": [1.5, 2.0, 1.0, 1.2, 2.5, None],
            "roe": [0.2, -0.1, 0.15, 0.05, 0.3, 0.1],
            "operating_margin": [0.3, -0.05, 0.2, 0.1, 0.25, 0.12],
            "revenue_growth_yoy": [0.2, 0.0, 0.05, 0.02, 0.4, 0.1],
            "ret_1m": [0.1, -0.1, 0.05, 0.0, 0.2, -0.05],
            "ret_3m": [0.2, -0.2, 0.1, 0.0, 0.3, -0.1],
            "ret_6m": [0.3, -0.3, 0.15, 0.05, 0.4, -0.15],
            "relative_volume": [2.0, 0.5, 1.0, 1.2, 1.5, 0.8],
        }
    )


def test_ev_ladder_falls_back():
    row = pd.Series({"ev_ebitda": None, "ev_ebit": 7.0, "ev_sales": 1.2})
    val, rung = resolve_ev_multiple(row)
    assert val == 7.0 and rung == "ev_ebit"
    row2 = pd.Series({"ev_ebitda": None, "ev_ebit": None, "ev_sales": 1.2})
    val2, rung2 = resolve_ev_multiple(row2)
    assert val2 == 1.2 and rung2 == "ev_sales"


def test_pe_ladder_prefers_forward():
    row = pd.Series({"pe_forward": 18.0, "pe_ttm": 22.0})
    val, rung = resolve_pe_multiple(row)
    assert val == 18.0 and rung == "pe_forward"
    row2 = pd.Series({"pe_forward": None, "pe_ttm": 22.0})
    val2, rung2 = resolve_pe_multiple(row2)
    assert val2 == 22.0 and rung2 == "pe_ttm"
    # Non-positive forward falls through to positive ttm
    row3 = pd.Series({"pe_forward": -5.0, "pe_ttm": 15.0})
    val3, rung3 = resolve_pe_multiple(row3)
    assert val3 == 15.0 and rung3 == "pe_ttm"


def test_pe_ladder_in_value_frame():
    df = _toy_market()
    framed = value_metric_frame(df)
    # A has pe_forward → rung pe_forward; B has only pe_ttm
    assert framed.loc[0, "value_pe_rung"] == "pe_forward"
    assert framed.loc[1, "value_pe_rung"] == "pe_ttm"
    assert framed.loc[0, "_pe_for_value"] == 9.0
    assert framed.loc[1, "_pe_for_value"] == 20.0
    pillars = pillar_percentiles(df, winsorize=(0.0, 1.0))
    assert "value_pe_rung" in pillars.columns
    assert pillars["value"].notna().all()


def test_financials_skip_ev_and_renormalize():
    df = _toy_market()
    framed = value_metric_frame(df)
    fin = framed[framed["sector"] == "Financials"]
    assert (fin["value_ev_rung"] == "inapplicable").all()
    pillars = pillar_percentiles(df, winsorize=(0.0, 1.0))
    fin_p = pillars[pillars["sector"] == "Financials"]
    assert fin_p["value"].notna().all()
    assert (fin_p["value_n_metrics"] <= 2).all()


def test_negative_quality_not_treated_as_missing():
    df = _toy_market()
    pillars = pillar_percentiles(df, winsorize=(0.0, 1.0))
    # B has negative ROE/margin within Energy — should rank below A, not NaN
    assert pillars.loc[1, "quality"] < pillars.loc[0, "quality"]
    assert pillars.loc[1, "quality_n_metrics"] == 3


def test_negative_multiple_maps_to_worst_not_nan():
    df = _toy_market()
    df.loc[0, "pe_ttm"] = -5.0
    pillars = pillar_percentiles(df, winsorize=(0.0, 1.0))
    # Negative PE contributes 0 to value stack mean (not dropped as missing)
    assert pillars.loc[0, "value_n_metrics"] >= 2


def test_size_buckets_and_peer_keys():
    assert assign_size_bucket(300e9) == "mega"
    assert assign_size_bucket(50e9) == "large"
    assert assign_size_bucket(3e9) == "mid"
    assert assign_size_bucket(1.5e9) == "small"
    df = _toy_market()
    keys = peer_group_key(df.assign(size_bucket=df["market_cap"].map(assign_size_bucket)), peer_frame="sector_x_size")
    assert "Energy|mid" in set(keys)
    assert "Information Technology|mega" in set(keys)


def test_immutable_snapshot_store(tmp_path: Path):
    cfg = load_scoring_config()
    snap = run_snapshot(
        as_of=date(2026, 7, 22),
        market=FixtureMarketProvider(),
        social=FixtureSocialProvider(history_days=14),
        cfg=cfg,
        market_mode="fixture",
        social_mode="fixture",
    )
    path = persist_immutable(snap, root=tmp_path)
    assert path.exists()
    with pytest.raises(SnapshotExistsError):
        persist_immutable(snap, root=tmp_path)
    loaded = load_immutable(date(2026, 7, 22), root=tmp_path)
    assert loaded.universe_id == snap.universe_id
    assert "value_coverage" in loaded.standings.columns
    assert loaded.standings["value_ev_rung"].map(lambda v: v is None or isinstance(v, str)).all()
    assert loaded.meta["meta"]["social_is_fixture"] is True
    assert loaded.meta["meta"]["universe_as_of"]


def test_store_snapshot_validates_api_response(tmp_path: Path):
    from standing.web.app import SnapshotResponse, _serialize

    cfg = load_scoring_config()
    snap = run_snapshot(
        as_of=date(2026, 7, 22),
        market=FixtureMarketProvider(),
        social=FixtureSocialProvider(history_days=14),
        cfg=cfg,
        market_mode="fixture",
        social_mode="fixture",
    )
    persist_immutable(snap, root=tmp_path)
    loaded = load_immutable(date(2026, 7, 22), root=tmp_path).to_standing_snapshot()
    payload = _serialize(loaded)
    meta = {
        "as_of": loaded.as_of.isoformat(),
        "universe_id": loaded.universe_id,
        "methodology_version": loaded.methodology_version,
        "score_kind": loaded.score_kind,
        "placeholder": loaded.placeholder,
        "n_names": int(loaded.meta.get("n_names", len(payload["standings"]))),
        "low_confidence_sectors": list(loaded.meta.get("low_confidence_sectors") or []),
        "sector_counts": dict(loaded.meta.get("sector_counts") or {}),
        "market_provider": loaded.meta.get("market_provider", "unknown"),
        "social_provider": loaded.meta.get("social_provider", "unknown"),
    }
    validated = SnapshotResponse.model_validate(
        {"meta": meta, "standings": payload["standings"], "heat": payload["heat"]}
    )
    assert validated.standings
