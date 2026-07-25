"""Sector × size peer buckets — dampens percentile drift when the universe expands."""

from __future__ import annotations

import pandas as pd

# Market-cap USD thresholds (inclusive lower bound of each bucket).
SIZE_BUCKET_EDGES: tuple[tuple[str, float], ...] = (
    ("mega", 200e9),
    ("large", 10e9),
    ("mid", 2e9),
    ("small", 0.0),
)


def assign_size_bucket(market_cap: float | None) -> str:
    if market_cap is None or (isinstance(market_cap, float) and market_cap != market_cap):
        return "unknown"
    cap = float(market_cap)
    for name, lower in SIZE_BUCKET_EDGES:
        if cap >= lower:
            return name
    return "small"


def attach_size_buckets(df: pd.DataFrame, *, cap_col: str = "market_cap") -> pd.DataFrame:
    out = df.copy()
    if cap_col not in out.columns:
        out["size_bucket"] = "unknown"
        return out
    out["size_bucket"] = out[cap_col].map(assign_size_bucket)
    return out


def peer_group_key(
    df: pd.DataFrame,
    *,
    peer_frame: str = "sector",
    sector_col: str = "sector",
) -> pd.Series:
    """
    Peer key for percentile ranking.

    - sector: GICS-11 only (current default)
    - sector_x_size: GICS-11 × mega/large/mid/small (planned for 400–500 expansion)
    """
    frame = (peer_frame or "sector").strip().lower()
    if frame in ("sector_x_size", "sector×size", "gics-11×size_bucket", "gics11_x_size"):
        if "size_bucket" not in df.columns:
            work = attach_size_buckets(df)
            buckets = work["size_bucket"]
        else:
            buckets = df["size_bucket"]
        return df[sector_col].astype(str) + "|" + buckets.astype(str)
    return df[sector_col].astype(str)
