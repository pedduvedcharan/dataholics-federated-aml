"""Feature engineering for the cross-bank AML model (CONTRACTS section 3).

Every other module (bank, coordinator, redteam, sar) imports this file. The rules:

* ``FEATURE_NAMES`` is a fixed, ordered list. Its sha256 travels with every
  model update so a coordinator can refuse updates built on a different vector.
* ``featurize(df)`` uses only the dataframe it is given. Account aggregates are
  counted inside that dataframe (one bank's shard), never across banks.
* No scalers, no target encoding, no learned statistics. Every feature is
  bounded or log-scaled so a single global logistic model is meaningful.

Entry point for a self-test on synthetic rows::

    python -m fedaml.features --selftest
    python -m fedaml.features --csv data/sample_50k.csv
"""
from __future__ import annotations

import argparse
import hashlib
import logging
import os
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger("fedaml.features")

# --------------------------------------------------------------------------- #
# Column contract (CONTRACTS section 2)
# --------------------------------------------------------------------------- #
CANON_COLUMNS = [
    "ts", "from_bank", "from_acct", "to_bank", "to_acct",
    "amt_recv", "cur_recv", "amt_paid", "cur_paid", "fmt", "is_laundering",
]

# Raw Kaggle header -> canonical name. Lets featurize() accept the raw CSV too.
RAW_TO_CANON = {
    "Timestamp": "ts",
    "From Bank": "from_bank",
    "Account": "from_acct",
    "To Bank": "to_bank",
    "Account.1": "to_acct",
    "Amount Received": "amt_recv",
    "Receiving Currency": "cur_recv",
    "Amount Paid": "amt_paid",
    "Payment Currency": "cur_paid",
    "Payment Format": "fmt",
    "Is Laundering": "is_laundering",
}

# Fixed vocabulary for the payment-format one-hot. Unknown formats -> all zeros.
FMT_VOCAB = ["ACH", "Credit Card", "Cheque", "Wire", "Reinvestment", "Bitcoin", "Cash"]


def _fmt_feature_name(fmt: str) -> str:
    return "fmt_" + fmt.replace(" ", "_")


FEATURE_NAMES: list[str] = (
    ["log_amt", "is_usd", "cur_mismatch", "same_bank", "round_amt",
     "hour_sin", "hour_cos", "dow_sin", "dow_cos"]
    + [_fmt_feature_name(f) for f in FMT_VOCAB]
    + ["snd_txn_cnt_log", "snd_uniq_rcv_log", "rcv_in_deg_log", "snd_amt_mean_log"]
)

N_FEATURES = len(FEATURE_NAMES)

# Where data/ lives. Override with FEDAML_DATA_DIR (containers mount ./data).
DATA_DIR = Path(os.environ.get("FEDAML_DATA_DIR", "data"))

# dtypes used whenever a bank CSV is read, so account ids never become ints.
CSV_DTYPES = {
    "from_bank": "string", "to_bank": "string",  # bank codes keep leading zeros ("011")
    "from_acct": "string", "to_acct": "string",
    "amt_recv": "float64", "amt_paid": "float64",
    "cur_recv": "string", "cur_paid": "string", "fmt": "string",
    "is_laundering": "int8",
}


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def feature_names_sha256() -> str:
    """sha256 over the newline-joined FEATURE_NAMES. Shipped in every update."""
    return hashlib.sha256("\n".join(FEATURE_NAMES).encode("utf-8")).hexdigest()


def canonicalize(df: pd.DataFrame) -> pd.DataFrame:
    """Rename raw Kaggle headers to canonical names if present; verify columns."""
    if any(c in df.columns for c in RAW_TO_CANON):
        df = df.rename(columns=RAW_TO_CANON)
    missing = [c for c in CANON_COLUMNS if c not in df.columns and c != "is_laundering"]
    if missing:
        raise ValueError(f"dataframe is missing columns {missing}")
    return df


