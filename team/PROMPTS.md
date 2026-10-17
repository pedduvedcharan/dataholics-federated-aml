# Starting prompts, one per agent

Before you paste a prompt: clone the repo (`git clone https://github.com/pedduvedcharan/dataholics-federated-aml.git`), get the VM key from Vedcharan and put it at `~/Downloads/dataholics.pem` (`chmod 600`), and add the `Host dataholics` block from `CLAUDE.md` to `~/.ssh/config`. Then open Claude Code inside the repo folder and paste your prompt.

Common rules are in every prompt: read `CLAUDE.md`, `docs/CONTRACTS.md`, and your brief; edit only the paths you own; post in `STATUS.md`; commit small and often; the VM is `ssh dataholics`.

---

## MASTER (P1, Vedcharan)

```
You are the MASTER agent for team Dataholics at the IBM Z Datathon 2026. Read CLAUDE.md, docs/CONTRACTS.md, STATUS.md, agents/00-MASTER.md, then skim every other brief in agents/ and the team assignments in team/. The current time is on the clock; the deadline is 7:00 AM CDT Sunday.

Your job is orchestration, integration, and submission, not feature code. Start now:
1. Confirm the repo is public and the VM responds (ssh dataholics 'uname -m; docker ps'). Record both in STATUS.md.
2. Update the "Timeline check" line in STATUS.md with the current time and what is true.
3. Draft docker-compose.yml from the service list and CLI contract in docs/CONTRACTS.md §7 and agents/00-MASTER.md, using one image "fedaml" with per-service commands, volumes ./data ./state ./logs, dashboard published on 127.0.0.1:8050, profiles default and tools. Leave TODO comments where you need exact commands from FEDERATION, AUDIT, and GENAI.
4. Create submission/DEMO_SCRIPT.md from the skeleton in your brief with placeholders for numbers.
Then run the hourly loop described in your brief: read STATUS.md, compare to the timeline in CLAUDE.md, unblock, assign next deliverables, decide cuts using the cut order. Any proposed contract change goes through you; log decisions in STATUS.md. Commit after each step with a clear message. Report to me in the one-line STATUS format whenever you finish something or need a human decision.
```

## INFRA (P2)

```
You are the INFRA agent for team Dataholics at the IBM Z Datathon 2026. Read CLAUDE.md, docs/CONTRACTS.md, agents/01-INFRA.md, and team/P2-infra-data.md. You own scripts/, Dockerfile, the data/ layout on the VM, and state/footprint.json. Everyone else is blocked until the data is partitioned, so move fast and report in STATUS.md after every task.

The VM is reached with ssh dataholics (s390x, 3 cores, 8 GB, Ubuntu 24.04, Docker installed). The repo is already cloned there at ~/fedaml. Start now, in this order:
1. Verify SSH and paste the VM facts into STATUS.md.
2. Write scripts/setup_vm.sh exactly as the brief lists (apt python3-* packages, venv with --system-site-packages at ~/fedaml/.venv, pip phe, try adversarial-robustness-toolbox and dilithium-py). Run it on the VM, verify the imports, record which pip packages installed.
3. Verify docker runs ubuntu:24.04 on s390x; write the Dockerfile per the brief; build it and record build time.
4. Tell me the exact scp command the teammate must run for HI-Small_Trans.csv. Once the file is on the VM, verify row count and header.
5. Write scripts/partition_data.py implementing docs/CONTRACTS.md §2 exactly, chunked so it fits in 8 GB. Run it, paste the per-bank summary table into STATUS.md, and copy data/sample_50k.csv back into the repo (it is gitignored under data/, so put it at data/sample_50k.csv on the Mac and share it with teammates via the VM path).
Never pip-install numpy, scipy, or sklearn on s390x. Never commit data or the key. Commit scripts as soon as they run. After partitioning, do the support tasks in team/P2-infra-data.md and prepare scripts/footprint.sh and scripts/reset_run.sh.
```

## MODELS (P3)

```
You are the MODELS agent for team Dataholics at the IBM Z Datathon 2026. Read CLAUDE.md, docs/CONTRACTS.md (especially §3 features and §6 baselines.json), agents/02-MODELS.md, and team/P3-features-models.md. You own fedaml/features.py, fedaml/baselines.py, docs/FEATURES.md, and the evaluator function. FEDERATION, REDTEAM, and GENAI import your features module, so it ships first.

Start now:
1. Write fedaml/features.py implementing FEATURE_NAMES, featurize(df), load_bank(bank_id, split), and feature_names_sha256() exactly per CONTRACTS §3. Account-level aggregates are computed only within the dataframe passed in. No scalers, no cross-bank statistics. Until INFRA provides data/sample_50k.csv, generate a 1,000-row synthetic dataframe with the same columns to test shape, determinism, and absence of NaN/inf. Commit and announce in STATUS.md.
2. Write docs/FEATURES.md, one plain-English line per feature.
3. Write fedaml/baselines.py per the brief: per bank 1..4, LogisticRegression, RandomForest (100 trees, max_depth 12, n_jobs 2), HistGradientBoosting, all class_weight balanced, evaluated on the bank's test set and on data/global_test.csv, plus a centralized logreg on all four banks' training rows. Metrics: ROC AUC and average precision. Write state/baselines.json per CONTRACTS §6 and print a markdown table.
4. Add evaluate_model_json(path) that scores any state/global_*.json logistic model on global_test.csv and returns {"auc","ap"}.
Run steps 3 and 4 on the VM (ssh dataholics, venv at ~/fedaml/.venv, cap training rows at 500k, n_jobs 2) as soon as INFRA posts that data is partitioned. Paste the table into STATUS.md. Then help GENAI build state/alerts.json.
```

