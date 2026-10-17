"""Build ``state/alerts.json``: the top-20 flagged chains from the global model (GENAI owns).

    python -m fedaml.alerts --test data/global_test.csv --model state/global_final.json \
        --out state/alerts.json --top 20

Scoring uses the exact logistic formula of the federated global model
(``sigmoid(featurize(df) @ coef + intercept)``) so the SAR attributes the flag to the
model that the banks trained, not to a second opinion. ``global_test.csv`` is the
regulator-side held-out set (CONTRACTS §2), so chains may span several banks.

Filter: same-account transfers and chains touching < 2 banks are skipped while ranking
(MASTER decision Oct 17 16:16); ``meta`` reports precision before and after.

Output schema (CONTRACTS §6, agents/06-GENAI.md):
    {"meta": {...precision, filter, demo_alert_id...}, "alerts":
    [{"alert_id", "score", "rank", "model_sha256", "trigger": {row}, "rows": [<=10 rows],
      "banks_involved": [codes], "institutions": [{"code","label","role","rows"}], "accounts": [...], "top_features": [{"name","value","weight","contribution"}],
      "chain_summary": {"n_rows","total_amt_paid","sender_other_txns","receiver_onward_txns","laundering_rows"}}]}
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
        digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"),
                                           allow_nan=False).encode()).hexdigest()
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
        if isinstance(v, (np.integer, np.bool_)):
            v = int(v)
        elif pd.isna(v):
            v = None
        elif isinstance(v, (np.floating,)):
            v = round(float(v), 2)
        elif isinstance(v, pd.Timestamp):
            v = v.isoformat()
        out[c] = v
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


def _bank_key(b: str) -> tuple[int, str]:
    return (int(b), b) if b.isdigit() else (10**9, b)


def load_bank_labels(path: str) -> dict[str, str]:
    """``data/bank_map.json`` (INFRA) -> {from_bank code: "bank <id> (<role>)"}; {} if absent."""
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        bm = json.load(f)
    out: dict[str, str] = {}
    for bid, meta in (bm.get("banks") or {}).items():
        code = meta.get("from_bank", meta.get("code"))
        if code is not None:
            role = meta.get("role")
            out[str(code)] = f"bank {bid}" + (f" ({role})" if role else "")
    return out


def institutions(rows: list[dict], banks: list[str], labels: dict[str, str]) -> list[dict]:
    """One entry per bank code in the chain: federation label (if any), role, rows touching it."""
    trig = rows[0]
    out = []
    for b in banks:
        roles = []
        if b == str(trig["from_bank"]):
            roles.append("sender's bank")
        if b == str(trig["to_bank"]):
            roles.append("receiver's bank")
        n = sum(1 for r in rows if str(r["from_bank"]) == b or str(r["to_bank"]) == b)
        out.append({"code": b, "label": labels.get(b), "role": ", ".join(roles) or "counterparty / downstream",
                    "rows": n})
    return out


def _alert(rank: int, pos: int, idx, p: np.ndarray, X: np.ndarray, coef: np.ndarray, names: list[str],
           model: dict, rows: list[dict], n_s: int, n_r: int, banks: list[str], labels: dict[str, str]) -> dict:
    accounts = sorted({str(r["from_acct"]) for r in rows} | {str(r["to_acct"]) for r in rows})
    return {
        "alert_id": f"A{rank:02d}",
        "rank": rank,
        "score": round(float(p[pos]), 6),
        "model_sha256": model.get("sha256"),
        "model_round": model.get("round"),
        "trigger": rows[0],
        "rows": rows,
        "banks_involved": banks,
        "institutions": institutions(rows, banks, labels),
        "accounts": accounts,
        "top_features": top_features(X[pos], coef, names),
        "chain_summary": {
            "n_rows": len(rows),
            "total_amt_paid": round(float(sum(r.get("amt_paid") or 0.0 for r in rows)), 2),
            "sender_other_txns": int(n_s),
            "receiver_onward_txns": int(n_r),
            "n_banks": len(banks),
            "laundering_rows": int(sum(int(r.get("is_laundering") or 0) for r in rows)),
        },
    }


def build_alerts(df: pd.DataFrame, model: dict, top: int = 20, max_rows: int = 10,
                 bank_labels: dict[str, str] | None = None, exclude_self: bool = True,
                 min_banks: int = 2, extra_k: tuple[int, ...] = (50, 100)) -> tuple[list[dict], dict]:
    """Rank rows by score and keep the top ``top`` that pass the product filter.

    Filter (agreed with MASTER, Oct 17 16:16): skip same-account transfers (``from_acct == to_acct``,
    a currency conversion inside one account, not a chain) and chains touching fewer than ``min_banks``
    banks. Returns ``(alerts, meta)``; meta reports precision of the trigger labels before and after.
    """
    labels = bank_labels or {}
    p, X = score(df, model)
    coef = np.asarray(model["coef"], dtype=np.float64)
    names = list(model.get("feature_names"))
    y = df["is_laundering"].fillna(0).astype(int).to_numpy()
    self_mask = (df["from_acct"].astype(str) == df["to_acct"].astype(str)).to_numpy()
    order = np.argsort(-p, kind="stable")

    raw = order[:top]
    k_max = max((top,) + tuple(extra_k))
    kept: list[tuple[int, list[dict], int, int, list[str]]] = []
    skipped_self = skipped_banks = 0
    for pos in order:
        if len(kept) >= k_max:
            break
        if exclude_self and self_mask[pos]:
            skipped_self += 1
            continue
        rows, n_s, n_r = gather_chain(df, df.index[pos], max_rows)
        banks = sorted({str(r["from_bank"]) for r in rows} | {str(r["to_bank"]) for r in rows}, key=_bank_key)
        if len(banks) < min_banks:
            skipped_banks += 1
            continue
        kept.append((int(pos), rows, n_s, n_r, banks))

    alerts = [_alert(rank, pos, df.index[pos], p, X, coef, names, model, rows, n_s, n_r, banks, labels)
              for rank, (pos, rows, n_s, n_r, banks) in enumerate(kept[:top], start=1)]

    def prec(positions: list[int]) -> dict:
        tp = int(sum(y[q] for q in positions))
        return {"k": len(positions), "true_laundering": tp, "precision": round(tp / len(positions), 4) if positions else None}

    demo = next((a for a in alerts if int(a["trigger"].get("is_laundering") or 0) == 1), None)
    meta = {
        "source": None,
        "model_sha256": model.get("sha256"), "model_round": model.get("round"),
        "n_scored": int(len(df)), "prevalence": round(float(y.mean()), 6) if len(y) else None,
        "filter": {"exclude_same_account": exclude_self, "min_banks": min_banks},
        "unfiltered": {**prec([int(q) for q in raw]), "same_account_in_top": int(self_mask[raw].sum())},
        "filtered": {f"at_{len(kept[:k])}": prec([q for q, *_ in kept[:k]]) for k in (top,) + tuple(extra_k)},
        "removed_while_ranking": {"same_account": skipped_self, "fewer_than_min_banks": skipped_banks},
        "same_account_rows_in_sample": int(self_mask.sum()),
        "same_account_laundering_in_sample": int(y[self_mask].sum()),
        "demo_alert_id": demo["alert_id"] if demo else None,
        "demo_alert_rule": "highest-ranked alert after the filter whose trigger is labelled laundering",
    }
    return alerts, meta


def write_json_atomic(path: str, obj) -> None:
    """Write JSON via temp file + rename so the dashboard never reads a half file."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path) or ".", suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        json.dump(obj, f, indent=1)
    os.replace(tmp, path)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build state/alerts.json from the global model")
    ap.add_argument("--test", default="data/global_test.csv",
                    help="CSV to score; comma-separate several, e.g. data/banks/bank_2/test.csv,data/banks/bank_3/test.csv")
    ap.add_argument("--model", default="state/global_final.json")
    ap.add_argument("--out", default="state/alerts.json")
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--max-rows", type=int, default=10)
    ap.add_argument("--nrows", type=int, default=None, help="read only the first N rows (debug)")
    ap.add_argument("--bank-map", default=None, help="data/bank_map.json (default: next to --test)")
    ap.add_argument("--min-banks", type=int, default=2, help="drop chains touching fewer banks (default 2)")
    ap.add_argument("--keep-same-account", action="store_true", help="do not drop from_acct == to_acct rows")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    np.random.seed(args.seed)

    from fedaml.features import read_csv  # string dtypes for bank codes and account ids

    paths = [x for x in args.test.split(",") if x]
    df = pd.concat([read_csv(x, nrows=args.nrows) for x in paths], ignore_index=True)
    bm = args.bank_map or os.path.join(os.path.dirname(paths[0]) or ".", "bank_map.json")
    labels = load_bank_labels(bm if os.path.exists(bm) else os.path.join("data", "bank_map.json"))
    log.info("loaded %s: %d rows, laundering rate %.5f", ",".join(paths), len(df), df["is_laundering"].mean())
    model = load_model(args.model)
    alerts, meta = build_alerts(df, model, args.top, args.max_rows, labels,
                                exclude_self=not args.keep_same_account, min_banks=args.min_banks)
    meta["source"] = paths
    write_json_atomic(args.out, {"meta": meta, "alerts": alerts})
    u, f = meta["unfiltered"], meta["filtered"][f"at_{len(alerts)}"] if alerts else {}
    log.info("unfiltered top-%d: %d/%d labelled laundering, %d same-account", u["k"], u["true_laundering"], u["k"],
             u["same_account_in_top"])
    log.info("filtered: %s; removed while ranking: %s; demo alert %s", meta["filtered"],
             meta["removed_while_ranking"], meta["demo_alert_id"])
    log.info("wrote %d alerts to %s (top score %.4f)", len(alerts), args.out, alerts[0]["score"] if alerts else 0.0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
