"""Bank client: local training on the bank's own shard, one audited update per round (FEDERATION owns).

    python -m fedaml.bank --bank-id 1 --coordinator http://coordinator:8000 --epochs 1

Per round: fetch the global logistic weights, warm-start a local logistic
regression from them, run a bounded amount of local optimisation on this
bank's train set with "balanced" class weights, take delta = local - global,
L2-clip it, add Gaussian noise when the coordinator's config says DP is on,
and send the exact CONTRACTS section 4 message through ``fedaml.egress.send``,
the only door out of a bank. Raw rows never leave this process. Local test AUC
is logged every round.

Local trainers (``--trainer``):
  prox (default)   FedProx-style: minimise the balanced logistic loss plus (mu/2)||w - w_global||^2
                   with scipy L-BFGS (``--mu`` 0.5, ``--local-iters`` 50). The proximal pull keeps
                   honest deltas small and aligned, so the coordinator's geometric rogue screen
                   (defense.py) separates a poisoned update from honest heterogeneity.
  lbfgs            ``LogisticRegression(class_weight="balanced", warm_start=True, max_iter=10*epochs)``.
                   Fastest to converge but jumps to each bank's own optimum, so honest deltas
                   diverge and trip the defense.
  sgd              CONTRACTS section 4 literal: ``SGDClassifier(loss="log_loss")`` warm-started,
                   ``partial_fit`` E epochs in 4096-row minibatches, balanced weights passed as
                   sample_weight (partial_fit rejects the string). With a 1:1000 class ratio its
                   steps are ~1000x too large and it plateaus below the single-bank baselines;
                   kept for comparison.
"""
from __future__ import annotations

import argparse
import logging
import os
import time
import warnings

import numpy as np
import requests
from scipy.optimize import minimize
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression, SGDClassifier
from sklearn.metrics import roc_auc_score
from sklearn.utils.class_weight import compute_class_weight

from fedaml import dp, egress
from fedaml.coordinator import N_FEATURES, payload_sha256
from fedaml.features import FEATURE_NAMES, feature_names_sha256, load_bank

log = logging.getLogger("fedaml.bank")
warnings.filterwarnings("ignore", category=ConvergenceWarning)  # bounded local iterations are intentional


def sigmoid_scores(X: np.ndarray, coef: np.ndarray, intercept: float) -> np.ndarray:
    z = X.astype(np.float64) @ coef + intercept
    return 1.0 / (1.0 + np.exp(-np.clip(z, -500, 500)))


