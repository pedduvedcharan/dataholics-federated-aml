# INFRA agent — VM, Docker, data landing, footprint

## Goal
By 13:00 the VM is ready, the dataset is partitioned per `docs/CONTRACTS.md` §2, and every other agent can `ssh dataholics` and run Python there. By 20:00 `state/footprint.json` holds measured numbers.

## You own
`scripts/setup_vm.sh`, `scripts/partition_data.py`, `scripts/footprint.sh`, `Dockerfile`, `.gitignore` entries for data, `data/` layout on the VM.

## Inputs you need (ask MASTER)
VM host/user, path to the `.pem` key on the Mac, the Kaggle file `HI-Small_Trans.csv` on a teammate's laptop.

## Tasks, in order
1. **SSH alias.** Add the `Host dataholics` block from CLAUDE.md to `~/.ssh/config`; `chmod 600` the key; verify `ssh dataholics 'uname -m; nproc; free -g; df -h /'` prints s390x, 3, ~8 GB, ~50 GB. Paste the output into STATUS.md.
2. **System packages** (`scripts/setup_vm.sh`, idempotent):
   `sudo apt-get update && sudo apt-get install -y python3-venv python3-numpy python3-scipy python3-pandas python3-sklearn python3-flask python3-matplotlib python3-requests git docker-compose-v2 strace`
   Then `python3 -m venv --system-site-packages ~/fedaml/.venv && . ~/fedaml/.venv/bin/activate && pip install phe` and try `pip install adversarial-robustness-toolbox dilithium-py`; record which succeed in STATUS.md (ART failing is fine, REDTEAM has a fallback).
   Verify: `python3 -c "import numpy, pandas, sklearn, flask; print(sklearn.__version__)"`.
3. **Docker check.** `docker run --rm ubuntu:24.04 uname -m` → s390x. Write `Dockerfile`: `FROM ubuntu:24.04`, apt the same python3-* packages, `pip install --break-system-packages phe requests`, `COPY fedaml /app/fedaml`, `WORKDIR /app`, `ENV PYTHONPATH=/app`. Build once: `docker build -t fedaml .` and record build time. Entry command is set per service in compose (MASTER owns compose).
4. **Data landing.** Teammate runs `scp HI-Small_Trans.csv dataholics:~/fedaml/data/raw/`. Verify row count with `wc -l` (expect ~5.08M) and `head -2`.
5. **Partition** (`scripts/partition_data.py`, pandas, chunked read to stay under 8 GB): implement CONTRACTS §2 exactly. Output `data/banks/bank_{1..5}/{train,test}.csv`, `data/global_test.csv`, `data/bank_map.json` (bank id → original From Bank code, row counts, laundering counts). Print a summary table and paste it in STATUS.md. Also write `data/sample_50k.csv` (random 50k rows, all laundering rows included) and scp it back to the Mac at `fedaml-repo/data/sample_50k.csv` so other agents can develop locally.
6. **Footprint** (`scripts/footprint.sh`): during the full compose run, sample `docker stats --no-stream --format '{{.Name}} {{.MemUsage}}'` every 5 s into `logs/footprint.log`; at the end write `state/footprint.json` (peak RSS per container in MB, seconds per round from coordinator log, total runtime, `"arch":"s390x","cpu_count":3`).
7. **Screenshots for criterion 3.** Capture `uname -a`, `lscpu | head`, `docker ps`, `docker stats` on the VM into `submission/screenshots/`. Do this once things run end to end (~18:00) and again before the video.

## Pitfalls
- pandas on 3 cores and 8 GB: read the CSV with `usecols` and `dtype` set, `chunksize=1_000_000`; never load twice.
- `apt` package names on Ubuntu 24.04 are exactly as listed; if `python3-sklearn` is missing, report immediately, do not try to pip-compile it.
- Keep the VM's `~/fedaml` in sync via `git pull`, not scp of code.

## Done when
STATUS.md has: VM facts, package install results, Docker arch check, data summary table, and later footprint numbers with their file paths.
