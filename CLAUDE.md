# Dataholics — IBM Z Datathon 2026 — Cross-Bank AML via Federated Learning

Read this file first, then `docs/CONTRACTS.md`, then your own brief in `agents/`. Humans: your assignment is in `team/`. Update `STATUS.md` when you start, finish, or get blocked.

## Event (fixed facts)
- IBM Z Datathon 2026 (Shooting Stars Foundation + IBM, on Hack2Skill). 24-hour build: Sat Oct 17 2026 8 AM CDT → Sun Oct 18 ~9 AM CDT. **Hard internal deadline: submit by 7 AM CDT Sunday.** In person at UT Dallas (Davidson Auditorium) until ~4 PM Sat, then remote.
- Team "Dataholics", 6 UT Dallas students, leader Vedcharan Peddu. Per-person assignments: `team/P1..P6-*.md` (each person drives one or two agent briefs).
- Theme: **AI Secured: Innovation Without Exposure** — AI that creates value from sensitive data without exposing data, identities, models or systems. IBM Z angles: encryption, cryptography, quantum-safe.

## Judging (40 pts, 10 each)
1. Value to community and theme fit. 2. Novelty. 3. Technical design and AI/ML open-source packages running ON LinuxONE (screenshots of containers, security, compute). 4. Execution and a ≤3-min video with live demo.
- Mandatory: a team-trained predictive model (several compared) AND a generative AI layer (small CPU LLM).
- AI Innovation Excellence Award rewards unconventional AI + technical depth.

## Rules
- All project code written during the event by the team. No reused prior projects. Open-source libraries are fine; list links to all of them in the submission.
- Data must be public or synthetic. No real personal data. No political topics.
- Never commit the dataset, the `.pem` key, or any secret. `data/`, `*.pem`, `.venv/` are gitignored.

## The locked idea (Oct 17, noon CDT)
**Problem.** Criminals split one laundering scheme across several banks because each bank can only see its own transactions. Pooling raw data has failed legally (Dutch TMNL shut down 2024; Singapore COSMIC only shares after suspicion; US 314(b) barely used).
**Solution.** Banks jointly train one laundering detector without any raw transaction leaving a bank, then prove it by attacking the model themselves.
**Pitch line.** "What the Dutch banks had to shut down, built so it would have been legal."

