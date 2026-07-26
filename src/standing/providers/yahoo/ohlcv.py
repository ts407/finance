"""Yahoo Finance daily OHLCV — free multi-year backfill path for Track M."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"


def yahoo_symbol(ticker: str) -> str:
    t = ticker.strip().upper()
    # Common ADR / class share mappings can be added later; Yahoo uses bare US tickers.
    return t


def bars_from_chart_payload(payload: dict[str, Any]) -> pd.DataFrame:
    results = (payload.get("chart") or {}).get("result") or []
    if not results:
        err = ((payload.get("chart") or {}).get("error")) or "empty chart result"
        raise ValueError(f"Yahoo chart error: {err}")
    result = results[0]
    ts = result.get("timestamp") or []
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    closes = quote.get("close") or []
    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    volumes = quote.get("volume") or []
    rows = []
    for i, t in enumerate(ts):
        c = closes[i] if i < len(closes) else None
        if c is None:
            continue
        rows.append(
            {
                "date": datetime.fromtimestamp(int(t), tz=timezone.utc).date().isoformat(),
                "open": opens[i] if i < len(opens) else None,
                "high": highs[i] if i < len(highs) else None,
                "low": lows[i] if i < len(lows) else None,
                "close": float(c),
                "volume": float(volumes[i]) if i < len(volumes) and volumes[i] is not None else 0.0,
            }
        )
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date").reset_index(drop=True)


class YahooOHLCV:
    """Fetch or load Yahoo daily bars; cassette_dir enables offline golden tests."""

    def __init__(
        self,
        *,
        cassette_dir: Path | None = None,
        cache_dir: Path | None = None,
        timeout_s: float = 30.0,
        allow_network: bool = True,
        period1: int = 1577836800,  # 2020-01-01 UTC
    ):
        self._cassette_dir = cassette_dir
        self._cache_dir = cache_dir
        self._timeout_s = timeout_s
        self._allow_network = allow_network
        self._period1 = period1

    def _cache_path(self, ticker: str) -> Path | None:
        if self._cache_dir is None:
            return None
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        return self._cache_dir / f"{yahoo_symbol(ticker)}.csv"

    def load_bars(self, ticker: str) -> pd.DataFrame | None:
        sym = yahoo_symbol(ticker)
        if self._cassette_dir is not None:
            for name in (f"{sym}.csv", f"{sym.lower()}.csv", f"{ticker.lower()}.csv"):
                path = self._cassette_dir / name
                if path.exists():
                    df = pd.read_csv(path)
                    df["date"] = pd.to_datetime(df["date"])
                    return df.sort_values("date").reset_index(drop=True)

        cache = self._cache_path(ticker)
        if cache is not None and cache.exists():
            df = pd.read_csv(cache)
            df["date"] = pd.to_datetime(df["date"])
            return df.sort_values("date").reset_index(drop=True)

        if not self._allow_network:
            return None

        period2 = int(datetime.now(tz=timezone.utc).timestamp())
        qs = urlencode(
            {
                "period1": self._period1,
                "period2": period2,
                "interval": "1d",
                "events": "history",
            }
        )
        url = f"{YAHOO_CHART_URL.format(symbol=sym)}?{qs}"
        try:
            req = Request(url, headers={"User-Agent": "Mozilla/5.0 standing-research/0.1"})
            with urlopen(req, timeout=self._timeout_s) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            df = bars_from_chart_payload(payload)
        except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError, KeyError):
            return None
        if df is None or df.empty:
            return None
        if cache is not None:
            out = df.copy()
            out["date"] = out["date"].dt.strftime("%Y-%m-%d")
            out.to_csv(cache, index=False)
        return df

    def metadata(self) -> dict[str, Any]:
        return {
            "name": "yahoo-chart-daily",
            "cassette_dir": str(self._cassette_dir) if self._cassette_dir else None,
            "cache_dir": str(self._cache_dir) if self._cache_dir else None,
            "allow_network": self._allow_network,
            "period1": self._period1,
        }
