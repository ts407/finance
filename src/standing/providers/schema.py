"""Shared social row contract used by fixture and live providers."""

from __future__ import annotations

import pandas as pd

SOCIAL_COLUMNS = ("date", "ticker", "source_id", "mention_count", "neg_share", "upvotes")


def empty_social_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=list(SOCIAL_COLUMNS))


def normalize_social_frame(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return empty_social_frame()
    out = df.copy()
    for col in SOCIAL_COLUMNS:
        if col not in out.columns:
            if col == "neg_share":
                out[col] = 0.5
            elif col == "upvotes":
                out[col] = 0
            elif col == "mention_count":
                out[col] = 0
            else:
                out[col] = None
    out = out.loc[:, list(SOCIAL_COLUMNS)]
    out["date"] = out["date"].astype(str)
    out["ticker"] = out["ticker"].astype(str)
    out["source_id"] = out["source_id"].astype(str)
    out["mention_count"] = pd.to_numeric(out["mention_count"], errors="coerce").fillna(0).astype(int)
    out["neg_share"] = pd.to_numeric(out["neg_share"], errors="coerce").fillna(0.5).clip(0, 1)
    out["upvotes"] = pd.to_numeric(out["upvotes"], errors="coerce").fillna(0).astype(int)
    return out.reset_index(drop=True)


def assert_social_contract(df: pd.DataFrame) -> None:
    missing = [c for c in SOCIAL_COLUMNS if c not in df.columns]
    if missing:
        raise AssertionError(f"social frame missing columns: {missing}")
