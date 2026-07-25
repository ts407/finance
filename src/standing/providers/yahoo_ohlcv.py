"""Yahoo Finance chart API — free OHLCV fallback when Stooq is blocked."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pandas as pd

YAHOO_CHART_URL = (
    "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    "?interval=1d&range=2y"
)


def yahoo_symbol(ticker: str) -> str:
    return ticker.strip().upper()


def fetch_yahoo_bars(ticker: str, *, timeout_s: float = 30.0) -> pd.DataFrame | None:
    url = YAHOO_CHART_URL.format(symbol=yahoo_symbol(ticker))
    req = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; StandingResearchBot/0.1)",
            "Accept": "application/json",
        },
    )
    try:
        with urlopen(req, timeout=timeout_s) as resp:
            import json

            payload = json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, ValueError):
        return None

    results = (payload.get("chart") or {}).get("result") or []
    if not results:
        return None
    result = results[0]
    timestamps = result.get("timestamp") or []
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []
    rows = []
    for i, ts in enumerate(timestamps):
        close = closes[i] if i < len(closes) else None
        if close is None:
            continue
        vol = volumes[i] if i < len(volumes) else None
        day = datetime.fromtimestamp(int(ts), tz=timezone.utc).date()
        rows.append({"date": pd.Timestamp(day), "close": float(close), "volume": float(vol or 0)})
    if not rows:
        return None
    return pd.DataFrame(rows).sort_values("date").reset_index(drop=True)


def yahoo_features_for(ticker: str, *, as_of: date | None = None) -> dict[str, float | None] | None:
    from standing.providers.stooq.ohlcv import compute_ohlcv_features

    bars = fetch_yahoo_bars(ticker)
    if bars is None or bars.empty:
        return None
    return compute_ohlcv_features(bars, as_of=as_of)
