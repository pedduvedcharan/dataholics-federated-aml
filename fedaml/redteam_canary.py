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
import os
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


def prox_update(X: np.ndarray, y: np.ndarray, start: np.ndarray, class_w: dict, mu: float = 0.5,
                C: float = 1.0, local_iters: int = 50) -> np.ndarray:
    """FEDERATION's default trainer (fedaml.bank prox, read-only reuse): delta = prox optimum - global."""
    from types import SimpleNamespace
    from fedaml.bank import BankClient as Bank
    shim = SimpleNamespace(args=SimpleNamespace(mu=mu, C=C, local_iters=local_iters), class_weight=class_w)
    return Bank.prox_solve(shim, start.copy(), X, y) - start


def raw_updates(X: np.ndarray, y: np.ndarray, canary: np.ndarray, start: np.ndarray, trials: int, trainer: str,
                subsample: float, epochs: int, eta: float, seed: int, mu: float = 0.1) -> dict[str, np.ndarray]:
    """Pre-noise updates for both worlds. Trial t uses the same seeded subsample of the bank's
    other rows in both worlds (the attacker does not know which rows those are), so IN and OUT
    differ only by the target row."""
    w = compute_class_weight("balanced", classes=np.array([0, 1]), y=y)
    cw = {0: float(w[0]), 1: float(w[1])}
    rng = np.random.default_rng(seed)
    ups = {"in": [], "out": []}
    for t in range(trials):
        keep = rng.random(len(y)) < subsample if subsample < 1 else np.ones(len(y), dtype=bool)
        Xo, yo = X[keep], y[keep]
        for world, (Xa, ya) in (("in", (np.vstack([Xo, canary[None, :]]), np.r_[yo, 1])), ("out", (Xo, yo))):
            if trainer == "prox":
                ups[world].append(prox_update(Xa, ya, start, cw, mu=mu))
            else:
                ups[world].append(local_update(Xa, ya, start, epochs, eta, cw, seed + 1000 + t))
    return {k: np.array(v) for k, v in ups.items()}


def clopper_pearson_eps(tp: int, n_in: int, fp: int, n_out: int, dp_delta: float = 1e-5,
                        conf: float = 0.95) -> float:
    """Empirical epsilon lower bound: ln((TPR_lo - delta) / FPR_hi), 0 when not significant."""
    a = 1 - conf
    tpr_lo = beta.ppf(a / 2, tp, n_in - tp + 1) if tp > 0 else 0.0
    fpr_hi = beta.ppf(1 - a / 2, fp + 1, n_out - fp) if fp < n_out else 1.0
    if tpr_lo - dp_delta <= 0 or fpr_hi <= 0:
        return 0.0
    return max(0.0, math.log((tpr_lo - dp_delta) / fpr_hi))


