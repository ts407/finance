from __future__ import annotations

import numpy as np
import pandas as pd

from standing.domain.scoring.peer_buckets import attach_size_buckets, peer_group_key
from standing.domain.scoring.value_metrics import EV_INAPPLICABLE_SECTORS, value_metric_frame

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
    ranks = valid.rank(method="average", ascending=higher_is_better)
    pct = (ranks - 1) / max(len(valid) - 1, 1) * 100.0
    out = pd.Series(np.nan, index=s.index, dtype=float)
    out.loc[pct.index] = pct
    return out


def _peer_relative_percentile(
    df: pd.DataFrame,
    value_col: str,
    peer_col: str = "_peer",
    higher_is_better: bool = True,
    winsorize: tuple[float, float] | None = (0.01, 0.99),
) -> pd.Series:
    parts: list[pd.Series] = []
    for _, group in df.groupby(peer_col, sort=False):
        vals = group[value_col]
        if winsorize is not None:
            vals = winsorize_series(vals, winsorize[0], winsorize[1])
        parts.append(_percentile_rank(vals, higher_is_better=higher_is_better))
    return pd.concat(parts).reindex(df.index)


def _multiple_to_value_percentile(
    df: pd.DataFrame,
    col: str,
    *,
    peer_col: str,
    winsorize: tuple[float, float],
) -> pd.Series:
    """
    Invert positive multiples (cheaper = higher). Non-positive but present values
    map to the worst score (0) — not NaN (which would silently drop / inflate peers).
    """
    raw = pd.to_numeric(df[col], errors="coerce")
    positive = raw.where(raw > 0)
    inv = 1.0 / positive
    tmp = df[[peer_col]].copy()
    tmp["_v"] = inv
    pct = _peer_relative_percentile(tmp, "_v", peer_col=peer_col, higher_is_better=True, winsorize=winsorize)
    bad = raw.notna() & (raw <= 0)
    pct = pct.copy()
    pct.loc[bad] = 0.0
    return pct


def _signed_quality_percentile(
    df: pd.DataFrame,
    col: str,
    *,
    peer_col: str,
    winsorize: tuple[float, float],
) -> pd.Series:
    """
    Higher is better. Missing stays NaN. Present values (including negative) are ranked
    after winsorizing — negatives land in the worst decile naturally, not as 'missing'.
    """
    tmp = df[[peer_col]].copy()
    tmp["_q"] = pd.to_numeric(df[col], errors="coerce")
    return _peer_relative_percentile(tmp, "_q", peer_col=peer_col, higher_is_better=True, winsorize=winsorize)


def pillar_percentiles(
    df: pd.DataFrame,
    *,
    winsorize: tuple[float, float] = (0.01, 0.99),
    peer_frame: str = "sector",
) -> pd.DataFrame:
    """
    Compute peer-relative V / Q / M percentiles with value coverage metadata.

    Value: PE-ladder (forward→ttm), pb, and EV-ladder (or skip for Financials/REITs).
    Within-pillar: mean of available metric percentiles (renormalize), not NaN pillar.
    """
    work = attach_size_buckets(value_metric_frame(df))
    work["_peer"] = peer_group_key(work, peer_frame=peer_frame)
    out = work[["ticker", "sector", "size_bucket"]].copy()
    out["peer_group"] = work["_peer"]

    pe_pct = _multiple_to_value_percentile(work, "_pe_for_value", peer_col="_peer", winsorize=winsorize)
    pb_pct = _multiple_to_value_percentile(work, "pb", peer_col="_peer", winsorize=winsorize)
    ev_pct = _multiple_to_value_percentile(work, "_ev_for_value", peer_col="_peer", winsorize=winsorize)

    value_stack = pd.concat([pe_pct, pb_pct, ev_pct], axis=1)
    # For EV-inapplicable sectors, ignore EV column entirely in the mean
    inapplicable = work["sector"].isin(EV_INAPPLICABLE_SECTORS)
    value_stack.loc[inapplicable, value_stack.columns[2]] = np.nan

    out["value"] = value_stack.mean(axis=1, skipna=True)
    out["value_n_metrics"] = value_stack.notna().sum(axis=1).astype(int)
    # Expected metrics: 2 for financials/REITs, 3 otherwise
    expected = np.where(inapplicable, 2, 3)
    out["value_coverage"] = (out["value_n_metrics"] / expected).clip(0, 1)
    out["value_pe_rung"] = work["value_pe_rung"]
    out["value_ev_rung"] = work["value_ev_rung"]
    out["value_metric_set"] = work["value_metric_set"]
    # Confidence haircut: full coverage → 1.0; each missing metric reduces
    out["value_confidence"] = out["value_coverage"]

    # Quality — signed ranking (negatives are worst, not missing)
    quality_parts = []
    for col in ("roe", "operating_margin", "revenue_growth_yoy"):
        quality_parts.append(
            _signed_quality_percentile(work, col, peer_col="_peer", winsorize=winsorize)
        )
    q_stack = pd.concat(quality_parts, axis=1)
    out["quality"] = q_stack.mean(axis=1, skipna=True)
    out["quality_n_metrics"] = q_stack.notna().sum(axis=1).astype(int)
    out["quality_coverage"] = (out["quality_n_metrics"] / 3.0).clip(0, 1)

    # Momentum
    mom_parts = []
    for col in ("ret_1m", "ret_3m", "ret_6m", "relative_volume"):
        tmp = work[["_peer"]].copy()
        tmp["_m"] = pd.to_numeric(work[col], errors="coerce")
        mom_parts.append(
            _peer_relative_percentile(tmp, "_m", peer_col="_peer", higher_is_better=True, winsorize=winsorize)
        )
    m_stack = pd.concat(mom_parts, axis=1)
    out["momentum"] = m_stack.mean(axis=1, skipna=True)
    out["momentum_n_metrics"] = m_stack.notna().sum(axis=1).astype(int)
    out["momentum_coverage"] = (out["momentum_n_metrics"] / 4.0).clip(0, 1)

    global_parts = []
    for col in ("ret_1m", "ret_3m", "ret_6m", "relative_volume"):
        vals = winsorize_series(pd.to_numeric(work[col], errors="coerce"), winsorize[0], winsorize[1])
        global_parts.append(_percentile_rank(vals, higher_is_better=True))
    out["momentum_global"] = pd.concat(global_parts, axis=1).mean(axis=1, skipna=True)

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
    # Cross-pillar: still require all three pillars present
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
