from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from standing.config import ROOT
from standing.domain.scoring.base import _peer_relative_percentile
from standing.market.ohlcv_store import OHLCVStore
from standing.providers.market_fixture import FIXTURE_TICKERS
from standing.providers.stooq.ohlcv import compute_ohlcv_features
from standing.research.ic import (
    cross_section_ic_timeseries,
    forward_total_return,
    month_end_trading_dates,
)

DEFAULT_REPORT_DIR = ROOT / "artifacts" / "research" / "track_m"


def fixture_universe() -> pd.DataFrame:
    return pd.DataFrame(
        [{"ticker": t, "sector": s, "listing": listing} for t, s, listing in FIXTURE_TICKERS]
    )


def _rebalance_dates_from_bars(bars_by_ticker: dict[str, pd.DataFrame]) -> list[date]:
    # Use intersection-ish: take dates from the ticker with most history
    if not bars_by_ticker:
        return []
    longest = max(bars_by_ticker.values(), key=len)
    idx = pd.DatetimeIndex(longest["date"])
    dates = month_end_trading_dates(idx)
    # Need enough history before first date for 6M momentum + forward horizon after last
    if len(dates) < 8:
        return dates
    # drop first 6 months (need 126 trading days ≈ 6 months) and last month (need forward)
    return dates[6:-1]


def _score_raw_ret(frame: pd.DataFrame, col: str) -> pd.Series:
    return frame[col]


def _score_sector_percentile(frame: pd.DataFrame, col: str) -> pd.Series:
    tmp = frame[["sector"]].copy()
    tmp["_x"] = frame[col]
    return _peer_relative_percentile(
        tmp, "_x", peer_col="sector", higher_is_better=True, winsorize=(0.01, 0.99)
    )


def _score_product_momentum(frame: pd.DataFrame) -> pd.Series:
    """Median of sector-relative percentiles of ret_1m/3m/6m + relative_volume."""
    parts = []
    for col in ("ret_1m", "ret_3m", "ret_6m", "relative_volume"):
        if col not in frame.columns or frame[col].notna().sum() < 5:
            continue
        parts.append(_score_sector_percentile(frame, col))
    if not parts:
        return pd.Series(np.nan, index=frame.index)
    return pd.concat(parts, axis=1).median(axis=1, skipna=True)


SIGNAL_BUILDERS = {
    "ret_1m_raw": lambda f: _score_raw_ret(f, "ret_1m"),
    "ret_3m_raw": lambda f: _score_raw_ret(f, "ret_3m"),
    "ret_6m_raw": lambda f: _score_raw_ret(f, "ret_6m"),
    "ret_1m_sector_pct": lambda f: _score_sector_percentile(f, "ret_1m"),
    "ret_3m_sector_pct": lambda f: _score_sector_percentile(f, "ret_3m"),
    "ret_6m_sector_pct": lambda f: _score_sector_percentile(f, "ret_6m"),
    "product_momentum_v2": _score_product_momentum,
}


