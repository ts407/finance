from __future__ import annotations

import numpy as np


def shrink_social(
    s_obs: float | np.ndarray,
    n: float | np.ndarray,
    *,
    k: float = 10.0,
    prior: float = 50.0,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Parametric shrinkage toward a flat prior.

    S_used = c * S_obs + (1 - c) * prior
    c = n / (n + k)

    Returns (S_used, c). c is the model confidence quantity.
    """
    s_obs_arr = np.asarray(s_obs, dtype=float)
    n_arr = np.asarray(n, dtype=float)
    n_arr = np.maximum(n_arr, 0.0)
    c = n_arr / (n_arr + float(k))
    s_used = c * s_obs_arr + (1.0 - c) * float(prior)
    return s_used, c
