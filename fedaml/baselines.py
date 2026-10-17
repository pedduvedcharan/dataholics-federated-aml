"""Per-bank baselines and the shared evaluator (MODELS, CONTRACTS section 6).

For each bank: LogisticRegression, RandomForest and HistGradientBoosting trained
on that bank's ``train.csv`` only, scored on the bank's own ``test.csv`` and on
``data/global_test.csv``. Plus a *centralized* logistic regression on all banks'
training rows concatenated: the upper bound that is illegal in practice.

Writes ``state/baselines.json``::

    {"per_bank": {"1": {"logreg": {"auc", "ap", "global_auc", "global_ap"}, "rf": ..., "hgb": ...}},
     "federated": {"auc", "ap"} | null,
     "centralized_logreg": {"auc", "ap"},
     "meta": {...}}

``evaluate_model_json(path)`` scores any ``state/global_*.json`` logistic model
on ``global_test.csv`` so FEDERATION, REDTEAM and the dashboard share one evaluator.

CLI::

    python -m fedaml.baselines --banks 1,2,3,4
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import time
from pathlib import Path

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score

from fedaml.features import (DATA_DIR, FEATURE_NAMES, feature_names_sha256,
                             load_bank, load_global_test)

log = logging.getLogger("fedaml.baselines")

STATE_DIR = Path(os.environ.get("FEDAML_STATE_DIR", "state"))
MODEL_KEYS = ["logreg", "rf", "hgb"]


# --------------------------------------------------------------------------- #
# Shared evaluator
# --------------------------------------------------------------------------- #
def metrics(y: np.ndarray, p: np.ndarray) -> dict[str, float]:
    """ROC AUC and average precision. Never accuracy: positives are ~1 in 1000."""
    y = np.asarray(y)
    if y.min() == y.max():
        log.warning("only one class present in evaluation set; metrics undefined")
        return {"auc": float("nan"), "ap": float("nan")}
    return {"auc": float(roc_auc_score(y, p)), "ap": float(average_precision_score(y, p))}


def load_model_json(path: str | Path) -> dict:
    """Load a ``state/global_*.json`` logistic model and check its feature vector."""
    with open(path) as f:
        model = json.load(f)
    names = model.get("feature_names")
    if names is not None and list(names) != FEATURE_NAMES:
        raise ValueError(f"{path}: feature_names differ from fedaml.features.FEATURE_NAMES")
    sha = model.get("feature_names_sha256")
    if sha is not None and sha != feature_names_sha256():
        raise ValueError(f"{path}: feature_names_sha256 mismatch")
    coef = np.asarray(model["coef"], dtype=np.float64).ravel()
    if coef.shape[0] != len(FEATURE_NAMES):
        raise ValueError(f"{path}: coef has {coef.shape[0]} entries, expected {len(FEATURE_NAMES)}")
    return model


def predict_proba_json(model: dict, X: np.ndarray) -> np.ndarray:
    """P(laundering) for each row under a JSON logistic model."""
    coef = np.asarray(model["coef"], dtype=np.float64).ravel()
    intercept = float(np.asarray(model["intercept"], dtype=np.float64).ravel()[0])
    z = np.asarray(X, dtype=np.float64) @ coef + intercept
    return 1.0 / (1.0 + np.exp(-np.clip(z, -500, 500)))


def evaluate_model_json(path: str | Path, data_dir: str | Path | None = None,
                        X: np.ndarray | None = None, y: np.ndarray | None = None) -> dict[str, float]:
    """Score a ``state/global_*.json`` model on ``global_test.csv`` -> ``{"auc","ap"}``.

    Pass ``X, y`` to reuse an already-featurized global test set.
    """
    model = load_model_json(path)
    if X is None or y is None:
        X, y = load_global_test(data_dir=data_dir)
    out = metrics(y, predict_proba_json(model, X))
    log.info("%s: auc=%.4f ap=%.4f on %d rows", path, out["auc"], out["ap"], len(y))
    return out


# --------------------------------------------------------------------------- #
# Baseline models
# --------------------------------------------------------------------------- #
def make_models(seed: int, n_jobs: int) -> dict[str, object]:
    """The three models compared per bank. All class-weighted for the 1:1000 imbalance."""
    return {
        "logreg": LogisticRegression(class_weight="balanced", max_iter=200),
        "rf": RandomForestClassifier(n_estimators=100, max_depth=12, n_jobs=n_jobs,
                                     class_weight="balanced_subsample", random_state=seed),
        "hgb": HistGradientBoostingClassifier(class_weight="balanced", random_state=seed),
    }


def cap_rows(X: np.ndarray, y: np.ndarray, max_rows: int, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """Random subsample to ``max_rows`` keeping every laundering row."""
    if len(y) <= max_rows:
        return X, y
    rng = np.random.default_rng(seed)
    pos = np.flatnonzero(y == 1)
    neg = np.flatnonzero(y == 0)
    keep_neg = rng.choice(neg, size=max(0, max_rows - len(pos)), replace=False)
    idx = np.sort(np.concatenate([pos, keep_neg]))
    log.info("capped %d -> %d rows (kept all %d positives)", len(y), len(idx), len(pos))
    return X[idx], y[idx]


def run_baselines(banks: list[int], data_dir: Path, max_rows: int, seed: int, n_jobs: int,
                  models: list[str], centralized: bool = True) -> dict:
    """Train/evaluate every (bank, model) and the centralized ceiling."""
    Xg, yg = load_global_test(data_dir=data_dir)
    result: dict = {"per_bank": {}, "federated": None, "centralized_logreg": None,
                    "meta": {"train_rows": {}, "test_rows": {}, "fit_seconds": {},
                             "global_test_rows": int(len(yg)),
                             "global_test_positives": int(yg.sum()),
                             "max_rows": max_rows, "seed": seed, "n_jobs": n_jobs,
                             "feature_names_sha256": feature_names_sha256()}}
    all_X, all_y = [], []
    for b in banks:
        Xtr, ytr = load_bank(b, "train", data_dir=data_dir)
        Xtr, ytr = cap_rows(Xtr, ytr, max_rows, seed)
        Xte, yte = load_bank(b, "test", data_dir=data_dir)
        all_X.append(Xtr); all_y.append(ytr)
        result["meta"]["train_rows"][str(b)] = int(len(ytr))
        result["meta"]["test_rows"][str(b)] = int(len(yte))
        result["per_bank"][str(b)] = {}
        result["meta"]["fit_seconds"][str(b)] = {}
        for key, model in make_models(seed, n_jobs).items():
            if key not in models:
                continue
            t0 = time.time()
            model.fit(Xtr, ytr)
            dt = time.time() - t0
            own = metrics(yte, model.predict_proba(Xte)[:, 1])
            glob = metrics(yg, model.predict_proba(Xg)[:, 1])
            result["per_bank"][str(b)][key] = {"auc": own["auc"], "ap": own["ap"],
                                               "global_auc": glob["auc"], "global_ap": glob["ap"]}
            result["meta"]["fit_seconds"][str(b)][key] = round(dt, 1)
            log.info("bank %d %-6s own auc=%.4f ap=%.4f | global auc=%.4f ap=%.4f (%.1fs)",
                     b, key, own["auc"], own["ap"], glob["auc"], glob["ap"], dt)
    if centralized and all_X:
        Xc = np.concatenate(all_X); yc = np.concatenate(all_y)
        t0 = time.time()
        clf = LogisticRegression(class_weight="balanced", max_iter=200).fit(Xc, yc)
        glob = metrics(yg, clf.predict_proba(Xg)[:, 1])
        result["centralized_logreg"] = glob
        result["meta"]["centralized_train_rows"] = int(len(yc))
        result["meta"]["fit_seconds"]["centralized_logreg"] = round(time.time() - t0, 1)
        log.info("centralized logreg on %d rows: global auc=%.4f ap=%.4f",
                 len(yc), glob["auc"], glob["ap"])
    return result


def attach_federated(result: dict, model_path: Path, data_dir: Path) -> dict:
    """Fill ``result["federated"]`` from a global model JSON if it exists."""
    if model_path.exists():
        result["federated"] = evaluate_model_json(model_path, data_dir=data_dir)
        result["meta"]["federated_model"] = str(model_path)
    else:
        log.info("no federated model at %s yet; federated = null", model_path)
    return result


def write_json_atomic(obj: dict, path: Path) -> None:
    """Write JSON to tmp then rename so readers never see a partial file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=2)
    os.replace(tmp, path)