def build_calibration_panel(
    store: OHLCVStore,
    *,
    universe: pd.DataFrame | None = None,
    horizon_days: int = 21,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    uni = universe if universe is not None else fixture_universe()
    tickers = uni["ticker"].tolist()
    sectors = dict(zip(uni["ticker"], uni["sector"], strict=False))
    bars = store.fetch_many(tickers)
    meta = {
        "n_requested": len(tickers),
        "n_with_bars": len(bars),
        "tickers_missing": sorted(set(tickers) - set(bars)),
        "source": store._client.metadata(),
    }
    rebalances = _rebalance_dates_from_bars(bars)
    meta["n_rebalance_dates"] = len(rebalances)
    if not rebalances:
        return pd.DataFrame(), meta

    rows: list[dict[str, Any]] = []
    for d in rebalances:
        cross_rows = []
        for t, bdf in bars.items():
            feats = compute_ohlcv_features(bdf, as_of=d)
            closes = bdf.set_index("date")["close"].astype(float).sort_index()
            fwd = forward_total_return(closes, as_of=d, horizon_days=horizon_days)
            if feats.get("ret_1m") is None or fwd is None:
                continue
            cross_rows.append(
                {
                    "as_of": d.isoformat(),
                    "ticker": t,
                    "sector": sectors.get(t, "Unknown"),
                    "forward_ret": fwd,
                    **feats,
                }
            )
        if len(cross_rows) < 10:
            continue
        frame = pd.DataFrame(cross_rows)
        for name, builder in SIGNAL_BUILDERS.items():
            frame[name] = builder(frame)
        rows.append(frame)

    if not rows:
        return pd.DataFrame(), meta
    panel = pd.concat(rows, ignore_index=True)
    meta["n_panel_rows"] = int(len(panel))
    meta["date_start"] = panel["as_of"].min()
    meta["date_end"] = panel["as_of"].max()
    return panel, meta


def run_momentum_calibration(
    *,
    store: OHLCVStore | None = None,
    horizon_days: int = 21,
    out_dir: Path | None = None,
    allow_network: bool = True,
) -> dict[str, Any]:
    """
    Validate the evaluation apparatus against known momentum signals.

    Writes IC summaries + raw IC series under artifacts/research/track_m/.
    """
    store = store or OHLCVStore(allow_network=allow_network)
    out = out_dir or DEFAULT_REPORT_DIR
    out.mkdir(parents=True, exist_ok=True)

    panel, meta = build_calibration_panel(store, horizon_days=horizon_days)
    if panel.empty:
        report = {
            "track": "M",
            "status": "failed_empty_panel",
            "meta": meta,
            "note": "No OHLCV panel built — check network/cache.",
        }
        path = out / "momentum_calibration.json"
        path.write_text(json.dumps(report, indent=2) + "\n")
        return report

    panel_path = out / "momentum_panel.csv"
    panel.to_csv(panel_path, index=False)

    summaries = []
    ic_frames = {}
    for signal in SIGNAL_BUILDERS:
        series, summary = cross_section_ic_timeseries(
            panel,
            score_col=signal,
            forward_col="forward_ret",
            signal_name=signal,
            horizon_days=horizon_days,
        )
        summaries.append(summary.to_dict())
        ic_frames[signal] = series

    ic_df = pd.DataFrame(ic_frames)
    ic_path = out / "momentum_ic_timeseries.csv"
    ic_df.to_csv(ic_path, index_label="as_of")

    # Pick product momentum + best raw for apparatus check
    by_name = {s["signal"]: s for s in summaries}
    product = by_name.get("product_momentum_v2", {})
    best = max(summaries, key=lambda s: abs(s.get("mean_ic") or 0.0))

    apparatus_ok = bool(
        product
        and product.get("n_ic_obs", 0) >= 12
        and abs(product.get("mean_ic") or 0.0) > 0.01
        and (product.get("tstat") or 0.0) > 1.5
    )

    report = {
        "track": "M",
        "phase": "apparatus_calibration",
        "status": "ok" if apparatus_ok else "weak_or_inconclusive",
        "horizon_days": horizon_days,
        "meta": meta,
        "apparatus_check": {
            "signal": "product_momentum_v2",
            "passed": apparatus_ok,
            "rule": "n_ic_obs>=12 AND |mean_ic|>0.01 AND tstat>1.5",
            "interpretation": (
                "If product momentum IC is not found in multi-year OHLCV, the evaluation "
                "chain is suspect. If found at plausible magnitude, the meter is calibrated "
                "before applying it to weak/expensive Social."
            ),
        },
        "product_momentum_v2": product,
        "best_abs_mean_ic": best,
        "all_signals": summaries,
        "sigma_ic_for_power": {
            "signal": "product_momentum_v2",
            "mu_ic": product.get("mean_ic"),
            "sigma_ic": product.get("sigma_ic"),
            "T_80pct_power_days": product.get("power_days_80"),
            "formula": "T ≈ (2.80 · σ_IC / μ_IC)²",
        },
        "paths": {
            "panel": str(panel_path.relative_to(ROOT)),
            "ic_timeseries": str(ic_path.relative_to(ROOT)),
        },
        "social_track": "locked — no Social analysis until live density feasibility exists",
    }
    report_path = out / "momentum_calibration.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    report["report_path"] = str(report_path.relative_to(ROOT))
    return report