### Architecture (containers on the LinuxONE VM)
- `bank1..bank4`: each holds its own shard of the IBM AML dataset (split by `From Bank`), trains locally, sends only clipped + noised model updates through one audited egress function.
- `coordinator`: federated averaging (FedAvg) over updates; differential privacy (DP); rogue-bank defense (norm clipping + outlier exclusion); writes global model + status JSON + attestation.
- `rogue`: a 5th bank that sends poisoned updates to hide its own laundering. Coordinator must detect and exclude it. (Addition #4)
- `attacker`: membership-inference red team against the global model, DP off vs DP on. `redteam` command prints the side-by-side table.
- `dashboard`: "regulator view" — live egress audit (rows shared: 0, parameters shared: N), round metrics, privacy budget meter, rogue exclusions, redteam results. (Addition #2)
- `genai`: small CPU LLM writes a Suspicious Activity Report (SAR) for a flagged chain; template fallback.
- Stretch only: Paillier-encrypted aggregation (`phe`), ML-DSA-signed model updates (`dilithium-py`).

### Dataset
- Primary: IBM Transactions for Anti Money Laundering (AML), **HI-Small_Trans.csv** on Kaggle (login needed, teammate downloads, scp to server). ~5.08M rows, columns: Timestamp, From Bank, Account, To Bank, Account.1, Amount Received, Receiving Currency, Amount Paid, Payment Currency, Payment Format, Is Laundering. Laundering rate ≈ 1 in 981.
  https://www.kaggle.com/datasets/ealtman2019/ibm-transactions-for-anti-money-laundering-aml
- Backup (no login): IBM TabFormer card transactions, no bank column. https://github.com/IBM/TabFormer

## Agents
| Brief | Role | Owns (code paths) |
|---|---|---|
| `agents/00-MASTER.md` | Orchestrator: timeline, integration, cuts, submission | `STATUS.md`, `README.md`, `docker-compose.yml`, `submission/` |
| `agents/01-INFRA.md` | Server, Docker, data landing + partition, footprint numbers | `scripts/`, `data/` layout, `Dockerfile` |
| `agents/02-MODELS.md` | Features, per-bank baselines, multi-model comparison | `fedaml/features.py`, `fedaml/baselines.py` |
| `agents/03-FEDERATION.md` | Bank client, coordinator, FedAvg, DP, rogue defense, rogue bank | `fedaml/bank.py`, `fedaml/coordinator.py`, `fedaml/dp.py`, `fedaml/defense.py`, `fedaml/rogue.py` |
| `agents/04-REDTEAM.md` | Membership inference attacker, `redteam` command | `fedaml/redteam.py` |
| `agents/05-AUDIT-DASHBOARD.md` | Egress audit function, regulator dashboard, privacy meter | `fedaml/egress.py`, `fedaml/dashboard/` |
| `agents/06-GENAI.md` | LLM runtime test on s390x, SAR generator, template fallback | `fedaml/sar.py`, `fedaml/llm/` |

Each agent: read this file + `docs/CONTRACTS.md` + your brief. Work only in the paths you own; if you must change a shared contract, write the proposal in `STATUS.md` under "Contract changes" and ping MASTER. Never edit another agent's files. Keep every step runnable; commit small and often.

## Repo and runtime conventions
- Project folder is `~/Documents/dataholics` on the Mac; repo lives at `~/Documents/dataholics/fedaml-repo` and `~/fedaml` on the VM (git push to GitHub, pull on the VM). Python package `fedaml/`, one module per concern, `python -m fedaml.<module>` entrypoints. `fedaml` is a working name; MASTER may rename before submission.
- Python 3.12. **On the VM use Ubuntu apt packages** (`python3-numpy python3-scipy python3-pandas python3-sklearn python3-flask python3-matplotlib`) inside a venv created with `--system-site-packages`. pip only for pure-Python packages (`phe`, `dilithium-py`, `adversarial-robustness-toolbox` if it installs cleanly). Never pip-install numpy/scipy/sklearn on s390x (hours of compiling).
- Docker images: base `ubuntu:24.04` + apt python3-* packages, one `Dockerfile` for all services, service chosen by command. Containers share `./state`, `./logs`, `./data` as volumes.
- Models are saved as JSON (weights + feature names + sha256). **No pickle** across containers.
- Every number on a slide must come from a file in `state/` or `logs/` produced on the VM.

## LinuxONE VM
- Ubuntu 24.04, **s390x (IBM Z, big-endian), CPU-only, 3 cores, 8 GB RAM, 50 GB disk**, passwordless sudo, Docker installed, user in docker group.
- Host from earlier setup: `148.100.99.63`, user `linux1`, key `~/Downloads/dataholics.pem`. Confirm with the team lead if a new VM replaced it.
- SSH alias (add to `~/.ssh/config` on the Mac):
  ```
  Host dataholics
    HostName 148.100.99.63
    User linux1
    IdentityFile ~/Downloads/dataholics.pem
    ServerAliveInterval 60
  ```
  Then `ssh dataholics '<command>'`, `scp file dataholics:~/`, `ssh -L 8050:localhost:8050 dataholics` for the dashboard.
- Jupyter or dashboards bind to localhost on the VM; reach them through SSH tunnels only.
- Community Cloud VMs expire (~Nov 16 2026). Code lives in GitHub, not only on the VM.

## s390x gotchas
- Big-endian: pretrained x86 binaries (GGUF, ONNX, pickles) can break. Train on the VM; test the LLM runtime in hour one; keep the template SAR fallback.
- Rust-based pip packages often fail to build. Prefer pure Python or apt.
- 3 cores: cap pandas/sklearn `n_jobs=2`; subsample to ≤ 500k rows per bank for training; keep `HistGradientBoosting` as the boosting model (no XGBoost/LightGBM).

## Timeline (CDT, Sat → Sun)
| Window | Must be true at the end |
|---|---|
| 12:00–13:00 | VM ready, data on VM and partitioned, `features.py` drafted, every agent has a local scaffold |
| 13:00–15:00 | 2-bank FedAvg over HTTP works on the VM; per-bank baselines table; egress logging live; LLM runtime verdict |
| 15:00–17:30 | DP + clipping + rogue defense; redteam DP off/on table; dashboard v1; SAR template output |
| 17:30–20:00 | All services in docker compose on the VM; end-to-end run; footprint measured |
| 20:00–23:00 | Demo rehearsal twice; README + library links; fix list |
| 23:00–02:00 | Video (≤3 min), slides, architecture diagram |
| 02:00–06:00 | Buffer; stretch only if everything above is green |
| 06:00–07:00 | **Submit.** Title: `Dataholics_IBM Z Datathon 2026 Project` |

## Cut order if behind (MASTER decides)
Cut first → last: Paillier, ML-DSA signing, LLM (fall back to template SAR), dashboard polish, privacy budget meter, rogue bank. **Never cut:** 2+ bank FedAvg, redteam DP off/on table, egress audit with "rows shared: 0", the video.

## Submission checklist
- Video ≤3 min: problem, data, solution, how it uses IBM Z (show the LinuxONE terminal, `docker ps`, model running).
- Public GitHub repo link, links to every open-source library and the dataset.
- Optional: architecture diagram, prototype link.
- Claims discipline: say "sandboxed containers" not Secure Execution; attacks are synthetic and say so; report measured RAM/time, not estimates; DP epsilon is approximate and say so.
