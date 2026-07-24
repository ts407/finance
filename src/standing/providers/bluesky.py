"""Bluesky cashtag search behind the SocialProvider contract.

Uses app.bsky.feed.searchPosts on api.bsky.app with since/until date range —
the economical path for ticker mentions (full getRepo backfill is optional later).
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Sequence

import pandas as pd

from standing.providers.base import FetchCursor, ProviderMeta, SocialProvider
from standing.providers.http import JsonFetcher, build_url, get_json
from standing.providers.market_fixture import FIXTURE_TICKERS
from standing.providers.schema import empty_social_frame, normalize_social_frame

SOURCE_ID = "bluesky"
SEARCH_BASE = "https://api.bsky.app/xrpc/app.bsky.feed.searchPosts"

# Minimal finance polarity stub — full lexicon/NLP is C3 (archive corpora), not this provider.
_BEARISH = re.compile(
    r"\b(bearish|crash|dump|short|sell|bagholder|fraud|overvalued|plunge|tank)\b",
    re.I,
)
_BULLISH = re.compile(
    r"\b(bullish|moon|rally|long|buy|undervalued|breakout|squeeze)\b",
    re.I,
)


def _post_neg_share(text: str) -> float:
    bear = 1 if _BEARISH.search(text or "") else 0
    bull = 1 if _BULLISH.search(text or "") else 0
    if bear == bull:
        return 0.5
    return 1.0 if bear else 0.0


def _parse_created(value: str | None) -> date | None:
    if not value:
        return None
    try:
        # Bluesky timestamps are ISO-8601 with Z
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).date()
    except ValueError:
        return None


class BlueskySocialProvider(SocialProvider, ProviderMeta):
    def __init__(
        self,
        *,
        tickers: Sequence[str] | None = None,
        history_days: int = 14,
        max_posts_per_ticker: int = 100,
        fetcher: JsonFetcher | None = None,
    ):
        if tickers is None:
            tickers = [t for t, _, _ in FIXTURE_TICKERS]
        self._tickers = [t.upper() for t in tickers]
        self._history_days = max(1, int(history_days))
        self._max_posts = max(1, int(max_posts_per_ticker))
        self._fetcher: JsonFetcher = fetcher or (lambda url, headers=None: get_json(url, headers=headers))

    def name(self) -> str:
        return "bluesky-search"

    def is_fixture(self) -> bool:
        return False

    def metadata(self) -> dict:
        return {
            "source_id": SOURCE_ID,
            "history_days": self._history_days,
            "tickers": len(self._tickers),
            "max_posts_per_ticker": self._max_posts,
            "endpoint": SEARCH_BASE,
            "live": True,
            "auth": "none",
            "note": "search-with-date-range; full getRepo backfill is a later path",
        }

    def _search_ticker(self, ticker: str, start: date, end: date) -> list[dict]:
        since = datetime(start.year, start.month, start.day, tzinfo=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S.000Z"
        )
        until = datetime(end.year, end.month, end.day, 23, 59, 59, tzinfo=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S.000Z"
        )
        collected: list[dict] = []
        cursor: str | None = None
        while len(collected) < self._max_posts:
            url = build_url(
                SEARCH_BASE,
                {
                    "q": f"${ticker}",
                    "limit": min(100, self._max_posts - len(collected)),
                    "sort": "latest",
                    "since": since,
                    "until": until,
                    "cursor": cursor,
                },
            )
            payload = self._fetcher(url, None)
            posts = payload.get("posts") or []
            if not posts:
                break
            collected.extend(posts)
            cursor = payload.get("cursor")
            if not cursor:
                break
        return collected[: self._max_posts]

    def fetch_since(self, cursor: FetchCursor) -> tuple[pd.DataFrame, FetchCursor]:
        end = cursor.as_of
        start = end - timedelta(days=self._history_days - 1)

        # (ticker, day) → aggregates
        counts: dict[tuple[str, str], int] = defaultdict(int)
        neg_hits: dict[tuple[str, str], list[float]] = defaultdict(list)
        likes: dict[tuple[str, str], int] = defaultdict(int)

        for ticker in self._tickers:
            try:
                posts = self._search_ticker(ticker, start, end)
            except RuntimeError:
                continue
            for post in posts:
                record = post.get("record") or {}
                d = _parse_created(record.get("createdAt") or post.get("indexedAt"))
                if d is None or d < start or d > end:
                    continue
                key = (ticker, d.isoformat())
                counts[key] += 1
                neg_hits[key].append(_post_neg_share(str(record.get("text") or "")))
                likes[key] += int(post.get("likeCount") or 0)

        rows = []
        for (ticker, day), n in sorted(counts.items()):
            negs = neg_hits[(ticker, day)]
            rows.append(
                {
                    "date": day,
                    "ticker": ticker,
                    "source_id": SOURCE_ID,
                    "mention_count": n,
                    "neg_share": float(sum(negs) / len(negs)) if negs else 0.5,
                    "upvotes": likes[(ticker, day)],
                }
            )

        df = normalize_social_frame(pd.DataFrame(rows) if rows else empty_social_frame())
        next_cursor = FetchCursor(as_of=end, token=f"bluesky:{start.isoformat()}:{end.isoformat()}")
        return df, next_cursor
