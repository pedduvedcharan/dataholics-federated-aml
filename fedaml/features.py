"""LOCAL STUB of MODELS' features.py (CONTRACTS section 3). NOT COMMITTED. Replaced when MODELS pushes."""
from __future__ import annotations

import hashlib
import json
import os

import numpy as np
import pandas as pd

FMT_VOCAB = ["ACH", "Credit Card", "Cheque", "Wire", "Reinvestment", "Bitcoin", "Cash"]
FEATURE_NAMES: list[str] = (
    ["log_amt", "is_usd", "cur_mismatch", "same_bank", "round_amt",
     "hour_sin", "hour_cos", "dow_sin", "dow_cos"]
    + [f"fmt_{f}" for f in FMT_VOCAB]
    + ["snd_txn_cnt_log", "snd_uniq_rcv_log", "rcv_in_deg_log", "snd_amt_mean_log"]
)
DATA_DIR = os.environ.get("FEDAML_DATA_DIR", "data")


def feature_names_sha256() -> str:
    return hashlib.sha256(",".join(FEATURE_NAMES).encode()).hexdigest()


def featurize(df: pd.DataFrame) -> np.ndarray:
    ts = pd.to_datetime(df["ts"], errors="coerce")
    hour = ts.dt.hour.fillna(0).to_numpy()
    dow = ts.dt.dayofweek.fillna(0).to_numpy()
    amt = df["amt_paid"].astype(float).to_numpy()
    cols = [
        np.log1p(np.maximum(amt, 0)),
        (df["cur_paid"] == "US Dollar").to_numpy(float),
        (df["cur_paid"] != df["cur_recv"]).to_numpy(float),
        (df["from_bank"] == df["to_bank"]).to_numpy(float),
        (np.mod(amt, 100) == 0).astype(float),
        np.sin(2 * np.pi * hour / 24), np.cos(2 * np.pi * hour / 24),
        np.sin(2 * np.pi * dow / 7), np.cos(2 * np.pi * dow / 7),
    ]
    for f in FMT_VOCAB:
        cols.append((df["fmt"] == f).to_numpy(float))
    snd = df["from_acct"].astype(str)
    rcv = df["to_acct"].astype(str)
    cols.append(np.log1p(snd.map(snd.value_counts()).to_numpy(float)))
    cols.append(np.log1p(snd.map(df.groupby(snd)["to_acct"].nunique()).to_numpy(float)))
    cols.append(np.log1p(rcv.map(rcv.value_counts()).to_numpy(float)))
    cols.append(np.log1p(snd.map(df.groupby(snd)["amt_paid"].mean()).to_numpy(float)))
    X = np.column_stack(cols).astype(np.float32)
    return np.nan_to_num(X)


def load_bank(bank_id: int, split: str = "train", data_dir: str | None = None):
    path = os.path.join(data_dir or DATA_DIR, "banks", f"bank_{bank_id}", f"{split}.csv")
    df = pd.read_csv(path)
    return featurize(df), df["is_laundering"].astype(int).to_numpy()


def load_global_test(data_dir: str | None = None):
    df = pd.read_csv(os.path.join(data_dir or DATA_DIR, "global_test.csv"))
    return featurize(df), df["is_laundering"].astype(int).to_numpy()


def evaluate_model_json(path: str, test_csv: str | None = None) -> dict:
    from sklearn.metrics import average_precision_score, roc_auc_score
    with open(path) as f:
        m = json.load(f)
    df = pd.read_csv(test_csv or os.path.join(DATA_DIR, "global_test.csv"))
    X, y = featurize(df), df["is_laundering"].astype(int).to_numpy()
    z = X @ np.asarray(m["coef"], float) + float(m["intercept"][0])
    p = 1 / (1 + np.exp(-z))
    return {"auc": float(roc_auc_score(y, p)), "ap": float(average_precision_score(y, p))}
