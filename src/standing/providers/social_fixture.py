from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from standing.providers.base import FetchCursor, ProviderMeta, SocialProvider
from standing.providers.market_fixture import FIXTURE_TICKERS


def _stable_ticker_salt(ticker: str) -> int:
    """Process-stable salt (avoid Python's randomized hash())."""
    return sum((i + 1) * ord(ch) for i, ch in enumerate(ticker)) % 10_000


def _synth_social_day(as_of: date, seed: int = 7) -> pd.DataFrame:
    """NB mention counts + AR(1)-ish sentiment noise — fixture placeholder data."""
    rng = np.random.default_rng(seed + as_of.toordinal())
    rows = []
    for ticker, _sector, _listing in FIXTURE_TICKERS:
        # Base attention varies by ticker (stable across processes)
        base = 5 + (_stable_ticker_salt(ticker) % 40)
        for source in ("reddit", "reddit_wsb", "stocktwits"):
            # WSB sometimes dominates — cap logic must handle this
            burst = 1.0
            if source == "reddit_wsb" and rng.random() < 0.15:
                burst = float(rng.uniform(3.0, 12.0))
            count = max(0, int(rng.negative_binomial(base, 0.35) * burst))
            if count == 0:
                continue
            neg = float(np.clip(rng.beta(2, 5) + (0.25 if burst > 3 else 0.0), 0, 1))
            upvotes = int(rng.integers(0, max(1, count * 20)))
            rows.append(
                {
                    "date": as_of.isoformat(),
                    "ticker": ticker,
                    "source_id": source,
                    "mention_count": count,
                    "neg_share": neg,
                    "upvotes": upvotes,
                }
            )
    return pd.DataFrame(rows)


class FixtureSocialProvider(SocialProvider, ProviderMeta):
    def __init__(self, seed: int = 7, history_days: int = 14, path: Path | None = None):
        self._seed = seed
        self._history_days = history_days
        self._path = path
        self._cache: dict[date, pd.DataFrame] = {}

    def name(self) -> str:
        return "fixture-social"

    def is_fixture(self) -> bool:
        return True

    def metadata(self) -> dict:
        return {
            "seed": self._seed,
            "history_days": self._history_days,
            "placeholder": True,
            "sources": ["reddit", "reddit_wsb", "stocktwits"],
            "live": "later_after_approval_or_firestream",
        }

    def _day(self, d: date) -> pd.DataFrame:
        if d not in self._cache:
            if self._path and self._path.exists():
                all_df = pd.read_csv(self._path)
                all_df["date"] = pd.to_datetime(all_df["date"]).dt.date
                self._cache[d] = all_df[all_df["date"] == d].copy()
            else:
                self._cache[d] = _synth_social_day(d, seed=self._seed)
        return self._cache[d]

    def fetch_since(self, cursor: FetchCursor) -> tuple[pd.DataFrame, FetchCursor]:
        """Return up to history_days of daily rows ending at cursor.as_of."""
        end = cursor.as_of
        start = end - timedelta(days=self._history_days - 1)
        frames = [self._day(start + timedelta(days=i)) for i in range(self._history_days)]
        df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        next_cursor = FetchCursor(as_of=end, token=f"fixture:{end.isoformat()}")
        return df, next_cursor
