"""Differential privacy primitives for federated updates (FEDERATION owns).

Mechanism (update-level, applied by the bank BEFORE ``egress.send`` so the
coordinator never sees a raw delta):

1. ``clip``:   delta <- delta * min(1, clip_norm / ||delta||_2)
2. ``add_noise``: delta <- delta + N(0, (sigma * clip_norm)^2 I)

Unit of protection
------------------
One bank's whole model update in one round (participant-level DP). It is
NOT a per-transaction guarantee. Everything the coordinator, the dashboard
and the red team see is post-processing of these noised updates.

Approximate epsilon accounting (``epsilon_spent``)
-------------------------------------------------
Each round releases one Gaussian mechanism with L2 sensitivity ``clip_norm``
and noise std ``sigma * clip_norm``, i.e. noise multiplier z = sigma.
T rounds of the Gaussian mechanism compose exactly (in zCDP terms,
rho = T / (2 sigma^2)) to a single Gaussian mechanism with multiplier
z_T = sigma / sqrt(T). We convert (z_T, delta) to epsilon with the analytic
Gaussian mechanism of Balle & Wang (ICML 2018)::

    delta(eps) = Phi(1/(2 z_T) - eps z_T) - exp(eps) * Phi(-1/(2 z_T) - eps z_T)

and solve for the smallest eps with delta(eps) <= delta by bisection.
Simplifications, hence "approximate": we ignore that the aggregate is an
average over banks (only helps), we treat every round as a fresh release of
the same sensitivity (true because the bank re-clips every round), and we do
not use privacy amplification of any kind. Report the value as
"approximately epsilon = X at delta = Y" and never as an exact bound.
"""
from __future__ import annotations

import logging
import math

import numpy as np

log = logging.getLogger("fedaml.dp")

_SQRT2 = math.sqrt(2.0)
_LOG_SQRT_2PI = 0.5 * math.log(2.0 * math.pi)


def clip(delta: np.ndarray, clip_norm: float) -> tuple[np.ndarray, float]:
    """L2-clip ``delta`` to ``clip_norm``. Returns (clipped, original_norm)."""
    delta = np.asarray(delta, dtype=np.float64)
    norm = float(np.linalg.norm(delta))
    if clip_norm <= 0 or norm <= clip_norm or norm == 0.0:
        return delta.copy(), norm
    return delta * (clip_norm / norm), norm


def add_noise(
    delta: np.ndarray, sigma: float, clip_norm: float, rng: np.random.Generator
) -> np.ndarray:
    """Add isotropic Gaussian noise with std ``sigma * clip_norm`` to a clipped delta."""
    delta = np.asarray(delta, dtype=np.float64)
    if sigma <= 0:
        return delta.copy()
    return delta + rng.normal(0.0, sigma * clip_norm, size=delta.shape)


def _log_ndtr(x: float) -> float:
    """log of the standard normal CDF, stable for very negative x."""
    if x < -20.0:
        return -0.5 * x * x - math.log(-x) - _LOG_SQRT_2PI
    return math.log(0.5 * math.erfc(-x / _SQRT2))


def _ndtr(x: float) -> float:
    return 0.5 * math.erfc(-x / _SQRT2)


def gaussian_delta(eps: float, z: float) -> float:
    """delta(eps) of the Gaussian mechanism with sensitivity 1 and noise std z."""
    a = 1.0 / (2.0 * z)
    term1 = _ndtr(a - eps * z)
    term2 = math.exp(eps + _log_ndtr(-a - eps * z))
    return max(0.0, term1 - term2)


def epsilon_spent(sigma: float, rounds: int, delta: float = 1e-5) -> float:
    """Approximate epsilon after ``rounds`` releases with noise multiplier ``sigma``.

    See the module docstring for the formula. Returns ``inf`` when sigma <= 0
    (no noise) and 0.0 when no rounds have completed.
    """
    if rounds <= 0:
        return 0.0
    if sigma <= 0:
        return float("inf")
    z_t = sigma / math.sqrt(rounds)
    if gaussian_delta(0.0, z_t) <= delta:
        return 0.0
    lo, hi = 0.0, 1.0
    while gaussian_delta(hi, z_t) > delta:
        hi *= 2.0
        if hi > 1e6:
            return float("inf")
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        if gaussian_delta(mid, z_t) > delta:
            lo = mid
        else:
            hi = mid
    return round(hi, 4)


def privatize(
    delta: np.ndarray,
    clip_norm: float,
    sigma: float,
    enabled: bool,
    rng: np.random.Generator,
) -> tuple[np.ndarray, dict]:
    """Clip always; add noise when ``enabled``. Returns (delta, info dict for logs)."""
    clipped, raw_norm = clip(delta, clip_norm)
    out = add_noise(clipped, sigma, clip_norm, rng) if enabled else clipped
    info = {
        "raw_norm": round(raw_norm, 6),
        "clipped_norm": round(float(np.linalg.norm(clipped)), 6),
        "sent_norm": round(float(np.linalg.norm(out)), 6),
        "clip_norm": clip_norm,
        "dp_enabled": bool(enabled),
        "sigma": sigma if enabled else 0.0,
    }
    return out, info


if __name__ == "__main__":  # quick table for the README / privacy meter
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    for s in (0.5, 0.8, 1.0, 2.0, 4.0):
        row = ", ".join(f"T={t}: {epsilon_spent(s, t):.2f}" for t in (1, 5, 10))
        log.info("sigma=%s  approx epsilon (delta=1e-5): %s", s, row)
