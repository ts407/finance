"""Wikipedia pageviews as an attention proxy (SocialProvider contract).

Uses the public Wikimedia pageviews REST API — no key, daily grain since ~2015.
Maps ticker → enwiki title via the static seed in ticker_map.py.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable, Sequence
from urllib.parse import quote

import pandas as pd

from standing.providers.base import FetchCursor, ProviderMeta, SocialProvider
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
    ):
        if tickers is None:
            tickers = [t for t, _, _ in FIXTURE_TICKERS]
        self._tickers = [t.upper() for t in tickers]
        self._history_days = max(1, int(history_days))
        self._fetcher: JsonFetcher = fetcher or (lambda url, headers=None: get_json(url, headers=headers))

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
        }

    def fetch_since(self, cursor: FetchCursor) -> tuple[pd.DataFrame, FetchCursor]:
        end = cursor.as_of
        start = end - timedelta(days=self._history_days - 1)
        start_s = start.strftime("%Y%m%d") + "00"
        end_s = end.strftime("%Y%m%d") + "00"

        rows: list[dict] = []
        for ticker in self._tickers:
            title = wikipedia_title_for(ticker)
            if not title:
                continue
            url = PAGEVIEWS_TMPL.format(
                article=quote(title, safe="._%-"),
                start=start_s,
                end=end_s,
            )
            try:
                payload = self._fetcher(url, None)
            except RuntimeError:
                # Missing article / 404 window → skip ticker quietly
                continue
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
                        "neg_share": 0.5,  # attention proxy, not sentiment
                        "upvotes": 0,
                    }
                )

        df = normalize_social_frame(pd.DataFrame(rows) if rows else empty_social_frame())
        next_cursor = FetchCursor(as_of=end, token=f"wikipedia:{start.isoformat()}:{end.isoformat()}")
        return df, next_cursor


def default_fixture_tickers() -> Iterable[str]:
    return [t for t, _, _ in FIXTURE_TICKERS]
