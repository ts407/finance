"""Golden-cassette tests for Finnhub mapping + Stooq OHLCV + seed universe."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from standing.providers.factory import make_market_provider, make_social_provider
from standing.providers.finnhub.client import FinnhubClient
from standing.providers.finnhub.mapping import map_finnhub_row
from standing.providers.finnhub.market import FinnhubMarketProvider
from standing.providers.stooq.ohlcv import StooqOHLCV, compute_ohlcv_features, parse_stooq_csv
from standing.universe.gics_map import map_finnhub_industry
from standing.universe.seeds import load_seed_frame, load_seed_tickers

CASSETTES = Path(__file__).resolve().parent / "cassettes"
FINNHUB_CASSETTES = CASSETTES / "finnhub"
STOOQ_CASSETTES = CASSETTES / "stooq"


def test_gics_map_technology():
    assert map_finnhub_industry("Technology") == "Information Technology"
    assert map_finnhub_industry("Health Care") == "Health Care"
    assert map_finnhub_industry("TotallyUnknownIndustryXYZ") is None


def test_map_finnhub_row_percent_normalize():
    metric = json.loads((FINNHUB_CASSETTES / "AAPL_metric.json").read_text())
    profile = json.loads((FINNHUB_CASSETTES / "AAPL_profile2.json").read_text())
    row = map_finnhub_row(
        ticker="AAPL",
        as_of_iso="2026-07-22",
        metric_payload=metric,
        profile_payload=profile,
        seed_listing="US",
    )
    assert row["ticker"] == "AAPL"
    assert row["sector"] == "Information Technology"
    assert row["listing"] == "US"
    assert row["pe_ttm"] == pytest.approx(32.4)
    assert row["pe_forward"] == pytest.approx(28.5)
    assert row["pb"] == pytest.approx(45.2)
    assert row["ev_ebitda"] == pytest.approx(22.5)
    # roeTTM 147 → 1.47; operatingMarginTTM 30.5 → 0.305
    assert row["roe"] == pytest.approx(1.47)
    assert row["operating_margin"] == pytest.approx(0.305)
    assert row["revenue_growth_yoy"] == pytest.approx(0.061)
    assert row["ret_3m"] == pytest.approx(0.085)
    assert row["ret_6m"] == pytest.approx(0.152)
    assert row["market_cap"] == pytest.approx(3_200_000_000_000.0)


def test_stooq_ohlcv_features_from_cassette():
    text = (STOOQ_CASSETTES / "aapl.us.csv").read_text()
    bars = parse_stooq_csv(text)
    feats = compute_ohlcv_features(bars, as_of=date(2026, 7, 22))
    assert feats["last_price"] is not None and feats["last_price"] > 0
    assert feats["ret_1m"] is not None
    assert feats["ret_3m"] is not None
    assert feats["ret_6m"] is not None
    assert feats["adv_20d"] is not None and feats["adv_20d"] > 0
    assert feats["relative_volume"] is not None


def test_finnhub_provider_cassette_offline():
    client = FinnhubClient(cassette_dir=FINNHUB_CASSETTES, allow_network=False)
    ohlcv = StooqOHLCV(cassette_dir=STOOQ_CASSETTES, allow_network=False)
    provider = FinnhubMarketProvider(
        client=client,
        ohlcv=ohlcv,
        tickers=["AAPL", "MSFT"],
        seed_listings={"AAPL": "US", "MSFT": "US"},
        allow_historical_as_of=True,
    )
    assert provider.supports_historical() is True
    assert provider.is_fixture() is False
    df = provider.fetch(date(2026, 7, 22))
    assert len(df) == 2
    assert set(df["ticker"]) == {"AAPL", "MSFT"}
    aapl = df.loc[df["ticker"] == "AAPL"].iloc[0]
    # Stooq overlays exact returns over metric proxies
    assert pd.notna(aapl["ret_1m"])
    assert pd.notna(aapl["adv_20d"])
    assert aapl["sector"] == "Information Technology"
    stats = provider.metadata()["last_completeness"]
    assert stats["n"] == 2
    assert stats["columns"]["pe_ttm"] == 1.0


def test_live_provider_refuses_historical_without_flag():
    client = FinnhubClient(cassette_dir=FINNHUB_CASSETTES, allow_network=False)
    provider = FinnhubMarketProvider(
        client=client,
        tickers=["AAPL"],
        allow_historical_as_of=False,
    )
    historical = date(2020, 1, 15)
    assert historical != date.today()
    with pytest.raises(Exception, match="refuses historical"):
        provider.fetch(historical)


def test_seed_universe_dedupe():
    frame = load_seed_frame()
    tickers = load_seed_tickers()
    assert len(tickers) == len(set(tickers))
    assert "AAPL" in tickers
    assert "ASML" in tickers
    # SP500 wins listing over later sets for shared names
    aapl = frame.loc[frame["ticker"] == "AAPL"].iloc[0]
    assert aapl["listing"] == "US"
    assert aapl["seed_set"] == "SP500"
    assert len(tickers) >= 100


def test_factory_defaults_to_fixture(monkeypatch):
    monkeypatch.delenv("STANDING_MARKET", raising=False)
    monkeypatch.delenv("STANDING_MARKET_PROVIDER", raising=False)
    monkeypatch.delenv("STANDING_SOCIAL", raising=False)
    monkeypatch.delenv("STANDING_SOCIAL_PROVIDER", raising=False)
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    m = make_market_provider()
    s = make_social_provider()
    assert m.name() == "fixture-market"
    assert s.name().startswith("fixture")


def test_factory_finnhub_from_cassettes(monkeypatch):
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    monkeypatch.setenv("STANDING_STOOQ_CASSETTES", str(STOOQ_CASSETTES))
    provider = make_market_provider("finnhub", cassette_dir=FINNHUB_CASSETTES)
    assert isinstance(provider, FinnhubMarketProvider)
    df = provider.fetch(date(2026, 7, 22), tickers=["AAPL"])
    assert len(df) == 1
    assert df.iloc[0]["ticker"] == "AAPL"
