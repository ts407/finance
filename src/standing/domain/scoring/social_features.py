from __future__ import annotations

import numpy as np
import pandas as pd


def sentiment_polarity(neg_share: float | np.ndarray) -> np.ndarray:
    """
    Map negative-mention share → signed polarity in [-1, 1].

    neg_share 0.0 → +1 (bullish), 0.5 → 0 (neutral), 1.0 → -1 (bearish).
    """
    neg = np.asarray(neg_share, dtype=float)
    return np.clip(1.0 - 2.0 * neg, -1.0, 1.0)


def blend_sentiment(
    volume_score: float | np.ndarray,
    neg_share: float | np.ndarray,
    *,
    weight: float = 1.0,
) -> np.ndarray:
    """
    Combine a 0–100 volume-attention score with sentiment into a signed social score.

    Volume is *amplitude* (how loud), sentiment is *sign* (which way). A loud name
    (volume 90 ≈ +40 above neutral 50) reads +40·polarity: bullish sentiment keeps it
    high, bearish sentiment flips it symmetrically low, neutral sentiment collapses it
    toward 50. Quiet names (volume ≈ 50) barely move regardless of sentiment.

    ``weight`` in [0, 1] interpolates between pure volume (0) and full sentiment sign (1).
    Result stays in [0, 100] so downstream shrinkage/tilt are unchanged.
    """
    vol = np.asarray(volume_score, dtype=float)
    pol = sentiment_polarity(neg_share)
    w = float(np.clip(weight, 0.0, 1.0))
    amplitude = vol - 50.0
    signed = amplitude * ((1.0 - w) + w * pol)
    return np.clip(50.0 + signed, 0.0, 100.0)


def apply_source_cap(
    daily: pd.DataFrame,
    *,
    cap: float = 0.50,
    ticker_col: str = "ticker",
    date_col: str = "date",
    source_col: str = "source_id",
    count_col: str = "mention_count",
) -> pd.DataFrame:
    """
    Cap each source's share of a ticker's daily mentions at `cap`.
    Overflow is downsampled (scaled down), not redistributed.
    """
    if daily.empty:
        return daily.copy()
    out = daily.copy()
    group_cols = [ticker_col, date_col]
    totals = out.groupby(group_cols, sort=False)[count_col].transform("sum")
    share = np.where(totals > 0, out[count_col] / totals, 0.0)
    scale = np.ones(len(out), dtype=float)
    over = share > cap
    # scale source count so share == cap
    scale[over] = (cap * totals[over]) / out.loc[over, count_col].to_numpy()
    out["mention_count_capped"] = out[count_col] * scale
    out["source_share"] = share
    out["cap_headroom"] = np.maximum(0.0, cap - share)
    return out


def aggregate_mentions(
    daily_capped: pd.DataFrame,
    *,
    window_days: int = 7,
    ticker_col: str = "ticker",
    date_col: str = "date",
    count_col: str = "mention_count_capped",
    neg_col: str = "neg_share",
    as_of: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """
    Transform: log1p(count) → share of universe daily volume → 7-day aggregate.

    Also averages neg_share over the window (mention-count weighted).
    """
    if daily_capped.empty:
        return pd.DataFrame(
            columns=[ticker_col, "n", "s_obs", "neg_share", "universe_share_7d"]
        )

    df = daily_capped.copy()
    df[date_col] = pd.to_datetime(df[date_col])
    if as_of is None:
        as_of = df[date_col].max()
    start = as_of - pd.Timedelta(days=window_days - 1)
    df = df[(df[date_col] >= start) & (df[date_col] <= as_of)]

    # Per day universe total of log1p counts
    df["log_count"] = np.log1p(df[count_col].astype(float))
    day_tot = df.groupby(date_col, sort=False)["log_count"].transform("sum")
    df["day_share"] = np.where(day_tot > 0, df["log_count"] / day_tot, 0.0)

    # Aggregate per ticker over window
    rows = []
    for ticker, g in df.groupby(ticker_col, sort=False):
        n = float(g[count_col].sum())
        share_7d = float(g["day_share"].sum())
        # Map share into a 0–100 observational social score via cross-section later;
        # here return raw share + n + weighted neg_share.
        if n > 0 and neg_col in g.columns:
            neg = float(np.average(g[neg_col].astype(float), weights=g[count_col].astype(float)))
        else:
            neg = 0.5
        rows.append(
            {
                ticker_col: ticker,
                "n": n,
                "universe_share_7d": share_7d,
                "neg_share": neg,
            }
        )
    agg = pd.DataFrame(rows)
    if agg.empty:
        return agg

    # Observational social score: percentile of universe_share_7d across tickers
    ranks = agg["universe_share_7d"].rank(method="average")
    agg["s_obs"] = (ranks - 1) / max(len(agg) - 1, 1) * 100.0
    return agg
