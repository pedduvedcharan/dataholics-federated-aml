# P2 — Infra and data

**Agent brief you drive:** `agents/01-INFRA.md`. You are the only person who touches the VM's system packages and the raw data. Everyone is blocked until the data is partitioned, so your first two hours matter most.

## Your deliverables
`scripts/setup_vm.sh`, `scripts/partition_data.py`, `scripts/footprint.sh`, `Dockerfile`, data on the VM in the layout from `docs/CONTRACTS.md` §2, `data/sample_50k.csv` in the repo for local development, `state/footprint.json`, screenshots for judging criterion 3.

## Hour by hour
- **12:00–12:20** SSH alias from CLAUDE.md into `~/.ssh/config`; `chmod 600 ~/Downloads/dataholics.pem`; `ssh dataholics 'uname -m; nproc; free -g; df -h /'`; paste the output in STATUS.md.
- **12:20–12:50** `scripts/setup_vm.sh`: apt packages (`python3-venv python3-numpy python3-scipy python3-pandas python3-sklearn python3-flask python3-matplotlib python3-requests git docker-compose-v2 strace`), venv with `--system-site-packages`, `pip install phe`, then try `adversarial-robustness-toolbox` and `dilithium-py`. Record what installed. Verify imports. Clone the repo to `~/fedaml` on the VM: `git clone https://github.com/pedduvedcharan/dataholics-federated-aml.git ~/fedaml`.
- **12:50–13:00** `docker run --rm ubuntu:24.04 uname -m`. Write the `Dockerfile` (ubuntu:24.04, same apt packages, `pip install --break-system-packages phe requests`, copy `fedaml/`). Build and time it.
- **13:00–13:30** Get `HI-Small_Trans.csv` from the teammate who downloaded it: `scp HI-Small_Trans.csv dataholics:~/fedaml/data/raw/`. `wc -l`, `head -2`.
- **13:30–14:30** `scripts/partition_data.py` per CONTRACTS §2, chunked pandas. Produce `data/banks/bank_1..5/{train,test}.csv`, `data/global_test.csv`, `data/bank_map.json`, `data/sample_50k.csv`. Paste the summary table (rows and laundering counts per bank) in STATUS.md. scp `sample_50k.csv` into the repo on the Mac and push.
- **14:30–17:30** Support: help P4 run two bank terminals on the VM; help P6 with build tools if llama.cpp is attempted (`cmake build-essential`); keep an eye on RAM with `free -g` while people train.
- **17:30–20:00** During P1's full compose run: `scripts/footprint.sh` sampling `docker stats` every 5 s; write `state/footprint.json`. Capture `uname -a`, `lscpu | head`, `docker ps`, `docker stats` into `submission/screenshots/`.
- **20:00–23:00** Help P1 rehearse: tunnels, terminals, resetting `state/` and `logs/` between runs (`scripts/reset_run.sh`).
- **23:00 onward** Second screenshot pass before the video; keep the VM alive during recording; help stitch the video.

## Done when
STATUS.md has VM facts, package results, Docker arch, data summary table, footprint numbers with paths, and screenshots exist.
