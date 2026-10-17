"""Per-bank baselines and the shared evaluator (MODELS, CONTRACTS section 6).

For each bank: LogisticRegression, RandomForest and HistGradientBoosting trained
on that bank's ``train.csv`` only, scored on the bank's own ``test.csv`` and on
``data/global_test.csv``. Plus a *centralized* logistic regression on all banks'
training rows concatenated: the upper bound that is illegal in practice.

Writes ``state/baselines.json``::

    {"per_bank": {"1": {"logreg": {"auc", "ap", "own_auc", "own_ap", "global_auc", "global_ap"}, ...}},
     "federated": {"auc", "ap", "n", "per_bank": {id: {"auc","ap"}}, "global_auc", "global_ap"} | null,
     "centralized_logreg": {"auc", "ap", "per_bank": {...}, "global_auc", "global_ap"},
     "meta": {...}}

``auc``/``ap`` everywhere are on the **pooled** basis: each bank's ``test.csv``
featurized within that bank, predictions pooled. ``global_auc``/``global_ap`` score
``global_test.csv`` (the red team's control; its mixed-bank account aggregates are
systematically smaller, so it reads lower).

``evaluate_model_pooled(path, bank_ids)`` and ``evaluate_model_json(path)`` are the
shared evaluators for FEDERATION, REDTEAM and the dashboard.

CLI::

    python -m fedaml.baselines --banks 1,2,3,4
    python -m fedaml.baselines --evaluate state/global_final.json
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

    This is the red team's control. For the headline number use
    :func:`evaluate_model_pooled`: ``global_test.csv`` is a mixed-bank sample, so
    its within-frame account aggregates are smaller than in a bank's own file.
    Pass ``X, y`` to reuse an already-featurized global test set.
    """
    model = load_model_json(path)
    if X is None or y is None:
        X, y = load_global_test(data_dir=data_dir)
    out = metrics(y, predict_proba_json(model, X))
    log.info("%s: global_test auc=%.4f ap=%.4f on %d rows", path, out["auc"], out["ap"], len(y))
    return out


def load_bank_tests(bank_ids: list[int], data_dir: str | Path | None = None
                    ) -> dict[int, tuple[np.ndarray, np.ndarray]]:
    """Each bank's ``test.csv`` featurized *within that bank* -> ``{id: (X, y)}``."""
    return {b: load_bank(b, "test", data_dir=data_dir) for b in bank_ids}


def pooled_metrics(scores: dict[int, np.ndarray], tests: dict[int, tuple[np.ndarray, np.ndarray]]) -> dict:
    """Pool per-bank predictions and labels -> ``{"auc","ap","n","per_bank":{id:{"auc","ap"}}}``."""
    per_bank = {str(b): metrics(tests[b][1], scores[b]) for b in tests}
    y = np.concatenate([tests[b][1] for b in tests])
    p = np.concatenate([scores[b] for b in tests])
    out = metrics(y, p)
    out["n"] = int(len(y))
    out["per_bank"] = per_bank
    return out


def evaluate_model_pooled(path: str | Path, bank_ids: list[int] | None = None,
                          data_dir: str | Path | None = None,
                          tests: dict[int, tuple[np.ndarray, np.ndarray]] | None = None) -> dict:
    """Headline evaluator: featurize each bank's ``test.csv`` within that bank, score it
    with the ``state/global_*.json`` model, pool the predictions.

    Returns ``{"auc","ap","n","per_bank":{id:{"auc","ap"}}}``. Pass ``tests`` from
    :func:`load_bank_tests` to reuse already-featurized test sets.
    """
    model = load_model_json(path)
    if tests is None:
        tests = load_bank_tests(bank_ids or [1, 2, 3, 4], data_dir=data_dir)
    scores = {b: predict_proba_json(model, X) for b, (X, _) in tests.items()}
    out = pooled_metrics(scores, tests)
    log.info("%s: pooled auc=%.4f ap=%.4f on %d rows (banks %s)",
             path, out["auc"], out["ap"], out["n"], list(tests))
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


def _score_all(model, tests: dict, Xg: np.ndarray, yg: np.ndarray) -> dict:
    """Pooled (headline) and global_test (control) metrics for a fitted sklearn model."""
    pooled = pooled_metrics({b: model.predict_proba(X)[:, 1] for b, (X, _) in tests.items()}, tests)
    glob = metrics(yg, model.predict_proba(Xg)[:, 1])
    return {"auc": pooled["auc"], "ap": pooled["ap"], "per_bank": pooled["per_bank"],
            "global_auc": glob["auc"], "global_ap": glob["ap"]}


