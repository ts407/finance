"""Provider factory — scored desk stays on fixtures by default."""

from __future__ import annotations

import os
from pathlib import Path

from standing.providers.base import MarketProvider, SocialProvider
from standing.providers.finnhub.market import FinnhubMarketProvider
from standing.providers.market_fixture import FixtureMarketProvider
from standing.providers.social_fixture import FixtureSocialProvider


def make_market_provider(
    name: str | None = None,
    *,
    cassette_dir: Path | str | None = None,
) -> MarketProvider:
    """
    Resolve market provider.

    Default: fixture (scored desk / CI).
    `finnhub` is for adapter preview / batch validation only.
    """
    key = (name or os.environ.get("STANDING_MARKET_PROVIDER") or "fixture").strip().lower()
    if key in ("fixture", "fixtures", "synth"):
        return FixtureMarketProvider()
    if key in ("finnhub", "live-market", "live"):
        # Cassette-driven preview stays offline unless a key is present.
        allow_network = None
        if cassette_dir is not None and not os.environ.get("FINNHUB_API_KEY"):
            allow_network = False
        return FinnhubMarketProvider.from_env(
            cassette_dir=cassette_dir,
            allow_network=allow_network,
        )
    raise ValueError(f"Unknown market provider: {key!r}")


def make_social_provider(
    name: str | None = None,
    *,
    history_days: int = 14,
) -> SocialProvider:
    key = (name or os.environ.get("STANDING_SOCIAL_PROVIDER") or "fixture").strip().lower()
    if key in ("fixture", "fixtures", "synth"):
        return FixtureSocialProvider(history_days=history_days)
    raise ValueError(
        f"Unknown social provider: {key!r} (live social gated — fixture only in v1)"
    )