def _fmt(v: float | None) -> str:
    return "n/a" if v is None or (isinstance(v, float) and np.isnan(v)) else f"{v:.3f}"


def markdown_table(result: dict) -> str:
    """Markdown table of every (bank, model) plus the centralized and federated rows."""
    lines = ["| Model | Train data | Own-test AUC | Own-test AP | Global-test AUC | Global-test AP |",
             "|---|---|---|---|---|---|"]
    for b, per in result["per_bank"].items():
        for key, m in per.items():
            lines.append(f"| {key} | bank {b} only | {_fmt(m['auc'])} | {_fmt(m['ap'])} "
                         f"| {_fmt(m['global_auc'])} | {_fmt(m['global_ap'])} |")
    c = result.get("centralized_logreg")
    if c:
        lines.append(f"| **centralized logreg (illegal ceiling)** | all banks pooled | – | – "
                     f"| {_fmt(c['auc'])} | {_fmt(c['ap'])} |")
    fed = result.get("federated")
    if fed:
        lines.append(f"| **federated logreg (ours)** | no rows leave any bank | – | – "
                     f"| {_fmt(fed['auc'])} | {_fmt(fed['ap'])} |")
    return "\n".join(lines)


def _main() -> None:
    parser = argparse.ArgumentParser(description="per-bank baselines + centralized ceiling")
    parser.add_argument("--banks", default="1,2,3,4")
    parser.add_argument("--models", default=",".join(MODEL_KEYS), help="subset of logreg,rf,hgb")
    parser.add_argument("--max-rows", type=int, default=500_000)
    parser.add_argument("--n-jobs", type=int, default=2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--data-dir", default=str(DATA_DIR))
    parser.add_argument("--state-dir", default=str(STATE_DIR))
    parser.add_argument("--federated-model", default=None,
                        help="global model JSON to score (default: <state-dir>/global_final.json)")
    parser.add_argument("--no-centralized", action="store_true")
    parser.add_argument("--evaluate", default=None,
                        help="only score this global_*.json on global_test.csv and exit")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    data_dir, state_dir = Path(args.data_dir), Path(args.state_dir)

    if args.evaluate:
        print(json.dumps(evaluate_model_json(args.evaluate, data_dir=data_dir)))
        return

    banks = [int(b) for b in args.banks.split(",") if b.strip()]
    models = [m for m in args.models.split(",") if m in MODEL_KEYS]
    t0 = time.time()
    result = run_baselines(banks, data_dir, args.max_rows, args.seed, args.n_jobs, models,
                           centralized=not args.no_centralized)
    fed_path = Path(args.federated_model) if args.federated_model else state_dir / "global_final.json"
    attach_federated(result, fed_path, data_dir)
    result["meta"]["total_seconds"] = round(time.time() - t0, 1)
    out = state_dir / "baselines.json"
    write_json_atomic(result, out)
    log.info("wrote %s in %.1fs", out, result["meta"]["total_seconds"])
    print(markdown_table(result))


if __name__ == "__main__":
    _main()