class BankClient:
    """Honest bank. ``rogue.RogueBank`` subclasses it and overrides ``local_delta`` / ``claimed_samples``."""

    name = "bank"

    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.bank_id = args.bank_id
        self.url = args.coordinator.rstrip("/")
        self.rng = np.random.default_rng(args.seed + 1000 * args.bank_id)
        self.cfg = self.fetch_config()
        self.X, self.y = load_bank(args.bank_id, "train", nrows=args.max_rows or None, data_dir=args.data_dir or None)
        self.X_test, self.y_test = load_bank(args.bank_id, "test", data_dir=args.data_dir or None)
        self.X = self.X.astype(np.float64)  # SGDClassifier needs X and warm-start coef_ in the same dtype
        if self.X.shape[1] != N_FEATURES:
            raise SystemExit(f"feature vector has {self.X.shape[1]} columns, expected {N_FEATURES}")
        classes = np.array([0, 1])
        if self.y.sum() == 0 or self.y.sum() == len(self.y):
            raise SystemExit(f"bank {self.bank_id}: train split has a single class; cannot train")
        w = compute_class_weight("balanced", classes=classes, y=self.y)
        self.class_weight = {0: float(w[0]), 1: float(min(w[1], args.pos_weight_cap))}
        log.info("%s %d ready: %d train rows (%d laundering), %d test rows, class_weight=%s, dp=%s sigma=%s clip=%s",
                 self.name, self.bank_id, len(self.y), int(self.y.sum()), len(self.y_test),
                 {k: round(v, 2) for k, v in self.class_weight.items()}, self.cfg["dp"]["enabled"],
                 self.cfg["dp"]["sigma"], self.cfg["dp"]["clip_norm"])

    # ----- coordinator I/O
    def fetch_config(self) -> dict:
        deadline = time.time() + self.args.connect_timeout
        while True:
            try:
                r = requests.get(f"{self.url}/config", timeout=10)
                r.raise_for_status()
                cfg = r.json()
                if cfg["feature_names_sha256"] != feature_names_sha256():
                    raise SystemExit("coordinator runs a different feature vector; refusing to train")
                return cfg
            except requests.RequestException as exc:
                if time.time() > deadline:
                    raise SystemExit(f"coordinator unreachable at {self.url}: {exc}")
                log.info("waiting for coordinator at %s ...", self.url)
                time.sleep(3)

    def wait_for_round(self, rnd: int) -> dict | None:
        """Poll until /global/<rnd> opens; None when training finished before that round."""
        while True:
            try:
                r = requests.get(f"{self.url}/global/{rnd}", timeout=10)
                if r.status_code == 200:
                    return r.json()
                if r.status_code == 404 and r.json().get("done"):
                    return None
            except requests.RequestException as exc:
                log.warning("coordinator not reachable (%s); retrying", exc)
            time.sleep(self.args.poll)

    # ----- training
    def train_local(self, coef: np.ndarray, intercept: float, X: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, float]:
        """Warm-start from the global weights, optimise locally, return (coef, intercept)."""
        if self.args.trainer == "prox":
            w = self.prox_solve(np.concatenate([coef, [intercept]]), X, y)
            return w[:-1].copy(), float(w[-1])
        if self.args.trainer == "lbfgs":
            clf = LogisticRegression(class_weight="balanced", warm_start=True, max_iter=10 * self.args.epochs,
                                     C=self.args.C, tol=1e-6)
            clf.classes_ = np.array([0, 1])
            clf.coef_ = coef.reshape(1, -1).astype(np.float64).copy()
            clf.intercept_ = np.array([intercept], dtype=np.float64)
            clf.fit(X, y)
            return clf.coef_.ravel().copy(), float(clf.intercept_[0])
        clf = SGDClassifier(loss="log_loss", penalty="l2", alpha=self.args.alpha, learning_rate=self.args.lr_schedule,
                            eta0=self.args.eta0, warm_start=True, random_state=self.args.seed, average=False)
        clf.classes_ = np.array([0, 1])
        clf.coef_ = coef.reshape(1, -1).astype(np.float64).copy()
        clf.intercept_ = np.array([intercept], dtype=np.float64)
        n = len(y)
        sw = np.where(y == 1, self.class_weight[1], self.class_weight[0])
        for epoch in range(self.args.epochs):
            order = self.rng.permutation(n)
            for start in range(0, n, self.args.batch_size):
                idx = order[start:start + self.args.batch_size]
                clf.partial_fit(X[idx], y[idx], classes=np.array([0, 1]), sample_weight=sw[idx])
        return clf.coef_.ravel().copy(), float(clf.intercept_[0])

    def prox_solve(self, w0: np.ndarray, X: np.ndarray, y: np.ndarray) -> np.ndarray:
        """argmin_w  sum_i sw_i * logloss_i(w) / sum(sw) + l2/2 ||w_coef||^2 + mu/2 ||w - w0||^2."""
        mu, l2 = self.args.mu, 1.0 / (self.args.C * len(y))
        sw = np.where(y == 1, self.class_weight[1], self.class_weight[0])
        S = float(sw.sum())
        Xb = np.hstack([X, np.ones((len(y), 1))])

        def f(w):
            z = Xb @ w
            p = 1.0 / (1.0 + np.exp(-z))
            loss = float(np.sum(sw * (np.logaddexp(0.0, z) - y * z)) / S + 0.5 * l2 * np.sum(w[:-1] ** 2) + 0.5 * mu * np.sum((w - w0) ** 2))
            g = (Xb.T @ (sw * (p - y))) / S + mu * (w - w0)
            g[:-1] += l2 * w[:-1]
            return loss, g

        res = minimize(f, w0, jac=True, method="L-BFGS-B", options={"maxiter": self.args.local_iters})
        return res.x

    def local_delta(self, coef: np.ndarray, intercept: float) -> np.ndarray:
        """Honest delta = local weights - global weights, as one vector [coef..., intercept]."""
        lc, li = self.train_local(coef, intercept, self.X, self.y)
        self.local_auc = round(float(roc_auc_score(self.y_test, sigmoid_scores(self.X_test, lc, li))), 4)
        return np.concatenate([lc - coef, [li - intercept]])

    def claimed_samples(self) -> int:
        return int(len(self.y))

    # ----- one round
    def build_message(self, rnd: int, vec: np.ndarray) -> dict:
        d = self.cfg["dp"]
        msg = {"bank_id": int(self.bank_id), "round": int(rnd), "n_samples": self.claimed_samples(),
               "delta_coef": [float(v) for v in vec[:-1]], "delta_intercept": [float(vec[-1])],
               "clip_norm": float(d["clip_norm"]), "dp": {"enabled": bool(d["enabled"]), "sigma": float(d["sigma"])},
               "feature_names_sha256": feature_names_sha256(), "payload_sha256": "", "signature": None}
        msg["payload_sha256"] = payload_sha256(msg)
        return msg

    def run(self) -> None:
        rounds = int(self.cfg["rounds"])
        for rnd in range(1, rounds + 1):
            g = self.wait_for_round(rnd)
            if g is None:
                log.info("coordinator finished before round %d; exiting", rnd)
                return
            coef, intercept = np.asarray(g["coef"], dtype=np.float64), float(g["intercept"][0])
            t0 = time.time()
            global_auc = round(float(roc_auc_score(self.y_test, sigmoid_scores(self.X_test, coef, intercept))), 4)
            raw = self.local_delta(coef, intercept)
            d = self.cfg["dp"]
            vec, info = dp.privatize(raw, d["clip_norm"], d["sigma"], bool(d["enabled"]), self.rng)
            msg = self.build_message(rnd, vec)
            reply = egress.send(self.url, msg, self.bank_id, rnd)
            log.info("round %d: local test AUC global=%.4f local=%.4f | delta raw_norm=%.3f sent_norm=%.3f dp=%s | %.1fs | coordinator: %s",
                     rnd, global_auc, self.local_auc, info["raw_norm"], info["sent_norm"], info["dp_enabled"],
                     time.time() - t0, reply)
            if not reply.get("accepted"):
                log.error("round %d update rejected: %s", rnd, reply)
        log.info("%s %d finished %d rounds", self.name, self.bank_id, rounds)


