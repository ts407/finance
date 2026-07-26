"""Seed universe loaders: SP500 ∪ NDX100 ∪ liquid ADR lists."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from standing.config import ROOT

DEFAULT_UNIVERSE_DIR = ROOT / "config" / "universe"

SEED_FILES = {
    "SP500": "sp500.csv",
    "NDX100": "ndx100.csv",
    "LIQUID_ADR": "liquid_adr.csv",
}

SECTORS_FILE = "sectors.csv"


def load_seed_frame(
    seed_sets: list[str] | None = None,
    *,
    universe_dir: Path | None = None,
) -> pd.DataFrame:
    """
    Load and dedupe seed tickers.

    CSV columns: ticker, listing[, sector_hint]
    Dedup keeps first occurrence (SP500 before NDX100 before ADR by default order).
    """
    base = universe_dir or DEFAULT_UNIVERSE_DIR
    sets = seed_sets or list(SEED_FILES.keys())
    frames: list[pd.DataFrame] = []
    for name in sets:
        filename = SEED_FILES.get(name)
        if filename is None:
            raise ValueError(f"Unknown seed set: {name}")
        path = base / filename
        if not path.exists():
            raise FileNotFoundError(f"Seed file missing: {path}")
        df = pd.read_csv(path)
        if "ticker" not in df.columns:
            raise ValueError(f"{path} must have a ticker column")
        df = df.copy()
        df["ticker"] = df["ticker"].astype(str).str.upper().str.strip()
        if "listing" not in df.columns:
            df["listing"] = "ADR" if name == "LIQUID_ADR" else "US"
        df["seed_set"] = name
        frames.append(df[["ticker", "listing", "seed_set"]])
    if not frames:
        return pd.DataFrame(columns=["ticker", "listing", "seed_set"])
    out = pd.concat(frames, ignore_index=True)
    out = out.drop_duplicates(subset=["ticker"], keep="first").reset_index(drop=True)
    return out


def load_seed_tickers(
    seed_sets: list[str] | None = None,
    *,
    universe_dir: Path | None = None,
) -> list[str]:
    return load_seed_frame(seed_sets, universe_dir=universe_dir)["ticker"].tolist()


def listing_lookup(
    seed_sets: list[str] | None = None,
    *,
    universe_dir: Path | None = None,
) -> dict[str, str]:
    frame = load_seed_frame(seed_sets, universe_dir=universe_dir)
    return dict(zip(frame["ticker"], frame["listing"], strict=False))


def load_sector_map(*, universe_dir: Path | None = None) -> dict[str, str]:
    """Load the bundled ticker → GICS-11 sector reference (``sectors.csv``)."""
    base = universe_dir or DEFAULT_UNIVERSE_DIR
    path = base / SECTORS_FILE
    if not path.exists():
        return {}
    df = pd.read_csv(path)
    if "ticker" not in df.columns or "sector" not in df.columns:
        raise ValueError(f"{path} must have ticker,sector columns")
    df["ticker"] = df["ticker"].astype(str).str.upper().str.strip()
    df["sector"] = df["sector"].astype(str).str.strip()
    return dict(zip(df["ticker"], df["sector"], strict=False))


def load_universe_meta(
    seed_sets: list[str] | None = None,
    *,
    universe_dir: Path | None = None,
    default_sector: str = "Information Technology",
) -> dict[str, dict[str, str]]:
    """
    Merge seed listings with the sector reference into ``{ticker: {sector, listing}}``.

    Tickers absent from ``sectors.csv`` fall back to ``default_sector`` so the desk
    stays resilient; callers that require a real sector should check coverage.
    """
    frame = load_seed_frame(seed_sets, universe_dir=universe_dir)
    sectors = load_sector_map(universe_dir=universe_dir)
    out: dict[str, dict[str, str]] = {}
    for ticker, listing in zip(frame["ticker"], frame["listing"], strict=False):
        out[ticker] = {
            "sector": sectors.get(ticker, default_sector),
            "listing": str(listing),
        }
    return out
