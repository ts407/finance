from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class FetchCursor:
    """Opaque social ingest cursor — identical for fixture and live."""

    as_of: date
    token: str | None = None


class MarketProvider(ABC):
    """Market fundamentals + price features. Fixture and live share this interface."""

    @abstractmethod
    def fetch(self, as_of: date, tickers: list[str] | None = None) -> pd.DataFrame:
        """
        Return one row per ticker with at least:
        ticker, sector, market_cap, adv_20d, pe_ttm, pb, ev_ebitda,
        roe, operating_margin, revenue_growth_yoy,
        ret_1m, ret_3m, ret_6m, relative_volume
        """


class SocialProvider(ABC):
    """Social mentions. Fixture and live share this interface."""

    @abstractmethod
    def fetch_since(self, cursor: FetchCursor) -> tuple[pd.DataFrame, FetchCursor]:
        """
        Return daily mention rows since cursor and the next cursor.

        Columns: date, ticker, source_id, mention_count, neg_share, upvotes
        """


class ProviderMeta(ABC):
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def is_fixture(self) -> bool: ...

    @abstractmethod
    def metadata(self) -> dict[str, Any]: ...

    def supports_historical(self) -> bool:
        """True if arbitrary as_of is meaningful (fixtures yes; live Finnhub no)."""
        return self.is_fixture()