def add_common_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--bank-id", type=int, required=True)
    p.add_argument("--coordinator", default="http://coordinator:8000")
    p.add_argument("--epochs", type=int, default=1, help="local epochs (sgd) or 10x L-BFGS iterations (lbfgs)")
    p.add_argument("--trainer", choices=["prox", "lbfgs", "sgd"], default=os.environ.get("TRAINER", "prox"))
    p.add_argument("--mu", type=float, default=float(os.environ.get("MU", "0.5")), help="proximal strength for the prox trainer")
    p.add_argument("--local-iters", type=int, default=50, help="L-BFGS iterations per round for the prox trainer")
    p.add_argument("--C", type=float, default=1.0, help="inverse l2 strength (lbfgs and prox)")
    p.add_argument("--batch-size", type=int, default=4096)
    p.add_argument("--alpha", type=float, default=1e-4, help="SGD l2 regularisation")
    p.add_argument("--lr-schedule", default="optimal", choices=["optimal", "constant", "invscaling", "adaptive"])
    p.add_argument("--eta0", type=float, default=0.01)
    p.add_argument("--pos-weight-cap", type=float, default=1e9, help="cap the balanced positive class weight")
    p.add_argument("--max-rows", type=int, default=0, help="train on at most this many rows (0 = all)")
    p.add_argument("--data-dir", default=os.environ.get("FEDAML_DATA_DIR", ""))
    p.add_argument("--poll", type=float, default=2.0)
    p.add_argument("--connect-timeout", type=float, default=120.0)
    p.add_argument("--seed", type=int, default=42)


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description="fedaml honest bank client")
    add_common_args(p)
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    BankClient(args).run()


if __name__ == "__main__":
    main()
