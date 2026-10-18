"""Bank-local scoring, alerts and investigator reports (GENAI owns; CONTRACTS §9.1).

    python -m fedaml.bank_local --banks 1,2,3,4 [--sar-engine none|template|llm] [--sar-top 3]

After federated training, each bank scores ITS OWN ``data/banks/bank_<b>/test.csv`` with the final
federated model and keeps the review queue and reports in ``state/bank_local/bank_<b>/``. Nothing
per-transaction leaves that folder; ``state/bank_local/summary.json`` carries aggregates only.

Scoring is the logistic formula of ``fedaml.baselines.predict_proba_json`` on features computed within
the bank. Ranking uses MODELS' ``cap_for_alerts`` (log_amt clipped at log1p(1e7)) and drops same-account
transfers; the reported score is that ranking score, and the contribution table is computed from the same
capped features, so ``intercept + sum(contributions)`` equals the logit of ``score``. ``score_raw`` (uncapped)
is reported next to it. Single-bank chains are fine here: a bank only sees its own rows.

Honest boundary: in the demo all banks run on one VM; the bank boundary is a logical one (separate files
and routes), not network isolation.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import math
import os
import sys

import numpy as np
import pandas as pd

from fedaml import alerts as A

log = logging.getLogger("fedaml.bank_local")

WORDING = "alerts are ranked for analyst review inside the bank; they are not detected laundering"
LABEL_NOTE = ("synthetic ground-truth label from the IBM AML HI-Small dataset; not known to the bank, "
              "the model or the investigator at alert time")
DEMO_BANKS = (2, 3, 4)  # bank 1 is unlearnable (MASTER decision Oct 17 15:55)


def _f(v) -> float | None:
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else round(float(v), 6)


def score_bank(df: pd.DataFrame, model: dict) -> dict:
    """Score one bank's rows: ranking probability (capped), raw probability, capped X, logits."""
    p_cap, X_cap = A.score(df, model, cap=True)
    p_raw, _ = A.score(df, model, cap=False)
    coef = np.asarray(model["coef"], dtype=np.float64)
    b0 = float(np.asarray(model["intercept"], dtype=np.float64).ravel()[0])
    return {"p": p_cap, "p_raw": p_raw, "X": X_cap, "coef": coef, "intercept": b0, "logit": X_cap @ coef + b0}


def rank_queue(df: pd.DataFrame, s: dict, k: int) -> tuple[list[int], int]:
    """Positions of the top-k rows by ranking score, same-account transfers removed. Returns (positions, skipped)."""
    same = (df["from_acct"].astype(str) == df["to_acct"].astype(str)).to_numpy()
    order = np.argsort(-s["p"], kind="stable")
    kept, skipped = [], 0
    for pos in order:
        if len(kept) >= k:
            break
        if same[pos]:
            skipped += 1
            continue
        kept.append(int(pos))
    return kept, skipped


def queue_row(b: int, rank: int, pos: int, df: pd.DataFrame, s: dict) -> dict:
    r = df.iloc[pos]
    return {"alert_id": f"B{b}-A{rank:02d}", "rank": rank, "score": _f(s["p"][pos]), "score_raw": _f(s["p_raw"][pos]),
            "ts": str(r["ts"]), "from_acct": str(r["from_acct"]), "to_acct": str(r["to_acct"]),
            "to_bank": str(r["to_bank"]), "amt_paid": _f(r["amt_paid"]), "cur_paid": str(r["cur_paid"]),
            "fmt": str(r["fmt"]), "is_laundering": int(r["is_laundering"]), "has_sar": False}


def sar_alert(b: int, rank: int, pos: int, df: pd.DataFrame, s: dict, model: dict, labels: dict) -> dict:
    """Alert record in the shape fedaml.sar expects, built only from this bank's rows."""
    idx = df.index[pos]
    rows, n_s, n_r = A.gather_chain(df, idx, 10)
    banks = sorted({str(x["from_bank"]) for x in rows} | {str(x["to_bank"]) for x in rows}, key=A._bank_key)
    a = A._alert(rank, pos, idx, s["p"], s["X"], s["coef"], list(model["feature_names"]), model,
                 rows, n_s, n_r, banks, labels)
    a["alert_id"] = f"B{b}-A{rank:02d}"
    a["sample_desc"] = f"bank {b}'s own test-period records"
    a["scope_note"] = (f"Scored inside bank {b} on its own records with the shared model; no other bank's rows "
                       "were used and nothing in this report leaves the bank.")
    return a


