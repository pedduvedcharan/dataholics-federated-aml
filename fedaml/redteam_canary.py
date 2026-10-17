"""DP auditing game: can the coordinator tell whether ONE flagged transaction was used?

Why this exists: on the real IBM AML shards every row-level membership attack
sits at chance even with DP off (see docs/REDTEAM.md).  The model is a
21-parameter logistic regression and the learnable laundering (banks 2-4) is
~100 near-identical ACH rows, so there is nothing row-specific to read.  That
is a result, not a proof of privacy.  The standard way to *measure* what DP
buys in that situation is the auditing game of Jagielski et al. (2020) and
Nasr et al. (2021):

* World IN:  bank b trains its round update on its data plus one target row.
* World OUT: bank b trains on its data alone.
* The update is clipped and (DP on) noised with FEDERATION's own
  ``fedaml.dp.privatize``.  The attacker sees only that update, exactly what
  the coordinator receives, and guesses IN or OUT.

Each trial reshuffles local SGD (different seed), so DP off is not trivially
deterministic: the attacker must beat natural training noise.  The target row
is a real laundering transaction from bank b's held-out test file (the one the
current model scores lowest, i.e. the suspect whose inclusion moves the update
most; DP must hold for every row, so the worst case is the honest test).  The
attacker knows the training recipe (standard in DP auditing): half the trials
estimate the IN-minus-OUT direction and a threshold, the other half are scored.
We also report an empirical lower bound on epsilon from the attack's TPR/FPR
(Clopper-Pearson, 95 %), to set next to the accountant's approximate epsilon.

    python -m fedaml.redteam_canary --bank 2 --sigmas 0,0.3,0.5,0.8 --trials 120
"""
from __future__ import annotations

import argparse
import logging
import math
import time
from pathlib import Path
from typing import Optional

import numpy as np
from scipy.stats import beta
from sklearn.linear_model import SGDClassifier
from sklearn.metrics import roc_auc_score
from sklearn.utils.class_weight import compute_class_weight

from fedaml import dp
from fedaml.redteam import _best_threshold, _bootstrap_auc_ci, verdict, write_json_atomic
from fedaml.redteam_data import _labels, _read, featurize

log = logging.getLogger("fedaml.redteam_canary")


def local_update(X: np.ndarray, y: np.ndarray, start: np.ndarray, epochs: int, eta: float,
                 class_w: dict, seed: int) -> np.ndarray:
    """One bank round: SGD log-loss from the global weights, delta = local - global (CONTRACTS §4)."""
    clf = SGDClassifier(loss="log_loss", learning_rate="constant", eta0=eta, random_state=seed)
    clf.partial_fit(X[:2], np.array([0, 1]), classes=np.array([0, 1]))      # allocate coef_
    clf.coef_, clf.intercept_ = start[:-1].reshape(1, -1).copy(), start[-1:].copy()
    sw = np.where(y == 1, class_w[1], class_w[0])
    for _ in range(epochs):
        clf.partial_fit(X, y, sample_weight=sw)
    return np.r_[clf.coef_.ravel(), clf.intercept_] - start


def clopper_pearson_eps(tp: int, n_in: int, fp: int, n_out: int, dp_delta: float = 1e-5,
                        conf: float = 0.95) -> float:
    """Empirical epsilon lower bound: ln((TPR_lo - delta) / FPR_hi), 0 when not significant."""
    a = 1 - conf
    tpr_lo = beta.ppf(a / 2, tp, n_in - tp + 1) if tp > 0 else 0.0
    fpr_hi = beta.ppf(1 - a / 2, fp + 1, n_out - fp) if fp < n_out else 1.0
    if tpr_lo - dp_delta <= 0 or fpr_hi <= 0:
        return 0.0
    return max(0.0, math.log((tpr_lo - dp_delta) / fpr_hi))


