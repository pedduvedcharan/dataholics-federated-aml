#!/usr/bin/env python3
"""Partition HI-Small_Trans.csv per docs/CONTRACTS.md section 2 (INFRA owns this file).

Two chunked passes over the raw CSV so peak memory stays far below 8 GB on the 3-core VM:

  pass 1  per from_bank row/laundering counts + every timestamp  -> 5 busiest banks, global time cutoff
  pass 2  rows of those 5 banks, global_test candidates (ts >= cutoff), sample_50k rows

Outputs under --out (default data/):
  banks/bank_<1..5>/train.csv, test.csv   80/20 time-ordered split per bank, train capped at 500k
                                          by random subsample that keeps every laundering row
  global_test.csv                         200k stratified (by label) sample from the last 20% of
                                          time across ALL banks (coordinator / regulator only)
  bank_map.json                           bank id -> original From Bank code, counts, cutoffs
  sample_50k.csv                          50k random rows incl. ALL laundering rows (local dev)
  partition_summary.md                    the table pasted into STATUS.md

Bank ids 1..4 = the four busiest `From Bank` codes; bank 5 (rogue) = the fifth busiest.

Read the outputs with:
  pd.read_csv(p, dtype={"from_bank": str, "to_bank": str, "from_acct": str, "to_acct": str},
              parse_dates=["ts"])
Account ids look like hex ("81245E60") and WILL be mangled into floats unless read as str.
"""
from __future__ import annotations

import argparse
import json
import logging
import resource
import time
from pathlib import Path

import numpy as np
import pandas as pd
from pandas.api.types import union_categoricals

log = logging.getLogger("partition_data")

RAW_COLS = [
    "Timestamp", "From Bank", "Account", "To Bank", "Account.1", "Amount Received",
    "Receiving Currency", "Amount Paid", "Payment Currency", "Payment Format", "Is Laundering",
]
NEW_COLS = [
    "ts", "from_bank", "from_acct", "to_bank", "to_acct", "amt_recv",
    "cur_recv", "amt_paid", "cur_paid", "fmt", "is_laundering",
]
RENAME = dict(zip(RAW_COLS, NEW_COLS))
LOWCARD = ["cur_recv", "cur_paid", "fmt"]  # kept categorical to save RAM
RAW_DTYPES = {
    "From Bank": str, "Account": str, "To Bank": str, "Account.1": str,
    "Amount Received": "float64", "Amount Paid": "float64",
    "Receiving Currency": "category", "Payment Currency": "category", "Payment Format": "category",
    "Is Laundering": "int8",
}
TS_IN_FORMAT = "%Y/%m/%d %H:%M"
TS_OUT_FORMAT = "%Y-%m-%d %H:%M:%S"


def parse_ts(s: pd.Series) -> pd.Series:
    """Parse the raw Timestamp column (fast path with the known format, generic fallback)."""
    try:
        return pd.to_datetime(s, format=TS_IN_FORMAT)
    except (ValueError, TypeError):
        return pd.to_datetime(s)


def concat_parts(parts: list[pd.DataFrame]) -> pd.DataFrame:
    """Concatenate chunk slices while keeping LOWCARD columns categorical (pd.concat would
    fall back to object dtype when the per-chunk categories differ)."""
    if not parts:
        return pd.DataFrame(columns=NEW_COLS)
    out: dict[str, object] = {}
    for c in parts[0].columns:
        if c in LOWCARD:
            out[c] = union_categoricals([p[c] for p in parts], ignore_order=True)
        else:
            out[c] = pd.concat([p[c] for p in parts], ignore_index=True)
    return pd.DataFrame(out)


def peak_rss_mb() -> float:
    """Peak resident set size of this process in MB (Linux reports KB, macOS bytes)."""
    import sys
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return rss / 1024 / 1024 if sys.platform == "darwin" else rss / 1024


def write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_csv(tmp, index=False, date_format=TS_OUT_FORMAT)
    tmp.replace(path)


def pass1(raw: Path, chunksize: int) -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
    """Return (per-bank counts sorted busiest first, all ts as int64 ns, all labels as int8)."""
    counts: pd.DataFrame | None = None
    ts_parts: list[np.ndarray] = []
    y_parts: list[np.ndarray] = []
    n = 0
    t0 = time.time()
    reader = pd.read_csv(
        raw, usecols=["Timestamp", "From Bank", "Is Laundering"],
        dtype={"From Bank": str, "Is Laundering": "int8"}, chunksize=chunksize,
    )
    for i, ch in enumerate(reader):
        n += len(ch)
        ts_parts.append(parse_ts(ch["Timestamp"]).to_numpy("datetime64[ns]").astype("int64"))
        y_parts.append(ch["Is Laundering"].to_numpy())
        g = ch.groupby("From Bank", sort=False)["Is Laundering"].agg(rows="size", laund="sum")
        counts = g if counts is None else counts.add(g, fill_value=0)
        log.info("pass1 chunk %d: %d rows so far (%.0fs, peak %.0f MB)", i, n, time.time() - t0, peak_rss_mb())
    assert counts is not None, "empty input"
    counts = counts.astype("int64").sort_values(["rows", "laund"], ascending=False)
    return counts, np.concatenate(ts_parts), np.concatenate(y_parts)