def demo_record(b: int, rank: int, pos: int, df: pd.DataFrame, s: dict, model: dict, model_file: str,
                threshold: dict, k: int, related: list[dict]) -> dict:
    """demo.json (CONTRACTS §9.1): every number computed from the saved model and the bank's file."""
    from fedaml.features import FEATURE_DESCRIPTIONS

    r = df.iloc[pos]
    names = list(model["feature_names"])
    x = s["X"][pos]
    feats = [{"name": n, "meaning": FEATURE_DESCRIPTIONS.get(n, n), "value": round(float(x[i]), 6),
              "weight": round(float(s["coef"][i]), 6), "contribution": round(float(x[i] * s["coef"][i]), 6)}
             for i, n in enumerate(names)]
    lab = int(r["is_laundering"])
    return {
        "bank_id": b, "alert_id": f"B{b}-A{rank:02d}", "synthetic": True,
        "source": f"data/banks/bank_{b}/test.csv data row {int(df.index[pos])} (0-based, header excluded)",
        "model": {"file": model_file, "sha256": model.get("sha256"), "round": model.get("round")},
        "transaction": {"ts": str(r["ts"]), "from_acct": str(r["from_acct"]), "to_acct": str(r["to_acct"]),
                        "to_bank": str(r["to_bank"]), "amt_paid": _f(r["amt_paid"]), "cur_paid": str(r["cur_paid"]),
                        "amt_recv": _f(r["amt_recv"]), "cur_recv": str(r["cur_recv"]), "fmt": str(r["fmt"])},
        "features": feats,
        "intercept": round(s["intercept"], 6),
        "logit": round(float(s["logit"][pos]), 6),
        "score": _f(s["p"][pos]),
        "score_raw": _f(s["p_raw"][pos]),
        "score_note": ("score = sigmoid(intercept + sum(contribution)); features as used for ranking "
                       "(log_amt capped at log1p(1e7)); score_raw uses the uncapped log_amt"),
        "threshold": threshold, "alerted": rank <= k, "rank": rank,
        "priority": "high" if rank <= 5 else "normal",
        "label": {"is_laundering": lab, "note": LABEL_NOTE},
        "related": related,
        "sar": None,
    }


def write_json(path: str, obj) -> None:
    A.write_json_atomic(path, obj)


def run_bank(b: int, model: dict, model_file: str, data_dir: str, k: int,
             labels: dict) -> dict:
    """Score bank b, write its alerts.json, return in-memory context for demo/SAR steps."""
    from fedaml.features import read_csv

    path = os.path.join(data_dir, "banks", f"bank_{b}", "test.csv")
    df = read_csv(path)
    s = score_bank(df, model)
    kept, skipped = rank_queue(df, s, k)
    rows = [queue_row(b, i + 1, pos, df, s) for i, pos in enumerate(kept)]
    thr = {"value": rows[-1]["score"] if rows else None,
           "rule": f"score of rank {k} in bank {b}'s own review queue (top {k} after removing same-account "
                   f"transfers); a transaction is alerted when it ranks in the top {k}"}
    meta = {"bank_id": b, "model_sha256": model.get("sha256"), "model_round": model.get("round"),
            "model_file": model_file, "source": path, "n_scored": int(len(df)), "k": k, "threshold": thr,
            "labelled_in_top_k": int(sum(r["is_laundering"] for r in rows)),
            "prevalence": round(float(df["is_laundering"].mean()), 6) if len(df) else None,
            "filters": {"exclude_same_account": True, "same_account_skipped": skipped,
                        "log_amt_cap": "fedaml.features.cap_for_alerts (log1p(1e7)), ranking only"},
            "wording": WORDING}
    log.info("bank %d: %d rows scored, top-%d holds %d labelled laundering (prevalence %.4f%%), threshold %.6f",
             b, len(df), k, meta["labelled_in_top_k"], 100 * (meta["prevalence"] or 0), thr["value"] or 0)
    return {"bank": b, "df": df, "s": s, "kept": kept, "doc": {"meta": meta, "alerts": rows}, "labels": labels}