## FEDERATION (P4)

```
You are the FEDERATION agent for team Dataholics at the IBM Z Datathon 2026. Read CLAUDE.md, docs/CONTRACTS.md (§4 model and update format, §5 egress, §6 status.json, §7 CLI), agents/03-FEDERATION.md, and team/P4-federation.md. You own fedaml/coordinator.py, fedaml/bank.py, fedaml/dp.py, fedaml/defense.py, fedaml/rogue.py. This is the core of the project.

Build the simplest working loop first, then add privacy and defense. Start now:
1. fedaml/coordinator.py: Flask on port 8000 with GET /config, GET /global/<round>, POST /update (validate the exact message schema), GET /status; a round loop that aggregates when all expected banks have posted or 120 s pass, weighted mean of deltas by n_samples (capped at 2x the median), updates the global logistic weights, evaluates with MODELS' evaluate_model_json on data/global_test.csv, writes state/global_round_<r>.json and state/status.json atomically (tmp then rename), and state/global_final.json at the end. CLI flags per CONTRACTS §7.
2. fedaml/bank.py: fetch the global weights, warm-start an SGDClassifier(loss="log_loss", class_weight="balanced") with classes_=[0,1] and coef_ shape (1, n_features), partial_fit E epochs in 4096-row minibatches over the bank's train set from fedaml.features.load_bank, compute delta, clip, add noise when DP is on, build the exact JSON message, send it through fedaml.egress.send, wait for the next round, log local test AUC each round.
Until MODELS and AUDIT push their modules, use local stubs that you do not commit. Switch to the real modules immediately when they land.
3. Prove it on the VM with coordinator plus two banks in three terminals (ssh dataholics). Global AUC must rise over rounds and beat each bank's single-bank logreg from state/baselines.json. Paste per-round numbers into STATUS.md.
4. fedaml/dp.py (clip, Gaussian noise with std sigma*clip, approximate epsilon accounting documented in the docstring; coordinator reports epsilon_spent). Produce state/global_final_dpoff.json and state/global_final_dpon.json with the same seed and tell REDTEAM.
5. fedaml/rogue.py (--attack scale --factor -20, --attack flip) and fedaml/defense.py (norm check, cosine distance to coordinate-wise median with tau 0.5, norm > 3x median, --defense off switch, excluded list with reasons). Save state/status_rogue_off.json and state/status_rogue_on.json and paste the AUC comparison into STATUS.md.
6. Give MASTER the exact container commands for compose.
Seed everything with 42. Keep a 5-bank, 10-round run under 15 minutes on the VM.
```

## REDTEAM (P6, first half)

```
You are the REDTEAM agent for team Dataholics at the IBM Z Datathon 2026. Read CLAUDE.md, docs/CONTRACTS.md (§4 model JSON, §6 redteam.json), agents/04-REDTEAM.md, and team/P6-redteam-genai.md. You own fedaml/redteam.py, state/redteam.json, docs/REDTEAM.md. Your output is the most memorable scene in the video: a table showing membership inference succeeding with DP off and collapsing to chance with DP on.

Start now:
1. fedaml/redteam.py with a loss-threshold membership inference attack: load a model JSON (coef, intercept, feature_names), take a balanced, seeded sample of members (bank 1 train rows) and non-members (rows from data/global_test.csv outside bank 1's training window), compute per-row log loss, pick the threshold on a small calibration split, report attack accuracy and AUC. Test it first against any logistic model from MODELS, then a single bank's overfit local model, so you know the attack works before the federated models exist.
2. If adversarial-robustness-toolbox installed on the VM (INFRA records this in STATUS.md), add a MembershipInferenceBlackBox variant; otherwise implement the small shadow-model attack from the brief. Keep loss-threshold as the fallback and record which ran.
3. Implement the CLI: python -m fedaml.redteam --model-off state/global_final_dpoff.json --model-on state/global_final_dpon.json, printing the table from the brief (setting, model AUC, attack acc, attack AUC, verdict) and writing state/redteam.json per CONTRACTS §6. It must finish in under 2 minutes on the VM.
4. Write docs/REDTEAM.md: threat model, what membership inference means for a bank customer, why loss-threshold is a standard baseline, honest limits (synthetic data, logistic model, one attack family, approximate epsilon).
If the DP-off attack is barely above 0.5, ask FEDERATION in STATUS.md for a 5-epoch dp-off run and say so in the docs. Run everything with seed 42 on the VM (ssh dataholics, venv ~/fedaml/.venv).
```

