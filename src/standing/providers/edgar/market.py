"""Live MarketProvider: SEC EDGAR fundamentals + Yahoo/Stooq OHLCV."""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from standing.providers.base import MarketProvider, ProviderMeta
from standing.providers.cache import DiskCache
from standing.providers.edgar.client import EdgarClient
from standing.providers.edgar.fundamentals import extract_fundamentals
from standing.providers.market_fixture import FIXTURE_TICKERS


def _fixture_meta() -> dict[str, tuple[str, str]]:
    return {t: (sector, listing) for t, sector, listing in FIXTURE_TICKERS}


class EdgarMarketProvider(MarketProvider, ProviderMeta):
    def __init__(
        self,
        *,
        client: EdgarClient | None = None,
        tickers: list[str] | None = None,
        cache: DiskCache | None = None,
    ):
        self._cache = cache if cache is not None else DiskCache(ttl_seconds=24 * 3600)
        self._client = client or EdgarClient(cache=self._cache)
        meta = _fixture_meta()
        if tickers is None:
            tickers = list(meta.keys())
        self._tickers = [t.upper() for t in tickers]
        self._meta = meta
        self._last: dict[str, Any] = {}

    def name(self) -> str:
        return "edgar-yahoo-market"

    def is_fixture(self) -> bool:
        return False

    def metadata(self) -> dict[str, Any]:
        return {
            "fundamentals": "sec-edgar-companyconcept",
            "ohlcv": "yahoo (stooq attempted upstream via features)",
            "point_in_time": "filed <= as_of",
            "last": self._last,
        }

    def fetch(self, as_of: date, tickers: list[str] | None = None) -> pd.DataFrame:
        wanted = [t.upper() for t in (tickers or self._tickers)]
        rows: list[dict[str, Any]] = []
        errors: list[str] = []
        for ticker in wanted:
            sector, listing = self._meta.get(ticker, ("Information Technology", "US"))
            try:
                row = extract_fundamentals(
                    self._client,
                    ticker=ticker,
                    as_of=as_of,
                    sector=sector,
                    listing=listing,
                )
            except Exception as exc:  # noqa: BLE001 — keep desk resilient
                errors.append(f"{ticker}: {exc}")
                continue
            if row is None:
                errors.append(f"{ticker}: no CIK/facts")
                continue
            # Drop internal debug blob from frame
            row.pop("_edgar", None)
            # Admission needs finite caps; skip thin rows
            if row.get("market_cap") is None or row.get("adv_20d") is None:
                errors.append(f"{ticker}: missing market_cap/adv")
                continue
            rows.append(row)

        self._last = {"n": len(rows), "errors": errors[:20], "error_n": len(errors)}
        if not rows:
            return pd.DataFrame(
                columns=[
                    "ticker",
                    "sector",
                    "listing",
                    "market_cap",
                    "adv_20d",
                    "pe_ttm",
                    "pb",
                    "ev_ebitda",
                    "ev_ebit",
                    "ev_sales",
                    "roe",
                    "operating_margin",
                    "revenue_growth_yoy",
                    "ret_1m",
                    "ret_3m",
                    "ret_6m",
                    "relative_volume",
                    "as_of",
                ]
            )
        return pd.DataFrame(rows).reset_index(drop=True)
