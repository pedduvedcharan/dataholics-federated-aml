# Demo script — Dataholics — target 2:40, hard cap 3:00

Every `{{NUMBER}}` below is filled from a file produced on the LinuxONE VM. The "source" column is the file of
origin; if the file does not exist, the number does not go on screen. Recording: 1280×720, one take per scene,
stitched. Narrators: P1 (scenes 1, 2, 7), P5 (scene 3, 4), P6 (scenes 5, 6).

## Pre-flight (15 min before recording)
```
# Mac terminal A: tunnel for dashboard + coordinator
ssh -L 8050:localhost:8050 -L 8000:localhost:8000 dataholics
# VM: fresh state
cd ~/fedaml && git pull && scripts/reset_run.sh        # INFRA: wipes state/ logs/ keeps data/
docker compose build                                   # only if the image changed
docker compose up -d dashboard                         # dashboard first, so it is already open
# Mac browser: http://localhost:8050  (expect "waiting" panels)
# Confirm these exist from earlier VM runs (they are shown in scenes 5 and 6, not produced live):
ls state/global_final_dpoff.json state/global_final_dpon.json state/redteam.json state/alerts.json state/sar/
```
Terminals on screen: VM terminal (left, large font), browser with dashboard (right). Nothing else visible.

## Scenes

| # | Scene | Time | Narrator | What is on screen | Say |
|---|---|---|---|---|---|
| 1 | Problem | 0:00–0:20 | P1 | Slide 1 | "Criminals split one laundering scheme across several banks; each bank sees only its slice. The Dutch banks pooled raw transactions to fix this and regulators shut it down in 2024. What if the data never had to move?" |
| 2 | IBM Z | 0:20–0:30 | P1 | VM terminal: `uname -m` → s390x, `docker ps` | "Five banks, a coordinator and a regulator dashboard, each a sandboxed container on IBM LinuxONE, s390x, 3 cores, 8 GB." |
| 3 | Dashboard, training | 0:30–1:10 | P5 | `docker compose up -d` then browser | "Each bank trains locally; only clipped and noised model updates leave through one audited function. Regulator view: transaction rows shared: **0**. Model parameters shared: {{PARAMS_SHARED}}. Global AUC climbs from {{AUC_R1}} to {{AUC_FINAL}}, above every single-bank model ({{BEST_SINGLE_AUC}}) and close to the illegal centralized ceiling ({{CENTRAL_AUC}})." Then `docker compose run --rm tryleak` → blocked counter goes to 1: "and when a bank tries to send raw rows, it is refused and logged." |
| 4 | Rogue bank | 1:10–1:40 | P5 | Dashboard rogue panel | "Bank 5 is poisoning its updates to hide its own laundering (synthetic attack). The coordinator scores every update against the median and excludes bank 5 in {{ROGUE_EXCLUDED_ROUNDS}} of {{ROUNDS}} rounds. With the defense off the global AUC fell to {{AUC_DEFENSE_OFF}}; with it on, {{AUC_DEFENSE_ON}}." |
| 5 | Red team | 1:40–2:20 | P6 | VM terminal: `docker compose run --rm attacker` | "Now we attack our own model: membership inference, can an attacker holding the global model tell whether a customer was in a bank's training data? DP off: attack accuracy {{ATTACK_ACC_OFF}}, it leaks. DP on: {{ATTACK_ACC_ON}}, a coin flip, at a model AUC cost of {{AUC_COST}}. Privacy budget spent: ε ≈ {{EPSILON}} (approximate)." Point at the privacy meter. |
| 6 | SAR | 2:20–2:40 | P6 | `cat state/sar/{{ALERT_ID}}.md` | "For a flagged chain across {{BANKS_INVOLVED}} banks, a small CPU LLM on the same box writes the suspicious activity report. The model decides, the LLM narrates; every number and id is inserted by code." ({{SAR_ENGINE}}: {{SAR_SECONDS}} s per report) |
| 7 | Close | 2:40–2:55 | P1 | Slide: footprint + links | "IBM AML data, open-source attack tooling, IBM Z. Peak RAM {{PEAK_RSS_MB}} MB across all containers, {{SEC_PER_ROUND}} s per round, {{TOTAL_RUNTIME}} total. What the Dutch banks had to shut down, built so it would have been legal." |

## Placeholders → file of origin
| Placeholder | Source file (on the VM) | Field |
|---|---|---|
| PARAMS_SHARED | `logs/egress/bank_*.jsonl` (via dashboard `/api/state` egress summary) | `totals.params_shared` |
| AUC_R1, AUC_FINAL | `state/status.json` | `rounds[0].global_auc`, `rounds[-1].global_auc` |
| BEST_SINGLE_AUC, CENTRAL_AUC | `state/baselines.json` | max over `per_bank.*.*.auc`; `centralized_logreg.auc` |
| ROUNDS, ROGUE_EXCLUDED_ROUNDS | `state/status_rogue_on.json` | `total_rounds`; count of rounds with bank 5 in `excluded` |
| AUC_DEFENSE_OFF / AUC_DEFENSE_ON | `state/status_rogue_off.json` / `state/status_rogue_on.json` | `rounds[-1].global_auc` |
| ATTACK_ACC_OFF, ATTACK_ACC_ON, AUC_COST | `state/redteam.json` | `dp_off.attack_acc`, `dp_on.attack_acc`, `model_auc_off - model_auc_on` |
| EPSILON | `state/status.json` | `dp.epsilon_spent` (label "approximate") |
| ALERT_ID, BANKS_INVOLVED | `state/alerts.json` | first alert with ≥2 banks |
| SAR_ENGINE, SAR_SECONDS | `state/sar/<id>.md` footer; `docs/GENAI.md` | engine line; measured seconds |
| PEAK_RSS_MB, SEC_PER_ROUND, TOTAL_RUNTIME | `state/footprint.json` | sum of `per_container_peak_rss_mb`; `seconds_per_round`; `total_runtime_s` |

## Timing rule
A live 10-round, 5-bank run must finish in **< 15 min** (FEDERATION tunes epochs/row caps). Scene 3 does NOT wait for it:
start the run, talk over rounds 1–3, then cut to a pre-recorded or already-finished dashboard for the final AUC.
Scenes 5 and 6 use models and files produced earlier on the VM; say "produced on this machine earlier today".

## Fallbacks (decide before recording, write the choice here)
- Dashboard not ready → scene 3 shows `tail -f logs/egress/bank_1.jsonl` and `cat state/status.json | python3 -m json.tool`.
- Rogue not ready → cut scene 4, give its 30 s to scene 5. (Rogue is last in the cut order; never cut 3 or 5.)
- LLM not running on s390x → `--engine template`, say "template engine" on screen; keep scene 6 at 15 s.
- Live run too slow → `ROUNDS=5 docker compose up`, and state the round count on screen.

## Claims discipline (say these words, not others)
"sandboxed containers" (not Secure Execution) · "synthetic data, synthetic attacks" · "measured on this VM" · "ε is approximate".

## Rehearsal log
| Take | Time (CDT) | Duration | Notes / fixes |
|---|---|---|---|
| 1 | | | |
| 2 | | | |
