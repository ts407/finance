"""Wikipedia pageviews as an attention proxy (SocialProvider contract).

Uses the public Wikimedia pageviews REST API — no key, daily grain since ~2015.
Maps ticker → enwiki title via the static seed in ticker_map.py.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from typing import Iterable, Sequence
from urllib.parse import quote

import pandas as pd

from standing.providers.base import FetchCursor, ProviderMeta, SocialProvider
from standing.providers.cache import DiskCache
from standing.providers.http import JsonFetcher, get_json
from standing.providers.market_fixture import FIXTURE_TICKERS
from standing.providers.schema import empty_social_frame, normalize_social_frame
from standing.providers.ticker_map import wikipedia_title_for

SOURCE_ID = "wikipedia_pageviews"
PAGEVIEWS_TMPL = (
    "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
    "en.wikipedia/all-access/user/{article}/daily/{start}/{end}"
)


class WikipediaPageviewsProvider(SocialProvider, ProviderMeta):
    def __init__(
        self,
        *,
        tickers: Sequence[str] | None = None,
        history_days: int = 14,
        fetcher: JsonFetcher | None = None,
        cache: DiskCache | None = None,
        max_workers: int = 8,
    ):
        if tickers is None:
            tickers = [t for t, _, _ in FIXTURE_TICKERS]
        self._tickers = [t.upper() for t in tickers]
        self._history_days = max(1, int(history_days))
        self._fetcher: JsonFetcher = fetcher or (lambda url, headers=None: get_json(url, headers=headers))
        self._cache = cache
        self._max_workers = max(1, int(max_workers))

    def name(self) -> str:
        return "wikipedia-pageviews"

    def is_fixture(self) -> bool:
        return False

    def metadata(self) -> dict:
        mapped = sum(1 for t in self._tickers if wikipedia_title_for(t))
        return {
            "source_id": SOURCE_ID,
            "history_days": self._history_days,
            "tickers": len(self._tickers),
            "mapped_titles": mapped,
            "live": True,
            "auth": "none",
            "cache": bool(self._cache),
        }

    def _fetch_ticker(self, ticker: str, start: date, end: date, start_s: str, end_s: str) -> list[dict]:
        title = wikipedia_title_for(ticker)
        if not title:
            return []
        cache_parts = (ticker, start_s, end_s)
        if self._cache is not None:
            cached = self._cache.get_json("wikipedia", *cache_parts)
            if cached is not None:
                return list(cached)

        url = PAGEVIEWS_TMPL.format(
            article=quote(title, safe="._%-"),
            start=start_s,
            end=end_s,
        )
        try:
            payload = self._fetcher(url, None)
        except RuntimeError:
            return []

        rows: list[dict] = []
        for item in payload.get("items") or []:
            ts = str(item.get("timestamp", ""))[:8]
            if len(ts) != 8:
                continue
            d = date(int(ts[:4]), int(ts[4:6]), int(ts[6:8]))
            if d < start or d > end:
                continue
            views = int(item.get("views") or 0)
            if views <= 0:
                continue
            rows.append(
                {
                    "date": d.isoformat(),
                    "ticker": ticker,
                    "source_id": SOURCE_ID,
                    "mention_count": views,
                    "neg_share": 0.5,
                    "upvotes": 0,
                }
            )
        if self._cache is not None:
            self._cache.set_json("wikipedia", *cache_parts, data=rows)
        return rows

    def fetch_since(self, cursor: FetchCursor) -> tuple[pd.DataFrame, FetchCursor]:
        end = cursor.as_of
        start = end - timedelta(days=self._history_days - 1)
        start_s = start.strftime("%Y%m%d") + "00"
        end_s = end.strftime("%Y%m%d") + "00"

        rows: list[dict] = []
        # Custom fetcher (tests) → serial; live → threaded
        if self._fetcher is not get_json and not hasattr(self._fetcher, "__name__"):
            # Always allow thread pool; mocks are sync and fine
            pass

        with ThreadPoolExecutor(max_workers=self._max_workers) as pool:
            futs = {
                pool.submit(self._fetch_ticker, t, start, end, start_s, end_s): t
                for t in self._tickers
            }
            for fut in as_completed(futs):
                rows.extend(fut.result())

        df = normalize_social_frame(pd.DataFrame(rows) if rows else empty_social_frame())
        next_cursor = FetchCursor(as_of=end, token=f"wikipedia:{start.isoformat()}:{end.isoformat()}")
        return df, next_cursor


def default_fixture_tickers() -> Iterable[str]:
    return [t for t, _, _ in FIXTURE_TICKERS]
