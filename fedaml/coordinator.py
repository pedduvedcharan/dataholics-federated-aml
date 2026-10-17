"""Federated coordinator: Flask API + FedAvg round loop (FEDERATION owns, CONTRACTS section 4, 6, 7).

    python -m fedaml.coordinator --rounds 10 --banks 1,2,3,4,5 --dp on --sigma 0.8 --clip 1.0 --defense on

Endpoints on ``--port`` (default 8000, binds ``--host`` 0.0.0.0 for compose):
  GET  /config            run configuration the banks must obey (dp, clip, rounds, ...)
  GET  /global/<round>    {"round","coef","intercept","feature_names"} ; 404 until that round opens
  POST /update            one bank update, exact schema of CONTRACTS section 4 ; 409 for a wrong round
  GET  /status            same document as state/status.json plus live fields

Round loop (main thread): a round closes when every expected bank has posted or
``--round-timeout`` seconds passed since the first update of that round. Updates
pass ``defense.screen_updates``; accepted deltas are averaged with weights =
claimed n_samples capped at 2x the median claim; global += mean delta; the model
is scored with MODELS' pooled evaluator (each bank's test.csv featurized within
that bank, predictions pooled; CONTRACTS section 6); files are written atomically
(tmp + rename). The coordinator never sees raw rows: banks
clip and noise before ``egress.send``.
"""
from __future__ import annotations

import argparse
import copy
import datetime as _dt
import glob
import hashlib
import json
import logging
import os
import threading
import time

import numpy as np

from fedaml import defense, dp
from fedaml.features import FEATURE_NAMES, feature_names_sha256

log = logging.getLogger("fedaml.coordinator")

UPDATE_KEYS = {"bank_id", "round", "n_samples", "delta_coef", "delta_intercept", "clip_norm",
               "dp", "feature_names_sha256", "payload_sha256", "signature"}
N_FEATURES = len(FEATURE_NAMES)


