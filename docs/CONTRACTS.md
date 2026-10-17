# Shared contracts (every agent obeys these; changes go through MASTER)

## 1. Directory layout (repo root = `~/fedaml` on the VM)
```
fedaml/                 Python package
  features.py           MODELS   — row -> feature vector, FEATURE_NAMES
  baselines.py          MODELS   — per-bank LogReg/RF/HGB comparison
  bank.py               FEDERATION — bank client (python -m fedaml.bank --bank-id 1)
  coordinator.py        FEDERATION — Flask server + FedAvg loop
  dp.py                 FEDERATION — clip + Gaussian noise + epsilon accounting
  defense.py            FEDERATION — rogue update detection
  rogue.py              FEDERATION — poisoned bank client
  redteam.py            REDTEAM  — membership inference, `redteam` table
  egress.py             AUDIT    — the ONLY function allowed to send data out of a bank
  dashboard/            AUDIT    — Flask app on :8050 reading state/ and logs/
  sar.py                GENAI    — SAR writer (LLM or template)
  llm/                  GENAI    — runtime wrapper
scripts/                INFRA    — setup_vm.sh, partition_data.py, footprint.sh
data/raw/HI-Small_Trans.csv            (gitignored)
data/banks/bank_<id>/train.csv, test.csv
data/global_test.csv                   held-out across all banks (coordinator/regulator only)
state/                  machine-readable outputs (gitignored except examples/)
logs/egress/bank_<id>.jsonl
docker-compose.yml, Dockerfile, README.md, STATUS.md
```

## 2. Data partition (INFRA produces, everyone consumes)
- Source: `HI-Small_Trans.csv`. Rename columns to: `ts, from_bank, from_acct, to_bank, to_acct, amt_recv, cur_recv, amt_paid, cur_paid, fmt, is_laundering`.
- Pick the **4 busiest `from_bank` values** → bank ids `1..4` (mapping saved in `data/bank_map.json`). Rogue bank = 5th busiest → `data/banks/bank_5/`.
- Each bank dir: 80/20 time-ordered split into `train.csv` / `test.csv` (earlier rows train). Cap train at 500,000 rows by random subsample **keeping all laundering rows**.
- `data/global_test.csv`: 200,000-row stratified sample from the last 20% of time across ALL banks.
- Laundering label column: `is_laundering` ∈ {0,1}.

## 3. Feature vector (MODELS owns `features.py`; FEDERATION, REDTEAM, GENAI import it)
`FEATURE_NAMES` is a fixed ordered list. `featurize(df) -> np.ndarray[n, len(FEATURE_NAMES)]`, float32. Only transforms that need **no cross-bank statistics**:
```
log_amt            log1p(amt_paid)
is_usd             cur_paid == "US Dollar"
cur_mismatch       cur_paid != cur_recv
same_bank          from_bank == to_bank
round_amt          amt_paid % 100 == 0
hour_sin, hour_cos, dow_sin, dow_cos
fmt_<X>            one-hot over FIXED vocab: ACH, Credit Card, Cheque, Wire, Reinvestment, Bitcoin, Cash  (unknown -> all zeros)
snd_txn_cnt_log    log1p(# txns by from_acct within this bank's own data)
snd_uniq_rcv_log   log1p(# distinct to_acct for from_acct, within bank)
rcv_in_deg_log     log1p(# txns to to_acct, within bank)
snd_amt_mean_log   log1p(mean amt_paid of from_acct, within bank)
```
No StandardScaler. All features are already bounded or log-scaled so one global logistic model is meaningful.

