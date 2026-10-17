# P4 — Federation (coordinator, banks, DP, rogue bank and defense)

**Agent brief you drive:** `agents/03-FEDERATION.md`. This is the biggest and most central piece. Start with the simplest possible working loop and only then add privacy and defense.

## Your deliverables
`fedaml/coordinator.py`, `fedaml/bank.py`, `fedaml/dp.py`, `fedaml/defense.py`, `fedaml/rogue.py`, `state/status.json`, `state/global_final.json`, `state/global_final_dpoff.json`, `state/global_final_dpon.json`, `state/status_rogue_off.json`, `state/status_rogue_on.json`.

## Hour by hour
- **12:00–13:30** Coordinator MVP (Flask, endpoints in CONTRACTS §4, in-memory round loop, weighted FedAvg of deltas, atomic JSON writes). Bank client MVP (SGDClassifier warm-started from the global weights, delta, clip, send). Stub `egress.send` locally until P5 ships it, and stub `features` until P3 ships it. Do not commit stubs.
- **13:30–15:00** Run 2 banks + coordinator in three terminals on the VM with real data. Global AUC must rise over rounds and beat each bank's own logreg (P3's table). Paste the per-round numbers in STATUS.md. Switch to the real `egress.send` the moment P5 pushes it.
- **15:00–16:00** `dp.py`: clip, Gaussian noise, approximate epsilon accounting, reported in status.json. Run dp-on and dp-off with the same seed and save both final models for P6.
- **16:00–17:30** `rogue.py` (scaled or label-flipped updates) and `defense.py` (norm check, cosine distance to the coordinate-wise median, exclusion with reasons, `--defense off` switch, weight cap on claimed n_samples). Produce the two status files (defense off vs on). Paste "defense off AUC / defense on AUC / rounds excluded" in STATUS.md.
- **17:30–20:00** Give P1 the exact container commands; help wire compose; fix anything that only shows up in containers (hostnames, volumes, timing).
- **20:00–23:00** Demo rehearsal support: a clean 10-round run with 5 banks must complete in under 15 minutes. Tune epochs and row caps if not.
- **23:00 onward** On call for the video run. Then, only if P1 says everything is green: stretch (Paillier via `phe` on the delta vectors, or ML-DSA signatures via `dilithium-py`).

## Done when
Every acceptance check for FEDERATION in `agents/00-MASTER.md` passes on the VM, with commands in STATUS.md.
