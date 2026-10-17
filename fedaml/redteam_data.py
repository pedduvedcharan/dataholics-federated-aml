"""Data assembly for the membership-inference red team (REDTEAM agent).

Builds exactly balanced member / non-member samples for two target
populations, plus shadow material from a second bank:

* ``laundering`` - laundering rows of the member banks' training sets vs unseen
                   laundering rows (the customers a leak actually hurts)
* ``all``        - any row of the member banks' training sets vs any unseen row
* ``laundering@global_test`` - footnote: non-members from the mixed-bank
                   hold-out instead, to expose distribution shift

Whole files are featurised before sampling so the within-bank account
aggregates (snd_txn_cnt_log, ...) match what the bank computed in training.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

log = logging.getLogger("fedaml.redteam")


@dataclass
class Population:
    """One balanced member/non-member sample (n members, n non-members)."""
    X_mem: np.ndarray
    y_mem: np.ndarray
    X_non: np.ndarray
    y_non: np.ndarray

    @property
    def n(self) -> int:
        return int(len(self.y_mem))


@dataclass
class AttackData:
    feature_names: list[str]
    pops: dict[str, Population]            # "all", "laundering"
    X_test: np.ndarray                      # member bank's test.csv, for model AUC
    y_test: np.ndarray
    shadow: Optional[dict] = None           # {"X_full","y_full", "pops": {...}} from the shadow bank
    X_global: Optional[np.ndarray] = None   # global_test.csv when present (secondary AUC)
    y_global: Optional[np.ndarray] = None
    meta: dict = field(default_factory=dict)


def featurize(df: pd.DataFrame) -> tuple[np.ndarray, list[str]]:
    """Call MODELS' featurize; returns float32 matrix and the feature order."""
    from fedaml.features import FEATURE_NAMES, featurize as _f  # MODELS owns this
    return _f(df).astype(np.float32), list(FEATURE_NAMES)


def _read(path: Path) -> pd.DataFrame:
    """Read a bank/global CSV with MODELS' safe dtypes (account ids stay strings)."""
    from fedaml.features import read_csv
    log.info("reading %s", path)
    return read_csv(path)


def _labels(df: pd.DataFrame) -> np.ndarray:
    from fedaml.features import labels
    return labels(df)


def _after_window(pool: pd.DataFrame, train: pd.DataFrame) -> np.ndarray:
    """Mask of pool rows dated strictly after the member bank's training window."""
    try:
        t_pool = pd.to_datetime(pool["ts"], errors="coerce")
        t_max = pd.to_datetime(train["ts"], errors="coerce").max()
        mask = (t_pool > t_max).to_numpy()
    except (KeyError, TypeError, ValueError):
        log.warning("no parsable ts column; non-members not time-filtered")
        return np.ones(len(pool), dtype=bool)
    if mask.sum() < 1000:
        log.warning("only %d pool rows after the training window; time filter dropped", mask.sum())
        return np.ones(len(pool), dtype=bool)
    return mask


def _balanced(X_m: np.ndarray, y_m: np.ndarray, X_p: np.ndarray, y_p: np.ndarray,
              m_idx: np.ndarray, p_idx: np.ndarray, n: int, rng: np.random.Generator) -> Population:
    k = int(min(n, len(m_idx), len(p_idx)))
    a = rng.choice(m_idx, k, replace=False)
    b = rng.choice(p_idx, k, replace=False)
    return Population(X_m[a], y_m[a], X_p[b], y_p[b])


def _populations(X_m, y_m, X_p, y_p, pool_mask: np.ndarray, n: int, rng) -> dict[str, Population]:
    all_m, all_p = np.arange(len(y_m)), np.flatnonzero(pool_mask)
    pos_m, pos_p = np.flatnonzero(y_m == 1), np.flatnonzero((y_p == 1) & pool_mask)
    pops = {"all": _balanced(X_m, y_m, X_p, y_p, all_m, all_p, n, rng)}
    if len(pos_m) >= 20 and len(pos_p) >= 20:
        pops["laundering"] = _balanced(X_m, y_m, X_p, y_p, pos_m, pos_p, n, rng)
    else:
        log.warning("too few laundering rows for the laundering target (%d members, %d non-members)",
                    len(pos_m), len(pos_p))
    return pops