def play(X: np.ndarray, y: np.ndarray, canary: np.ndarray, start: np.ndarray, sigma: float, clip: float,
         trials: int, epochs: int, eta: float, seed: int) -> dict:
    """Run the IN/OUT game `trials` times per world and score a projection attack."""
    w = compute_class_weight("balanced", classes=np.array([0, 1]), y=y)
    cw = {0: float(w[0]), 1: float(w[1])}
    X_in, y_in = np.vstack([X, canary[None, :]]), np.r_[y, 1]
    rng = np.random.default_rng(seed)
    ups = {"in": [], "out": []}
    for t in range(trials):
        for world, (Xa, ya) in (("in", (X_in, y_in)), ("out", (X, y))):
            raw = local_update(Xa, ya, start, epochs, eta, cw, seed + 1000 + t)
            sent, _ = dp.privatize(raw, clip, sigma, sigma > 0, rng)
            ups[world].append(sent)
    U_in, U_out = np.array(ups["in"]), np.array(ups["out"])
    half = trials // 2
    direction = U_in[:half].mean(0) - U_out[:half].mean(0)
    direction /= np.linalg.norm(direction) + 1e-12
    s_cal = np.r_[U_in[:half] @ direction, U_out[:half] @ direction]
    m_cal = np.r_[np.ones(half), np.zeros(half)]
    t = _best_threshold(-s_cal, m_cal)                                       # IN iff score > -t
    s_in, s_out = U_in[half:] @ direction, U_out[half:] @ direction
    s, m = np.r_[s_in, s_out], np.r_[np.ones(len(s_in)), np.zeros(len(s_out))]
    pred = -s < t
    tp, fp = int(pred[m == 1].sum()), int(pred[m == 0].sum())
    res = {"sigma": sigma, "clip_norm": clip, "trials_per_world": trials, "n_scored": int(len(s)),
           "attack_acc": float(np.mean(pred == (m == 1))), "attack_auc": float(roc_auc_score(m, s)),
           "attack_auc_ci90": _bootstrap_auc_ci(s, m, seed), "tpr": tp / len(s_in), "fpr": fp / len(s_out),
           "eps_empirical_lower_95": clopper_pearson_eps(tp, len(s_in), fp, len(s_out)),
           "eps_accountant_1round": dp.epsilon_spent(sigma, 1) if sigma > 0 else None,
           "raw_update_norm_mean": None}
    res["verdict"] = verdict(res)
    return res


def pick_canary(X_te: np.ndarray, y_te: np.ndarray, start: np.ndarray) -> tuple[int, np.ndarray]:
    """The held-out laundering row the starting model scores lowest (largest-gradient suspect)."""
    pos = np.flatnonzero(y_te == 1)
    z = X_te[pos] @ start[:-1] + start[-1]
    i = int(pos[np.argmin(z)])
    return i, X_te[i]


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="DP auditing game on one flagged transaction")
    ap.add_argument("--bank", type=int, default=2)
    ap.add_argument("--start-model", help="global model JSON to start the round from (default: zeros = round 1)")
    ap.add_argument("--sigmas", default="0,0.3,0.5,0.8")
    ap.add_argument("--clip", type=float, default=1.0)
    ap.add_argument("--trials", type=int, default=120, help="per world (IN and OUT)")
    ap.add_argument("--epochs", type=int, default=1)
    ap.add_argument("--eta", type=float, default=1e-3)
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--out", default="state/redteam_canary.json")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    t0 = time.time()
    bdir = Path(args.data_dir) / "banks" / f"bank_{args.bank}"
    tr, te = _read(bdir / "train.csv"), _read(bdir / "test.csv")
    import pandas as pd
    Xb, names = featurize(pd.concat([tr, te], ignore_index=True))
    X, y = Xb[: len(tr)].astype(np.float64), _labels(tr)
    X_te, y_te = Xb[len(tr):].astype(np.float64), _labels(te)
    start = np.zeros(len(names) + 1)
    if args.start_model:
        from fedaml.redteam import align_columns, load_model
        m = load_model(args.start_model)
        start = np.r_[m["coef"], m["intercept"]]
    idx, canary = pick_canary(X_te, y_te, start)
    rows = {}
    for sg in [float(s) for s in args.sigmas.split(",")]:
        rows[f"DP off" if sg == 0 else f"DP on σ={sg}"] = play(X, y, canary, start, sg, args.clip, args.trials,
                                                             args.epochs, args.eta, args.seed)
    seconds = time.time() - t0
    report = {"attack": "dp_audit_canary", "bank": args.bank, "target_row": f"bank_{args.bank} test.csv laundering row #{idx}",
              "target_row_txn": {k: str(v) for k, v in te.iloc[idx].items() if k not in ("from_acct", "to_acct")},
              "start_model": args.start_model or "zeros (round 1)", "rows": rows, "seed": args.seed,
              "runtime_s": round(seconds, 1), "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    write_json_atomic(args.out, report)
    print(f"{'setting':<14}{'attack acc':>11}{'attack AUC':>11}  {'90% CI':<13}{'TPR':>6}{'FPR':>6}{'emp. ε ≥':>10}{'acct ε (1 rd)':>15}   verdict")
    for name, r in rows.items():
        ci = f"[{r['attack_auc_ci90'][0]:.2f}, {r['attack_auc_ci90'][1]:.2f}]"
        acct = "∞ (no noise)" if r["eps_accountant_1round"] is None else f"≈{r['eps_accountant_1round']:.1f}"
        print(f"{name:<14}{r['attack_acc']:>11.3f}{r['attack_auc']:>11.3f}  {ci:<13}{r['tpr']:>6.2f}{r['fpr']:>6.2f}"
              f"{r['eps_empirical_lower_95']:>10.2f}{acct:>15}   {r['verdict']}")
    print(f"\ngame: bank {args.bank} round update with vs without one held-out laundering row (#{idx}); "
          f"{args.trials} trials per world, half to calibrate | clip {args.clip} | seed {args.seed} | {seconds:.1f}s | wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
