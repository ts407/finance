from __future__ import annotations

import math

import numpy as np
import pytest

from standing.config import load_scoring_config
from standing.domain.scoring.shrinkage import shrink_social
from standing.domain.scoring.tilt import attention_tilt, final_standing, hype_dampener


def test_shrinkage_continuity():
    """S_used moves continuously from prior toward S_obs as n increases."""
    s_obs = 80.0
    prior = 50.0
    k = 10.0
    prev = None
    for n in range(0, 101):
        s_used, c = shrink_social(s_obs, n, k=k, prior=prior)
        assert 0.0 <= c <= 1.0
        assert prior <= float(s_used) <= s_obs
        if prev is not None:
            assert float(s_used) >= prev - 1e-12
        prev = float(s_used)
    # endpoints
    s0, c0 = shrink_social(s_obs, 0, k=k, prior=prior)
    assert float(s0) == pytest.approx(prior)
    assert float(c0) == pytest.approx(0.0)
    s_big, c_big = shrink_social(s_obs, 10_000, k=k, prior=prior)
    assert float(s_big) == pytest.approx(s_obs, abs=0.05)
    assert float(c_big) == pytest.approx(1.0, abs=0.01)


def test_no_two_score_processes():
    """
    There is a single generation path: Base + Tilt → clip.
    No renorm/floor alternate that could disagree with Final.
    """
    rng = np.random.default_rng(0)
    base = rng.uniform(0, 100, size=200)
    s_used = rng.uniform(0, 100, size=200)
    neg = rng.uniform(0, 1, size=200)
    tilt = attention_tilt(s_used, tilt_max=10, beta=1.5, neg_share=neg)
    final = final_standing(base, tilt)
    # Identity of the only process
    assert np.allclose(final, np.clip(base + tilt, 0, 100))
    # Tilt magnitude never exceeds tilt_max
    assert np.all(np.abs(tilt) <= 10.0 + 1e-9)
    # Hype dampener only shrinks positive tilt
    raw = attention_tilt(s_used, tilt_max=10, beta=1.5, neg_share=None)
    damp = hype_dampener(neg)
    for r, t, d in zip(raw, tilt, damp, strict=True):
        if r > 0:
            assert t == pytest.approx(r * d)
        else:
            assert t == pytest.approx(r)


def test_placeholder_true_on_fixture_config():
    cfg = load_scoring_config()
    assert cfg.placeholder is True
    assert cfg.score_kind == "editorial_descriptive"
    assert cfg.methodology_version == "2.2.0"
    # Fixture-bound social/market posture
    assert cfg.social_pipeline["reddit_comments"] is False
    assert cfg.social_tilt["shape"] == "tanh"
    assert cfg.social_tilt["symmetric"] is True
    # Tilt stays bounded (±5) regardless of attention mode — the real safety rail.
    assert math.isclose(cfg.social_tilt["tilt_max"], 5)
    # Track S is unlocked: sentiment axis is a supported, bounded attention mode.
    assert cfg.social_tilt.get("attention_mode") in ("volume_only", "volume_plus_sentiment")
    if cfg.social_tilt.get("attention_mode") == "volume_plus_sentiment":
        assert 0.0 <= float(cfg.social_tilt.get("sentiment_weight", 1.0)) <= 1.0


def test_tilt_tanh_saturates():
    lo = attention_tilt(0.0, tilt_max=10, beta=1.5)
    hi = attention_tilt(100.0, tilt_max=10, beta=1.5)
    mid = attention_tilt(50.0, tilt_max=10, beta=1.5)
    assert float(mid) == pytest.approx(0.0)
    assert abs(float(hi)) < 10.0  # tanh never fully reaches ±tilt_max at finite beta*1
    assert float(hi) > 0
    assert float(lo) < 0