def split_bank(df: pd.DataFrame, train_cap: int, rng: np.random.Generator) -> tuple[pd.DataFrame, pd.DataFrame, bool]:
    """80/20 time-ordered split; cap train by random subsample keeping all laundering rows."""
    df = df.sort_values("ts", kind="stable").reset_index(drop=True)
    n_train = int(0.8 * len(df))
    train, test = df.iloc[:n_train], df.iloc[n_train:]
    capped = False
    if len(train) > train_cap:
        pos = train[train["is_laundering"] == 1]
        neg = train[train["is_laundering"] == 0]
        k = max(train_cap - len(pos), 0)
        keep = rng.choice(len(neg), size=min(k, len(neg)), replace=False)
        train = pd.concat([pos, neg.iloc[np.sort(keep)]]).sort_values("ts", kind="stable")
        capped = True
    return train.reset_index(drop=True), test.reset_index(drop=True), capped


def stratified_sample(df: pd.DataFrame, n: int, rng: np.random.Generator) -> pd.DataFrame:
    """Sample n rows keeping the laundering proportion of df (all laundering rows if n is large)."""
    pos = df[df["is_laundering"] == 1]
    neg = df[df["is_laundering"] == 0]
    n = min(n, len(df))
    n_pos = min(len(pos), int(round(n * len(pos) / max(len(df), 1))))
    n_neg = min(len(neg), n - n_pos)
    ip = rng.choice(len(pos), size=n_pos, replace=False)
    ineg = rng.choice(len(neg), size=n_neg, replace=False)
    out = pd.concat([pos.iloc[np.sort(ip)], neg.iloc[np.sort(ineg)]])
    return out.sort_values("ts", kind="stable").reset_index(drop=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", default="data/raw/HI-Small_Trans.csv")
    ap.add_argument("--out", default="data")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--chunksize", type=int, default=1_000_000)
    ap.add_argument("--n-banks", type=int, default=4, help="honest banks; one more is the rogue")
    ap.add_argument("--train-cap", type=int, default=500_000)
    ap.add_argument("--global-test-n", type=int, default=200_000)
    ap.add_argument("--sample-n", type=int, default=50_000)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    raw, out = Path(args.raw), Path(args.out)
    rng = np.random.default_rng(args.seed)
    t_start = time.time()

    # ---------------- pass 1 ----------------
    counts, ts_all, y_all = pass1(raw, args.chunksize)
    n_total, n_pos_total = len(ts_all), int(y_all.sum())
    top = counts.head(args.n_banks + 1)
    bank_codes = list(top.index)  # index 0 -> bank 1 ... index n_banks -> rogue
    code_to_id = {code: i + 1 for i, code in enumerate(bank_codes)}
    ts_sorted = np.sort(ts_all)
    cutoff_ns = int(ts_sorted[int(0.8 * n_total)])
    cutoff = pd.Timestamp(cutoff_ns)
    time_min, time_max = pd.Timestamp(int(ts_sorted[0])), pd.Timestamp(int(ts_sorted[-1]))
    n_cand = int((ts_all >= cutoff_ns).sum())
    del ts_sorted, ts_all, y_all
    log.info("total rows %d, laundering %d (1 in %.0f)", n_total, n_pos_total, n_total / max(n_pos_total, 1))
    log.info("time range %s .. %s ; global_test cutoff %s (%d candidate rows)", time_min, time_max, cutoff, n_cand)
    log.info("busiest from_bank codes: %s", {c: int(top.loc[c, "rows"]) for c in bank_codes})

    # ---------------- pass 2 ----------------
    n_neg_total = n_total - n_pos_total
    neg_rate = min(1.0, 1.02 * max(args.sample_n - n_pos_total, 0) / max(n_neg_total, 1))
    parts: dict[int, list[pd.DataFrame]] = {i: [] for i in code_to_id.values()}
    gt_parts: list[pd.DataFrame] = []
    smp_parts: list[pd.DataFrame] = []
    t0 = time.time()
    reader = pd.read_csv(raw, usecols=RAW_COLS, dtype=RAW_DTYPES, chunksize=args.chunksize)
    for i, ch in enumerate(reader):
        ch = ch.rename(columns=RENAME)[NEW_COLS]
        ch["ts"] = parse_ts(ch["ts"])
        ch["is_laundering"] = ch["is_laundering"].clip(0, 1).astype("int8")
        for code, bid in code_to_id.items():
            sel = ch[ch["from_bank"] == code]
            if len(sel):
                parts[bid].append(sel)
        gt_parts.append(ch[ch["ts"] >= cutoff])
        pos = ch["is_laundering"].to_numpy() == 1
        pick = pos | (rng.random(len(ch)) < neg_rate)
        smp_parts.append(ch[pick])
        log.info("pass2 chunk %d done (%.0fs, peak %.0f MB)", i, time.time() - t0, peak_rss_mb())
    del ch

    # ---------------- per-bank outputs ----------------
    banks_meta: dict[str, dict] = {}
    rows_md = []
    for code, bid in code_to_id.items():
        df = concat_parts(parts.pop(bid))
        train, test, capped = split_bank(df, args.train_cap, rng)
        bdir = out / "banks" / f"bank_{bid}"
        write_csv(train, bdir / "train.csv")
        write_csv(test, bdir / "test.csv")
        role = "bank" if bid <= args.n_banks else "rogue"
        meta = {
            "from_bank": code, "role": role, "dir": str(bdir),
            "rows_raw": int(len(df)), "laundering_raw": int(df["is_laundering"].sum()),
            "train_rows": int(len(train)), "train_laundering": int(train["is_laundering"].sum()),
            "test_rows": int(len(test)), "test_laundering": int(test["is_laundering"].sum()),
            "train_capped": capped,
            "time_min": str(df["ts"].min()), "time_max": str(df["ts"].max()),
            "train_time_max": str(train["ts"].max()), "test_time_min": str(test["ts"].min()),
        }
        banks_meta[str(bid)] = meta
        rows_md.append(
            f"| {bid} | {role} | {code} | {meta['rows_raw']:,} | {meta['laundering_raw']:,} "
            f"| 1 in {meta['rows_raw'] / max(meta['laundering_raw'], 1):,.0f} | {meta['train_rows']:,} "
            f"| {meta['train_laundering']:,} | {meta['test_rows']:,} | {meta['test_laundering']:,} "
            f"| {'yes' if capped else 'no'} |"
        )
        log.info("bank %d (%s %s): %s", bid, role, code, {k: v for k, v in meta.items() if 'time' not in k})
        del df, train, test

    # ---------------- global test + sample ----------------
    gt = stratified_sample(concat_parts(gt_parts), args.global_test_n, rng)
    del gt_parts
    write_csv(gt, out / "global_test.csv")
    gt_meta = {"rows": int(len(gt)), "laundering": int(gt["is_laundering"].sum()),
               "cutoff_ts": str(cutoff), "candidate_rows": n_cand, "stratified_by": "is_laundering"}
    log.info("global_test: %s", gt_meta)
    del gt

    smp = concat_parts(smp_parts)
    del smp_parts
    if len(smp) > args.sample_n:  # trim random negatives down to exactly sample_n, keep all positives
        pos = smp[smp["is_laundering"] == 1]
        neg = smp[smp["is_laundering"] == 0]
        k = max(args.sample_n - len(pos), 0)
        neg = neg.iloc[np.sort(rng.choice(len(neg), size=min(k, len(neg)), replace=False))]
        smp = pd.concat([pos, neg])
    smp = smp.sort_values("ts", kind="stable").reset_index(drop=True)
    write_csv(smp, out / "sample_50k.csv")
    smp_meta = {"rows": int(len(smp)), "laundering": int(smp["is_laundering"].sum())}
    log.info("sample_50k: %s", smp_meta)

    # ---------------- bank_map.json + summary ----------------
    elapsed = time.time() - t_start
    bank_map = {
        "source": raw.name, "seed": args.seed,
        "n_rows_total": n_total, "n_laundering_total": n_pos_total,
        "time_min": str(time_min), "time_max": str(time_max),
        "columns": NEW_COLS, "ts_format": TS_OUT_FORMAT,
        "read_hint": "pd.read_csv(p, dtype={'from_bank': str, 'to_bank': str, 'from_acct': str, 'to_acct': str}, parse_dates=['ts'])",
        "split": "per bank 80/20 by time; train capped at %d keeping all laundering rows" % args.train_cap,
        "banks": banks_meta, "global_test": gt_meta, "sample_50k": smp_meta,
        "partition_runtime_s": round(elapsed, 1), "partition_peak_rss_mb": round(peak_rss_mb(), 1),
    }
    (out / "bank_map.json").write_text(json.dumps(bank_map, indent=2))

    header = ("| bank_id | role | from_bank | rows_raw | laund_raw | laund_rate | train_rows | train_laund "
              "| test_rows | test_laund | train_capped |\n|---|---|---|---|---|---|---|---|---|---|---|")
    summary = "\n".join([
        f"Source `{raw.name}`: {n_total:,} rows, {n_pos_total:,} laundering (1 in {n_total / max(n_pos_total, 1):,.0f}), "
        f"{time_min} .. {time_max}.", "", header, *rows_md, "",
        f"`global_test.csv`: {gt_meta['rows']:,} rows, {gt_meta['laundering']:,} laundering, stratified by label "
        f"from {n_cand:,} rows with ts >= {cutoff} (last 20% of time, all banks).",
        f"`sample_50k.csv`: {smp_meta['rows']:,} rows, {smp_meta['laundering']:,} laundering (all of them).",
        f"Partition runtime {elapsed:,.0f}s, peak RSS {peak_rss_mb():,.0f} MB, seed {args.seed}.",
    ])
    (out / "partition_summary.md").write_text(summary + "\n")
    print("\n" + summary)


if __name__ == "__main__":
    main()
