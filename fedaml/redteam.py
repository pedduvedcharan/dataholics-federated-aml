"""Membership-inference red team against the federated AML model (REDTEAM agent).

Threat model: an honest-but-curious party holding the global model JSON (the
coordinator, any bank, anyone who obtains a round file) tries to tell whether
a given transaction row was in bank 1's training set.  The same attack is run
against the model trained with DP off and the one trained with DP on, and the
two rows are printed side by side.

    python -m fedaml.redteam --model-off state/global_final_dpoff.json \
                             --model-on  state/global_final_dpon.json

Writes state/redteam.json per docs/CONTRACTS.md section 6.  Library code only
logs; the CLI prints.  Everything is seeded (default 42).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

import numpy as np
from scipy.special import expit
from sklearn.linear_model import LogisticRegression, SGDClassifier
from sklearn.metrics import roc_auc_score
from sklearn.utils.class_weight import compute_class_weight

from fedaml.redteam_data import AttackData, Population, load_attack_data

log = logging.getLogger("fedaml.redteam")

LEAK_AUC = 0.60      # attack AUC at or above this: the model LEAKS membership
CHANCE_AUC = 0.55    # below this: indistinguishable from a coin flip -> PROTECTED
EPS = 1e-7


# --------------------------------------------------------------------------- model
def load_model(path: str | os.PathLike) -> dict:
    """Load a CONTRACTS section 4 model JSON into numpy arrays."""
    with open(path) as fh:
        raw = json.load(fh)
    coef = np.asarray(raw["coef"], dtype=np.float64).ravel()
    intercept = float(np.asarray(raw["intercept"], dtype=np.float64).ravel()[0])
    names = list(raw.get("feature_names") or [])
    if names and len(names) != coef.size:
        raise ValueError(f"{path}: {len(names)} feature names but {coef.size} coefficients")
    return {"coef": coef, "intercept": intercept, "feature_names": names,
            "sha256": raw.get("sha256"), "round": raw.get("round"), "path": str(path)}


def model_sha256(coef: np.ndarray, intercept: float, names: list[str]) -> str:
    blob = json.dumps({"coef": [float(c) for c in coef], "intercept": [intercept],
                       "feature_names": names}, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()


def align_columns(X: np.ndarray, have: list[str], want: list[str]) -> np.ndarray:
    """Reorder feature columns from the order `have` to the model's order `want`."""
    if not want or have == want:
        return X
    missing = [n for n in want if n not in have]
    if missing:
        raise ValueError(f"model needs features absent from features.py: {missing}")
    return X[:, [have.index(n) for n in want]]


def predict_proba(model: dict, X: np.ndarray, have: list[str]) -> np.ndarray:
    """P(laundering) under the logistic model, float64 in (EPS, 1-EPS)."""
    Xa = align_columns(X, have, model["feature_names"]).astype(np.float64)
    return np.clip(expit(Xa @ model["coef"] + model["intercept"]), EPS, 1.0 - EPS)