def play(raw: dict[str, np.ndarray], sigma: float, clip: float, seed: int, bank: int = 0,
         draws: int = 20) -> dict:
    """Score the strongest standard adversary against the clipped (+ noised) updates.

    The attacker knows the training recipe (as DP assumes), so it simulates
    noise-free training on the calibration half of the trials to learn the
    IN-minus-OUT direction of the *clipped* update; for Gaussian noise the
    projection onto that direction is the likelihood-ratio test.  Every update
    is then released ``draws`` times through ``fedaml.dp.privatize`` (fresh
    noise each time), the threshold is set on the calibration half and the
    attack is scored on the held-out half.  CIs bootstrap over trials, not
    draws, so repeated noise on one update cannot fake precision.  Noise is
    seeded by (seed, bank, sigma) so banks are independent evidence.
    """
    rng = np.random.default_rng([seed, bank, int(round(sigma * 1000))])
    clipped = {w: np.array([dp.clip(u, clip)[0] for u in raw[w]]) for w in raw}
    trials = len(clipped["in"])
    half = trials // 2
    direction = clipped["in"][:half].mean(0) - clipped["out"][:half].mean(0)
    direction /= np.linalg.norm(direction) + 1e-12

    def release(world: str, idx: range) -> tuple[np.ndarray, np.ndarray]:
        k = draws if sigma > 0 else 1
        sc, tr = [], []
        for t in idx:
            for _ in range(k):
                sc.append(dp.privatize(raw[world][t], clip, sigma, sigma > 0, rng)[0] @ direction)
                tr.append(t)
        return np.array(sc), np.array(tr)

    ci_, _ = release("in", range(half)); co_, _ = release("out", range(half))
    thr = _best_threshold(-np.r_[ci_, co_], np.r_[np.ones(len(ci_)), np.zeros(len(co_))])   # IN iff score > -thr
    s_in, t_in = release("in", range(half, trials)); s_out, t_out = release("out", range(half, trials))
    s, m = np.r_[s_in, s_out], np.r_[np.ones(len(s_in)), np.zeros(len(s_out))]
    pred = -s < thr
    tp, fp = int(pred[m == 1].sum()), int(pred[m == 0].sum())
    # cluster bootstrap over held-out trials
    boot, ev = [], np.arange(half, trials)
    brng = np.random.default_rng(seed)
    for _ in range(300):
        pick = brng.choice(ev, len(ev), replace=True)
        bi = np.concatenate([s_in[t_in == t] for t in pick]); bo = np.concatenate([s_out[t_out == t] for t in pick])
        boot.append(roc_auc_score(np.r_[np.ones(len(bi)), np.zeros(len(bo))], np.r_[bi, bo]))
    n_trials_scored = int(trials - half)
    res = {"sigma": sigma, "clip_norm": clip, "trials_per_world": trials, "noise_draws_per_update": draws if sigma > 0 else 1,
           "n_scored": int(len(s)), "n_trials_scored_per_world": n_trials_scored,
           "attack_acc": float(np.mean(pred == (m == 1))), "attack_auc": float(roc_auc_score(m, s)),
           "attack_auc_ci90": [float(x) for x in np.percentile(boot, [5, 95])],
           "tpr": tp / len(s_in), "fpr": fp / len(s_out),
           # epsilon bound counts independent trials only (conservative: draws are not independent mechanisms here)
           "eps_empirical_lower_95": clopper_pearson_eps(int(round(tp / len(s_in) * n_trials_scored)), n_trials_scored,
                                                         int(round(fp / len(s_out) * n_trials_scored)), n_trials_scored),
           "eps_accountant_1round": dp.epsilon_spent(sigma, 1) if sigma > 0 else None,
           "raw_update_norm_mean": float(np.linalg.norm(raw["out"], axis=1).mean()),
           "raw_in_minus_out_norm_mean": float(np.linalg.norm(raw["in"] - raw["out"], axis=1).mean()),
           "noise_std_per_coord": sigma * clip}
    res["verdict"] = verdict(res)
    res["auc_distance_from_chance"] = abs(res["attack_auc"] - 0.5)
    return res


def pick_canary(X_te: np.ndarray, y_te: np.ndarray, start: np.ndarray) -> tuple[int, np.ndarray]:
    """The held-out laundering row the starting model scores lowest (largest-gradient suspect)."""
    pos = np.flatnonzero(y_te == 1)
    z = X_te[pos] @ start[:-1] + start[-1]
    i = int(pos[np.argmin(z)])
    return i, X_te[i]


def default_mu() -> float:
    """Same proximal strength the banks use: env MU (compose sets it), else the demo value 0.1."""
    return float(os.environ.get("MU", "0.1"))


