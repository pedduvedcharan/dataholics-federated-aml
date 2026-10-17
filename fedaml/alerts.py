"""Build ``state/alerts.json``: the top-20 flagged chains from the global model (GENAI owns).

    python -m fedaml.alerts --test data/global_test.csv --model state/global_final.json \
        --out state/alerts.json --top 20

Scoring uses the exact logistic formula of the federated global model
(``sigmoid(featurize(df) @ coef + intercept)``) so the SAR attributes the flag to the
model that the banks trained, not to a second opinion. ``global_test.csv`` is the
regulator-side held-out set (CONTRACTS §2), so chains may span several banks.

Output schema (CONTRACTS §6, agents/06-GENAI.md):
    [{"alert_id", "score", "rank", "model_sha256", "trigger": {row}, "rows": [<=10 rows],
      "banks_involved": [...], "accounts": [...], "top_features": [{"name","value","weight","contribution"}],
      "chain_summary": {"n_rows","total_amt_paid","sender_other_txns","receiver_onward_txns"}}]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import tempfile

import numpy as np
import pandas as pd

log = logging.getLogger("fedaml.alerts")

ROW_COLS = ["ts", "from_bank", "from_acct", "to_bank", "to_acct", "amt_paid", "cur_paid",
            "amt_recv", "cur_recv", "fmt", "is_laundering"]


def load_model(path: str) -> dict:
    """Load a global model JSON (CONTRACTS §4) and verify its sha256 if present."""
    with open(path) as f:
        m = json.load(f)
    if "sha256" in m:
        body = {k: m[k] for k in ("coef", "intercept", "feature_names") if k in m}
        digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
        if digest != m["sha256"]:
            log.warning("model sha256 in file (%s...) differs from recomputed (%s...); "
                        "using the file's value", m["sha256"][:12], digest[:12])
    return m


def score(df: pd.DataFrame, model: dict) -> tuple[np.ndarray, np.ndarray]:
    """Return (probabilities, feature matrix) using the global logistic model."""
    from fedaml.features import FEATURE_NAMES, featurize  # MODELS owns this (CONTRACTS §3)

    names = model.get("feature_names", FEATURE_NAMES)
    if list(names) != list(FEATURE_NAMES):
        raise ValueError("model feature_names differ from fedaml.features.FEATURE_NAMES")
    X = featurize(df).astype(np.float64)
    coef = np.asarray(model["coef"], dtype=np.float64)
    intercept = float(np.asarray(model["intercept"], dtype=np.float64).ravel()[0])
    z = X @ coef + intercept
    return 1.0 / (1.0 + np.exp(-z)), X


def _row_dict(r: pd.Series) -> dict:
    out = {}
    for c in ROW_COLS:
        if c not in r.index:
            continue
        v = r[c]
        if isinstance(v, (np.integer,)):
            v = int(v)
        elif isinstance(v, (np.floating,)):
            v = round(float(v), 2)
        elif isinstance(v, pd.Timestamp):
            v = v.isoformat()
        out[c] = v if not (isinstance(v, float) and np.isnan(v)) else None
    return out


def gather_chain(df: pd.DataFrame, idx: int, max_rows: int = 10) -> tuple[list[dict], int, int]:
    """Trigger row first, then the sender's other txns and the receiver's onward txns, <= max_rows."""
    trig = df.loc[idx]
    sender, receiver = str(trig["from_acct"]), str(trig["to_acct"])
    sender_other = df[(df["from_acct"].astype(str) == sender) & (df.index != idx)]
    receiver_onward = df[df["from_acct"].astype(str) == receiver]
    n_s, n_r = len(sender_other), len(receiver_onward)
    budget = max_rows - 1
    take_s = min(n_s, max(budget // 2, budget - n_r))
    take_r = min(n_r, budget - take_s)
    chain = pd.concat([df.loc[[idx]], sender_other.sort_values("ts").head(take_s),
                       receiver_onward.sort_values("ts").head(take_r)])
    out = [_row_dict(r) for _, r in chain.iterrows()]
    out[0]["role"] = "trigger"
    for d in out[1:take_s + 1]:
        d["role"] = "sender_other"
    for d in out[take_s + 1:]:
        d["role"] = "receiver_onward"
    return out, n_s, n_r


def top_features(x: np.ndarray, coef: np.ndarray, names: list[str], k: int = 5) -> list[dict]:
    """Top-k features by |value * coefficient| for one row."""
    contrib = x * coef
    order = np.argsort(-np.abs(contrib))[:k]
    return [{"name": names[i], "value": round(float(x[i]), 4), "weight": round(float(coef[i]), 4),
             "contribution": round(float(contrib[i]), 4)} for i in order if x[i] != 0.0 or i == order[0]]


def build_alerts(df: pd.DataFrame, model: dict, top: int = 20, max_rows: int = 10) -> list[dict]:
    """Score every row, take the top ``top`` by probability, attach chain + attribution."""
    p, X = score(df, model)
    coef = np.asarray(model["coef"], dtype=np.float64)
    names = list(model.get("feature_names"))
    order = np.argsort(-p)[:top]
    alerts = []
    for rank, pos in enumerate(order, start=1):
        idx = df.index[pos]
        rows, n_s, n_r = gather_chain(df, idx, max_rows)
        banks = sorted({int(r["from_bank"]) for r in rows} | {int(r["to_bank"]) for r in rows})
        accounts = sorted({str(r["from_acct"]) for r in rows} | {str(r["to_acct"]) for r in rows})
        alerts.append({
            "alert_id": f"A{rank:02d}",
            "rank": rank,
            "score": round(float(p[pos]), 6),
            "model_sha256": model.get("sha256"),
            "model_round": model.get("round"),
            "trigger": rows[0],
            "rows": rows,
            "banks_involved": banks,
            "accounts": accounts,
            "top_features": top_features(X[pos], coef, names),
            "chain_summary": {
                "n_rows": len(rows),
                "total_amt_paid": round(float(sum(r.get("amt_paid") or 0.0 for r in rows)), 2),
                "sender_other_txns": int(n_s),
                "receiver_onward_txns": int(n_r),
                "n_banks": len(banks),
            },
        })
    return alerts


def write_json_atomic(path: str, obj) -> None:
    """Write JSON via temp file + rename so the dashboard never reads a half file."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path) or ".", suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        json.dump(obj, f, indent=1)
    os.replace(tmp, path)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build state/alerts.json from the global model")
    ap.add_argument("--test", default="data/global_test.csv")
    ap.add_argument("--model", default="state/global_final.json")
    ap.add_argument("--out", default="state/alerts.json")
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--max-rows", type=int, default=10)
    ap.add_argument("--nrows", type=int, default=None, help="read only the first N rows (debug)")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    np.random.seed(args.seed)

    df = pd.read_csv(args.test, nrows=args.nrows)
    log.info("loaded %s: %d rows, laundering rate %.5f", args.test, len(df), df["is_laundering"].mean())
    model = load_model(args.model)
    alerts = build_alerts(df, model, args.top, args.max_rows)
    write_json_atomic(args.out, alerts)
    hit = sum(int(a["trigger"].get("is_laundering") or 0) for a in alerts)
    log.info("wrote %d alerts to %s (top score %.4f, %d/%d triggers are labelled laundering)",
             len(alerts), args.out, alerts[0]["score"] if alerts else 0.0, hit, len(alerts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
