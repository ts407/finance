from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Iterable

import pandas as pd

from standing.config import ROOT
from standing.providers.stooq.ohlcv import compute_ohlcv_features
from standing.providers.yahoo.ohlcv import YahooOHLCV

DEFAULT_OHLCV_CACHE = ROOT / "artifacts" / "market" / "ohlcv"


class OHLCVStore:
    """
    Cached daily OHLCV panel for Track M.

    Bars are fetched via Yahoo (default) and written under artifacts/market/ohlcv/.
    Feature extraction reuses Stooq helper semantics (21/63/126 trading-day returns).
    """

    def __init__(
        self,
        *,
        cache_dir: Path | None = None,
        allow_network: bool = True,
        period1: int = 1420070400,  # 2015-01-01 — multi-year depth
    ):
        self.cache_dir = cache_dir or DEFAULT_OHLCV_CACHE
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._client = YahooOHLCV(
            cache_dir=self.cache_dir,
            allow_network=allow_network,
            period1=period1,
        )

    def fetch_many(self, tickers: Iterable[str]) -> dict[str, pd.DataFrame]:
        out: dict[str, pd.DataFrame] = {}
        for t in tickers:
            bars = self._client.load_bars(t)
            if bars is not None and not bars.empty:
                out[t.upper()] = bars
        return out

    def features_as_of(self, ticker: str, as_of: date) -> dict[str, float | None] | None:
        bars = self._client.load_bars(ticker)
        if bars is None or bars.empty:
            return None
        return compute_ohlcv_features(bars, as_of=as_of)

    def panel_features(
        self,
        tickers: list[str],
        as_of_dates: list[date],
        *,
        sectors: dict[str, str] | None = None,
    ) -> pd.DataFrame:
        """Long panel: one row per (as_of, ticker) with momentum feature columns."""
        rows: list[dict] = []
        for t in tickers:
            bars = self._client.load_bars(t)
            if bars is None or bars.empty:
                continue
            for d in as_of_dates:
                feats = compute_ohlcv_features(bars, as_of=d)
                if feats.get("ret_1m") is None and feats.get("ret_3m") is None:
                    continue
                row = {
                    "as_of": d.isoformat(),
                    "ticker": t.upper(),
                    "sector": (sectors or {}).get(t.upper(), "Unknown"),
                    **feats,
                }
                rows.append(row)
        return pd.DataFrame(rows)
