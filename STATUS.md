# STATUS board — update when you start, finish, or block. Newest entry at top of each section.

## Timeline check (MASTER updates hourly)
- 12:50 CDT Sat (13:00 window): **mostly green except data.** True: VM ready (`setup_vm.sh` ran: venv, apt python3-sklearn 1.4.1/pandas 2.1.4/flask 3.0.2, docker-compose-v2 2.40.3, image `fedaml:latest` built 926 MB); `features.py` + `baselines.py` + `docs/FEATURES.md` pushed; `egress.py` + tests + `try_leak.py` pushed; `redteam.py` (419 lines) and `fedaml/llm/` scaffolds in tree; compose + demo script drafted. NOT true: **Kaggle CSV not on VM, so no partition, no `sample_50k.csv`.** FEDERATION has no code in the tree yet (coordinator+bank MVP is the 15:00 window's critical path; start on `make_synthetic` rows now). VM repo at 9f172a8, needs `git pull`.
- 12:45 CDT Sat: **Window 12:00–13:00 at risk.** True: repo public (verified `gh repo view` → PUBLIC), VM reachable, repo cloned at `~/fedaml` on VM, base build tools installed (`~/setup.log` ends INSTALL_DONE), `docker-compose.yml` drafted, `submission/DEMO_SCRIPT.md` drafted. Not yet true: data on VM, partition, `features.py`, venv, python3-* apt packages, `docker compose` plugin, Dockerfile, any agent scaffold. Kaggle CSV owner not yet confirmed → single biggest risk for the 13:00 and 15:00 windows.
- 12:00 CDT Sat: project locked, briefs written. Nothing built yet.

## Agent status
| Agent | State | Last update | Next deliverable |
|---|---|---|---|
| MASTER | active | 12:50 | hourly loop; collect exact container commands from FEDERATION/AUDIT/GENAI; `docker compose up` on VM by 17:30 |
| INFRA | in progress | 12:50 (seen by MASTER: setup_vm.sh done on VM, image built) | **name the Kaggle downloader; land CSV**; `partition_data.py`; `sample_50k.csv` to repo; record build time + pip results in STATUS |
| MODELS | features.py matches INFRA partition output (ISO ts, string bank codes); baselines + evaluator tested on synthetic 4-bank partition; VM watcher armed; blocked on data + venv | 13:15 | baselines on VM → table here |
| FEDERATION | not started (no code in tree at 12:50) | | coordinator + bank MVP on `features.make_synthetic()` rows; use real `egress.send` (shipped) |
| REDTEAM | in progress (redteam.py 419 lines, uncommitted) | 12:50 (seen by MASTER) | commit; `--selftest` on synthetic logreg; wait for dp-off/dp-on models |
| AUDIT | egress.py + tests + try_leak.py pushed (80179a8) | 12:50 | `summarize(logs_dir)`; dashboard v1 (bind 0.0.0.0, port 8050, `/api/state`) |
| GENAI | in progress (fedaml/llm scaffold → llama.cpp HTTP client) | 12:50 (seen by MASTER) | runtime verdict in STATUS (tokens/s or 'template'); `sar.py --engine template` first |

## VM facts (INFRA, measured 12:40 CDT Sat via `ssh dataholics`; MASTER re-verified 12:40: `docker ps` empty, no venv, no data/, python3-sklearn/pandas/flask not yet installed)
```
$ uname -m          -> s390x
$ nproc             -> 3
$ free -g           -> Mem total 7 GiB, used 1, free 5, available 6; Swap 0
$ df -h /           -> /dev/dasda1  50G  2.9G used  45G avail (7%)
$ /etc/os-release   -> Ubuntu 24.04.5 LTS
$ python3 --version -> Python 3.12.3
$ docker --version  -> Docker version 29.1.3 (docker compose plugin NOT present until setup_vm.sh installs docker-compose-v2)
$ id -nG            -> linux1 adm cdrom sudo dip plugdev cpacfstats lxd docker
VM clock is UTC (17:40 UTC == 12:40 CDT). Repo cloned at ~/fedaml (commit 07ae21c).
```
SSH alias `dataholics` added to `~/.ssh/config` on the lead's Mac; key `~/Downloads/dataholics.pem` is mode 600.

## INFRA: VM setup + Docker (done 12:55 CDT, logs on VM: `~/fedaml/logs/setup_vm.log`, `~/fedaml/logs/docker_build.log`)
- `scripts/setup_vm.sh` ran clean. apt stack (s390x wheels from Ubuntu): numpy 1.26.4, scipy 1.11.4, pandas 2.1.4, sklearn 1.4.1.post1, flask 3.0.2, matplotlib 3.6.3, requests 2.31.0. Docker Compose 2.40.3 now installed.
- venv: `~/fedaml/.venv` (`--system-site-packages`). Activate: `. ~/fedaml/.venv/bin/activate`.
- pip results: **phe 1.5.0 OK, dilithium-py OK, adversarial-robustness-toolbox 1.20.1 OK** (ART warns PyTorch missing; sklearn estimators work). Nothing failed.
- Docker: `docker run --rm ubuntu:24.04 uname -m` -> `s390x`. `docker build -t fedaml .` = **90 s**, image 926 MB, `docker run --rm fedaml` prints `fedaml image ok s390x 1.4.1.post1`. Image has phe + requests + dilithium-py (rebuilt after adding dilithium-py).
- Layout on VM: `~/fedaml/data/{raw,banks}`, `~/fedaml/state`, `~/fedaml/logs/egress`. Compose mounts `./data ./state ./logs` into `/app/...`.
- Helpers: `scripts/footprint.sh start|stop|report` (docker stats every 5 s -> `logs/footprint.log` -> `state/footprint.json`), `scripts/reset_run.sh [--down]`, `scripts/partition_when_landed.sh` (watcher running on the VM: partitions automatically once the CSV upload finishes; log `~/fedaml/logs/partition.log`).
- Hardware detail for slides (from `lscpu`, saved in `submission/screenshots/01_vm_facts.txt` on the VM): IBM/S390 machine type 9175, 3 CPUs @ 5508 MHz, Big Endian, hypervisor z/VM 7.3.0, kernel 6.8.0-147 s390x; CPU flags include `vx`, `nnpa`. Say "LinuxONE VM on IBM Z (machine type 9175)"; don't name a model number we can't source.
- `cmake`, `build-essential`, `pkg-config` preinstalled on the VM for P6 (llama.cpp attempts). `scripts/footprint.sh` verified against a live container.
- Read partitioned CSVs with `dtype={'from_bank': str, 'to_bank': str, 'from_acct': str, 'to_acct': str}, parse_dates=['ts']` — account ids like `81245E60` turn into floats otherwise. `ts` is written as `YYYY-MM-DD HH:MM:SS`.

## Blockers
- [12:45] **Kaggle `HI-Small_Trans.csv` not on the VM.** Needs: a teammate with a Kaggle login downloads it and runs `scp HI-Small_Trans.csv dataholics:~/fedaml/data/raw/`. Owner: P2 to name the downloader. Everything downstream waits on this.
- ~~[12:45] `docker compose` plugin missing~~ → RESOLVED 12:50: Docker Compose 2.40.3 installed by `setup_vm.sh`.

## Contract changes (proposed → MASTER accepts/rejects)
- REDTEAM (12:55), heads-up not a change: §4 says `SGDClassifier(loss="log_loss", class_weight="balanced")` + `partial_fit`, but sklearn raises `class_weight 'balanced' is not supported for partial_fit`. Fix: `compute_class_weight("balanced", classes=[0,1], y=y_train)` and pass the dict (see `fedaml.redteam.sgd_logreg`). FEDERATION's bank client will hit this.
- REDTEAM (12:55), heads-up for MODELS/INFRA: the within-bank account aggregates (`snd_txn_cnt_log` etc.) depend on the frame they are computed over. `global_test.csv` is a 200k mixed-bank sample, so its aggregates are systematically smaller than in a 500k bank train file; on synthetic data this alone moved model AUC by ~0.1. Suggest MODELS compute aggregates from a per-row account history that is consistent between train and test (e.g., counts within the same file are fine for train; for `global_test`, counts within global_test are what the regulator would see — just know the gap exists). REDTEAM reports a same-bank control (`--nonmembers bank_test`) for this reason.
- REDTEAM (12:55), extra keys in `state/redteam.json`: in addition to §6 keys it adds `target` ("laundering"|"all"), `verdict` inside `dp_off`/`dp_on`, `n_per_class`, `seed`, `runtime_s`, `generated_at`, `detail`. Dashboard can ignore them.
- REDTEAM → FEDERATION request: please produce BOTH `state/global_final_dpoff.json` (dp off) and `state/global_final_dpon.json` (dp on) from otherwise identical runs, and keep `feature_names` in the model JSON. If the DP-off attack is near chance on real data I will ask for a 5-epoch DP-off run (`--epochs 5`).

## Integration notes from MASTER (read if you own a service)
- **Everyone works in this ONE clone on the lead's Mac.** `git add` only the paths you own (never `git add -A`), commit small, `git pull --rebase` before push. MASTER's 12:50 commit accidentally swept in `fedaml/features.py` (MODELS); content is intact, no action needed.
- INFRA's `Dockerfile` (12:42) matches compose: `WORKDIR /app`, `PYTHONPATH=/app`, `logs/egress` pre-created, `curl` present. `docker-compose.yml` validated as YAML (11 services); `docker compose config` to be run on the VM once the plugin is installed.
- Compose uses ONE image `fedaml` built from `./Dockerfile` (INFRA). `WORKDIR /app`, `PYTHONPATH=/app`; volumes mounted at `/app/data`, `/app/state`, `/app/logs`, so relative paths `data/...`, `state/...`, `logs/...` in code work unchanged.
- **Servers must bind `0.0.0.0` inside their container** (coordinator :8000, dashboard :8050). The brief's "bind 127.0.0.1" applies to the *host* side: compose publishes `127.0.0.1:8050:8050` and `127.0.0.1:8000:8000`, so nothing is reachable from the internet. AUDIT and FEDERATION: add a `--host` flag defaulting to `0.0.0.0`, or read `HOST` env.
- Coordinator URL inside compose is `http://coordinator:8000`. Banks must retry the first `GET /config` for ~60 s (coordinator may start later than the bank).
- Run knobs are env vars with defaults (`ROUNDS=10 DP=on SIGMA=0.8 CLIP=1.0 DEFENSE=on EPOCHS=1 ROGUE_ATTACK=scale ROGUE_FACTOR=-20 SEED=42`), e.g. `DP=off DEFENSE=off docker compose up`. Keep CLI flag names exactly as CONTRACTS §7.
- `scripts/` is mounted read-only at `/app/scripts` so `scripts/try_leak.py` works inside the `tryleak` tools service.
- Tools profile (`docker compose run --rm <svc>`): `attacker`, `genai`, `alerts`, `baselines`, `tryleak`.

## Decisions log
- Oct 17 12:58 (MASTER): `docker compose config` passes on the VM (Compose 2.40.3). Removed the `${ALERT_ID:?}` guard (it broke plain `docker compose up`); genai defaults to `A01`. Added `alerts` tools service for `fedaml.alerts`.
- Oct 17 13:05 (MODELS → GENAI): `python -m fedaml.baselines --alerts state/global_final.json --top-k 20` writes `state/alerts.json` = `{"model","model_sha256","n_scored","k","alerts_true_laundering","alerts":[{"alert_id":"A001","rank","score","txn":{ts,from_bank,from_acct,to_bank,to_acct,amt_paid,cur_paid,amt_recv,cur_recv,fmt,is_laundering,score},"top_features":[{"name","value","contribution","meaning"}×5],"chain":[≤10 txns touching sender/receiver in global_test, time-ordered],"banks_involved":[...]}]}`. **Superseded 13:15:** GENAI already has `fedaml/alerts.py` (contract says GENAI owns alerts.json), so MODELS removed its `--alerts` path to avoid two writers. GENAI: `fedaml.features.FEATURE_DESCRIPTIONS` (plain-English line per feature) and `fedaml.features.contributions(X, coef)` are there for you; your scoring formula matches `fedaml.baselines.predict_proba_json`, so the SAR and the dashboard will agree. MASTER: `--seed` is accepted by `fedaml.baselines`.
- Oct 17 12:50 (MASTER): compose TODOs closed for baselines/attacker/tryleak (flags verified in code). `genai` service gets `LLM_URL` (default `http://host.docker.internal:8080`) + `extra_hosts: host-gateway`, assuming llama-server runs on the VM host; GENAI to confirm.
- Oct 17 12:50 (MODELS): `fedaml.features` shipped. 20 features, order per CONTRACTS §3, one-hot names `fmt_ACH, fmt_Credit_Card, fmt_Cheque, fmt_Wire, fmt_Reinvestment, fmt_Bitcoin, fmt_Cash`. `feature_names_sha256()` = `4e58a8f815af595585d72f5852a886a60ba572ac2e09aecbcf6ef6f550792dcb`. `featurize()` accepts raw Kaggle headers or canonical names. `make_synthetic(n)` gives everyone test rows until data lands. `fedaml.baselines.evaluate_model_json(path)` / `predict_proba_json(model, X)` are the shared evaluator; `state/baselines.json` per_bank entries carry `auc, ap` (bank's own test) plus `global_auc, global_ap` (global_test.csv), extra keys only.
- Oct 17 12:50 (AUDIT): egress.send checks forbidden keys at any depth (stricter than the one-level minimum), caps lists at len(FEATURE_NAMES)+1 (falls back to 20 features from CONTRACTS §3 until features.py lands), 64 KB body, rejects NaN/non-JSON (banks must `.tolist()`). Audit log dir defaults to `logs/egress`, override with env `FEDAML_EGRESS_LOGS` or `logs_dir=`.
- Oct 17 12:45: MASTER drafted `docker-compose.yml` (default profile: coordinator, bank1-4, rogue, dashboard; profile `tools`: attacker, genai, baselines, tryleak) and `submission/DEMO_SCRIPT.md` with `{{PLACEHOLDER}}` numbers, each tied to a file in `state/` or `logs/`.
- Oct 17 12:45: Containers bind 0.0.0.0 internally; only the host publishes on 127.0.0.1 (see Integration notes). Not a CONTRACTS change; clarification.
- Oct 17 12:00: idea locked (cross-bank AML, federated). Additions accepted: regulator view (#2), rogue bank (#4). Paillier and ML-DSA are stretch.

## Numbers for the slides (file of origin required)
- (none yet)
