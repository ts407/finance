"""Compose multiple SocialProviders into one fetch_since stream."""

from __future__ import annotations

from typing import Sequence

import pandas as pd

from standing.providers.base import FetchCursor, ProviderMeta, SocialProvider
from standing.providers.schema import empty_social_frame, normalize_social_frame


class CompositeSocialProvider(SocialProvider, ProviderMeta):
    def __init__(self, providers: Sequence[SocialProvider], *, name: str = "composite-social"):
        if not providers:
            raise ValueError("CompositeSocialProvider requires at least one provider")
        self._providers = list(providers)
        self._name = name

    def name(self) -> str:
        return self._name

    def is_fixture(self) -> bool:
        return all(getattr(p, "is_fixture", lambda: False)() for p in self._providers)

    def metadata(self) -> dict:
        return {
            "providers": [
                {
                    "name": getattr(p, "name", lambda: type(p).__name__)(),
                    "is_fixture": getattr(p, "is_fixture", lambda: False)(),
                    "meta": getattr(p, "metadata", lambda: {})(),
                }
                for p in self._providers
            ]
        }

    def fetch_since(self, cursor: FetchCursor) -> tuple[pd.DataFrame, FetchCursor]:
        frames: list[pd.DataFrame] = []
        tokens: list[str] = []
        for provider in self._providers:
            df, nxt = provider.fetch_since(cursor)
            frames.append(normalize_social_frame(df))
            if nxt.token:
                tokens.append(str(nxt.token))
        if not frames:
            out = empty_social_frame()
        else:
            out = normalize_social_frame(pd.concat(frames, ignore_index=True))
        next_cursor = FetchCursor(
            as_of=cursor.as_of,
            token="|".join(tokens) if tokens else f"composite:{cursor.as_of.isoformat()}",
        )
        return out, next_cursor
