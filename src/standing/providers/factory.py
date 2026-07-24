"""Build market/social providers from a mode string (CLI / web)."""

from __future__ import annotations

from typing import Literal

from standing.providers.base import MarketProvider, SocialProvider
from standing.providers.bluesky import BlueskySocialProvider
from standing.providers.composite_social import CompositeSocialProvider
from standing.providers.market_fixture import FixtureMarketProvider
from standing.providers.social_fixture import FixtureSocialProvider
from standing.providers.wikipedia_pageviews import WikipediaPageviewsProvider

SocialMode = Literal["fixture", "wikipedia", "bluesky", "open", "all"]
SOCIAL_MODES: tuple[str, ...] = ("fixture", "wikipedia", "bluesky", "open", "all")


def build_market_provider() -> MarketProvider:
    """Live market adapters (Finnhub/Stooq) land later — fixture remains default."""
    return FixtureMarketProvider()


def build_social_provider(
    mode: str = "fixture",
    *,
    history_days: int = 14,
    tickers: list[str] | None = None,
) -> SocialProvider:
    mode = (mode or "fixture").lower().strip()
    if mode not in SOCIAL_MODES:
        raise ValueError(f"Unknown social mode {mode!r}; expected one of {SOCIAL_MODES}")

    fixture = FixtureSocialProvider(history_days=history_days)
    wiki = WikipediaPageviewsProvider(tickers=tickers, history_days=history_days)
    bluesky = BlueskySocialProvider(tickers=tickers, history_days=history_days)

    if mode == "fixture":
        return fixture
    if mode == "wikipedia":
        return wiki
    if mode == "bluesky":
        return bluesky
    if mode == "open":
        return CompositeSocialProvider([wiki, bluesky], name="open-attention")
    # all = fixtures (Reddit/ST stubs) + open live paths
    return CompositeSocialProvider([fixture, wiki, bluesky], name="all-social")
