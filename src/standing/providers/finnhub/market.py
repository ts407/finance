"""Finnhub MarketProvider — live/cassette fundamentals + optional Stooq OHLCV."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from standing.providers.base import MarketProvider, ProviderMeta
from standing.providers.finnhub.client import FinnhubClient, FinnhubError
from standing.providers.finnhub.mapping import completeness, map_finnhub_row, rows_to_frame
from standing.providers.stooq.ohlcv import StooqOHLCV
from standing.universe.seeds import listing_lookup, load_seed_tickers


class FinnhubMarketProvider(MarketProvider, ProviderMeta):
    """
    Builds the Standing market frame from Finnhub free endpoints (+ Stooq OHLCV).

    Does **not** support arbitrary historical as_of in live mode.
    Intended for batch preview / adapter validation — not the scored desk default.
    """

    def __init__(
        self,
        *,
        client: FinnhubClient | None = None,
        ohlcv: StooqOHLCV | None = None,
        tickers: list[str] | None = None,
        seed_listings: dict[str, str] | None = None,
        allow_historical_as_of: bool = False,
    ):
        self._client = client or FinnhubClient()
        self._ohlcv = ohlcv
        self._tickers = tickers
        self._seed_listings = seed_listings or {}
        self._allow_historical_as_of = allow_historical_as_of
        self._last_completeness: dict[str, Any] = {}

    @classmethod
    def from_env(
        cls,
        *,
        cassette_dir: Path | str | None = None,
        allow_network: bool | None = None,
        use_stooq: bool = True,
    ) -> FinnhubMarketProvider:
        cdir = Path(cassette_dir) if cassette_dir else None
        if cdir is None and os.environ.get("STANDING_FINNHUB_CASSETTES"):
            cdir = Path(os.environ["STANDING_FINNHUB_CASSETTES"])
        net = allow_network
        if net is None:
            net = os.environ.get("STANDING_ALLOW_NETWORK", "1") not in ("0", "false", "False")
        client = FinnhubClient(
            cassette_dir=cdir,
            allow_network=net,
        )
        ohlcv = None
        if use_stooq:
            stooq_dir = None
            if os.environ.get("STANDING_STOOQ_CASSETTES"):
                stooq_dir = Path(os.environ["STANDING_STOOQ_CASSETTES"])
            elif cdir is not None:
                # sibling ../stooq when using tests/cassettes/finnhub
                sibling = cdir.parent / "stooq"
                stooq_dir = sibling if sibling.exists() else None
            ohlcv = StooqOHLCV(cassette_dir=stooq_dir, allow_network=net)
        seeds = listing_lookup()
        # Desk default: compact fixture universe (seed lists are 100s of names — too slow for free tier)
        from standing.providers.market_fixture import FIXTURE_TICKERS

        desk_tickers = [t for t, _, _ in FIXTURE_TICKERS]
        return cls(
            client=client,
            ohlcv=ohlcv,
            tickers=desk_tickers,
            seed_listings=seeds,
            # Fundamentals are "as of now"; OHLCV still respects as_of. Allow desk date picks.
            allow_historical_as_of=True,
        )

    def name(self) -> str:
        return "finnhub-market"

    def is_fixture(self) -> bool:
        return False

    def supports_historical(self) -> bool:
        return self._allow_historical_as_of

    def metadata(self) -> dict[str, Any]:
        return {
            "placeholder_methodology": True,
            "supports_historical": self.supports_historical(),
            "ohlcv": self._ohlcv.metadata() if self._ohlcv else None,
            "cassette_dir": str(self._client.cassette_dir) if self._client.cassette_dir else None,
            "last_completeness": self._last_completeness,
            "scored_desk_default": False,
        }

    def fetch(self, as_of: date, tickers: list[str] | None = None) -> pd.DataFrame:
        if not self.supports_historical() and as_of != date.today():
            raise FinnhubError(
                f"Live Finnhub provider refuses historical as_of={as_of.isoformat()}; "
                "use fixtures for arbitrary dates or a stamped snapshot store."
            )
        wanted = tickers if tickers is not None else self._tickers
        if not wanted:
            wanted = load_seed_tickers()
        rows: list[dict[str, Any]] = []
        errors: list[str] = []
        for ticker in wanted:
            try:
                metric = self._client.company_basic_financials(ticker)
                profile = self._client.company_profile2(ticker)
            except FinnhubError as exc:
                errors.append(f"{ticker}: {exc}")
                continue
            ohlcv_feats = None
            if self._ohlcv is not None:
                ohlcv_feats = self._ohlcv.features_for(ticker, as_of=as_of)
            row = map_finnhub_row(
                ticker=ticker,
                as_of_iso=as_of.isoformat(),
                metric_payload=metric,
                profile_payload=profile,
                seed_listing=self._seed_listings.get(ticker.upper()),
                ohlcv=ohlcv_feats,
            )
            if row.get("sector") is None:
                errors.append(f"{ticker}: unmapped sector")
                continue
            rows.append(row)
        df = rows_to_frame(rows)
        self._last_completeness = completeness(df)
        self._last_completeness["errors"] = errors
        # Drop rows that fail hard admission prerequisites only at universe layer;
        # here keep schema-valid rows even with NaNs.
        return df.reset_index(drop=True)
