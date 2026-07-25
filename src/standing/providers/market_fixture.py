from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from standing.domain.scoring.base import GICS_11
from standing.providers.base import MarketProvider, ProviderMeta

# Compact but multi-sector demo universe (~44 names). Full 400–500 is a data job.
FIXTURE_TICKERS: list[tuple[str, str, str]] = [
    # ticker, sector, listing
    ("AAPL", "Information Technology", "US"),
    ("MSFT", "Information Technology", "US"),
    ("NVDA", "Information Technology", "US"),
    ("ORCL", "Information Technology", "US"),
    ("CRM", "Information Technology", "US"),
    ("AMZN", "Consumer Discretionary", "US"),
    ("TSLA", "Consumer Discretionary", "US"),
    ("HD", "Consumer Discretionary", "US"),
    ("NKE", "Consumer Discretionary", "US"),
    ("SBUX", "Consumer Discretionary", "US"),
    ("KO", "Consumer Staples", "US"),
    ("PEP", "Consumer Staples", "US"),
    ("WMT", "Consumer Staples", "US"),
    ("COST", "Consumer Staples", "US"),
    ("PG", "Consumer Staples", "US"),
    ("JPM", "Financials", "US"),
    ("BAC", "Financials", "US"),
    ("GS", "Financials", "US"),
    ("V", "Financials", "US"),
    ("MA", "Financials", "US"),
    ("JNJ", "Health Care", "US"),
    ("UNH", "Health Care", "US"),
    ("PFE", "Health Care", "US"),
    ("ABBV", "Health Care", "US"),
    ("MRK", "Health Care", "US"),
    ("XOM", "Energy", "US"),
    ("CVX", "Energy", "US"),
    ("COP", "Energy", "US"),
    ("SLB", "Energy", "US"),
    ("CAT", "Industrials", "US"),
    ("GE", "Industrials", "US"),
    ("HON", "Industrials", "US"),
    ("UPS", "Industrials", "US"),
    ("BA", "Industrials", "US"),
    ("LIN", "Materials", "US"),
    ("APD", "Materials", "US"),
    ("SHW", "Materials", "US"),
    ("NEM", "Materials", "US"),
    ("NEE", "Utilities", "US"),
    ("DUK", "Utilities", "US"),
    ("SO", "Utilities", "US"),
    ("AMT", "Real Estate", "US"),
    ("PLD", "Real Estate", "US"),
    ("O", "Real Estate", "US"),
    ("META", "Communication Services", "US"),
    ("GOOGL", "Communication Services", "US"),
    ("NFLX", "Communication Services", "US"),
    ("DIS", "Communication Services", "US"),
    ("TM", "Consumer Discretionary", "ADR"),
    ("SONY", "Consumer Discretionary", "ADR"),
    ("ASML", "Information Technology", "ADR"),
    ("SAP", "Information Technology", "ADR"),
    ("NVO", "Health Care", "ADR"),
    ("UL", "Consumer Staples", "ADR"),
]


def _synth_market(as_of: date, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed + as_of.toordinal())
    rows = []
    for i, (ticker, sector, listing) in enumerate(FIXTURE_TICKERS):
        g = rng.normal(0, 1)
        rows.append(
            {
                "ticker": ticker,
                "sector": sector,
                "listing": listing,
                "market_cap": float(rng.uniform(1.2e9, 3.0e12)),
                "adv_20d": float(rng.uniform(6e6, 5e9)),
                "pe_ttm": float(np.clip(rng.lognormal(3.0 + 0.15 * g, 0.45), 3, 120)),
                "pb": float(np.clip(rng.lognormal(1.0 + 0.1 * g, 0.4), 0.3, 40)),
                "ev_ebitda": float(np.clip(rng.lognormal(2.5 + 0.12 * g, 0.4), 2, 80)),
                "ev_ebit": float(np.clip(rng.lognormal(2.7 + 0.12 * g, 0.4), 3, 100)),
                "ev_sales": float(np.clip(rng.lognormal(1.5 + 0.12 * g, 0.45), 0.4, 30)),
                "roe": float(np.clip(0.08 + 0.12 * g + rng.normal(0, 0.05), -0.2, 0.6)),
                "operating_margin": float(
                    np.clip(0.12 + 0.08 * g + rng.normal(0, 0.04), -0.1, 0.5)
                ),
                "revenue_growth_yoy": float(
                    np.clip(0.05 + 0.1 * g + rng.normal(0, 0.08), -0.3, 0.8)
                ),
                "ret_1m": float(rng.normal(0.01 * g, 0.06)),
                "ret_3m": float(rng.normal(0.03 * g, 0.12)),
                "ret_6m": float(rng.normal(0.05 * g, 0.2)),
                "relative_volume": float(np.clip(rng.lognormal(0.0, 0.35), 0.3, 5.0)),
                "as_of": as_of.isoformat(),
            }
        )
    return pd.DataFrame(rows)


class FixtureMarketProvider(MarketProvider, ProviderMeta):
    def __init__(self, seed: int = 42, path: Path | None = None):
        self._seed = seed
        self._path = path

    def name(self) -> str:
        return "fixture-market"

    def is_fixture(self) -> bool:
        return True

    def metadata(self) -> dict:
        return {"seed": self._seed, "placeholder": True, "path": str(self._path)}

    def fetch(self, as_of: date, tickers: list[str] | None = None) -> pd.DataFrame:
        if self._path and self._path.exists():
            df = pd.read_csv(self._path)
        else:
            df = _synth_market(as_of, seed=self._seed)
        if tickers is not None:
            df = df[df["ticker"].isin(tickers)].copy()
        # Ensure sector strings are in GICS-11
        unknown = set(df["sector"]) - set(GICS_11)
        if unknown:
            raise ValueError(f"Non-GICS-11 sectors in fixture market: {unknown}")
        return df.reset_index(drop=True)