def run_baselines(banks: list[int], data_dir: Path, max_rows: int, seed: int, n_jobs: int,
                  models: list[str], centralized: bool = True) -> dict:
    """Train/evaluate every (bank, model) and the centralized ceiling.

    Every model is scored on the same **pooled** basis (each bank's test.csv
    featurized within that bank, predictions pooled) -> ``auc``/``ap``; the
    model's own-bank slice is ``own_auc``/``own_ap``; ``global_test.csv`` is kept
    as ``global_auc``/``global_ap`` for the red team's control.
    """
    Xg, yg = load_global_test(data_dir=data_dir)
    tests = load_bank_tests(banks, data_dir=data_dir)
    result: dict = {"per_bank": {}, "federated": None, "centralized_logreg": None,
                    "meta": {"basis": "pooled: each bank's test.csv featurized within that bank, "
                                      "predictions pooled over banks " + str(banks),
                             "train_rows": {}, "test_rows": {str(b): int(len(y)) for b, (_, y) in tests.items()},
                             "test_positives": {str(b): int(y.sum()) for b, (_, y) in tests.items()},
                             "fit_seconds": {},
                             "global_test_rows": int(len(yg)), "global_test_positives": int(yg.sum()),
                             "max_rows": max_rows, "seed": seed, "n_jobs": n_jobs,
                             "feature_names_sha256": feature_names_sha256()}}
    all_X, all_y = [], []
    for b in banks:
        Xtr, ytr = load_bank(b, "train", data_dir=data_dir)
        Xtr, ytr = cap_rows(Xtr, ytr, max_rows, seed)
        all_X.append(Xtr); all_y.append(ytr)
        result["meta"]["train_rows"][str(b)] = int(len(ytr))
        result["per_bank"][str(b)] = {}
        result["meta"]["fit_seconds"][str(b)] = {}
        for key, model in make_models(seed, n_jobs).items():
            if key not in models:
                continue
            t0 = time.time()
            model.fit(Xtr, ytr)
            dt = time.time() - t0
            sc = _score_all(model, tests, Xg, yg)
            own = sc["per_bank"][str(b)]
            result["per_bank"][str(b)][key] = {"auc": sc["auc"], "ap": sc["ap"],
                                               "own_auc": own["auc"], "own_ap": own["ap"],
                                               "global_auc": sc["global_auc"], "global_ap": sc["global_ap"]}
            result["meta"]["fit_seconds"][str(b)][key] = round(dt, 1)
            log.info("bank %d %-6s pooled auc=%.4f ap=%.4f | own auc=%.4f ap=%.4f | global auc=%.4f ap=%.4f (%.1fs)",
                     b, key, sc["auc"], sc["ap"], own["auc"], own["ap"], sc["global_auc"], sc["global_ap"], dt)
        del Xtr
    if centralized and all_X:
        Xc = np.concatenate(all_X); yc = np.concatenate(all_y)
        del all_X
        t0 = time.time()
        clf = LogisticRegression(class_weight="balanced", max_iter=200).fit(Xc, yc)
        result["centralized_logreg"] = _score_all(clf, tests, Xg, yg)
        result["meta"]["centralized_train_rows"] = int(len(yc))
        result["meta"]["fit_seconds"]["centralized_logreg"] = round(time.time() - t0, 1)
        log.info("centralized logreg on %d rows: pooled auc=%.4f ap=%.4f | global auc=%.4f ap=%.4f",
                 len(yc), result["centralized_logreg"]["auc"], result["centralized_logreg"]["ap"],
                 result["centralized_logreg"]["global_auc"], result["centralized_logreg"]["global_ap"])
    result["meta"]["_tests"] = tests  # reused by attach_federated, stripped before writing
    return result


def attach_federated(result: dict, model_path: Path, data_dir: Path) -> dict:
    """Fill ``result["federated"]`` (pooled + global_test) from a global model JSON if it exists."""
    tests = result["meta"].pop("_tests", None)
    if model_path.exists():
        fed = evaluate_model_pooled(model_path, data_dir=data_dir, tests=tests)
        glob = evaluate_model_json(model_path, data_dir=data_dir)
        fed["global_auc"], fed["global_ap"] = glob["auc"], glob["ap"]
        result["federated"] = fed
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
    """Markdown table: pooled basis (headline), own-bank slice, global_test control."""
    lines = ["| Model | Train data | Pooled AUC | Pooled AP | Own-bank AUC | Own-bank AP | global_test AUC | global_test AP |",
             "|---|---|---|---|---|---|---|---|"]
    for b, per in result["per_bank"].items():
        for key, m in per.items():
            lines.append(f"| {key} | bank {b} only | {_fmt(m['auc'])} | {_fmt(m['ap'])} "
                         f"| {_fmt(m['own_auc'])} | {_fmt(m['own_ap'])} "
                         f"| {_fmt(m['global_auc'])} | {_fmt(m['global_ap'])} |")
    c = result.get("centralized_logreg")
    if c:
        lines.append(f"| **centralized logreg (illegal ceiling)** | all banks pooled | {_fmt(c['auc'])} | {_fmt(c['ap'])} "
                     f"| – | – | {_fmt(c['global_auc'])} | {_fmt(c['global_ap'])} |")
    fed = result.get("federated")
    if fed:
        lines.append(f"| **federated logreg (ours)** | no rows leave any bank | {_fmt(fed['auc'])} | {_fmt(fed['ap'])} "
                     f"| – | – | {_fmt(fed.get('global_auc'))} | {_fmt(fed.get('global_ap'))} |")
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
                        help="only score this global_*.json (pooled over --banks, plus global_test control) and exit")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    data_dir, state_dir = Path(args.data_dir), Path(args.state_dir)

    banks = [int(b) for b in args.banks.split(",") if b.strip()]
    if args.evaluate:
        out = evaluate_model_pooled(args.evaluate, banks, data_dir=data_dir)
        glob = evaluate_model_json(args.evaluate, data_dir=data_dir)
        out["global_auc"], out["global_ap"] = glob["auc"], glob["ap"]
        print(json.dumps(out))
        return

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
