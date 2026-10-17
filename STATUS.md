# STATUS board — update when you start, finish, or block. Newest entry at top of each section.

## Timeline check (MASTER updates hourly)
- 12:45 CDT Sat: **Window 12:00–13:00 at risk.** True: repo public (verified `gh repo view` → PUBLIC), VM reachable, repo cloned at `~/fedaml` on VM, base build tools installed (`~/setup.log` ends INSTALL_DONE), `docker-compose.yml` drafted, `submission/DEMO_SCRIPT.md` drafted. Not yet true: data on VM, partition, `features.py`, venv, python3-* apt packages, `docker compose` plugin, Dockerfile, any agent scaffold. Kaggle CSV owner not yet confirmed → single biggest risk for the 13:00 and 15:00 windows.
- 12:00 CDT Sat: project locked, briefs written. Nothing built yet.

## Agent status
| Agent | State | Last update | Next deliverable |
|---|---|---|---|
| MASTER | active | 12:55 | hourly loop; collect exact container commands from FEDERATION/AUDIT/GENAI; `docker compose up` on VM by 17:30 |
| INFRA | in progress | 12:42 (commit 9f172a8: setup_vm.sh, Dockerfile) | run `setup_vm.sh` on VM; `docker build -t fedaml .` (record time); land CSV; `partition_data.py` |
| MODELS | in progress | 12:50 (features.py 302 lines in tree) | determinism/NaN checks; `docs/FEATURES.md`; push |
| FEDERATION | not started | | coordinator + bank MVP against stubs |
| REDTEAM | not started | | loss-threshold attack scaffold |
| AUDIT | not started | | `egress.py` + `tests/test_egress.py` (FEDERATION blocks on it) |
| GENAI | not started | | LLM runtime verdict on s390x (20-min caps) |

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

## Blockers
- [12:45] **Kaggle `HI-Small_Trans.csv` not on the VM.** Needs: a teammate with a Kaggle login downloads it and runs `scp HI-Small_Trans.csv dataholics:~/fedaml/data/raw/`. Owner: P2 to name the downloader. Everything downstream waits on this.
- [12:45] `docker compose` plugin missing on the VM. Owner: INFRA (`sudo apt-get install -y docker-compose-v2`). Blocks MASTER's 17:30 integration.

## Contract changes (proposed → MASTER accepts/rejects)
- (none)

## Integration notes from MASTER (read if you own a service)
- **Everyone works in this ONE clone on the lead's Mac.** `git add` only the paths you own (never `git add -A`), commit small, `git pull --rebase` before push. MASTER's 12:50 commit accidentally swept in `fedaml/features.py` (MODELS); content is intact, no action needed.
- INFRA's `Dockerfile` (12:42) matches compose: `WORKDIR /app`, `PYTHONPATH=/app`, `logs/egress` pre-created, `curl` present. `docker-compose.yml` validated as YAML (11 services); `docker compose config` to be run on the VM once the plugin is installed.
- Compose uses ONE image `fedaml` built from `./Dockerfile` (INFRA). `WORKDIR /app`, `PYTHONPATH=/app`; volumes mounted at `/app/data`, `/app/state`, `/app/logs`, so relative paths `data/...`, `state/...`, `logs/...` in code work unchanged.
- **Servers must bind `0.0.0.0` inside their container** (coordinator :8000, dashboard :8050). The brief's "bind 127.0.0.1" applies to the *host* side: compose publishes `127.0.0.1:8050:8050` and `127.0.0.1:8000:8000`, so nothing is reachable from the internet. AUDIT and FEDERATION: add a `--host` flag defaulting to `0.0.0.0`, or read `HOST` env.
- Coordinator URL inside compose is `http://coordinator:8000`. Banks must retry the first `GET /config` for ~60 s (coordinator may start later than the bank).
- Run knobs are env vars with defaults (`ROUNDS=10 DP=on SIGMA=0.8 CLIP=1.0 DEFENSE=on EPOCHS=1 ROGUE_ATTACK=scale ROGUE_FACTOR=-20 SEED=42`), e.g. `DP=off DEFENSE=off docker compose up`. Keep CLI flag names exactly as CONTRACTS §7.
- `scripts/` is mounted read-only at `/app/scripts` so `scripts/try_leak.py` works inside the `tryleak` tools service.
- Tools profile (`docker compose run --rm <svc>`): `attacker`, `genai`, `baselines`, `tryleak`.

## Decisions log
- Oct 17 12:50 (MODELS): `fedaml.features` shipped. 20 features, order per CONTRACTS §3, one-hot names `fmt_ACH, fmt_Credit_Card, fmt_Cheque, fmt_Wire, fmt_Reinvestment, fmt_Bitcoin, fmt_Cash`. `feature_names_sha256()` = `4e58a8f815af595585d72f5852a886a60ba572ac2e09aecbcf6ef6f550792dcb`. `featurize()` accepts raw Kaggle headers or canonical names. `make_synthetic(n)` gives everyone test rows until data lands. `fedaml.baselines.evaluate_model_json(path)` / `predict_proba_json(model, X)` are the shared evaluator; `state/baselines.json` per_bank entries carry `auc, ap` (bank's own test) plus `global_auc, global_ap` (global_test.csv), extra keys only.
- Oct 17 12:50 (AUDIT): egress.send checks forbidden keys at any depth (stricter than the one-level minimum), caps lists at len(FEATURE_NAMES)+1 (falls back to 20 features from CONTRACTS §3 until features.py lands), 64 KB body, rejects NaN/non-JSON (banks must `.tolist()`). Audit log dir defaults to `logs/egress`, override with env `FEDAML_EGRESS_LOGS` or `logs_dir=`.
- Oct 17 12:45: MASTER drafted `docker-compose.yml` (default profile: coordinator, bank1-4, rogue, dashboard; profile `tools`: attacker, genai, baselines, tryleak) and `submission/DEMO_SCRIPT.md` with `{{PLACEHOLDER}}` numbers, each tied to a file in `state/` or `logs/`.
- Oct 17 12:45: Containers bind 0.0.0.0 internally; only the host publishes on 127.0.0.1 (see Integration notes). Not a CONTRACTS change; clarification.
- Oct 17 12:00: idea locked (cross-bank AML, federated). Additions accepted: regulator view (#2), rogue bank (#4). Paillier and ML-DSA are stretch.

## Numbers for the slides (file of origin required)
- (none yet)