## 4. Model and update format (FEDERATION owns; REDTEAM, AUDIT, GENAI read)
- Global model = logistic regression: `coef` (len = n_features), `intercept` (1). Local training = `sklearn.linear_model.SGDClassifier(loss="log_loss", warm_start=True)` initialised from the global weights, `E` epochs of `partial_fit`, `class_weight="balanced"`.
- **Update** = local weights − global weights (delta), L2-clipped to `clip_norm`, Gaussian noise added when DP on.
- Message a bank POSTs (JSON) — this exact schema, nothing else:
```json
{"bank_id": 1, "round": 3, "n_samples": 412000,
 "delta_coef": [...], "delta_intercept": [0.01],
 "clip_norm": 1.0, "dp": {"enabled": true, "sigma": 0.8},
 "feature_names_sha256": "...", "payload_sha256": "...",
 "signature": null}
```
- Coordinator endpoints (Flask, port 8000): `GET /config`, `GET /global/<round>` → `{"round", "coef", "intercept", "feature_names"}`, `POST /update`, `GET /status`.
- Aggregation: weighted mean of accepted deltas by `n_samples`; new global = old + mean delta.
- Global model saved every round: `state/global_round_<r>.json` = `{"round","coef","intercept","feature_names","sha256","accepted_banks","excluded_banks"}`. Final: `state/global_final.json`.

## 5. Egress rule (AUDIT owns `egress.py`; FEDERATION must call it)
Banks send **only** via `egress.send(coordinator_url, payload: dict, bank_id, round)`. It:
1. Rejects (raises) if any key of the payload is in `FORBIDDEN_KEYS = {ts, from_acct, to_acct, amt_paid, amt_recv, cur_paid, cur_recv, fmt, is_laundering, rows, records, data}` or if any value is a list longer than `len(FEATURE_NAMES)+1`.
2. Appends to `logs/egress/bank_<id>.jsonl`:
`{"ts": iso, "bank_id", "round", "kind": "model_update", "bytes": N, "sha256", "keys": [...], "rows_shared": 0, "params_shared": n}`
3. POSTs and returns the response.

## 6. Status files (dashboard reads these; writers keep them valid JSON at all times, write to tmp then rename)
- `state/status.json` (coordinator): `{"round", "total_rounds", "dp": {"enabled","sigma","clip_norm","epsilon_spent","delta"}, "rounds": [{"round","accepted":[ids],"excluded":[{"bank_id","reason","score"}],"global_auc","global_ap","per_bank_auc":{id:auc}}], "banks_expected":[1,2,3,4,5]}`
- `state/redteam.json` (redteam): `{"attack":"loss_threshold|shadow", "dp_off": {"attack_acc","attack_auc","n"}, "dp_on": {...}, "model_auc_off", "model_auc_on"}`
- `state/baselines.json` (models): `{"per_bank": {id: {"logreg":{"auc","ap"},"rf":{...},"hgb":{...}}}, "federated": {"auc","ap"}, "centralized_logreg": {"auc","ap"}}`
- `state/footprint.json` (infra): `{"per_container_peak_rss_mb": {...}, "seconds_per_round", "total_runtime_s", "cpu_count":3, "arch":"s390x"}`
- `state/sar/<alert_id>.md` (genai) + `state/alerts.json` (genai builds from global model scores on `global_test.csv`): top-20 flagged chains.

## 7. CLI contract (what the demo script calls)
```
python -m fedaml.coordinator --rounds 10 --banks 1,2,3,4,5 --dp on --sigma 0.8 --clip 1.0 --defense on
python -m fedaml.bank --bank-id 1 --coordinator http://coordinator:8000 --epochs 1
python -m fedaml.rogue --bank-id 5 --coordinator http://coordinator:8000 --attack scale --factor -20
python -m fedaml.baselines --banks 1,2,3,4
python -m fedaml.redteam --model-off state/global_final_dpoff.json --model-on state/global_final_dpon.json
python -m fedaml.dashboard --port 8050
python -m fedaml.sar --alert-id <id> [--engine llm|template]
```
`docker compose up` brings up coordinator, bank1-4, rogue, dashboard. `attacker` and `genai` are run with `docker compose run`.

## 8. Logging and style
- Every module: `logging` at INFO with the module name; no prints in library code.
- `--seed 42` everywhere; results must be reproducible.
- Type hints, docstrings on public functions, no file > 300 lines without a reason.
