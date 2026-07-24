"""Track M research: IC time series, σ_IC, power sizing."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, timedelta
from typing import Any, Callable, Iterable

import numpy as np
import pandas as pd


def spearman_ic(score: pd.Series, forward: pd.Series) -> float:
    aligned = pd.concat([score, forward], axis=1, keys=["s", "f"]).dropna()
    if len(aligned) < 5:
        return float("nan")
    ra = aligned["s"].rank(method="average")
    rb = aligned["f"].rank(method="average")
    return float(ra.corr(rb, method="pearson"))


def month_end_trading_dates(index: pd.DatetimeIndex) -> list[date]:
    """Last available bar date in each calendar month."""
    if index.empty:
        return []
    s = pd.Series(1, index=pd.DatetimeIndex(index).sort_values())
    ends = s.groupby([s.index.year, s.index.month]).apply(lambda x: x.index.max())
    return [pd.Timestamp(ts).date() for ts in ends]


def forward_total_return(closes: pd.Series, *, as_of: date, horizon_days: int) -> float | None:
    """Look-ahead-free forward return: close[t+h]/close[t]-1 using trading-day offsets."""
    work = closes[closes.index.date <= as_of]
    if work.empty:
        return None
    # Position of last bar on/before as_of in the full series
    full = closes.sort_index()
    # find integer location
    mask = full.index.date <= as_of
    if not mask.any():
        return None
    loc = int(np.where(mask)[0][-1])
    j = loc + horizon_days
    if j >= len(full):
        return None
    base = float(full.iloc[loc])
    fut = float(full.iloc[j])
    if base == 0 or not np.isfinite(base) or not np.isfinite(fut):
        return None
    return fut / base - 1.0


@dataclass(frozen=True)
class ICSummary:
    signal: str
    horizon_days: int
    n_dates: int
    n_ic_obs: int
    mean_ic: float
    sigma_ic: float
    tstat: float
    power_days_80: float
    ic_positive_share: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def power_days_80(mean_ic: float, sigma_ic: float) -> float:
    """
    T ≈ (2.80 · σ_IC / μ_IC)² for 80% power (two-sided, approx).

    Returns inf when |μ_IC| is ~0.
    """
    if not np.isfinite(mean_ic) or not np.isfinite(sigma_ic) or abs(mean_ic) < 1e-12:
        return float("inf")
    return float((2.80 * sigma_ic / abs(mean_ic)) ** 2)


def summarize_ic_series(
    ic: pd.Series,
    *,
    signal: str,
    horizon_days: int,
) -> ICSummary:
    vals = ic.dropna().astype(float)
    n = int(len(vals))
    mean = float(vals.mean()) if n else float("nan")
    sigma = float(vals.std(ddof=1)) if n > 1 else float("nan")
    tstat = float(mean / (sigma / np.sqrt(n))) if n > 1 and sigma > 0 else float("nan")
    return ICSummary(
        signal=signal,
        horizon_days=horizon_days,
        n_dates=int(ic.shape[0]),
        n_ic_obs=n,
        mean_ic=mean,
        sigma_ic=sigma,
        tstat=tstat,
        power_days_80=power_days_80(mean, sigma),
        ic_positive_share=float((vals > 0).mean()) if n else float("nan"),
    )


ScoreFn = Callable[[pd.DataFrame], pd.Series]


def cross_section_ic_timeseries(
    panel: pd.DataFrame,
    *,
    score_col: str,
    forward_col: str = "forward_ret",
    date_col: str = "as_of",
    signal_name: str | None = None,
    horizon_days: int = 21,
) -> tuple[pd.Series, ICSummary]:
    """Compute IC(t) = Spearman(score, forward) per as_of date."""
    ics = []
    for as_of, g in panel.groupby(date_col, sort=True):
        ic = spearman_ic(g[score_col], g[forward_col])
        ics.append((pd.Timestamp(as_of), ic))
    series = pd.Series({t: v for t, v in ics}).sort_index()
    summary = summarize_ic_series(
        series, signal=signal_name or score_col, horizon_days=horizon_days
    )
    return series, summary


def demean_cross_section(s: pd.Series, group: pd.Series | None = None) -> pd.Series:
    """Cross-sectional demean; optional within-group (e.g. sector) demean."""
    if group is None:
        return s - s.mean()
    out = s.copy()
    for _, idx in group.groupby(group).groups.items():
        out.loc[idx] = s.loc[idx] - s.loc[idx].mean()
    return out