def pick_demo(ctx: dict[int, dict]) -> tuple[int, int] | None:
    """(bank, rank) of the highest-ranked labelled-laundering alert among DEMO_BANKS; ties -> lower bank id."""
    best = None
    for b in sorted(ctx):
        if b not in DEMO_BANKS:
            continue
        for r in ctx[b]["doc"]["alerts"]:
            if r["is_laundering"] == 1:
                if best is None or r["rank"] < best[1]:
                    best = (b, r["rank"])
                break
    return best


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Bank-local scoring, alerts and reports (CONTRACTS §9.1)")
    ap.add_argument("--banks", default="1,2,3,4")
    ap.add_argument("--model", default="state/global_final_dpon.json")
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--out", default="state/bank_local")
    ap.add_argument("--k", type=int, default=20)
    ap.add_argument("--sar-engine", choices=["none", "template", "llm"], default="template")
    ap.add_argument("--sar-top", type=int, default=3, help="also write reports for the demo bank's top N alerts")
    ap.add_argument("--timeout", type=float, default=60.0)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    np.random.seed(args.seed)

    model = A.load_model(args.model)
    labels = A.load_bank_labels(os.path.join(args.data_dir, "bank_map.json"))
    banks = [int(x) for x in args.banks.split(",") if x]
    ctx = {b: run_bank(b, model, args.model, args.data_dir, args.k, labels) for b in banks}

    demo = pick_demo(ctx)
    if demo is None:  # documented fallback: the top alert of the lowest demo bank present
        b0 = next((b for b in sorted(ctx) if b in DEMO_BANKS), sorted(ctx)[0])
        demo = (b0, 1)
        log.warning("no labelled-laundering alert in banks %s; demo falls back to bank %d rank 1", DEMO_BANKS, b0)
    db, _ = demo

    from fedaml.sar import write_sar

    reports: dict[int, int] = {b: 0 for b in ctx}
    demos: dict[int, dict] = {}
    for b, c in ctx.items():
        if not c["kept"]:
            continue
        # each bank's own demo: its top labelled-laundering alert, else its top alert (CONTRACTS §9.1)
        brank = next((r["rank"] for r in c["doc"]["alerts"] if r["is_laundering"] == 1), 1)
        targets = []
        if args.sar_engine != "none":
            targets = sorted({brank} | (set(range(1, args.sar_top + 1)) if b == db else set()))
        sar_dir = os.path.join(args.out, f"bank_{b}", "sar")
        sar_meta = None
        for rank in targets:
            if rank > len(c["kept"]):
                continue
            alert = sar_alert(b, rank, c["kept"][rank - 1], c["df"], c["s"], model, c["labels"])
            _, footer = write_sar(alert, model, args.sar_engine, sar_dir, timeout=args.timeout, seed=args.seed)
            os.chmod(os.path.join(sar_dir, f"{alert['alert_id']}.md"), 0o644)
            c["doc"]["alerts"][rank - 1]["has_sar"] = True
            reports[b] += 1
            if rank == brank:
                sar_meta = {"alert_id": alert["alert_id"], "engine": footer["engine"],
                            "model_file": os.path.basename(str(footer.get("model") or "")) or None,
                            "seconds": footer.get("seconds", footer.get("llm_seconds_before_fallback")),
                            "fallback_reason": footer.get("fallback_reason")}
        pos = c["kept"][brank - 1]
        related = A.gather_chain(c["df"], c["df"].index[pos], 11)[0][1:]
        d = demo_record(b, brank, pos, c["df"], c["s"], model, args.model, c["doc"]["meta"]["threshold"],
                        args.k, related)
        d["sar"] = sar_meta
        d["demo_rule"] = ("this bank's highest-ranked alert whose trigger is labelled laundering in the synthetic "
                          "data, else its top alert" + ("" if d["label"]["is_laundering"] else
                                                        " (no labelled alert in this bank's top k)"))
        d["walkthrough_bank"] = b == db
        check = 1.0 / (1.0 + math.exp(-(d["intercept"] + sum(f["contribution"] for f in d["features"]))))
        assert abs(check - d["score"]) < 1e-4, (b, check, d["score"])  # the walkthrough's arithmetic must close
        demos[b] = d

    for b, cb in ctx.items():
        write_json(os.path.join(args.out, f"bank_{b}", "alerts.json"), cb["doc"])
    for b, d in demos.items():
        write_json(os.path.join(args.out, f"bank_{b}", "demo.json"), d)
    summary = {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
               "model_sha256": model.get("sha256"),
               "walkthrough_bank": db,
               "walkthrough_rule": (f"bank among {list(DEMO_BANKS)} whose queue has a labelled-laundering alert at "
                                    "the highest rank (bank 1 is unlearnable)"),
               "per_bank": {str(b): {"n_scored": cb["doc"]["meta"]["n_scored"], "k": args.k,
                                     "n_alerts": len(cb["doc"]["alerts"]),
                                     "labelled_in_top_k": cb["doc"]["meta"]["labelled_in_top_k"],
                                     "reports_written": reports[b]} for b, cb in ctx.items()}}
    write_json(os.path.join(args.out, "summary.json"), summary)
    for b, d in demos.items():
        log.info("demo bank %d%s: %s rank %d score %.6f threshold %.6f label %d sar %s", b,
                 " (walkthrough)" if d["walkthrough_bank"] else "", d["alert_id"], d["rank"], d["score"],
                 d["threshold"]["value"], d["label"]["is_laundering"], d["sar"])
    log.info("summary: %s", json.dumps(summary["per_bank"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
