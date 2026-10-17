# STATUS board — update when you start, finish, or block. Newest entry at top of each section.

## Timeline check (MASTER updates hourly)
- 12:45 CDT Sat: **Window 12:00–13:00 at risk.** True: repo public (verified `gh repo view` → PUBLIC), VM reachable, repo cloned at `~/fedaml` on VM, base build tools installed (`~/setup.log` ends INSTALL_DONE), `docker-compose.yml` drafted, `submission/DEMO_SCRIPT.md` drafted. Not yet true: data on VM, partition, `features.py`, venv, python3-* apt packages, `docker compose` plugin, Dockerfile, any agent scaffold. Kaggle CSV owner not yet confirmed → single biggest risk for the 13:00 and 15:00 windows.
- 12:00 CDT Sat: project locked, briefs written. Nothing built yet.

## VM facts (MASTER verified 12:40 CDT via `ssh dataholics`)
```
uname -m      s390x
nproc         3
free -h       Mem: 7.8Gi total, 1.3Gi used, 6.6Gi available
df -h /       /dev/dasda1 50G, 2.9G used, 45G free
docker        Docker version 29.1.3, build 29.1.3-0ubuntu3~24.04.2 ; `docker ps` → no containers
docker compose  NOT INSTALLED ("docker: unknown command: docker compose") → INFRA: apt install docker-compose-v2
python3       3.12.3 ; no venv at ~/fedaml/.venv yet ; python3-sklearn/pandas/flask apt packages not installed yet
~/fedaml      clone of this repo at commit 07ae21c ; no data/ dir yet
```
SSH alias `dataholics` added to the Mac's `~/.ssh/config` (host 148.100.99.63, user linux1, key ~/Downloads/dataholics.pem).

## Agent status
| Agent | State | Last update | Next deliverable |
|---|---|---|---|
| MASTER | active | 12:45 | hourly loop; collect exact container commands from FEDERATION/AUDIT/GENAI; `docker compose up` on VM by 17:30 |
| INFRA | started (apt base tools done) | 12:45 (seen by MASTER) | `apt install docker-compose-v2 python3-{numpy,scipy,pandas,sklearn,flask,matplotlib,requests}`; venv; Dockerfile + `docker build -t fedaml .`; land CSV; partition |
| MODELS | not started | | `features.py` on synthetic 1k rows until `sample_50k.csv` exists |
| FEDERATION | not started | | coordinator + bank MVP against stubs |
| REDTEAM | not started | | loss-threshold attack scaffold |
| AUDIT | not started | | `egress.py` + `tests/test_egress.py` (FEDERATION blocks on it) |
| GENAI | not started | | LLM runtime verdict on s390x (20-min caps) |

## VM facts (INFRA, measured 12:40 CDT Sat via `ssh dataholics`)
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
- Compose uses ONE image `fedaml` built from `./Dockerfile` (INFRA). `WORKDIR /app`, `PYTHONPATH=/app`; volumes mounted at `/app/data`, `/app/state`, `/app/logs`, so relative paths `data/...`, `state/...`, `logs/...` in code work unchanged.
- **Servers must bind `0.0.0.0` inside their container** (coordinator :8000, dashboard :8050). The brief's "bind 127.0.0.1" applies to the *host* side: compose publishes `127.0.0.1:8050:8050` and `127.0.0.1:8000:8000`, so nothing is reachable from the internet. AUDIT and FEDERATION: add a `--host` flag defaulting to `0.0.0.0`, or read `HOST` env.
- Coordinator URL inside compose is `http://coordinator:8000`. Banks must retry the first `GET /config` for ~60 s (coordinator may start later than the bank).
- Run knobs are env vars with defaults (`ROUNDS=10 DP=on SIGMA=0.8 CLIP=1.0 DEFENSE=on EPOCHS=1 ROGUE_ATTACK=scale ROGUE_FACTOR=-20 SEED=42`), e.g. `DP=off DEFENSE=off docker compose up`. Keep CLI flag names exactly as CONTRACTS §7.
- `scripts/` is mounted read-only at `/app/scripts` so `scripts/try_leak.py` works inside the `tryleak` tools service.
- Tools profile (`docker compose run --rm <svc>`): `attacker`, `genai`, `baselines`, `tryleak`.

## Decisions log
- Oct 17 12:45: MASTER drafted `docker-compose.yml` (default profile: coordinator, bank1-4, rogue, dashboard; profile `tools`: attacker, genai, baselines, tryleak) and `submission/DEMO_SCRIPT.md` with `{{PLACEHOLDER}}` numbers, each tied to a file in `state/` or `logs/`.
- Oct 17 12:45: Containers bind 0.0.0.0 internally; only the host publishes on 127.0.0.1 (see Integration notes). Not a CONTRACTS change; clarification.
- Oct 17 12:00: idea locked (cross-bank AML, federated). Additions accepted: regulator view (#2), rogue bank (#4). Paillier and ML-DSA are stretch.

## Numbers for the slides (file of origin required)
- (none yet)
