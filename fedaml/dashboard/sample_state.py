"""Write SYNTHETIC example files so the dashboard can be developed before the
federation runs.  Never point the demo at these: every file carries
``"synthetic_sample": true`` and the page shows a SAMPLE DATA banner.

    python -m fedaml.dashboard.sample_state --out /tmp/fedaml_sample
    python -m fedaml.dashboard --state-dir /tmp/fedaml_sample/state --logs-dir /tmp/fedaml_sample/logs/egress
"""
from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path

from fedaml import egress


def write(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj | {"synthetic_sample": True}, indent=2))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--rounds", type=int, default=7)
    ap.add_argument("--total-rounds", type=int, default=10)
    args = ap.parse_args()
    rng = random.Random(42)
    out = Path(args.out)
    state, logs = out / "state", out / "logs" / "egress"

    rounds = []
    for r in range(1, args.rounds + 1):
        auc = 0.62 + 0.25 * (1 - math.exp(-r / 2.5)) + rng.uniform(-0.01, 0.01)
        excluded = [{"bank_id": 5, "reason": "cosine distance to median 0.93 > tau 0.5",
                     "score": round(0.9 + rng.uniform(0, 0.08), 3)}] if r >= 2 else []
        rounds.append({"round": r, "accepted": [1, 2, 3, 4] + ([5] if r < 2 else []),
                       "excluded": excluded, "pooled_auc": round(auc, 4), "pooled_ap": round(auc * 0.12, 4),
                       "global_auc": round(auc - 0.08, 4), "global_ap": round(auc * 0.09, 4),
                       "per_bank_auc": {str(b): round(auc - 0.05 + rng.uniform(-0.03, 0.03), 4)
                                        for b in range(1, 5)}})
    write(state / "status.json", {
        "round": args.rounds, "total_rounds": args.total_rounds,
        "dp": {"enabled": True, "sigma": 0.8, "clip_norm": 1.0,
               "epsilon_spent": round(0.55 * args.rounds, 2), "delta": 1e-5},
        "rounds": rounds, "banks_expected": [1, 2, 3, 4, 5]})
    write(state / "redteam.json", {
        "attack": "loss_threshold", "target": "laundering", "members": "bank_1 train rows",
        "dp_off": {"attack_acc": 0.71, "attack_auc": 0.76, "n": 420, "verdict": "LEAKS"},
        "dp_on": {"attack_acc": 0.52, "attack_auc": 0.53, "n": 420, "verdict": "PROTECTED"},
        "model_auc_off": 0.89, "model_auc_on": 0.86,
        "detail": {"dp_off": {"targets": {"all": {"result": {"attack_acc": 0.503, "attack_auc": 0.505, "n": 20000}}}},
                   "dp_on": {"targets": {"all": {"result": {"attack_acc": 0.499, "attack_auc": 0.501, "n": 20000}}}}}})
    write(state / "baselines.json", {
        "per_bank": {str(b): {"logreg": {"auc": 0.74 + 0.02 * b, "ap": 0.05},
                              "rf": {"auc": 0.78 + 0.01 * b, "ap": 0.07},
                              "hgb": {"auc": 0.80 + 0.01 * b, "ap": 0.08}} for b in range(1, 5)},
        "federated": {"auc": 0.87, "ap": 0.10}, "centralized_logreg": {"auc": 0.82, "ap": 0.10, "pooled_auc": 0.90, "pooled_ap": 0.12}})
    write(state / "footprint.json", {
        "per_container_peak_rss_mb": {"coordinator": 412, "bank1": 790, "bank2": 745,
                                      "bank3": 702, "bank4": 688, "rogue": 655, "dashboard": 61},
        "seconds_per_round": 38.5, "total_runtime_s": 421, "cpu_count": 3, "arch": "s390x"})

    # egress trail: one model update per bank per round, plus two blocked attempts
    logs.mkdir(parents=True, exist_ok=True)
    for f in logs.glob("bank_*.jsonl"):
        f.unlink()
    n = egress.feature_count()
    import fedaml.egress as eg  # monkeypatch the POST so nothing leaves this machine

    class _R:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"accepted": True}
    eg.requests.post = lambda *a, **k: _R()  # type: ignore[assignment]
    for r in range(1, args.rounds + 1):
        for b in [1, 2, 3, 4, 5]:
            payload = {"bank_id": b, "round": r, "n_samples": 400000 + 1000 * b,
                       "delta_coef": [rng.gauss(0, 0.05) for _ in range(n)],
                       "delta_intercept": [rng.gauss(0, 0.01)], "clip_norm": 1.0,
                       "dp": {"enabled": True, "sigma": 0.8}, "feature_names_sha256": "f" * 64,
                       "payload_sha256": "p" * 64, "signature": None}
            eg.send("http://coordinator:8000", payload, b, r, logs_dir=logs)
    for b in (1, 3):
        try:
            eg.send("http://coordinator:8000", {"bank_id": b, "round": 0,
                    "rows": [{"from_acct": "X", "amt_paid": 1.0}]}, b, 0, logs_dir=logs)
        except egress.EgressViolation:
            pass
    print(f"sample state in {state}  egress logs in {logs}")


if __name__ == "__main__":
    main()