# --------------------------------------------------------------------------- helpers
def canonical_json(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def payload_sha256(msg: dict) -> str:
    """sha256 over every field except payload_sha256 and signature (banks and coordinator agree)."""
    body = {k: v for k, v in msg.items() if k not in ("payload_sha256", "signature")}
    return hashlib.sha256(canonical_json(body)).hexdigest()


def atomic_write_json(obj, path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = f"{path}.tmp.{os.getpid()}"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=1)
    os.replace(tmp, path)


def model_json(rnd: int, coef: np.ndarray, intercept: np.ndarray, accepted: list[int],
               excluded: list[dict], extra: dict | None = None) -> dict:
    doc = {"round": rnd, "coef": [float(x) for x in coef], "intercept": [float(intercept[0])],
           "feature_names": list(FEATURE_NAMES), "feature_names_sha256": feature_names_sha256(),
           "accepted_banks": accepted, "excluded_banks": excluded}
    doc["sha256"] = hashlib.sha256(canonical_json({k: doc[k] for k in ("coef", "intercept", "feature_names")})).hexdigest()
    doc.update(extra or {})
    return doc


def validate_update(msg, expected_banks: list[int], current_round: int) -> tuple[int, str]:
    """Return (http_status, error) for a POSTed update; (200, "") when valid."""
    if not isinstance(msg, dict):
        return 400, "body must be a JSON object"
    if set(msg) != UPDATE_KEYS:
        return 400, f"keys must be exactly {sorted(UPDATE_KEYS)}; got {sorted(msg)}"
    if not isinstance(msg["bank_id"], int) or msg["bank_id"] not in expected_banks:
        return 400, f"unknown bank_id {msg['bank_id']!r}"
    if not isinstance(msg["round"], int):
        return 400, "round must be int"
    if msg["round"] != current_round:
        return 409, f"round {msg['round']} is not the current round {current_round}"
    if not isinstance(msg["n_samples"], int) or msg["n_samples"] <= 0:
        return 400, "n_samples must be a positive int"
    dc, di = msg["delta_coef"], msg["delta_intercept"]
    if not (isinstance(dc, list) and len(dc) == N_FEATURES and all(isinstance(v, (int, float)) for v in dc)):
        return 400, f"delta_coef must be a list of {N_FEATURES} numbers"
    if not (isinstance(di, list) and len(di) == 1 and isinstance(di[0], (int, float))):
        return 400, "delta_intercept must be a list of one number"
    if not all(np.isfinite(dc)) or not np.isfinite(di[0]):
        return 400, "non-finite values in delta"
    if not isinstance(msg["clip_norm"], (int, float)) or msg["clip_norm"] <= 0:
        return 400, "clip_norm must be a positive number"
    if not (isinstance(msg["dp"], dict) and set(msg["dp"]) == {"enabled", "sigma"}):
        return 400, 'dp must be {"enabled": bool, "sigma": number}'
    if msg["feature_names_sha256"] != feature_names_sha256():
        return 400, "feature_names_sha256 mismatch: bank runs a different feature vector"
    if msg["payload_sha256"] != payload_sha256(msg):
        return 400, "payload_sha256 does not match the payload"
    if msg["signature"] is not None and not isinstance(msg["signature"], str):
        return 400, "signature must be null or a string"
    return 200, ""


# --------------------------------------------------------------------------- coordinator
class Coordinator:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.lock = threading.Lock()
        self.banks = [int(b) for b in args.banks.split(",") if b.strip()]
        self.rounds = args.rounds
        self.dp_on = args.dp == "on"
        self.defense_on = args.defense == "on"
        self.round = 1
        self.done = False
        self.coef = np.zeros(N_FEATURES)
        self.intercept = np.zeros(1)
        self.models: dict[int, dict] = {1: model_json(1, self.coef, self.intercept, [], [])}
        self.updates: dict[int, dict] = {}
        self.first_update_at: float | None = None
        self.history: list[dict] = []
        self.started = time.time()
        self.round_times: list[float] = []
        self.rng = np.random.default_rng(args.seed)
        self.tests: dict = {}
        self.evaluate = None
        self._load_evaluator()
        for p in glob.glob(os.path.join(args.state_dir, "global_round_*.json")):
            os.remove(p)
        self.write_status()

    # ----- evaluation
    def _load_evaluator(self) -> None:
        """Featurize test.csv once for every expected and evaluation bank.

        Pooled AUC/AP (the headline) is computed over ``--eval-banks`` only (bank 1 is unlearnable
        with per-row features and would dominate the pool, MASTER 15:55); per-bank AUC is reported
        for every expected bank, including ones outside the pool.
        """
        from fedaml.baselines import evaluate_model_pooled, load_bank_tests
        self.eval_banks = [int(x) for x in self.args.eval_banks.split(",") if x.strip()]
        self.tests = {}
        for b in sorted(set(self.eval_banks) | set(self.banks)):
            try:
                X, y = load_bank_tests([b], data_dir=self.args.data_dir or None)[b]
                self.tests[b] = (X.astype(np.float64), y)
            except Exception as exc:  # noqa: BLE001
                log.warning("bank %s test.csv not loadable (%s); left out of the evaluation", b, exc)
        pool = {b: self.tests[b] for b in self.eval_banks if b in self.tests}
        if not pool:
            log.warning("no evaluation test sets loadable; global_auc will be null")
            self.evaluate = None
            return
        log.info("pooled evaluation set: banks %s, %d rows; per-bank AUC for banks %s", list(pool),
                 sum(len(y) for _, y in pool.values()), list(self.tests))
        self.evaluate = lambda path: evaluate_model_pooled(path, tests=pool)

    def _auc(self, coef: np.ndarray, intercept: np.ndarray, banks=None) -> float | None:
        """Pooled AUC of an arbitrary weight vector over ``banks`` (default: the evaluation pool)."""
        banks = [b for b in (banks or self.eval_banks) if b in self.tests]
        if not banks:
            return None
        from sklearn.metrics import roc_auc_score
        y = np.concatenate([self.tests[b][1] for b in banks])
        z = np.concatenate([self.tests[b][0] @ coef + float(intercept[0]) for b in banks])
        if y.min() == y.max():
            return None
        return round(float(roc_auc_score(y, 1.0 / (1.0 + np.exp(-np.clip(z, -500, 500))))), 6)

    # ----- documents
    def config(self) -> dict:
        a = self.args
        return {"rounds": self.rounds, "banks_expected": self.banks, "current_round": self.round, "done": self.done,
                "dp": {"enabled": self.dp_on, "sigma": a.sigma if self.dp_on else 0.0, "clip_norm": a.clip, "delta": a.delta,
                       "mode": a.dp_mode, "noise_added_by": ("bank" if a.dp_mode == "local" else "coordinator") if self.dp_on else "nobody"},
                "defense": {"enabled": self.defense_on, "tau": a.tau, "norm_ratio": a.norm_ratio, "weight_cap_factor": a.weight_cap},
                "round_timeout_s": a.round_timeout, "seed": a.seed, "feature_names": list(FEATURE_NAMES),
                "feature_names_sha256": feature_names_sha256(), "n_features": N_FEATURES}

    def status(self) -> dict:
        a = self.args
        eps = dp.epsilon_spent(a.sigma, len(self.history), a.delta) if self.dp_on else 0.0
        return {"round": len(self.history), "total_rounds": self.rounds,
                "dp": {"enabled": self.dp_on, "sigma": a.sigma if self.dp_on else 0.0, "clip_norm": a.clip,
                       "epsilon_spent": eps, "delta": a.delta, "mode": a.dp_mode,
                       "noise_added_by": ("bank" if a.dp_mode == "local" else "coordinator") if self.dp_on else "nobody",
                       "epsilon_note": "approximate; update-level (per bank per round) Gaussian mechanism composed over rounds, see fedaml/dp.py"},
                "defense": {"enabled": self.defense_on, "tau": a.tau, "norm_ratio": a.norm_ratio, "weight_cap_factor": a.weight_cap},
                "rounds": self.history, "banks_expected": self.banks, "eval_banks": self.eval_banks,
                "done": self.done, "current_round": self.round,
                "waiting_for": [b for b in self.banks if b not in self.updates] if not self.done else [],
                "seconds_per_round": round(float(np.mean(self.round_times)), 2) if self.round_times else None,
                "total_runtime_s": round(time.time() - self.started, 1), "tag": a.tag,
                "updated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")}

    def write_status(self) -> None:
        doc = self.status()
        atomic_write_json(doc, os.path.join(self.args.state_dir, "status.json"))
        if self.args.tag:
            atomic_write_json(doc, os.path.join(self.args.state_dir, f"status_{self.args.tag}.json"))

    # ----- API handlers (called under the Flask threads)
    def post_update(self, msg) -> tuple[dict, int]:
        with self.lock:
            if self.done:
                return {"accepted": False, "error": "training finished"}, 410
            code, err = validate_update(msg, self.banks, self.round)
            if code != 200:
                log.warning("rejected update from %s: %s", msg.get("bank_id") if isinstance(msg, dict) else "?", err)
                return {"accepted": False, "error": err, "current_round": self.round}, code
            if msg["bank_id"] in self.updates:
                log.info("bank %s re-posted round %d; replacing", msg["bank_id"], self.round)
            self.updates[msg["bank_id"]] = msg
            if self.first_update_at is None:
                self.first_update_at = time.time()
            log.info("round %d: update from bank %s (n_samples=%d, |delta|=%.4f) %d/%d received", self.round,
                     msg["bank_id"], msg["n_samples"], float(np.linalg.norm(msg["delta_coef"] + msg["delta_intercept"])),
                     len(self.updates), len(self.banks))
            return {"accepted": True, "round": self.round, "received": len(self.updates)}, 200

    def get_global(self, rnd: int) -> tuple[dict, int]:
        with self.lock:
            m = self.models.get(rnd)
            if m is None:
                return {"error": "round not open", "current_round": self.round, "done": self.done}, 404
            return {"round": rnd, "coef": m["coef"], "intercept": m["intercept"], "feature_names": m["feature_names"]}, 200

    # ----- round loop
    def round_ready(self) -> bool:
        if not self.updates:
            return False
        if all(b in self.updates for b in self.banks):
            return True
        return time.time() - self.first_update_at >= self.args.round_timeout

    def aggregate(self) -> None:
        a = self.args
        t0 = time.time()
        with self.lock:
            rnd, updates = self.round, dict(self.updates)
        deltas = {b: np.asarray(m["delta_coef"] + m["delta_intercept"], dtype=np.float64) for b, m in updates.items()}
        n_samples = {b: int(m["n_samples"]) for b, m in updates.items()}
        missing = [b for b in self.banks if b not in updates]
        noise_std = a.sigma * a.clip if (self.dp_on and a.dp_mode == "local") else 0.0
        accepted, excluded, scores = defense.screen_updates(deltas, a.clip, enabled=self.defense_on, tau=a.tau,
                                                            norm_ratio=a.norm_ratio, noise_std=noise_std)
        for b in missing:
            excluded.append({"bank_id": b, "reason": "no_update_before_timeout", "score": None})
        weights: dict[int, float] = {}
        if accepted:
            mean, weights = defense.weighted_mean({b: deltas[b] for b in accepted}, n_samples, a.weight_cap)
            if self.dp_on and a.dp_mode == "central":
                mean = dp.add_noise(mean, a.sigma, a.clip * max(weights.values()), self.rng)
            new_coef, new_int = self.coef + mean[:-1], self.intercept + mean[-1:]
        else:
            log.error("round %d: no accepted updates, global model unchanged", rnd)
            new_coef, new_int = self.coef.copy(), self.intercept.copy()
        local_auc = {str(b): self._auc(self.coef + deltas[b][:-1], self.intercept + deltas[b][-1:]) for b in updates}
        extra = {"n_samples_claimed": {str(b): n for b, n in n_samples.items()}, "weights": {str(b): w for b, w in weights.items()},
                 "update_sha256": {str(b): m["payload_sha256"] for b, m in updates.items()}, "defense_scores": {str(b): s for b, s in scores.items()},
                 "dp": {"enabled": self.dp_on, "sigma": a.sigma if self.dp_on else 0.0, "clip_norm": a.clip, "mode": a.dp_mode}}
        doc = model_json(rnd, new_coef, new_int, accepted, excluded, extra)
        path = os.path.join(a.state_dir, f"global_round_{rnd}.json")
        atomic_write_json(doc, path)
        metrics_ = {"auc": None, "ap": None, "per_bank": {}}
        if self.evaluate is not None:
            try:
                metrics_ = self.evaluate(path)
            except Exception as exc:  # noqa: BLE001
                log.error("evaluation failed: %s", exc)
        per_bank_auc = {str(b): self._auc(new_coef, new_int, banks=[b]) for b in sorted(self.tests)}
        entry = {"round": rnd, "accepted": accepted, "excluded": excluded,
                 "global_auc": None if metrics_["auc"] is None else round(float(metrics_["auc"]), 6),
                 "global_ap": None if metrics_["ap"] is None else round(float(metrics_["ap"]), 6),
                 "per_bank_auc": per_bank_auc, "local_model_auc": local_auc, "weights": extra["weights"],
                 "n_samples_claimed": extra["n_samples_claimed"], "defense_scores": extra["defense_scores"], "seconds": None}
        with self.lock:
            self.coef, self.intercept = new_coef, new_int
            self.history.append(entry)
            self.round_times.append(time.time() - t0 + (t0 - (self.first_update_at or t0)))
            entry["seconds"] = round(self.round_times[-1], 2)
            self.updates, self.first_update_at = {}, None
            self.round = rnd + 1
            self.models[self.round] = model_json(self.round, self.coef, self.intercept, accepted, excluded)
            if rnd >= self.rounds:
                self.done = True
                final = model_json(rnd, self.coef, self.intercept, accepted, excluded, {"total_rounds": self.rounds, "dp": extra["dp"]})
                atomic_write_json(final, os.path.join(a.state_dir, "global_final.json"))
                if a.tag:
                    atomic_write_json(final, os.path.join(a.state_dir, f"global_final_{a.tag}.json"))
            self.write_status()
        log.info("ROUND %d done: accepted=%s excluded=%s global_auc=%s global_ap=%s eps~%s",
                 rnd, accepted, [(e["bank_id"], e["reason"]) for e in excluded], entry["global_auc"], entry["global_ap"],
                 self.status()["dp"]["epsilon_spent"])

    def run(self) -> None:
        last_beat = time.time()
        while not self.done:
            time.sleep(0.5)
            with self.lock:
                ready = self.round_ready()
            if ready:
                self.aggregate()
            elif time.time() - last_beat > 30:
                last_beat = time.time()
                with self.lock:
                    log.info("round %d: waiting for banks %s", self.round, [b for b in self.banks if b not in self.updates])
        log.info("training finished after %d rounds in %.0f s; final model in %s/global_final.json; lingering %ds",
                 self.rounds, time.time() - self.started, self.args.state_dir, self.args.linger)
        time.sleep(self.args.linger)


