#!/usr/bin/env python3
"""Write a SYNTHETIC partition in the CONTRACTS section 2 layout for dry runs before the real data lands.

Uses MODELS' ``fedaml.features.make_synthetic`` so every column and dtype matches the real shards.
Never point the demo or any slide at these files.

  python scripts/make_synthetic_partition.py --out ~/smoke/data --rows 60000 --banks 5
->  <out>/banks/bank_<1..banks>/{train,test}.csv, <out>/global_test.csv, <out>/bank_map.json (marked synthetic)
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import numpy as np

from fedaml.features import make_synthetic

log = logging.getLogger("make_synthetic_partition")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="data")
    ap.add_argument("--rows", type=int, default=60_000, help="total synthetic rows across all banks")
    ap.add_argument("--banks", type=int, default=5, help="bank dirs to write (5 = four banks + rogue)")
    ap.add_argument("--global-test-n", type=int, default=10_000)
    ap.add_argument("--laundering-rate", type=float, default=0.02)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    out = Path(args.out)
    rng = np.random.default_rng(args.seed)
    df = make_synthetic(args.rows, seed=args.seed, n_banks=args.banks, laundering_rate=args.laundering_rate)
    df["from_bank"] = df["from_bank"].astype(str)
    df["to_bank"] = df["to_bank"].astype(str)
    banks_meta = {}
    for bid in range(1, args.banks + 1):
        part = df[df["from_bank"] == str(bid)].reset_index(drop=True)
        n_train = int(0.8 * len(part))
        train, test = part.iloc[:n_train], part.iloc[n_train:]
        bdir = out / "banks" / f"bank_{bid}"
        bdir.mkdir(parents=True, exist_ok=True)
        train.to_csv(bdir / "train.csv", index=False)
        test.to_csv(bdir / "test.csv", index=False)
        banks_meta[str(bid)] = {"from_bank": str(bid), "role": "bank" if bid < args.banks or args.banks < 5 else "rogue",
                                "train_rows": len(train), "train_laundering": int(train["is_laundering"].sum()),
                                "test_rows": len(test), "test_laundering": int(test["is_laundering"].sum())}
        log.info("bank %d: %s", bid, banks_meta[str(bid)])
    cutoff = int(0.8 * len(df))
    tail = df.iloc[cutoff:]
    gt = tail.iloc[np.sort(rng.choice(len(tail), size=min(args.global_test_n, len(tail)), replace=False))]
    gt.to_csv(out / "global_test.csv", index=False)
    (out / "bank_map.json").write_text(json.dumps({
        "SYNTHETIC": True, "source": "fedaml.features.make_synthetic", "seed": args.seed, "n_rows_total": len(df),
        "n_laundering_total": int(df["is_laundering"].sum()), "banks": banks_meta,
        "global_test": {"rows": len(gt), "laundering": int(gt["is_laundering"].sum())}}, indent=2))
    log.info("wrote synthetic partition to %s (global_test %d rows) -- NOT for the demo", out, len(gt))


if __name__ == "__main__":
    main()
