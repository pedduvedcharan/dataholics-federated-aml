"""Rogue bank (addition #4): a participant that poisons its updates to hide laundering (FEDERATION owns).

    python -m fedaml.rogue --bank-id 5 --coordinator http://coordinator:8000 --attack scale --factor -20

Attacks (all SYNTHETIC, say so in the demo):
  scale  multiply the honest delta by ``--factor`` (negative = push the global model the wrong way),
         then clip to the coordinator's clip norm so the update looks size-legal;
  flip   train on inverted labels so the update teaches the model that laundering is normal;
  none   behave honestly (control).
It also lies about its data size (``--claim-factor``, default 10x) to buy
weight in FedAvg; the coordinator caps claims at 2x the median. Everything it
does is logged loudly so the regulator view can show the exclusion.
"""
from __future__ import annotations

import argparse
import logging

import numpy as np

from fedaml.bank import BankClient, add_common_args

log = logging.getLogger("fedaml.rogue")


class RogueBank(BankClient):
    name = "ROGUE bank"

    def local_delta(self, coef: np.ndarray, intercept: float) -> np.ndarray:
        a = self.args
        if a.attack == "flip":
            lc, li = self.train_local(coef, intercept, self.X, 1 - self.y)
            self.local_auc = -1.0
            vec = np.concatenate([lc - coef, [li - intercept]])
            log.warning("ATTACK flip: trained on inverted labels, |delta|=%.3f", np.linalg.norm(vec))
            return vec
        vec = super().local_delta(coef, intercept)
        if a.attack == "scale":
            vec = vec * a.factor
            log.warning("ATTACK scale: honest delta x %.1f -> |delta|=%.3f (clipped to %.2f before sending)",
                        a.factor, np.linalg.norm(vec), self.cfg["dp"]["clip_norm"])
        return vec

    def claimed_samples(self) -> int:
        n = int(len(self.y) * self.args.claim_factor)
        if self.args.claim_factor != 1:
            log.warning("ATTACK lie: claiming n_samples=%d (really %d)", n, len(self.y))
        return n


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description="fedaml rogue bank (model poisoning, synthetic)")
    add_common_args(p)
    p.add_argument("--attack", choices=["scale", "flip", "none"], default="scale")
    p.add_argument("--factor", type=float, default=-20.0, help="multiplier for --attack scale")
    p.add_argument("--claim-factor", type=float, default=10.0, help="inflate claimed n_samples by this factor")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    log.warning("ROGUE bank %d starting: attack=%s factor=%s claim_factor=%s", args.bank_id, args.attack, args.factor, args.claim_factor)
    RogueBank(args).run()


if __name__ == "__main__":
    main()
