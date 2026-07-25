"""Stooq daily OHLCV helpers — free OHLCV path when Finnhub candles are premium."""

from __future__ import annotations

import io
from datetime import date
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pandas as pd

STOOQ_DAILY_URL = "https://stooq.com/q/d/l/?s={symbol}&i=d"


def stooq_symbol(ticker: str) -> str:
    t = ticker.strip().upper()
    if t.endswith(".US"):
        return t.lower()
    return f"{t.lower()}.us"


def parse_stooq_csv(text: str) -> pd.DataFrame:
    df = pd.read_csv(io.StringIO(text))
    # Normalize headers
    cols = {c.lower(): c for c in df.columns}
    rename = {}
    for want in ("date", "open", "high", "low", "close", "volume"):
        for c in df.columns:
            if c.lower() == want:
                rename[c] = want
                break
    df = df.rename(columns=rename)
    if "date" not in df.columns or "close" not in df.columns:
        raise ValueError(f"Unexpected Stooq CSV columns: {list(df.columns)}")
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    return df


def compute_ohlcv_features(df: pd.DataFrame, *, as_of: date | None = None) -> dict[str, float | None]:
    """Exact ret_1m/3m/6m, dollar ADV_20d, relative volume from daily bars."""
    if df.empty:
        return {
            "ret_1m": None,
            "ret_3m": None,
            "ret_6m": None,
            "adv_20d": None,
            "relative_volume": None,
            "last_price": None,
        }
    work = df.copy()
    if as_of is not None:
        work = work[work["date"] <= pd.Timestamp(as_of)]
    if work.empty:
        return {
            "ret_1m": None,
            "ret_3m": None,
            "ret_6m": None,
            "adv_20d": None,
            "relative_volume": None,
            "last_price": None,
        }

    closes = work["close"].astype(float)
    volumes = work["volume"].astype(float) if "volume" in work.columns else pd.Series(dtype=float)
    last = float(closes.iloc[-1])

    def total_return(trading_days: int) -> float | None:
        if len(closes) <= trading_days:
            return None
        base = float(closes.iloc[-(trading_days + 1)])
        if base == 0:
            return None
        return last / base - 1.0

    adv_20d = None
    relative_volume = None
    if not volumes.empty:
        dollar = closes * volumes
        window = dollar.iloc[-20:] if len(dollar) >= 20 else dollar
        if not window.empty:
            adv_20d = float(window.mean())
        vol_10 = volumes.iloc[-10:].mean() if len(volumes) >= 10 else None
        vol_60 = volumes.iloc[-60:].mean() if len(volumes) >= 60 else None
        if vol_10 is not None and vol_60 and vol_60 > 0:
            relative_volume = float(vol_10 / vol_60)

    return {
        "ret_1m": total_return(21),
        "ret_3m": total_return(63),
        "ret_6m": total_return(126),
        "adv_20d": adv_20d,
        "relative_volume": relative_volume,
        "last_price": last,
    }


class StooqOHLCV:
    """Fetch or load Stooq daily bars; cassette_dir enables offline golden tests."""

    def __init__(
        self,
        *,
        cassette_dir: Path | None = None,
        timeout_s: float = 30.0,
        allow_network: bool = True,
    ):
        self._cassette_dir = cassette_dir
        self._timeout_s = timeout_s
        self._allow_network = allow_network

    def load_bars(self, ticker: str) -> pd.DataFrame | None:
        sym = stooq_symbol(ticker)
        if self._cassette_dir is not None:
            path = self._cassette_dir / f"{sym}.csv"
            if path.exists():
                return parse_stooq_csv(path.read_text())
            # Also try bare ticker filename
            alt = self._cassette_dir / f"{ticker.lower()}.csv"
            if alt.exists():
                return parse_stooq_csv(alt.read_text())
        if not self._allow_network:
            return None
        url = STOOQ_DAILY_URL.format(symbol=sym)
        try:
            req = Request(url, headers={"User-Agent": "standing-research/0.1"})
            with urlopen(req, timeout=self._timeout_s) as resp:
                text = resp.read().decode("utf-8", errors="replace")
            if text.lstrip().startswith("<"):
                # JS challenge / HTML interstitial
                return None
            return parse_stooq_csv(text)
        except (HTTPError, URLError, TimeoutError, ValueError):
            return None

    def features_for(self, ticker: str, *, as_of: date | None = None) -> dict[str, float | None] | None:
        bars = self.load_bars(ticker)
        if bars is not None and not bars.empty:
            return compute_ohlcv_features(bars, as_of=as_of)
        # Stooq often serves a JS challenge from cloud IPs — fall back to Yahoo chart API.
        if self._allow_network:
            from standing.providers.yahoo_ohlcv import yahoo_features_for

            return yahoo_features_for(ticker, as_of=as_of)
        return None

    def metadata(self) -> dict[str, Any]:
        return {
            "name": "stooq-daily",
            "cassette_dir": str(self._cassette_dir) if self._cassette_dir else None,
            "allow_network": self._allow_network,
        }
