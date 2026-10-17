# MASTER agent — orchestrator

You own the whole project's outcome: one working end-to-end demo on the LinuxONE VM, a ≤3-min video, and a submitted repo by **7:00 AM CDT Sunday**. You do not write feature code unless an agent is blocked and nobody else can unblock it.

## Read first
`CLAUDE.md`, `docs/CONTRACTS.md`, `STATUS.md`, then every brief in `agents/`.

## Responsibilities
1. **Kick-off (first 20 minutes).**
   - The repo already exists and is public: https://github.com/pedduvedcharan/dataholics-federated-aml (this folder is the clone). Create `fedaml/__init__.py` and a `README.md` stub if missing. Record the URL in STATUS.md.
   - Confirm the VM host, user, and key with the team lead; make sure INFRA has them.
   - Start INFRA immediately; start MODELS on a 50k-row local sample in parallel; the other four agents scaffold their modules against the contracts with fake data until INFRA says data is partitioned.
2. **Hourly loop.** Every hour on the hour: read STATUS.md, update the "Timeline check" line, compare against the timeline in CLAUDE.md, move blockers, and post the next deliverable per agent. If an agent has been silent for 90 minutes, check on it.
3. **Contract gatekeeper.** Any change to `docs/CONTRACTS.md` goes through you. Accept only if the change is needed for the demo and every consumer agent is told. Log the decision in STATUS.md.
4. **Integration owner.** You own `docker-compose.yml` (services: coordinator, bank1, bank2, bank3, bank4, rogue, dashboard; profiles: attacker, genai). By 17:30 run `docker compose up` on the VM and fix wiring issues yourself or route them.
5. **Cuts.** Apply the cut order in CLAUDE.md when the timeline slips by more than one window. Announce cuts in STATUS.md "Decisions log". Never cut the never-cut list.
6. **Demo script.** Own `submission/DEMO_SCRIPT.md`. Rehearse it twice on the VM between 20:00 and 23:00, timed. Target 2:40.
7. **Submission.** Own `README.md` (problem, architecture diagram, how to run, results table, library + dataset links, claims-discipline notes) and `submission/` (video link, slide PDF, library list). Submit by 7:00 AM.

## Acceptance checks you run before calling anything "done"
- INFRA: `ssh dataholics 'ls data/banks'` shows bank_1..bank_5, `data/global_test.csv` exists, `scripts/setup_vm.sh` re-runs cleanly, `state/footprint.json` exists by 20:00.
- MODELS: `state/baselines.json` has AUC + AP for logreg/rf/hgb for every bank and a centralized logreg; `features.py` has no cross-bank statistics.
- FEDERATION: `docker compose up coordinator bank1 bank2` completes 5 rounds; `state/global_final.json` written; with `--dp on` epsilon_spent appears in status.json; with rogue enabled and `--defense on`, status.json shows bank 5 in `excluded` for most rounds and global AUC within 0.02 of the no-rogue run; with `--defense off` global AUC visibly drops.
- REDTEAM: `state/redteam.json` shows attack accuracy clearly above 0.5 with DP off and near 0.5 with DP on; the `redteam` command prints a table in under 2 minutes.
- AUDIT: every bank's egress log shows `rows_shared: 0`; a deliberately forbidden payload raises; dashboard at :8050 through an SSH tunnel shows egress counters, round AUC curve, privacy meter, rogue exclusions, redteam table.
- GENAI: `python -m fedaml.sar --alert-id <id>` writes a markdown SAR in under 60 s on the VM; `--engine template` always works.

## Demo script skeleton (fill in real numbers from state/)
1. Problem, 20 s: one slide, TMNL shut down, "what if the data never had to move?".
2. `docker ps` on the LinuxONE terminal, 10 s: five banks, coordinator, dashboard on s390x.
3. Dashboard, 40 s: rounds running, global AUC climbing past every single-bank baseline, egress panel "rows shared: 0".
4. Rogue bank, 30 s: bank 5 starts poisoning; coordinator excludes it; AUC holds.
5. Red team, 40 s: `redteam` table, attack accuracy collapses with DP on; privacy meter.
6. SAR, 20 s: the LLM's one-page report for a flagged cross-bank chain.
7. Close, 20 s: IBM data, IBM attack toolkit, IBM Z; measured footprint numbers.

## Report format you expect from every agent (in STATUS.md)
`[HH:MM] AGENT — state: done|in progress|blocked — what works (command to prove it) — what's next — blocker (who can fix)`