def _bank_frames(d: Path, bank: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, pd.Series]:
    """One bank's train/test, featurised jointly; also train-alone features and train timestamps."""
    bdir = d / "banks" / f"bank_{bank}"
    train, test = _read(bdir / "train.csv"), _read(bdir / "test.csv")
    X_both, _ = featurize(pd.concat([train, test], ignore_index=True))
    X_tr_alone, _ = featurize(train)      # exactly what the bank fed its local training
    return (X_both[: len(train)], _labels(train), X_both[len(train):], _labels(test), X_tr_alone, train["ts"])


def load_attack_data(data_dir: str, member_banks: list[int], n: int, seed: int,
                     shadow_bank: Optional[int] = None) -> AttackData:
    """Assemble attack data.

    Members come from the member banks' ``train.csv`` files.  Primary
    non-members are the same banks' later ``test.csv`` rows (same banks, later
    time, featurised together with train so account aggregates are
    consistent).  When ``global_test.csv`` exists, a second laundering-row
    population with non-members from the mixed-bank hold-out dated after the
    training window is built as the distribution-shift footnote
    (``"laundering@global_test"``).  Model AUC is measured on the member
    banks' pooled test files (CONTRACTS §4 pooled per-bank evaluation) and,
    when present, on global_test too.
    """
    d = Path(data_dir)
    rng = np.random.default_rng(seed)
    parts = [_bank_frames(d, b) for b in member_banks]
    X_tr = np.vstack([p[0] for p in parts]); y_tr = np.concatenate([p[1] for p in parts])
    X_te = np.vstack([p[2] for p in parts]); y_te = np.concatenate([p[3] for p in parts])
    X_tr_alone = np.vstack([p[4] for p in parts])
    names = featurize(pd.DataFrame(columns=["ts", "from_bank", "from_acct", "to_bank", "to_acct", "amt_recv",
                                            "cur_recv", "amt_paid", "cur_paid", "fmt", "is_laundering"]))[1]
    pops = _populations(X_tr, y_tr, X_te, y_te, np.ones(len(y_te), dtype=bool), n, rng)
    meta = {"member_banks": list(member_banks),
            "nonmembers": f"banks {member_banks} test.csv (same banks, later time)",
            "train_rows": int(len(y_tr)), "train_laundering_rows": int((y_tr == 1).sum()),
            "test_rows": int(len(y_te)), "test_laundering_rows": int((y_te == 1).sum())}
    data = AttackData(names, pops, X_te, y_te, meta=meta)

    gpath = d / "global_test.csv"
    if gpath.exists():
        gtest = _read(gpath)
        X_g, _ = featurize(gtest)
        y_g = _labels(gtest)
        train_ts = pd.DataFrame({"ts": pd.concat([p[5] for p in parts], ignore_index=True)})
        mask = _after_window(gtest, train_ts)
        pos_m, pos_p = np.flatnonzero(y_tr == 1), np.flatnonzero((y_g == 1) & mask)
        if len(pos_m) >= 20 and len(pos_p) >= 20:
            pops["laundering@global_test"] = _balanced(X_tr_alone, y_tr, X_g, y_g, pos_m, pos_p, n, rng)
        data.X_global, data.y_global = X_g, y_g
        meta["global_test_rows"] = int(len(gtest))
    else:
        log.warning("%s not found; no distribution-shift footnote, no global AUC", gpath)
    meta["n_per_class"] = {k: p.n for k, p in pops.items()}

    if shadow_bank is not None:
        sdir = d / "banks" / f"bank_{shadow_bank}"
        if (sdir / "train.csv").exists() and (sdir / "test.csv").exists():
            Xs_tr, ys_tr, Xs_te, ys_te, _, _ = _bank_frames(d, shadow_bank)
            data.shadow = {"X_full": Xs_tr, "y_full": ys_tr,
                           "pops": _populations(Xs_tr, ys_tr, Xs_te, ys_te, np.ones(len(ys_te), dtype=bool), n, rng)}
            meta["shadow_bank"] = shadow_bank
        else:
            log.warning("shadow bank %s not found under %s; shadow attack unavailable", shadow_bank, sdir)
    return data
