"""Update-level membership inference: what the coordinator learns from what leaves a bank.

The model-level attack (fedaml.redteam) asks what anyone holding the *final*
global model can infer.  This module asks the sharper federated-learning
question: the honest-but-curious coordinator sees every bank's per-round
update ``delta = local - global`` (the only thing that ever leaves a bank).
Given a laundering transaction row, can it tell *which bank's update that row
shaped*?  Score = how much the bank's update raises the model's logit for the
row, ``delta . x / ||x||`` (Nasr et al. 2019 / Melis et al. 2019 style
gradient alignment), averaged over rounds.  Members are the target bank's own
training laundering rows; non-members are laundering rows of the other member
banks, balanced exactly.  DP clipping + Gaussian noise on the update should
collapse this to chance; that is the DP-on row.

Real mode reads the payloads the coordinator persisted::

    python -m fedaml.redteam_updates --updates-off state/updates/dpoff \\
        --updates-on state/updates/dpon_s05 [--updates-on state/updates/dpon_s03]

Each file ``round_<r>_bank_<b>.json`` is the CONTRACTS section 4 message.
Simulation mode (``--simulate``) builds the deltas itself from the shards with
the section 4 recipe (clip + Gaussian noise) so the attack can be validated
before real updates exist; the output is labelled as simulated.
"""
from __future__ import annotations

import argparse
import glob
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Optional

import numpy as np
from sklearn.linear_model import LogisticRegression

from fedaml.redteam import (CHANCE_AUC, LEAK_AUC, _bootstrap_auc_ci, _best_threshold, _split,
                            model_sha256, verdict, write_json_atomic)
from fedaml.redteam_data import featurize, _read, _labels

log = logging.getLogger("fedaml.redteam_updates")


# ----------------------------------------------------------------------------- data
def member_rows(data_dir: str, banks: list[int]) -> dict[int, np.ndarray]:
    """Each member bank's laundering training rows, featurised as the bank did for training."""
    out = {}
    for b in banks:
        df = _read(Path(data_dir) / "banks" / f"bank_{b}" / "train.csv")
        X, _ = featurize(df)
        out[b] = X[_labels(df) == 1].astype(np.float64)
    return out


def load_updates(updates_dir: str) -> dict[int, dict[int, np.ndarray]]:
    """{bank_id: {round: delta[coef..., intercept]}} from persisted coordinator payloads."""
    out: dict[int, dict[int, np.ndarray]] = {}
    for path in sorted(glob.glob(os.path.join(updates_dir, "round_*_bank_*.json"))):
        with open(path) as fh:
            m = json.load(fh)
        vec = np.asarray(list(m["delta_coef"]) + list(m["delta_intercept"]), dtype=np.float64)
        out.setdefault(int(m["bank_id"]), {})[int(m["round"])] = vec
    if not out:
        raise FileNotFoundError(f"no round_<r>_bank_<b>.json payloads under {updates_dir}")
    return out


def simulate_updates(data_dir: str, banks: list[int], rounds: int, clip_norm: float, sigma: float,
                     dp: bool, seed: int) -> dict[int, dict[int, np.ndarray]]:
    """Stand-in for real payloads: local lbfgs optimum minus global, clipped, noised (section 4)."""
    rng = np.random.default_rng(seed)
    out: dict[int, dict[int, np.ndarray]] = {}
    for b in banks:
        df = _read(Path(data_dir) / "banks" / f"bank_{b}" / "train.csv")
        X, _ = featurize(df)
        y = _labels(df)
        local = LogisticRegression(class_weight="balanced", max_iter=300).fit(X, y)
        raw = np.r_[local.coef_.ravel(), local.intercept_]
        for r in range(1, rounds + 1):
            # the global model moves between rounds; a fresh seeded jitter keeps rounds distinct
            vec = raw + rng.normal(0, 0.05, raw.shape)
            norm = np.linalg.norm(vec)
            vec = vec * min(1.0, clip_norm / norm) if norm > 0 else vec
            if dp:
                vec = vec + rng.normal(0.0, sigma * clip_norm, vec.shape)
            out.setdefault(b, {})[r] = vec
    return out


# --------------------------------------------------------------------------- attack
def alignment_scores(delta_by_round: dict[int, np.ndarray], X: np.ndarray) -> np.ndarray:
    """Mean over rounds of delta.x/||x|| (how much the bank's updates push these rows' logits up)."""
    Xa = np.c_[X, np.ones(len(X))]                       # intercept column
    norms = np.linalg.norm(Xa, axis=1) + 1e-12
    return np.mean([(Xa @ d) / norms for d in delta_by_round.values()], axis=0)


