from __future__ import annotations

import numpy as np
import pandas as pd

GICS_11 = [
    "Communication Services",
    "Consumer Discretionary",
    "Consumer Staples",
    "Energy",
    "Financials",
    "Health Care",
    "Industrials",
    "Information Technology",
    "Materials",
    "Real Estate",
    "Utilities",
]


def winsorize_series(s: pd.Series, lower: float = 0.01, upper: float = 0.99) -> pd.Series:
    if s.dropna().empty:
        return s
    lo, hi = s.quantile(lower), s.quantile(upper)
    return s.clip(lower=lo, upper=hi)


def _percentile_rank(s: pd.Series, higher_is_better: bool = True) -> pd.Series:
    """0–100 peer percentile; NaNs stay NaN."""
    valid = s.dropna()
    if valid.empty:
        return pd.Series(np.nan, index=s.index)
    # average rank → percentile in [0, 100]
    ranks = valid.rank(method="average", ascending=higher_is_better)
    pct = (ranks - 1) / max(len(valid) - 1, 1) * 100.0
    out = pd.Series(np.nan, index=s.index, dtype=float)
    out.loc[pct.index] = pct
    return out


def _sector_relative_percentile(
    df: pd.DataFrame,
    value_col: str,
    sector_col: str = "sector",
    higher_is_better: bool = True,
    winsorize: tuple[float, float] | None = (0.01, 0.99),
) -> pd.Series:
    parts: list[pd.Series] = []
    for _, group in df.groupby(sector_col, sort=False):
        vals = group[value_col]
        if winsorize is not None:
            vals = winsorize_series(vals, winsorize[0], winsorize[1])
        parts.append(_percentile_rank(vals, higher_is_better=higher_is_better))
    return pd.concat(parts).reindex(df.index)


def pillar_percentiles(
    df: pd.DataFrame,
    *,
    winsorize: tuple[float, float] = (0.01, 0.99),
) -> pd.DataFrame:
    """
    Compute sector-relative V / Q / M percentiles.

    Value inputs (cheaper = higher): pe_ttm, pb, ev_ebitda
    Quality inputs: roe, operating_margin, revenue_growth_yoy
    Momentum inputs: ret_1m, ret_3m, ret_6m, relative_volume
    """
    out = df[["ticker", "sector"]].copy()

    # Value — invert multiples (lower multiple → higher standing)
    value_parts = []
    for col in ("pe_ttm", "pb", "ev_ebitda"):
        # Exclude non-positive for P/E-like fields
        series = df[col].where(df[col] > 0)
        inv = 1.0 / series
        tmp = df[["sector"]].copy()
        tmp["_v"] = inv
        value_parts.append(
            _sector_relative_percentile(tmp, "_v", higher_is_better=True, winsorize=winsorize)
        )
    out["value"] = pd.concat(value_parts, axis=1).median(axis=1, skipna=True)

    # Quality
    quality_parts = []
    for col in ("roe", "operating_margin", "revenue_growth_yoy"):
        tmp = df[["sector"]].copy()
        tmp["_q"] = df[col]
        quality_parts.append(
            _sector_relative_percentile(tmp, "_q", higher_is_better=True, winsorize=winsorize)
        )
    out["quality"] = pd.concat(quality_parts, axis=1).median(axis=1, skipna=True)

    # Momentum (sector-relative primary)
    mom_parts = []
    for col in ("ret_1m", "ret_3m", "ret_6m", "relative_volume"):
        tmp = df[["sector"]].copy()
        tmp["_m"] = df[col]
        mom_parts.append(
            _sector_relative_percentile(tmp, "_m", higher_is_better=True, winsorize=winsorize)
        )
    out["momentum"] = pd.concat(mom_parts, axis=1).median(axis=1, skipna=True)

    # Secondary global momentum display field (not in composite)
    global_parts = []
    for col in ("ret_1m", "ret_3m", "ret_6m", "relative_volume"):
        vals = winsorize_series(df[col], winsorize[0], winsorize[1])
        global_parts.append(_percentile_rank(vals, higher_is_better=True))
    out["momentum_global"] = pd.concat(global_parts, axis=1).median(axis=1, skipna=True)

    return out


def compute_base_standing(
    pillars: pd.DataFrame,
    weights: dict[str, float] | None = None,
) -> pd.Series:
    """Equal-weight Composite Standing from V/Q/M (default)."""
    w = weights or {"value": 1 / 3, "quality": 1 / 3, "momentum": 1 / 3}
    cols = ["value", "quality", "momentum"]
    weight_vec = np.array([w[c] for c in cols], dtype=float)
    weight_vec = weight_vec / weight_vec.sum()
    mat = pillars[cols].to_numpy(dtype=float)
    # Do not silently renorm missing pillars — require all three for a base score
    complete = ~np.isnan(mat).any(axis=1)
    base = np.full(len(pillars), np.nan)
    base[complete] = mat[complete] @ weight_vec
    return pd.Series(base, index=pillars.index, name="composite_standing")


def sector_occupancy_flags(
    df: pd.DataFrame,
    min_names: int = 30,
    sector_col: str = "sector",
) -> pd.Series:
    counts = df.groupby(sector_col)[sector_col].transform("size")
    return (counts < min_names).rename("sector_low_confidence")