def row_log_loss(p: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Per-row binary cross-entropy. Low loss on a row = the model 'knows' it well."""
    y = y.astype(np.float64)
    return -(y * np.log(p) + (1.0 - y) * np.log(1.0 - p))


def losses(model: dict, pop: Population, names: list[str]) -> tuple[np.ndarray, np.ndarray]:
    return (row_log_loss(predict_proba(model, pop.X_mem, names), pop.y_mem),
            row_log_loss(predict_proba(model, pop.X_non, names), pop.y_non))


def sgd_logreg(y: np.ndarray, seed: int) -> SGDClassifier:
    """SGD logistic regression with 'balanced' class weights computed up front
    (partial_fit rejects class_weight='balanced'; CONTRACTS section 4 recipe)."""
    classes = np.array([0, 1])
    w = compute_class_weight("balanced", classes=classes, y=y) if len(np.unique(y)) > 1 else np.ones(2)
    return SGDClassifier(loss="log_loss", class_weight={0: float(w[0]), 1: float(w[1])},
                         random_state=seed, warm_start=True)


# ------------------------------------------------------------------------- attacks
def _split(n: int, frac: float, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    perm = rng.permutation(n)
    k = max(1, int(round(n * frac)))
    return perm[:k], perm[k:]


def _best_threshold(loss: np.ndarray, is_mem: np.ndarray) -> float:
    """Threshold t maximising accuracy of the rule 'member iff loss < t'."""
    order = np.argsort(loss)
    l_sorted, m_sorted = loss[order], is_mem[order].astype(np.int64)
    cum_mem = np.cumsum(m_sorted)
    total_non = len(m_sorted) - cum_mem[-1]
    k = np.arange(1, len(l_sorted) + 1)
    correct = cum_mem + (total_non - (k - cum_mem))   # members below t + non-members above t
    best = int(np.argmax(correct))
    if best == len(l_sorted) - 1:
        return float(l_sorted[best]) + 1e-9
    return float((l_sorted[best] + l_sorted[best + 1]) / 2)


def _score(p_mem: np.ndarray, is_mem: np.ndarray, **extra) -> dict:
    return {"attack_acc": float(np.mean((p_mem >= 0.5) == (is_mem == 1))),
            "attack_auc": float(roc_auc_score(is_mem, p_mem)), "n": int(len(is_mem)), **extra}


def loss_threshold_attack(loss_mem: np.ndarray, loss_non: np.ndarray, seed: int,
                          calib_frac: float = 0.2) -> dict:
    """Yeom et al. (2018) baseline: member iff per-row loss is below a threshold.

    The threshold is chosen on a calibration split and scored on the rest, so
    the reported accuracy is honest. AUC uses -loss as the membership score.
    """
    rng = np.random.default_rng(seed)
    cm, em = _split(len(loss_mem), calib_frac, rng)
    cn, en = _split(len(loss_non), calib_frac, rng)
    t = _best_threshold(np.r_[loss_mem[cm], loss_non[cn]], np.r_[np.ones(len(cm)), np.zeros(len(cn))])
    loss_eval = np.r_[loss_mem[em], loss_non[en]]
    is_mem = np.r_[np.ones(len(em)), np.zeros(len(en))]
    return _score((loss_eval < t).astype(float), is_mem, threshold=t)


def shadow_attack(loss_mem: np.ndarray, loss_non: np.ndarray, target: str, data: AttackData,
                  seed: int, epochs: int = 5) -> dict:
    """Shadow-model attack (Shokri et al. 2017, 1-D variant).

    Train a shadow logistic model on bank 2 with the banks' recipe, take its
    per-row loss on rows it trained on vs rows it did not, fit a 1-D logistic
    attack classifier loss -> P(member), then apply it to the target model's
    losses. No target membership labels are used anywhere.
    """
    target = target.split("@")[0]          # footnote populations reuse the shadow bank's own pops
    if not data.shadow or target not in data.shadow["pops"]:
        raise RuntimeError("shadow data unavailable")
    shadow = sgd_logreg(data.shadow["y_full"], seed)
    for _ in range(epochs):
        shadow.partial_fit(data.shadow["X_full"], data.shadow["y_full"], classes=np.array([0, 1]))
    sm = {"coef": shadow.coef_.ravel(), "intercept": float(shadow.intercept_[0]),
          "feature_names": data.feature_names}
    l_in, l_out = losses(sm, data.shadow["pops"][target], data.feature_names)
    clf = LogisticRegression(random_state=seed)
    clf.fit(np.log1p(np.r_[l_in, l_out]).reshape(-1, 1), np.r_[np.ones(len(l_in)), np.zeros(len(l_out))])
    loss_eval = np.r_[loss_mem, loss_non]
    is_mem = np.r_[np.ones(len(loss_mem)), np.zeros(len(loss_non))]
    p_mem = clf.predict_proba(np.log1p(loss_eval).reshape(-1, 1))[:, 1]
    return _score(p_mem, is_mem, shadow_epochs=epochs)


def art_attack(model: dict, pop: Population, names: list[str], seed: int, calib_frac: float = 0.2) -> dict:
    """ART MembershipInferenceBlackBox (random-forest attack model over the
    target's predicted probabilities and the true label) when ART is installed.

    Fitted on the calibration split of true members/non-members (ART's standard
    usage, a stronger attacker than shadow), scored on the held-out split.
    ART's sklearn wrapper has no compute_loss, hence input_type='prediction'.
    """
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from art.attacks.inference.membership_inference import MembershipInferenceBlackBox
        from art.estimators.classification.scikitlearn import ScikitlearnLogisticRegression

    want = model["feature_names"] or names
    lr = LogisticRegression()
    lr.coef_, lr.intercept_ = model["coef"].reshape(1, -1), np.array([model["intercept"]])
    lr.classes_, lr.n_features_in_ = np.array([0, 1]), model["coef"].size
    rng = np.random.default_rng(seed)
    cm, em = _split(pop.n, calib_frac, rng)
    cn, en = _split(pop.n, calib_frac, rng)
    Xm, Xn = align_columns(pop.X_mem, names, want), align_columns(pop.X_non, names, want)
    atk = MembershipInferenceBlackBox(ScikitlearnLogisticRegression(model=lr), input_type="prediction",
                                      attack_model_type="rf")
    atk.fit(Xm[cm], pop.y_mem[cm], Xn[cn], pop.y_non[cn])
    p = np.r_[atk.infer(Xm[em], pop.y_mem[em], probabilities=True).ravel(),
              atk.infer(Xn[en], pop.y_non[en], probabilities=True).ravel()]
    return _score(p, np.r_[np.ones(len(em)), np.zeros(len(en))])


# ------------------------------------------------------------------------ pipeline
def verdict(res: dict) -> str:
    auc = res["attack_auc"]
    return "LEAKS" if auc >= LEAK_AUC else ("PROTECTED" if auc < CHANCE_AUC else "WEAK LEAK")


def attack_population(model: dict, data: AttackData, target: str, seed: int,
                      attack: str, shadow_epochs: int) -> dict:
    """Run the requested attack family on one target population.

    auto = ART if importable, else shadow, else loss-threshold; the
    loss-threshold baseline is always computed and reported as well.
    """
    pop = data.pops[target]
    if "@" in target:
        attack = "loss_threshold"          # footnotes use the plain baseline only
    loss_mem, loss_non = losses(model, pop, data.feature_names)
    out = {"n_per_class": pop.n, "mean_loss_members": float(loss_mem.mean()),
           "mean_loss_nonmembers": float(loss_non.mean()), "variants": {}}
    out["variants"]["loss_threshold"] = loss_threshold_attack(loss_mem, loss_non, seed)
    chosen = "loss_threshold"
    if attack in ("auto", "art"):
        try:
            out["variants"]["art_blackbox"] = art_attack(model, pop, data.feature_names, seed)
            chosen = "art_blackbox"
        except ImportError as exc:
            log.info("ART not available (%s); skipping art_blackbox", exc)
        except Exception as exc:  # noqa: BLE001 - never let the fancy attack kill the demo
            log.warning("ART attack failed: %s", exc)
    if attack in ("auto", "shadow") and chosen == "loss_threshold":
        try:
            out["variants"]["shadow"] = shadow_attack(loss_mem, loss_non, target, data, seed, shadow_epochs)
            chosen = "shadow"
        except Exception as exc:  # noqa: BLE001
            log.warning("shadow attack unavailable: %s", exc)
    out["attack"] = chosen
    out["result"] = dict(out["variants"][chosen])
    out["result"]["verdict"] = verdict(out["result"])
    return out


def evaluate_model(model: dict, data: AttackData, seed: int, attack: str = "auto",
                   shadow_epochs: int = 5) -> dict:
    """Model AUC on the member bank's test file (and global_test when present)
    plus the attack on every available population."""
    def auc(X, y):
        if X is None or len(np.unique(y)) < 2:
            return None
        return float(roc_auc_score(y, predict_proba(model, X, data.feature_names)))
    return {"model_auc": auc(data.X_test, data.y_test), "model_auc_global_test": auc(data.X_global, data.y_global),
            "model_sha256": model["sha256"], "model_path": model["path"],
            "targets": {t: attack_population(model, data, t, seed, attack, shadow_epochs) for t in data.pops}}


def write_json_atomic(path: str | os.PathLike, obj: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w") as fh:
        json.dump(obj, fh, indent=2, default=float)
    os.replace(tmp, path)


def train_overfit_local(data: AttackData, epochs: int, seed: int, out: str) -> str:
    """--selftest helper: fit one bank's local SGD logreg on exactly the member rows."""
    X = np.vstack([p.X_mem for p in data.pops.values()])
    y = np.concatenate([p.y_mem for p in data.pops.values()])
    clf = sgd_logreg(y, seed)
    for _ in range(epochs):
        clf.partial_fit(X, y, classes=np.array([0, 1]))
    coef, b = clf.coef_.ravel(), float(clf.intercept_[0])
    write_json_atomic(out, {"round": 0, "coef": coef.tolist(), "intercept": [b],
                            "feature_names": data.feature_names,
                            "sha256": model_sha256(coef, b, data.feature_names),
                            "accepted_banks": [data.meta["member_bank"]], "excluded_banks": [],
                            "note": f"redteam --selftest: local model, {epochs} epochs on the member sample only"})
    return out


FOOTNOTES = {"all": "all rows, same-bank non-members",
             "laundering@global_test": "laundering rows, mixed-bank hold-out non-members (distribution-shift check)"}


def format_table(rows: list[tuple[str, dict]], target: str) -> str:
    """The table from the brief; the setting column names the population each row used."""
    lines = [f"{'setting':<28}{'model AUC':>10}{'attack acc':>12}{'attack AUC':>12}   verdict"]
    for name, r in rows:
        t = r["targets"][target]["result"]
        lines.append(f"{name + ' / ' + target + ' rows':<28}{r['model_auc']:>10.3f}"
                     f"{t['attack_acc']:>12.3f}{t['attack_auc']:>12.3f}   {t['verdict']}")
    for o in [o for o in rows[0][1]["targets"] if o != target]:
        parts = "; ".join(f"{name}: acc {r['targets'][o]['result']['attack_acc']:.3f}, AUC "
                          f"{r['targets'][o]['result']['attack_auc']:.3f}, {r['targets'][o]['result']['verdict']}"
                          for name, r in rows)
        lines.append(f"  footnote, {FOOTNOTES.get(o, o)}: {parts}")
    return "\n".join(lines)


def build_report(off: dict, on: Optional[dict], data: AttackData, target: str, seed: int, seconds: float) -> dict:
    """state/redteam.json per CONTRACTS section 6, plus provenance the dashboard may ignore."""
    def pick(r: Optional[dict]) -> Optional[dict]:
        if r is None:
            return None
        t = r["targets"][target]["result"]
        return {"attack_acc": t["attack_acc"], "attack_auc": t["attack_auc"], "n": t["n"], "verdict": t["verdict"]}
    return {"attack": off["targets"][target]["attack"], "target": target,
            "dp_off": pick(off), "dp_on": pick(on),
            "model_auc_off": off["model_auc"], "model_auc_on": on["model_auc"] if on else None,
            "model_auc_global_test_off": off.get("model_auc_global_test"),
            "model_auc_global_test_on": on.get("model_auc_global_test") if on else None,
            "members": f"bank_{data.meta['member_bank']} train rows", "nonmembers": data.meta["nonmembers"],
            "n_per_class": data.meta["n_per_class"], "seed": seed, "runtime_s": round(seconds, 1),
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "detail": {"dp_off": off, "dp_on": on, "data": {k: v for k, v in data.meta.items()}}}


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Membership-inference red team: DP off vs DP on")
    ap.add_argument("--model-off", help="global model JSON trained with DP off")
    ap.add_argument("--model-on", help="global model JSON trained with DP on")
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--out", default="state/redteam.json")
    ap.add_argument("--member-bank", type=int, default=1)
    ap.add_argument("--shadow-bank", type=int, default=2)
    ap.add_argument("--target", choices=["laundering", "all"], default="laundering",
                    help="headline population for the table and redteam.json (both are always computed)")
    ap.add_argument("--n", type=int, default=20000, help="max members and non-members each")
    ap.add_argument("--attack", choices=["auto", "loss_threshold", "shadow", "art"], default="auto")
    ap.add_argument("--shadow-epochs", type=int, default=5)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--selftest", action="store_true",
                    help="train an overfit local model on the member sample and attack it (no federated model needed)")
    ap.add_argument("--selftest-epochs", type=int, default=20)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    if not args.model_off and not args.selftest:
        ap.error("--model-off is required unless --selftest")

    t0 = time.time()
    data = load_attack_data(args.data_dir, args.member_bank, args.n, args.seed,
                            None if args.attack == "loss_threshold" else args.shadow_bank)
    target = args.target if args.target in data.pops else "all"
    rows: list[tuple[str, dict]] = []
    if args.selftest:
        path = train_overfit_local(data, args.selftest_epochs, args.seed,
                                   str(Path(args.out).parent / "redteam_selftest_model.json"))
        log.info("selftest model written to %s", path)
        rows.append(("local", evaluate_model(load_model(path), data, args.seed, args.attack, args.shadow_epochs)))
    if args.model_off:
        rows.append(("DP off", evaluate_model(load_model(args.model_off), data, args.seed, args.attack, args.shadow_epochs)))
    on = None
    if args.model_on:
        on = evaluate_model(load_model(args.model_on), data, args.seed, args.attack, args.shadow_epochs)
        rows.append(("DP on", on))
    seconds = time.time() - t0
    off = rows[-1][1] if on is None else rows[-2][1]
    write_json_atomic(args.out, build_report(off, on, data, target, args.seed, seconds))
    print(format_table(rows, target))
    print(f"\nattack: {off['targets'][target]['attack']} | members: bank_{args.member_bank} train | "
          f"non-members: {data.meta['nonmembers']} | n per class: {data.meta['n_per_class']} | seed {args.seed} | "
          f"{seconds:.1f}s | wrote {args.out}")
    if seconds > 120:
        log.warning("run took %.0fs, over the 2-minute budget", seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
