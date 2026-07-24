from __future__ import annotations

import json
from datetime import date

import pandas as pd

from standing.pipeline.snapshot import run_snapshot
from standing.providers import (
    BlueskySocialProvider,
    CompositeSocialProvider,
    FetchCursor,
    FixtureMarketProvider,
    FixtureSocialProvider,
    WikipediaPageviewsProvider,
    build_social_provider,
)
from standing.providers.schema import SOCIAL_COLUMNS, assert_social_contract
from standing.config import load_scoring_config


def _wiki_fetcher(url: str, headers=None):
    # Minimal synthetic Wikimedia response for Apple Inc.
    assert "Apple_Inc." in url or "Nvidia" in url
    article = "Apple_Inc." if "Apple_Inc." in url else "Nvidia"
    return {
        "items": [
            {
                "article": article,
                "timestamp": "2026072000",
                "views": 5000 if article.startswith("Apple") else 8000,
            },
            {
                "article": article,
                "timestamp": "2026072100",
                "views": 5200 if article.startswith("Apple") else 8100,
            },
            {
                "article": article,
                "timestamp": "2026072200",
                "views": 5400 if article.startswith("Apple") else 8200,
            },
        ]
    }


def _bluesky_fetcher(url: str, headers=None):
    ticker = "AAPL" if "%24AAPL" in url or "$AAPL" in url else "NVDA"
    return {
        "posts": [
            {
                "likeCount": 3,
                "record": {
                    "createdAt": "2026-07-21T12:00:00.000Z",
                    "text": f"${ticker} looks bullish into earnings",
                },
            },
            {
                "likeCount": 1,
                "record": {
                    "createdAt": "2026-07-22T09:00:00.000Z",
                    "text": f"Bearish on ${ticker} after dump",
                },
            },
        ],
        "cursor": None,
    }


def test_wikipedia_provider_contract():
    provider = WikipediaPageviewsProvider(
        tickers=["AAPL", "NVDA"],
        history_days=3,
        fetcher=_wiki_fetcher,
    )
    df, cursor = provider.fetch_since(FetchCursor(as_of=date(2026, 7, 22)))
    assert_social_contract(df)
    assert set(df["source_id"]) == {"wikipedia_pageviews"}
    assert set(df["ticker"]) == {"AAPL", "NVDA"}
    assert len(df) == 6
    assert cursor.as_of == date(2026, 7, 22)
    assert provider.is_fixture() is False


def test_bluesky_provider_contract():
    provider = BlueskySocialProvider(
        tickers=["AAPL", "NVDA"],
        history_days=3,
        max_posts_per_ticker=10,
        fetcher=_bluesky_fetcher,
    )
    df, cursor = provider.fetch_since(FetchCursor(as_of=date(2026, 7, 22)))
    assert_social_contract(df)
    assert set(df["source_id"]) == {"bluesky"}
    assert set(df["ticker"]) == {"AAPL", "NVDA"}
    # 2 posts × 2 tickers on distinct days → 4 rows
    assert len(df) == 4
    assert df["mention_count"].sum() == 4
    assert cursor.token.startswith("bluesky:")


def test_composite_and_factory_modes():
    fixture = FixtureSocialProvider(history_days=3)
    wiki = WikipediaPageviewsProvider(tickers=["AAPL"], history_days=3, fetcher=_wiki_fetcher)
    composite = CompositeSocialProvider([fixture, wiki], name="test-composite")
    df, _ = composite.fetch_since(FetchCursor(as_of=date(2026, 7, 22)))
    assert_social_contract(df)
    assert "wikipedia_pageviews" in set(df["source_id"])
    assert {"reddit", "reddit_wsb", "stocktwits"} & set(df["source_id"])

    built = build_social_provider("fixture", history_days=3)
    assert built.name() == "fixture-social"
    assert build_social_provider("wikipedia", history_days=3, tickers=["AAPL"]).name() == (
        "wikipedia-pageviews"
    )
    assert build_social_provider("open", history_days=3, tickers=["AAPL"]).name() == "open-attention"


def test_open_social_snapshot_with_mocks(monkeypatch):
    # Patch live constructors used by factory so snapshot stays offline.
    import standing.providers.factory as factory

    monkeypatch.setattr(
        factory,
        "WikipediaPageviewsProvider",
        lambda **kw: WikipediaPageviewsProvider(
            tickers=["AAPL", "NVDA"], history_days=kw.get("history_days", 3), fetcher=_wiki_fetcher
        ),
    )
    monkeypatch.setattr(
        factory,
        "BlueskySocialProvider",
        lambda **kw: BlueskySocialProvider(
            tickers=["AAPL", "NVDA"],
            history_days=kw.get("history_days", 3),
            fetcher=_bluesky_fetcher,
        ),
    )
    cfg = load_scoring_config()
    snap = run_snapshot(
        as_of=date(2026, 7, 22),
        market=FixtureMarketProvider(),
        social=factory.build_social_provider("open", history_days=3),
        cfg=cfg,
    )
    assert snap.meta["social_provider"] == "open-attention"
    assert len(snap.standings) > 0
    assert set(SOCIAL_COLUMNS)  # contract module import smoke