def featurize(df: pd.DataFrame) -> np.ndarray:
    """Turn a transactions dataframe into a float32 matrix [n, N_FEATURES].

    Aggregates (sender counts, receiver in-degree, sender mean amount) are
    computed on ``df`` alone. Pass one bank's data and you get that bank's
    view; nothing here looks outside the frame.
    """
    df = canonicalize(df)
    n = len(df)
    out = np.zeros((n, N_FEATURES), dtype=np.float32)
    if n == 0:
        return out
    col = {name: i for i, name in enumerate(FEATURE_NAMES)}

    amt = pd.to_numeric(df["amt_paid"], errors="coerce").fillna(0.0).to_numpy(dtype=np.float64)
    amt = np.clip(amt, 0.0, None)
    cur_paid = df["cur_paid"].astype("string").fillna("")
    cur_recv = df["cur_recv"].astype("string").fillna("")
    from_bank = df["from_bank"].astype("string").fillna("").str.strip()
    to_bank = df["to_bank"].astype("string").fillna("").str.strip()

    out[:, col["log_amt"]] = np.log1p(amt)
    out[:, col["is_usd"]] = (cur_paid == "US Dollar").to_numpy(dtype=np.float32)
    out[:, col["cur_mismatch"]] = (cur_paid != cur_recv).to_numpy(dtype=np.float32)
    out[:, col["same_bank"]] = (from_bank == to_bank).to_numpy(dtype=np.float32)
    out[:, col["round_amt"]] = (np.abs(np.mod(amt, 100.0)) < 1e-6).astype(np.float32)

    ts = _parse_ts(df["ts"])
    hour = ts.dt.hour.fillna(0).to_numpy(dtype=np.float64)
    dow = ts.dt.dayofweek.fillna(0).to_numpy(dtype=np.float64)
    out[:, col["hour_sin"]] = np.sin(2 * np.pi * hour / 24.0)
    out[:, col["hour_cos"]] = np.cos(2 * np.pi * hour / 24.0)
    out[:, col["dow_sin"]] = np.sin(2 * np.pi * dow / 7.0)
    out[:, col["dow_cos"]] = np.cos(2 * np.pi * dow / 7.0)

    fmt = df["fmt"].astype("string").fillna("")
    for f in FMT_VOCAB:
        out[:, col[_fmt_feature_name(f)]] = (fmt == f).to_numpy(dtype=np.float32)

    # Account-level aggregates, strictly within this dataframe.
    snd_key = (from_bank + "|" + df["from_acct"].astype("string").fillna("")).astype(object)
    rcv_key = (to_bank + "|" + df["to_acct"].astype("string").fillna("")).astype(object)
    snd_cnt = snd_key.map(snd_key.value_counts()).to_numpy(dtype=np.float64)
    snd_uniq = snd_key.map(
        pd.DataFrame({"s": snd_key, "r": rcv_key}).groupby("s")["r"].nunique()
    ).to_numpy(dtype=np.float64)
    rcv_in = rcv_key.map(rcv_key.value_counts()).to_numpy(dtype=np.float64)
    snd_mean = snd_key.map(
        pd.Series(amt, index=df.index).groupby(snd_key).mean()
    ).to_numpy(dtype=np.float64)

    out[:, col["snd_txn_cnt_log"]] = np.log1p(snd_cnt)
    out[:, col["snd_uniq_rcv_log"]] = np.log1p(snd_uniq)
    out[:, col["rcv_in_deg_log"]] = np.log1p(rcv_in)
    out[:, col["snd_amt_mean_log"]] = np.log1p(snd_mean)

    # Belt and braces: the contract promises no NaN/inf, ever.
    np.nan_to_num(out, copy=False, nan=0.0, posinf=0.0, neginf=0.0)
    return out


def labels(df: pd.DataFrame) -> np.ndarray:
    """Laundering labels as int8 {0,1}."""
    df = canonicalize(df)
    return pd.to_numeric(df["is_laundering"], errors="coerce").fillna(0).to_numpy(dtype=np.int8)


def read_csv(path: str | Path, nrows: int | None = None) -> pd.DataFrame:
    """Read a partitioned bank CSV (or the raw Kaggle CSV) with safe dtypes."""
    head = pd.read_csv(path, nrows=0)
    canon_of = {c: RAW_TO_CANON.get(c, c) for c in head.columns}
    dtypes = {c: CSV_DTYPES[k] for c, k in canon_of.items() if k in CSV_DTYPES}
    df = pd.read_csv(path, dtype=dtypes, nrows=nrows)
    return canonicalize(df)