def attack(updates: dict[int, dict[int, np.ndarray]], members: dict[int, np.ndarray], seed: int,
           calib_frac: float = 0.2) -> dict:
    """For every target bank: its laundering rows vs the other banks' laundering rows, scored
    against the target bank's updates; pooled, threshold-calibrated, AUC with bootstrap CI."""
    rng = np.random.default_rng(seed)
    scores, labels, per_bank = [], [], {}
    banks = [b for b in members if b in updates]
    for b in banks:
        others = np.vstack([members[o] for o in banks if o != b])
        k = int(min(len(members[b]), len(others)))
        mem = members[b][rng.choice(len(members[b]), k, replace=False)]
        non = others[rng.choice(len(others), k, replace=False)]
        s_m, s_n = alignment_scores(updates[b], mem), alignment_scores(updates[b], non)
        per_bank[str(b)] = {"n_members": int(k), "rounds": len(updates[b]),
                            "auc": float(_auc(np.r_[s_m, s_n], np.r_[np.ones(k), np.zeros(k)]))}
        scores += [s_m, s_n]
        labels += [np.ones(k), np.zeros(k)]
    s, is_mem = np.concatenate(scores), np.concatenate(labels)
    c, e = _split(len(s), calib_frac, rng)
    t = _best_threshold(-s[c], is_mem[c])                 # rule: member iff score > -t
    acc = float(np.mean((-s[e] < t) == (is_mem[e] == 1)))
    res = {"attack_acc": acc, "attack_auc": float(_auc(s[e], is_mem[e])),
           "attack_auc_ci90": _bootstrap_auc_ci(s[e], is_mem[e], seed), "n": int(len(e)),
           "n_per_class_total": int(is_mem.sum()), "per_bank": per_bank}
    res["verdict"] = verdict(res)
    return res


def _auc(score: np.ndarray, y: np.ndarray) -> float:
    from sklearn.metrics import roc_auc_score
    return roc_auc_score(y, score)


# ------------------------------------------------------------------------------ CLI
def _label(path: str) -> str:
    m = re.search(r"(dpoff|dpon[\w.]*)", Path(path).name)
    return m.group(1) if m else Path(path).name


def format_table(rows: list[tuple[str, dict]]) -> str:
    lines = [f"{'setting':<34}{'attack acc':>12}{'attack AUC':>12}  {'90% CI':<14} verdict"]
    for name, r in rows:
        ci = f"[{r['attack_auc_ci90'][0]:.2f}, {r['attack_auc_ci90'][1]:.2f}]"
        lines.append(f"{name:<34}{r['attack_acc']:>12.3f}{r['attack_auc']:>12.3f}  {ci:<14} {r['verdict']}")
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Update-level membership inference: DP off vs DP on")
    ap.add_argument("--updates-off", help="dir of persisted payloads from the DP-off run")
    ap.add_argument("--updates-on", action="append", default=[], help="dir(s) of payloads from DP-on run(s)")
    ap.add_argument("--simulate", action="store_true", help="build section-4-recipe deltas from the shards instead")
    ap.add_argument("--sigmas", default="0.3,0.5", help="simulate: DP sigmas to try")
    ap.add_argument("--clip", type=float, default=1.0)
    ap.add_argument("--rounds", type=int, default=10, help="simulate: rounds")
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--member-banks", default="2,3,4")
    ap.add_argument("--out", default="state/redteam_updates.json")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    if not args.simulate and not args.updates_off:
        ap.error("--updates-off is required unless --simulate")

    t0 = time.time()
    banks = [int(b) for b in args.member_banks.split(",")]
    members = member_rows(args.data_dir, banks)
    rows: list[tuple[str, dict]] = []
    if args.simulate:
        rows.append(("DP off / updates (simulated)",
                     attack(simulate_updates(args.data_dir, banks, args.rounds, args.clip, 0.0, False, args.seed), members, args.seed)))
        for sg in [float(s) for s in args.sigmas.split(",")]:
            rows.append((f"DP on σ={sg} / updates (simulated)",
                         attack(simulate_updates(args.data_dir, banks, args.rounds, args.clip, sg, True, args.seed), members, args.seed)))
    else:
        rows.append((f"DP off / updates ({_label(args.updates_off)})", attack(load_updates(args.updates_off), members, args.seed)))
        for d in args.updates_on:
            rows.append((f"DP on / updates ({_label(d)})", attack(load_updates(d), members, args.seed)))
    seconds = time.time() - t0
    report = {"attack": "update_alignment", "simulated": bool(args.simulate), "member_banks": banks,
              "members": "each target bank's train laundering rows", "nonmembers": "other member banks' train laundering rows",
              "rows": {name: r for name, r in rows}, "seed": args.seed, "runtime_s": round(seconds, 1),
              "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    write_json_atomic(args.out, report)
    print(format_table(rows))
    print(f"\nmembers: laundering rows per target bank {[(b, len(m)) for b, m in members.items()]} | "
          f"non-members: other member banks' laundering rows | seed {args.seed} | {seconds:.1f}s | wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
