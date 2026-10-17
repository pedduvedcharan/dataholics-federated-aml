# FEDERATION agent — bank client, coordinator, FedAvg, DP, rogue bank and its defense

## Goal
The core of the project. Five bank containers and one coordinator run federated averaging over HTTP on the VM; differential privacy is a flag; a rogue bank is detected and excluded. Every round's metrics land in `state/status.json`.

## You own
`fedaml/bank.py`, `fedaml/coordinator.py`, `fedaml/dp.py`, `fedaml/defense.py`, `fedaml/rogue.py`.
You consume `fedaml.features` (MODELS) and `fedaml.egress.send` (AUDIT). Until those exist, stub them locally but never commit the stubs.

## Tasks, in order
1. **Coordinator MVP** (by 15:00). Flask on :8000. In-memory state: current round, global `coef`/`intercept` (zeros init), config. `GET /config` (rounds, banks expected, dp, clip), `GET /global/<round>`, `POST /update` (validate schema from CONTRACTS §4, store), `GET /status`. A loop thread: when all expected non-excluded banks for the round have posted, or 120 s pass, aggregate (weighted mean of deltas by n_samples), update global, evaluate on `data/global_test.csv` via MODELS' evaluator, write `state/global_round_<r>.json` and `state/status.json` (tmp + rename), advance round. After the last round write `state/global_final.json`.
2. **Bank client MVP** (by 15:00). `python -m fedaml.bank --bank-id 1 --coordinator URL --epochs 1`. Loop: fetch global for the round, build `SGDClassifier(loss="log_loss", warm_start=True, class_weight="balanced", random_state=seed)`, set `coef_`/`intercept_`/`classes_`, `partial_fit` E epochs over the bank's train set in minibatches of 4096, compute delta, clip, (noise), build the exact message, send via `egress.send`, wait for next round. Log local test AUC each round.
3. **Prove 2-bank FedAvg** on the VM with two terminals before touching Docker. Global AUC must rise across rounds and exceed each bank's own logreg baseline on `global_test.csv`. Paste numbers in STATUS.md.
4. **dp.py.** `clip(delta, clip_norm)`, `add_noise(delta, sigma, clip_norm, rng)` (Gaussian with std `sigma*clip_norm`), and `epsilon_spent(sigma, rounds, delta=1e-5)` using the simple Gaussian-mechanism composition bound (document the formula in a docstring and label it approximate). Coordinator reports `epsilon_spent` in status.json. Banks apply clip + noise **before** egress, so the coordinator never sees the raw delta.
5. **rogue.py** (addition #4). Same as bank.py but `--attack scale --factor -20` multiplies its delta by the factor (model-poisoning to push laundering scores down), and `--attack flip` trains on flipped labels. Logs what it is doing loudly.
6. **defense.py.** On each round's set of deltas: (a) hard reject if `||delta|| > 1.5 * clip_norm` (should be impossible for honest banks), (b) compute the coordinate-wise median delta; score each bank by cosine distance to the median; exclude any bank with distance > `tau` (start 0.5) and any bank whose norm is > 3× the median norm. Record `{"bank_id","reason","score"}` in `excluded`. `--defense off` disables (b) so the demo can show the AUC drop.
7. **Two final runs for REDTEAM:** `state/global_final_dpoff.json` and `state/global_final_dpon.json` (same seed, same rounds). Also keep the "rogue, defense off" and "rogue, defense on" status files as `state/status_rogue_off.json` / `state/status_rogue_on.json` for the dashboard and README.
8. **Containerise.** Each service is the same image with a different command; the coordinator is reachable as `http://coordinator:8000` on the compose network. Hand MASTER the exact commands for compose.

## Pitfalls
- `SGDClassifier` needs `classes_=[0,1]` set before `partial_fit` with warm weights; set `coef_` shape `(1, n_features)`.
- Weighted averaging by `n_samples`: the rogue bank can lie about `n_samples`; cap the weight any bank can claim at 2× the median `n_samples` (say so in the README).
- Keep rounds short: 1 local epoch over ≤500k rows is roughly a minute per bank on this box. Ten rounds total is enough.
- Write JSON atomically; the dashboard polls these files.

## Done when
All eight tasks have a command in STATUS.md that reproduces them on the VM, and status.json for a 5-bank run with rogue + defense on shows bank 5 excluded and global AUC above every single-bank baseline.
