from __future__ import annotations

import numpy as np


def hype_dampener(
    neg_share: float | np.ndarray,
    *,
    pivot: float = 0.5,
) -> np.ndarray:
    """
    Dampen positive tilt when negative mention share exceeds pivot.

    d = 1 - 2 * max(0, neg_share - pivot)
    """
    neg = np.asarray(neg_share, dtype=float)
    d = 1.0 - 2.0 * np.maximum(0.0, neg - float(pivot))
    return np.clip(d, 0.0, 1.0)


def attention_tilt(
    s_used: float | np.ndarray,
    *,
    tilt_max: float = 10.0,
    beta: float = 1.5,
    neg_share: float | np.ndarray | None = None,
    dampener_pivot: float = 0.5,
) -> np.ndarray:
    """
    Symmetric tanh tilt around neutral 50.

    Tilt = tilt_max * tanh(beta * (S_used - 50) / 50)
    Positive tilt is scaled by the hype dampener when neg_share is provided.
    """
    s = np.asarray(s_used, dtype=float)
    raw = float(tilt_max) * np.tanh(float(beta) * (s - 50.0) / 50.0)
    if neg_share is None:
        return raw
    d = hype_dampener(neg_share, pivot=dampener_pivot)
    pos = raw > 0
    out = raw.copy()
    out[pos] = raw[pos] * d[pos]
    return out


def final_standing(
    base: float | np.ndarray,
    tilt: float | np.ndarray,
) -> np.ndarray:
    """Final Standing = clip(Base + Tilt, 0, 100). Single score process."""
    return np.clip(np.asarray(base, dtype=float) + np.asarray(tilt, dtype=float), 0.0, 100.0)
