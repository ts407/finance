"""Stooq OHLCV overlay on a base MarketProvider (fixture or Finnhub).

Gives real returns / ADV / relative volume without an API key.
Fundamentals stay on the base provider until Finnhub (or EDGAR) is wired with a key.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from standing.providers.base import MarketProvider, ProviderMeta
from standing.providers.market_fixture import FixtureMarketProvider
from standing.providers.stooq.ohlcv import StooqOHLCV


class StooqOverlayMarketProvider(MarketProvider, ProviderMeta):
    """
    Real OHLCV (Stooq, with Yahoo fallback) over a fundamentals base.

    Name kept for config compatibility; source may be stooq or yahoo.
    """
    def __init__(
        self,
        *,
        base: MarketProvider | None = None,
        ohlcv: StooqOHLCV | None = None,
        tickers: list[str] | None = None,
    ):
        self._base = base or FixtureMarketProvider()
        self._ohlcv = ohlcv or StooqOHLCV()
        self._tickers = tickers
        self._last_overlay: dict[str, Any] = {}

    def name(self) -> str:
        base_name = getattr(self._base, "name", lambda: "base")()
        return f"stooq-overlay/{base_name}"

    def is_fixture(self) -> bool:
        # Mixed: fundamentals may be fixture, OHLCV is live.
        return False

    def metadata(self) -> dict[str, Any]:
        return {
            "base": getattr(self._base, "metadata", lambda: {})(),
            "base_name": getattr(self._base, "name", lambda: "base")(),
            "ohlcv": self._ohlcv.metadata(),
            "last_overlay": self._last_overlay,
            "note": "Stooq supplies ret_*/adv_20d/relative_volume; fundamentals from base",
        }

    def fetch(self, as_of: date, tickers: list[str] | None = None) -> pd.DataFrame:
        wanted = tickers if tickers is not None else self._tickers
        base_df = self._base.fetch(as_of, tickers=wanted)
        if base_df.empty:
            return base_df

        overlaid = 0
        missing = 0
        rows = []
        for _, row in base_df.iterrows():
            data = row.to_dict()
            feats = self._ohlcv.features_for(str(data["ticker"]), as_of=as_of)
            if feats:
                for key in ("ret_1m", "ret_3m", "ret_6m", "adv_20d", "relative_volume"):
                    val = feats.get(key)
                    if val is not None:
                        data[key] = float(val)
                overlaid += 1
            else:
                missing += 1
            data["as_of"] = as_of.isoformat()
            rows.append(data)

        self._last_overlay = {
            "n": len(rows),
            "overlaid": overlaid,
            "missing_ohlcv": missing,
            "as_of": as_of.isoformat(),
        }
        return pd.DataFrame(rows).reset_index(drop=True)