def load_bank(bank_id: int, split: str = "train", nrows: int | None = None,
              data_dir: str | Path | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Load ``data/banks/bank_<id>/<split>.csv`` and return ``(X, y)``."""
    base = Path(data_dir) if data_dir else DATA_DIR
    path = base / "banks" / f"bank_{bank_id}" / f"{split}.csv"
    df = read_csv(path, nrows=nrows)
    X = featurize(df)
    y = labels(df)
    log.info("bank %s %s: %d rows, %d laundering (%.4f%%)",
             bank_id, split, len(y), int(y.sum()), 100.0 * y.mean() if len(y) else 0.0)
    return X, y


def load_global_test(nrows: int | None = None,
                     data_dir: str | Path | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Load ``data/global_test.csv`` (regulator/coordinator only) -> ``(X, y)``."""
    base = Path(data_dir) if data_dir else DATA_DIR
    df = read_csv(base / "global_test.csv", nrows=nrows)
    return featurize(df), labels(df)


def contributions(X: np.ndarray, coef: np.ndarray) -> np.ndarray:
    """Per-feature logit contributions ``X * coef`` for a logistic model.

    Used by GENAI to name the top reasons a transaction was flagged.
    """
    return np.asarray(X, dtype=np.float64) * np.asarray(coef, dtype=np.float64)[None, :]


# --------------------------------------------------------------------------- #
# Synthetic data (until INFRA lands the real shards, and for unit tests)
# --------------------------------------------------------------------------- #
def make_synthetic(n: int = 1000, seed: int = 42, n_banks: int = 4,
                   laundering_rate: float = 0.02) -> pd.DataFrame:
    """A dataframe with the canonical columns and a weak but learnable signal."""
    rng = np.random.default_rng(seed)
    banks = np.arange(1, n_banks + 1)
    from_bank = rng.choice(banks, size=n)
    to_bank = np.where(rng.random(n) < 0.6, from_bank, rng.choice(banks, size=n))
    accts = [f"8{rng.integers(0, 10**8):08X}" for _ in range(max(20, n // 10))]
    from_acct = rng.choice(accts, size=n)
    to_acct = rng.choice(accts, size=n)
    is_laund = (rng.random(n) < laundering_rate).astype(np.int8)
    amt = np.exp(rng.normal(6.0, 1.5, size=n)).round(2)
    amt = np.where(is_laund == 1, (amt * 3).round(-2), amt)  # launderers: bigger, rounder
    currencies = np.array(["US Dollar", "Euro", "Yuan", "Bitcoin", "Rupee"])
    cur_paid = rng.choice(currencies, size=n, p=[0.7, 0.15, 0.1, 0.02, 0.03])
    cur_recv = np.where(rng.random(n) < 0.9, cur_paid, rng.choice(currencies, size=n))
    fmts = np.array(FMT_VOCAB + ["UNKNOWN_FMT"])
    p_fmt = np.array([0.25, 0.25, 0.15, 0.15, 0.1, 0.03, 0.05, 0.02])
    fmt = rng.choice(fmts, size=n, p=p_fmt)
    fmt = np.where(is_laund == 1, rng.choice(["ACH", "Wire", "Bitcoin"], size=n), fmt)
    start = pd.Timestamp("2022-09-01 00:00")
    ts = start + pd.to_timedelta(np.sort(rng.integers(0, 10 * 24 * 60, size=n)), unit="m")
    df = pd.DataFrame({
        "ts": ts.strftime("%Y/%m/%d %H:%M"),
        "from_bank": from_bank, "from_acct": from_acct,
        "to_bank": to_bank, "to_acct": to_acct,
        "amt_recv": amt, "cur_recv": cur_recv,
        "amt_paid": amt, "cur_paid": cur_paid,
        "fmt": fmt, "is_laundering": is_laund,
    })
    return df


def selftest(df: pd.DataFrame) -> dict:
    """Shape, determinism, finiteness, and within-frame aggregation checks."""
    X1 = featurize(df)
    X2 = featurize(df.copy())
    assert X1.shape == (len(df), N_FEATURES), X1.shape
    assert X1.dtype == np.float32, X1.dtype
    assert np.array_equal(X1, X2), "featurize is not deterministic"
    assert np.isfinite(X1).all(), "NaN/inf in features"
    # Aggregates depend only on the frame given: half the frame != whole frame.
    half = featurize(df.iloc[: len(df) // 2])
    idx = FEATURE_NAMES.index("snd_txn_cnt_log")
    assert (half[:, idx] <= X1[: len(half), idx] + 1e-6).all()
    y = labels(df)
    return {
        "rows": int(len(df)), "n_features": N_FEATURES,
        "laundering_rows": int(y.sum()),
        "feature_names_sha256": feature_names_sha256(),
        "col_min": X1.min(axis=0).round(3).tolist(),
        "col_max": X1.max(axis=0).round(3).tolist(),
    }


# --------------------------------------------------------------------------- #
# Internals
# --------------------------------------------------------------------------- #
TS_FORMATS = ("%Y-%m-%d %H:%M:%S",   # INFRA partition_data.py output
              "%Y/%m/%d %H:%M")      # raw Kaggle CSV


def _parse_ts(s: pd.Series) -> pd.Series:
    """Parse timestamps with the known fixed formats first, generic parser last."""
    for fmt in TS_FORMATS:
        try:
            return pd.to_datetime(s, format=fmt, errors="raise")
        except (ValueError, TypeError):
            continue
    return pd.to_datetime(s, errors="coerce", format="mixed")


def _main() -> None:
    parser = argparse.ArgumentParser(description="fedaml feature self-test")
    parser.add_argument("--csv", help="CSV to featurize (raw Kaggle or canonical)")
    parser.add_argument("--nrows", type=int, default=None)
    parser.add_argument("--selftest", action="store_true", help="use 1,000 synthetic rows")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    if args.csv:
        df = read_csv(args.csv, nrows=args.nrows)
    else:
        df = make_synthetic(1000, seed=args.seed)
    report = selftest(df)
    log.info("features OK: %s", {k: v for k, v in report.items() if not k.startswith("col_")})
    for name, lo, hi in zip(FEATURE_NAMES, report["col_min"], report["col_max"]):
        log.info("  %-18s min=%8.3f max=%8.3f", name, lo, hi)


if __name__ == "__main__":
    _main()
