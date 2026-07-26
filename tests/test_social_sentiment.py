"""Track S sentiment axis: volume is amplitude, sentiment is sign."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from standing.config import ScoringConfig, apply_overrides, load_scoring_config
from standing.domain.scoring.pipeline import ScoreInputs, score_cross_section
from standing.domain.scoring.social_features import blend_sentiment, sentiment_polarity


def test_sentiment_polarity_maps_neg_share_to_sign():
    assert float(sentiment_polarity(0.0)) == pytest.approx(1.0)
    assert float(sentiment_polarity(0.5)) == pytest.approx(0.0)
    assert float(sentiment_polarity(1.0)) == pytest.approx(-1.0)


def test_blend_sentiment_full_weight_is_symmetric():
    # Loud name (volume 90 → +40 amplitude). Full sentiment weight.
    assert float(blend_sentiment(90.0, 0.0, weight=1.0)) == pytest.approx(90.0)  # bullish keeps high
    assert float(blend_sentiment(90.0, 1.0, weight=1.0)) == pytest.approx(10.0)  # bearish flips low
    assert float(blend_sentiment(90.0, 0.5, weight=1.0)) == pytest.approx(50.0)  # neutral collapses


def test_blend_sentiment_zero_weight_is_volume_only():
    for neg in (0.0, 0.5, 1.0):
        assert float(blend_sentiment(90.0, neg, weight=0.0)) == pytest.approx(90.0)


def test_blend_sentiment_quiet_names_barely_move():
    # Volume ~50 (neutral loudness): sentiment has little to amplify.
    assert float(blend_sentiment(50.0, 0.0, weight=1.0)) == pytest.approx(50.0)
    assert float(blend_sentiment(50.0, 1.0, weight=1.0)) == pytest.approx(50.0)


def _cfg(mode: str, weight: float = 1.0) -> ScoringConfig:
    base = load_scoring_config()
    return ScoringConfig(
        raw=apply_overrides(
            base.raw,
            {"social_tilt.attention_mode": mode, "social_tilt.sentiment_weight": weight},
        ),
        path=base.path,
    )


def _market(as_of: date, tickers: list[str]) -> pd.DataFrame:
    # Same-sector names, identical fundamentals; only social attention/sentiment differs.
    rows = []
    for tk in tickers:
        rows.append(
            {
                "ticker": tk,
                "sector": "Information Technology",
                "listing": "US",
                "market_cap": 5e11,
                "adv_20d": 1e9,
                "pe_ttm": 20.0,
                "pb": 5.0,
                "ev_ebitda": 15.0,
                "ev_ebit": 18.0,
                "ev_sales": 5.0,
                "roe": 0.2,
                "operating_margin": 0.25,
                "revenue_growth_yoy": 0.1,
                "ret_1m": 0.02,
                "ret_3m": 0.05,
                "ret_6m": 0.1,
                "relative_volume": 1.0,
                "as_of": as_of.isoformat(),
            }
        )
    return pd.DataFrame(rows)


def _social(as_of: date, mentions_neg: dict[str, tuple[int, float]]) -> pd.DataFrame:
    rows = []
    for tk, (count, neg) in mentions_neg.items():
        rows.append(
            {
                "date": as_of.isoformat(),
                "ticker": tk,
                "source_id": "reddit",
                "mention_count": count,
                "neg_share": neg,
                "upvotes": 100,
            }
        )
    return pd.DataFrame(rows)


def test_sentiment_axis_pushes_negative_names_below_positive():
    as_of = date(2026, 7, 26)
    # Two LOUD names (bullish vs bearish) plus quiet filler so the loud pair ranks
    # high on the volume axis and sentiment actually has amplitude to flip.
    tickers = ["AAA", "BBB", "Q1", "Q2", "Q3", "Q4"]
    market = _market(as_of, tickers)
    social = _social(
        as_of,
        {
            "AAA": (500, 0.1),  # loud + bullish
            "BBB": (500, 0.9),  # loud + bearish
            "Q1": (4, 0.5),
            "Q2": (4, 0.5),
            "Q3": (4, 0.5),
            "Q4": (4, 0.5),
        },
    )
    inputs = ScoreInputs(market=market, social_daily=social, as_of=pd.Timestamp(as_of))

    sent = score_cross_section(inputs, _cfg("volume_plus_sentiment", weight=1.0)).set_index("ticker")
    vol = score_cross_section(inputs, _cfg("volume_only")).set_index("ticker")

    # Sentiment axis: bearish name tilts strictly below the bullish name.
    assert sent.loc["BBB", "attention_tilt"] < sent.loc["AAA", "attention_tilt"]
    # And the bearish name is pushed negative (not merely damped toward zero).
    assert sent.loc["BBB", "attention_tilt"] < 0.0
    # Tilt stays bounded by tilt_max regardless of mode.
    tilt_max = float(load_scoring_config().social_tilt["tilt_max"])
    assert sent["attention_tilt"].abs().max() <= tilt_max + 1e-9
    assert vol["attention_tilt"].abs().max() <= tilt_max + 1e-9