def run_game(data_dir: str, bank: int, dp_cfgs: list[dict], trials: int, seed: int,
             trainer: str = "prox", subsample: float = 0.9, mu: Optional[float] = None) -> dict:
    """Library entry for ``fedaml.redteam``: one set of raw updates, one scored row per DP config."""
    import pandas as pd
    bdir = Path(data_dir) / "banks" / f"bank_{bank}"
    tr, te = _read(bdir / "train.csv"), _read(bdir / "test.csv")
    Xb, names = featurize(pd.concat([tr, te], ignore_index=True))
    X, y = Xb[: len(tr)].astype(np.float64), _labels(tr)
    X_te, y_te = Xb[len(tr):].astype(np.float64), _labels(te)
    start = np.zeros(len(names) + 1)
    idx, canary = pick_canary(X_te, y_te, start)
    mu = default_mu() if mu is None else mu
    raw = raw_updates(X, y, canary, start, trials, trainer, subsample, 1, 1e-3, seed, mu)
    rows = [play(raw, c["sigma"] if c["enabled"] else 0.0, c["clip_norm"], seed, bank) for c in dp_cfgs]
    return {"bank": bank, "target_index": idx, "trials_per_world": trials, "trainer": trainer, "mu": mu,
            "subsample": subsample, "start_model": "zeros (round 1)", "rows": rows}


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="DP auditing game on one flagged transaction")
    ap.add_argument("--bank", type=int, default=2)
    ap.add_argument("--start-model", help="global model JSON to start the round from (default: zeros = round 1)")
    ap.add_argument("--sigmas", default="0,0.3,0.5,0.8")
    ap.add_argument("--clip", type=float, default=1.0)
    ap.add_argument("--trials", type=int, default=120, help="per world (IN and OUT)")
    ap.add_argument("--trainer", choices=["prox", "sgd"], default="prox", help="prox = FEDERATION's default bank trainer")
    ap.add_argument("--mu", type=float, default=None, help="prox strength; default env MU, else 0.1 (match the banks)")
    ap.add_argument("--subsample", type=float, default=0.9,
                    help="fraction of the bank's other rows used per trial (attacker uncertainty); 1.0 = attacker knows them all")
    ap.add_argument("--draws", type=int, default=20, help="fresh DP noise draws per update (DP on)")
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
    mu = default_mu() if args.mu is None else args.mu
    raw = raw_updates(X, y, canary, start, args.trials, args.trainer, args.subsample, args.epochs, args.eta, args.seed, mu)
    rows = {}
    for sg in [float(s) for s in args.sigmas.split(",")]:
        rows["DP off" if sg == 0 else f"DP on σ={sg}"] = play(raw, sg, args.clip, args.seed, args.bank, args.draws)
    seconds = time.time() - t0
    report = {"attack": "dp_audit_canary", "bank": args.bank, "target_row": f"bank_{args.bank} test.csv laundering row #{idx}",
              "target_row_txn": {k: str(v) for k, v in te.iloc[idx].items() if k not in ("from_acct", "to_acct")},
              "start_model": args.start_model or "zeros (round 1)", "trainer": args.trainer, "mu": mu,
              "subsample": args.subsample, "rows": rows, "seed": args.seed,
              "runtime_s": round(seconds, 1), "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    write_json_atomic(args.out, report)
    print(f"{'setting':<14}{'attack acc':>11}{'attack AUC':>11}  {'90% CI':<13}{'TPR':>6}{'FPR':>6}{'emp. ε ≥':>10}{'acct ε (1 rd)':>15}   verdict")
    for name, r in rows.items():
        ci = f"[{r['attack_auc_ci90'][0]:.2f}, {r['attack_auc_ci90'][1]:.2f}]"
        acct = "∞ (no noise)" if r["eps_accountant_1round"] is None else f"≈{r['eps_accountant_1round']:.1f}"
        print(f"{name:<14}{r['attack_acc']:>11.3f}{r['attack_auc']:>11.3f}  {ci:<13}{r['tpr']:>6.2f}{r['fpr']:>6.2f}"
              f"{r['eps_empirical_lower_95']:>10.2f}{acct:>15}   {r['verdict']}")
    print(f"\ngame: bank {args.bank} round update with vs without one held-out laundering row (#{idx}); "
          f"{args.trials} trials per world, half to calibrate | trainer {args.trainer}, subsample {args.subsample} | clip {args.clip} | seed {args.seed} | {seconds:.1f}s | wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
