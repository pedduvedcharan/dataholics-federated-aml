"""Data assembly for the membership-inference red team (REDTEAM agent).

Builds exactly balanced member / non-member samples for two target
populations, plus shadow material from a second bank:

* ``all``        - any row of bank 1's training set vs any unseen row
* ``laundering`` - laundering rows of bank 1's training set vs unseen
                   laundering rows (the customers a leak actually hurts)

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
    X_test: np.ndarray                      # full global_test, for model AUC
    y_test: np.ndarray
    shadow: Optional[dict] = None           # {"X_full","y_full", "pops": {...}} from the shadow bank
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


def load_attack_data(data_dir: str, member_bank: int, n: int, seed: int,
                     nonmember_source: str = "global_test",
                     shadow_bank: Optional[int] = 2) -> AttackData:
    """Assemble attack data.

    Members come from ``banks/bank_<member_bank>/train.csv``.  Non-members are
    rows the model never trained on, either from ``global_test.csv`` dated after
    the member bank's training window (default, the regulator's hold-out) or
    from the member bank's own ``test.csv`` (``bank_test``: same bank, later
    time, featurised together with train so aggregates are consistent; the
    cleaner control for distribution shift).
    """
    d = Path(data_dir)
    rng = np.random.default_rng(seed)
    train = _read(d / "banks" / f"bank_{member_bank}" / "train.csv")
    gtest = _read(d / "global_test.csv")
    X_g, names = featurize(gtest)
    y_g = _labels(gtest)

    if nonmember_source == "bank_test":
        btest = _read(d / "banks" / f"bank_{member_bank}" / "test.csv")
        X_both, _ = featurize(pd.concat([train, btest], ignore_index=True))
        X_tr, X_pool = X_both[: len(train)], X_both[len(train):]
        y_tr, y_pool = _labels(train), _labels(btest)
        pool_mask = np.ones(len(btest), dtype=bool)
    else:
        X_tr, _ = featurize(train)
        y_tr, X_pool, y_pool = _labels(train), X_g, y_g
        pool_mask = _after_window(gtest, train)

    pops = _populations(X_tr, y_tr, X_pool, y_pool, pool_mask, n, rng)
    meta = {"member_bank": member_bank, "nonmember_source": nonmember_source,
            "train_rows": int(len(train)), "train_laundering_rows": int((y_tr == 1).sum()),
            "global_test_rows": int(len(gtest)), "n_per_class": {k: p.n for k, p in pops.items()}}
    data = AttackData(names, pops, X_g, y_g, meta=meta)

    if shadow_bank is not None:
        sdir = d / "banks" / f"bank_{shadow_bank}"
        if (sdir / "train.csv").exists() and (sdir / "test.csv").exists():
            s_tr, s_te = _read(sdir / "train.csv"), _read(sdir / "test.csv")
            Xs, _ = featurize(pd.concat([s_tr, s_te], ignore_index=True))
            ys_tr, ys_te = _labels(s_tr), _labels(s_te)
            data.shadow = {"X_full": Xs[: len(s_tr)], "y_full": ys_tr,
                           "pops": _populations(Xs[: len(s_tr)], ys_tr, Xs[len(s_tr):], ys_te,
                                                np.ones(len(s_te), dtype=bool), n, rng)}
            meta["shadow_bank"] = shadow_bank
        else:
            log.warning("shadow bank %s not found under %s; shadow attack unavailable", shadow_bank, sdir)
    return data
