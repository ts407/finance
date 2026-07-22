"""Map Finnhub metric + profile2 payloads onto the Standing market frame.

Golden-cassette tested. Live transport is separate (see market.py).
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from standing.universe.gics_map import map_finnhub_industry

# Standing MarketProvider columns (required contract).
MARKET_COLUMNS = [
    "ticker",
    "sector",
    "listing",
    "market_cap",
    "adv_20d",
    "pe_ttm",
    "pb",
    "ev_ebitda",
    "roe",
    "operating_margin",
    "revenue_growth_yoy",
    "ret_1m",
    "ret_3m",
    "ret_6m",
    "relative_volume",
    "as_of",
]

# metric key → standing column (ratios / levels before unit normalize).
METRIC_FIELD_MAP: dict[str, str] = {
    "peTTM": "pe_ttm",
    "pb": "pb",
    "currentEv/ebitdaAnnual": "ev_ebitda",
    "enterpriseValueMultipleTTM": "ev_ebitda",  # secondary; applied if primary missing
    "roeTTM": "roe",
    "operatingMarginTTM": "operating_margin",
    "revenueGrowthTTMYoy": "revenue_growth_yoy",
}

# Percent-looking fields: if |value| exceeds threshold, treat as percent and /100.
PERCENT_FIELDS: dict[str, float] = {
    "roe": 2.0,
    "operating_margin": 2.0,
    "revenue_growth_yoy": 1.0,
    "ret_1m": 2.0,
    "ret_3m": 2.0,
    "ret_6m": 2.0,
}


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(out):
        return None
    return out


def normalize_ratio_or_percent(value: float | None, *, threshold: float) -> float | None:
    """Finnhub mixes ratios and percent-scaled numbers; normalize to decimal ratio."""
    if value is None:
        return None
    if abs(value) > threshold:
        return value / 100.0
    return value


def _pick_metric(metric: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        if key in metric and metric[key] is not None:
            return _as_float(metric[key])
    return None


def market_cap_usd(profile: dict[str, Any], metric: dict[str, Any]) -> float | None:
    """Finnhub marketCapitalization is typically in millions USD."""
    raw = _as_float(profile.get("marketCapitalization"))
    if raw is None:
        raw = _as_float(metric.get("marketCapitalization"))
    if raw is None:
        return None
    # Values already in full USD are rare; millions are the free-tier convention.
    if raw < 1e7:
        return raw * 1_000_000.0
    return raw


def listing_from_profile(profile: dict[str, Any], seed_listing: str | None = None) -> str:
    if seed_listing in ("US", "ADR"):
        return seed_listing
    country = str(profile.get("country") or "").upper()
    exchange = str(profile.get("exchange") or "").upper()
    if country in ("US", "USA") or exchange in ("NASDAQ", "NYSE", "AMEX", "NYSE ARCA"):
        return "US"
    return "ADR"


def map_finnhub_row(
    *,
    ticker: str,
    as_of_iso: str,
    metric_payload: dict[str, Any],
    profile_payload: dict[str, Any],
    seed_listing: str | None = None,
    ohlcv: dict[str, float | None] | None = None,
) -> dict[str, Any]:
    """
    Build one Standing market row from Finnhub payloads (+ optional Stooq OHLCV overlays).

    `metric_payload` may be the raw API body `{metric, series, symbol, ...}` or the
    inner `metric` dict alone.
    """
    metric = metric_payload.get("metric") if "metric" in metric_payload else metric_payload
    if not isinstance(metric, dict):
        metric = {}
    profile = profile_payload or {}

    industry = profile.get("finnhubIndustry")
    sector = map_finnhub_industry(industry)

    row: dict[str, Any] = {
        "ticker": str(profile.get("ticker") or ticker).upper(),
        "sector": sector,
        "listing": listing_from_profile(profile, seed_listing),
        "market_cap": market_cap_usd(profile, metric),
        "pe_ttm": _pick_metric(metric, "peTTM"),
        "pb": _pick_metric(metric, "pb"),
        "ev_ebitda": _pick_metric(metric, "currentEv/ebitdaAnnual", "enterpriseValueMultipleTTM"),
        "roe": normalize_ratio_or_percent(
            _pick_metric(metric, "roeTTM"), threshold=PERCENT_FIELDS["roe"]
        ),
        "operating_margin": normalize_ratio_or_percent(
            _pick_metric(metric, "operatingMarginTTM"),
            threshold=PERCENT_FIELDS["operating_margin"],
        ),
        "revenue_growth_yoy": normalize_ratio_or_percent(
            _pick_metric(metric, "revenueGrowthTTMYoy"),
            threshold=PERCENT_FIELDS["revenue_growth_yoy"],
        ),
        "ret_1m": None,
        "ret_3m": None,
        "ret_6m": None,
        "adv_20d": None,
        "relative_volume": None,
        "as_of": as_of_iso,
    }

    # Momentum / ADV proxies from the same free metric call (used when Stooq absent).
    ret_3m_proxy = normalize_ratio_or_percent(
        _pick_metric(metric, "13WeekPriceReturnDaily"),
        threshold=PERCENT_FIELDS["ret_3m"],
    )
    ret_6m_proxy = normalize_ratio_or_percent(
        _pick_metric(metric, "26WeekPriceReturnDaily"),
        threshold=PERCENT_FIELDS["ret_6m"],
    )
    row["ret_3m"] = ret_3m_proxy
    row["ret_6m"] = ret_6m_proxy

    vol_10d = _pick_metric(metric, "10DayAverageTradingVolume")  # share millions
    last_price = _pick_metric(metric, "52WeekHigh")  # weak price proxy if no OHLCV
    # Prefer a dedicated price if present in metric dumps.
    for price_key in ("price", "lastPrice", "currentPrice"):
        p = _pick_metric(metric, price_key)
        if p is not None:
            last_price = p
            break
    if vol_10d is not None and last_price is not None:
        row["adv_20d"] = vol_10d * 1_000_000.0 * last_price

    vol_3m = _pick_metric(metric, "3MonthAverageTradingVolume")  # share millions (approx quarterly)
    if vol_10d is not None and vol_3m is not None and vol_3m > 0:
        # 3M figure is cumulative-ish in Finnhub docs examples; normalize roughly to daily.
        daily_3m = vol_3m / 63.0
        if daily_3m > 0:
            row["relative_volume"] = vol_10d / daily_3m

    if ohlcv:
        for key in ("ret_1m", "ret_3m", "ret_6m", "adv_20d", "relative_volume"):
            if ohlcv.get(key) is not None:
                row[key] = ohlcv[key]
        if ohlcv.get("last_price") is not None and vol_10d is not None and row["adv_20d"] is None:
            row["adv_20d"] = vol_10d * 1_000_000.0 * float(ohlcv["last_price"])

    return row


def rows_to_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    for col in MARKET_COLUMNS:
        if col not in df.columns:
            df[col] = None
    return df[MARKET_COLUMNS].copy()


def completeness(df: pd.DataFrame) -> dict[str, Any]:
    """Per-column non-null rates — adapter validation surface."""
    if df.empty:
        return {"n": 0, "columns": {}}
    rates = {c: float(df[c].notna().mean()) for c in MARKET_COLUMNS if c != "as_of"}
    return {"n": int(len(df)), "columns": rates}