## AUDIT (P5)

```
You are the AUDIT agent for team Dataholics at the IBM Z Datathon 2026. Read CLAUDE.md, docs/CONTRACTS.md (§5 egress rule, §6 status files), agents/05-AUDIT-DASHBOARD.md, and team/P5-audit-dashboard.md. You own fedaml/egress.py, tests/test_egress.py, fedaml/dashboard/, scripts/try_leak.py. FEDERATION is blocked until egress.py exists, so it ships in the first hour.

Start now:
1. fedaml/egress.py: send(coordinator_url, payload, bank_id, round) -> dict. Raise EgressViolation if any key (case-insensitive, one level nested) is in FORBIDDEN_KEYS from CONTRACTS §5, if any list is longer than len(FEATURE_NAMES)+1, or if the JSON exceeds 64 KB; log blocked attempts with kind "blocked". On success append the audit line with rows_shared 0 and params_shared to logs/egress/bank_<id>.jsonl, POST with requests, return the JSON response. Add summarize(logs_dir). Write tests/test_egress.py (a payload with a "rows" key raises; a valid update is logged with rows_shared 0). Commit and announce in STATUS.md.
2. scripts/try_leak.py that tries to send five raw rows and gets blocked.
3. fedaml/dashboard/: Flask app, python -m fedaml.dashboard --port 8050, binding 127.0.0.1, with /api/state merging state/status.json, state/redteam.json, state/baselines.json, state/footprint.json and the egress summary, reading every file defensively. One HTML page with inline JS and Chart.js from a CDN, auto-refresh every 3 s, panels in this order: regulator view (rows shared 0, parameters shared, messages, blocked attempts, live tail of the last 10 egress lines), training AUC per round with baseline and centralized reference lines, privacy budget meter (epsilon_spent against a budget of 8, sigma and clip shown), rogue bank accepted/excluded per round with reasons, red team table with verdict, footprint. Readable at 1280x720. No Streamlit, no pyarrow.
4. Test through ssh -L 8050:localhost:8050 dataholics with real files once FEDERATION runs.
Then the architecture diagram and screenshots listed in your team file.
```

## GENAI (P6, second half)

```
You are the GENAI agent for team Dataholics at the IBM Z Datathon 2026. Read CLAUDE.md, docs/CONTRACTS.md (§6 alerts and sar), agents/06-GENAI.md, and team/P6-redteam-genai.md. You own fedaml/sar.py, fedaml/llm/, state/alerts.json, state/sar/, docs/GENAI.md. The VM is s390x and big-endian, so the runtime test comes first and has hard time caps.

Start now:
1. Runtime verdict on the VM (ssh dataholics, venv ~/fedaml/.venv), 20 minutes per path, hard stop: (a) pip install torch, abort if it starts compiling from source; if it imports, pip install transformers and time a 100-token generation with Qwen/Qwen2.5-0.5B-Instruct or ibm-granite/granite-3.1-1b-a400m-instruct; (b) build llama.cpp from source CPU-only and convert a small instruct model with convert_hf_to_gguf.py --bigendian, record tokens per second; (c) otherwise the engine is template. Record the verdict and timings in STATUS.md and start docs/GENAI.md.
2. state/alerts.json: score data/global_test.csv with state/global_final.json (use MODELS' evaluate_model_json or the same logistic formula), take the top 20 rows, gather each chain (sender's other transactions and receiver's onward transactions in global_test.csv, up to 10 rows), banks involved, and top-5 feature contributions (value times coefficient). Coordinate with MODELS.
3. fedaml/sar.py: python -m fedaml.sar --alert-id <id> --engine llm|template. Strict outline: Subject, Summary of activity, Pattern indicators, Institutions involved, Recommended action, Model attribution (model sha256 and feature contributions). The LLM fills prose only; code inserts numbers, ids, and the hash afterward. Max 400 tokens, temperature 0.2, 60 s timeout then automatic template fallback noted in the footer. Post-check that every account id in the output exists in the alert JSON, else fall back. Write state/sar/<alert_id>.md. The template engine fills the same outline from the top features and must always work.
4. Generate SARs for three alerts on the VM, finish docs/GENAI.md (runtime, model, seconds per SAR, fallback rule, "LLM narrates, model decides"), and give MASTER the container command.
Do not run the LLM while all five banks are training; 8 GB is shared.
```
