"""Build market/social providers from mode strings (CLI / web / env)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from standing.providers.base import MarketProvider, SocialProvider
from standing.providers.bluesky import BlueskySocialProvider
from standing.providers.cache import DiskCache
from standing.providers.composite_social import CompositeSocialProvider
from standing.providers.edgar.market import EdgarMarketProvider
from standing.providers.finnhub.market import FinnhubMarketProvider
from standing.providers.market_fixture import FixtureMarketProvider
from standing.providers.social_fixture import FixtureSocialProvider
from standing.providers.stooq.ohlcv import StooqOHLCV
from standing.providers.stooq_overlay import StooqOverlayMarketProvider
from standing.providers.wikipedia_pageviews import WikipediaPageviewsProvider

SocialMode = Literal["fixture", "wikipedia", "bluesky", "open", "all"]
MarketMode = Literal["fixture", "stooq", "edgar", "finnhub", "live"]

SOCIAL_MODES: tuple[str, ...] = ("fixture", "wikipedia", "bluesky", "open", "all")
MARKET_MODES: tuple[str, ...] = ("fixture", "stooq", "edgar", "finnhub", "live")


def _live_cache() -> DiskCache | None:
    if os.environ.get("STANDING_DISABLE_CACHE") in ("1", "true", "True"):
        return None
    return DiskCache()


def _resolve_full_universe(full_universe: bool | None) -> bool:
    """Full seed universe (~170 names) vs the compact fixture desk (~54)."""
    if full_universe is not None:
        return full_universe
    return os.environ.get("STANDING_UNIVERSE", "desk").strip().lower() in ("seed", "full", "all")


def build_market_provider(
    mode: str | None = None,
    *,
    cassette_dir: Path | str | None = None,
    tickers: list[str] | None = None,
    full_universe: bool | None = None,
) -> MarketProvider:
    """
    Market modes:
    - fixture: synthetic
    - stooq: fixture fundamentals + live OHLCV overlay
    - edgar: SEC EDGAR fundamentals + Yahoo OHLCV (no API key)
    - finnhub: Finnhub fundamentals + OHLCV (needs FINNHUB_API_KEY or cassettes)
    - live: finnhub if key else edgar

    ``full_universe`` (or ``STANDING_UNIVERSE=seed``) expands the live desk from the
    compact fixture set to the full seed universe (SP500 ∪ NDX100 ∪ liquid ADRs).
    Ignored when explicit ``tickers`` are supplied.
    """
    key = (mode or os.environ.get("STANDING_MARKET") or os.environ.get("STANDING_MARKET_PROVIDER") or "fixture")
    key = key.strip().lower()
    if key not in MARKET_MODES and key not in ("fixtures", "synth", "live-market"):
        raise ValueError(f"Unknown market mode {key!r}; expected one of {MARKET_MODES}")

    seed_universe = _resolve_full_universe(full_universe) and tickers is None

    if key in ("fixture", "fixtures", "synth"):
        return FixtureMarketProvider()

    if key in ("live", "live-market"):
        if os.environ.get("FINNHUB_API_KEY") or cassette_dir:
            key = "finnhub"
        else:
            key = "edgar"

    if key == "stooq":
        return StooqOverlayMarketProvider(
            base=FixtureMarketProvider(),
            ohlcv=StooqOHLCV(),
            tickers=tickers,
        )

    if key == "edgar":
        return EdgarMarketProvider(
            tickers=tickers,
            cache=_live_cache() or DiskCache(),
            full_universe=seed_universe,
        )

    if key == "finnhub":
        return FinnhubMarketProvider.from_env(cassette_dir=cassette_dir, full_universe=seed_universe)

    raise ValueError(f"Unknown market mode {key!r}")


def build_social_provider(
    mode: str | None = None,
    *,
    history_days: int = 14,
    tickers: list[str] | None = None,
    full_universe: bool | None = None,
) -> SocialProvider:
    key = (mode or os.environ.get("STANDING_SOCIAL") or os.environ.get("STANDING_SOCIAL_PROVIDER") or "fixture")
    key = key.strip().lower()
    if key not in SOCIAL_MODES:
        raise ValueError(f"Unknown social mode {key!r}; expected one of {SOCIAL_MODES}")

    if tickers is None and _resolve_full_universe(full_universe):
        from standing.universe.seeds import load_seed_tickers

        tickers = load_seed_tickers()

    cache = _live_cache() if key != "fixture" else None
    fixture = FixtureSocialProvider(history_days=history_days)
    wiki = WikipediaPageviewsProvider(tickers=tickers, history_days=history_days, cache=cache)
    bluesky = BlueskySocialProvider(
        tickers=tickers, history_days=history_days, cache=cache, max_posts_per_ticker=25
    )

    if key == "fixture":
        return fixture
    if key == "wikipedia":
        return wiki
    if key == "bluesky":
        return bluesky
    if key == "open":
        return CompositeSocialProvider([wiki, bluesky], name="open-attention")
    return CompositeSocialProvider([fixture, wiki, bluesky], name="all-social")


# Aliases expected by tests from the live-market-adapter branch
def make_market_provider(
    name: str | None = None,
    *,
    cassette_dir: Path | str | None = None,
) -> MarketProvider:
    return build_market_provider(name, cassette_dir=cassette_dir)


def make_social_provider(
    name: str | None = None,
    *,
    history_days: int = 14,
) -> SocialProvider:
    return build_social_provider(name, history_days=history_days)