# --------------------------------------------------------------------------- Flask
def create_app(coord: Coordinator):
    from flask import Flask, jsonify, request
    app = Flask("fedaml.coordinator")
    logging.getLogger("werkzeug").setLevel(logging.WARNING)

    @app.get("/config")
    def _config():
        with coord.lock:
            return jsonify(coord.config())

    @app.get("/global/<int:rnd>")
    def _global(rnd: int):
        doc, code = coord.get_global(rnd)
        return jsonify(doc), code

    @app.post("/update")
    def _update():
        doc, code = coord.post_update(request.get_json(force=True, silent=True))
        return jsonify(doc), code

    @app.get("/status")
    def _status():
        with coord.lock:
            return jsonify(coord.status())

    return app


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="fedaml coordinator (FedAvg + DP + rogue defense)")
    p.add_argument("--rounds", type=int, default=10)
    p.add_argument("--banks", default="1,2,3,4,5", help="comma-separated bank ids expected each round")
    p.add_argument("--dp", choices=["on", "off"], default="on")
    p.add_argument("--sigma", type=float, default=0.8, help="noise multiplier: noise std = sigma * clip")
    p.add_argument("--clip", type=float, default=1.0, help="L2 clip norm every bank applies to its delta")
    p.add_argument("--delta", type=float, default=1e-5, help="DP delta for the epsilon report")
    p.add_argument("--dp-mode", choices=["central", "local"], default=os.environ.get("DP_MODE", "central"),
                   help="central: coordinator noises the aggregate (default); local: each bank noises its delta")
    p.add_argument("--defense", choices=["on", "off"], default="on")
    p.add_argument("--tau", type=float, default=0.8, help="max cosine distance to the median delta (rogue ~1-2, honest <0.7 with the prox trainer)")
    p.add_argument("--norm-ratio", type=float, default=3.0, help="max norm as a multiple of the median norm")
    p.add_argument("--weight-cap", type=float, default=2.0, help="cap on claimed n_samples as a multiple of the median claim")
    p.add_argument("--round-timeout", type=float, default=120.0, help="seconds after the first update before closing a round")
    p.add_argument("--host", default=os.environ.get("HOST", "0.0.0.0"))
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--state-dir", default="state")
    p.add_argument("--data-dir", default=os.environ.get("FEDAML_DATA_DIR", ""), help="dir holding banks/bank_<id>/test.csv (default data/)")
    p.add_argument("--eval-banks", default=os.environ.get("EVAL_BANKS", "2,3,4"),
                   help="banks whose test.csv form the pooled evaluation set (bank 1 is unlearnable with per-row features)")
    p.add_argument("--tag", default="", help="also write state/global_final_<tag>.json and state/status_<tag>.json")
    p.add_argument("--linger", type=float, default=60.0, help="seconds to keep serving after the last round")
    p.add_argument("--seed", type=int, default=42)
    return p.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    np.random.seed(args.seed)
    coord = Coordinator(args)
    app = create_app(coord)
    srv = threading.Thread(target=lambda: app.run(host=args.host, port=args.port, threaded=True, use_reloader=False), daemon=True)
    srv.start()
    log.info("coordinator up on %s:%d  rounds=%d banks=%s dp=%s sigma=%s clip=%s defense=%s", args.host, args.port,
             args.rounds, coord.banks, args.dp, args.sigma, args.clip, args.defense)
    coord.run()


if __name__ == "__main__":
    main()
