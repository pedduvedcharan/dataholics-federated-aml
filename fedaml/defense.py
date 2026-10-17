"""Rogue-update detection for the coordinator (FEDERATION owns).

Given the deltas received in one round:

(a) Hard norm check, always on. Honest banks clip to ``clip_norm`` before
    sending, so ``||delta|| > 1.5 * clip_norm`` is impossible for them. When
    DP is on the noise alone has expected norm ``sigma*clip_norm*sqrt(d)``, so
    the bound is widened by four noise standard deviations.
(b) Robust outlier screen, disabled by ``--defense off`` so the demo can show
    the damage. Needs at least three updates (with two, the median is the
    midpoint and the honest bank looks as far from it as the rogue):
      - coordinate-wise median of the deltas;
      - exclude a bank whose cosine distance to the median exceeds ``tau``;
      - exclude a bank whose norm exceeds ``norm_ratio`` x the median norm.

Why tau = 1.5 (cosine distance; 0 = same direction, 1 = orthogonal, 2 = opposite).
Measured on the real IBM AML shards, 10 rounds, prox trainer, clip 1.0:
honest banks 2-4 score 0.02-0.32; honest bank 1, whose data is not learnable
with per-row features, scores 0.94-1.33, i.e. roughly orthogonal to the
consensus; the scaled rogue (x -20) scores 1.84. Poisoning that hides
laundering has to push the model AGAINST the consensus, so the test excludes
updates that oppose it (similarity below -0.5), not updates that merely
disagree. tau 0.5 or 0.8 excluded honest bank 1 every round.

Every exclusion is recorded as ``{"bank_id", "reason", "score"}`` and the
scores of all banks are returned for the regulator dashboard.
"""
from __future__ import annotations

import logging
import math

import numpy as np

log = logging.getLogger("fedaml.defense")


def cosine_distance(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    if na == 0.0 or nb == 0.0:
        return 1.0
    return float(1.0 - np.dot(a, b) / (na * nb))


def screen_updates(
    deltas: dict[int, np.ndarray],
    clip_norm: float,
    enabled: bool = True,
    tau: float = 0.5,
    norm_ratio: float = 3.0,
    noise_std: float = 0.0,
) -> tuple[list[int], list[dict], dict[int, dict]]:
    """Return (accepted_ids, excluded [{bank_id, reason, score}], scores per bank)."""
    excluded: list[dict] = []
    scores: dict[int, dict] = {}
    if not deltas:
        return [], excluded, scores
    d = len(next(iter(deltas.values())))
    hard_bound = 1.5 * clip_norm + (4.0 * noise_std * math.sqrt(d) if noise_std > 0 else 0.0)

    survivors: dict[int, np.ndarray] = {}
    for bid, vec in deltas.items():
        norm = float(np.linalg.norm(vec))
        scores[bid] = {"norm": round(norm, 6)}
        if norm > hard_bound:
            excluded.append({"bank_id": bid, "reason": "norm_exceeds_clip_bound", "score": round(norm, 6)})
            log.warning("bank %s hard-rejected: norm %.4f > bound %.4f", bid, norm, hard_bound)
        else:
            survivors[bid] = vec

    if not enabled or len(survivors) < 3:
        if enabled and len(survivors) < 3 and survivors:
            log.info("defense: only %d updates, outlier screen needs 3; skipping", len(survivors))
        return sorted(survivors), excluded, scores

    stack = np.stack(list(survivors.values()))
    median = np.median(stack, axis=0)
    median_norm = float(np.median(np.linalg.norm(stack, axis=1)))
    accepted: list[int] = []
    for bid, vec in survivors.items():
        cos = cosine_distance(vec, median)
        norm = scores[bid]["norm"]
        scores[bid].update({"cosine_to_median": round(cos, 6), "norm_ratio": round(norm / median_norm, 6) if median_norm > 0 else None})
        if cos > tau:
            excluded.append({"bank_id": bid, "reason": "cosine_distance_to_median", "score": round(cos, 6)})
            log.warning("bank %s excluded: cosine distance %.3f > tau %.2f", bid, cos, tau)
        elif median_norm > 0 and norm > norm_ratio * median_norm:
            excluded.append({"bank_id": bid, "reason": "norm_ratio_to_median", "score": round(norm / median_norm, 6)})
            log.warning("bank %s excluded: norm %.3f > %.1fx median %.3f", bid, norm, norm_ratio, median_norm)
        else:
            accepted.append(bid)
    return sorted(accepted), excluded, scores


def weighted_mean(deltas: dict[int, np.ndarray], n_samples: dict[int, int], cap_factor: float = 2.0) -> tuple[np.ndarray, dict[int, float]]:
    """FedAvg weights = claimed n_samples capped at ``cap_factor`` x the median claim.

    The cap stops a rogue bank from buying influence by lying about its data size.
    Returns (mean delta, effective weight per bank).
    """
    ids = list(deltas)
    claims = np.array([max(1, int(n_samples[b])) for b in ids], dtype=float)
    cap = cap_factor * float(np.median(claims))
    w = np.minimum(claims, cap)
    w = w / w.sum()
    mean = np.sum([w[i] * deltas[b] for i, b in enumerate(ids)], axis=0)
    return mean, {b: round(float(w[i]), 6) for i, b in enumerate(ids)}
