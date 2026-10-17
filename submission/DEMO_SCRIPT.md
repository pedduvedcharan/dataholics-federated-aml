# Demo script — Dataholics — target 2:40, hard cap 3:00

Every `{{NUMBER}}` below is filled from a file produced on the LinuxONE VM. The "source" column is the file of
origin; if the file does not exist, the number does not go on screen. Recording: 1280×720, one take per scene,
stitched. Narrators: P1 (scenes 1, 2, 7), P5 (scene 3, 4), P6 (scenes 5, 6).

## Pre-flight (15 min before recording)
```
# Mac terminal A: tunnel for dashboard + coordinator
ssh -L 8050:localhost:8050 -L 8000:localhost:8000 dataholics
# VM: fresh state (nothing else running: no host-side llama-server, no stray python; `uptime` load < 0.5)
cd ~/fedaml && git pull && scripts/reset_run.sh --down # INFRA: wipes state/ logs/ keeps data/; --down recreates compose containers
docker compose build                                   # ALWAYS: the image COPYs fedaml/ at build time, so every git pull needs a build
docker compose run --rm tryleak                        # warm the tryleak layer once (first run ~2 s), reset_run.sh wipes the log after
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
| 3 | Dashboard, training | 0:30–1:10 | P5 | `docker compose up -d` then browser | "Each bank trains locally; only clipped and noised model updates leave through one audited function. Regulator view: transaction rows shared: **0**. Model parameters shared: {{PARAMS_SHARED}}. Global AUC climbs over the rounds to 0.97 with privacy noise on, as it is here. Without the noise the same model reaches 0.988: it matches the best bank's own detector (0.986) and finds more true laundering per alert than pooling everyone's raw rows would, the thing TMNL did (average precision 0.152 vs 0.088). The noise costs about two points of AUC; that is the price of the guarantee you will see tested in a minute. Banks whose own detectors are weak, like bank 3 at 0.78, get the strong model for free. Bank 1 sits at chance, marked with a star: its laundering is cheque, card and cash from fifteen accounts, invisible to per-row features, so it trains with us but is scored on its own." Then [VM terminal] `docker compose run --rm tryleak` → prints `[try_leak] BLOCKED by egress: forbidden key 'rows' at top level`; [browser] within 3 s the red "Blocked attempts" tile goes **up by one** and the egress tail shows the red BLOCKED line. Say: "Here a bank tries to push five raw transaction rows through the same door. The egress function refuses them, logs the attempt, and the regulator sees it live. Rows shared stays at zero." (~8 s) |
| 4 | Rogue bank | 1:10–1:40 | P5 | Dashboard rogue panel, loaded from the archived defense runs (`status_rogue_off.json` / `status_rogue_on.json`; header says "defense evaluated with DP off") | "Bank 5 is poisoning its updates to hide its own laundering, a synthetic attack we wrote ourselves. With the defense off the global model collapses to AUC 0.50. With it on, the coordinator scores every update against the median: bank 5 is excluded in 10 of 10 rounds, no honest bank is touched, and the model holds at 0.99. One honest finding: this screen is evaluated without privacy noise, because bank-side noise also hides the poisoned direction; privacy and robustness pull against each other, and we say so." |
| 5 | Red team | 1:40–2:20 | P6 | VM terminal: `docker compose run --rm attacker` (36 s on the VM; start it, talk over it; numbers from `state/redteam.json` sha a2a1bac2) | "Now we attack our own model. Membership inference: the coordinator, the one party that sees each bank's update, asks whether one real laundering transaction was in bank 3's update this round. **The rows the model remembers are the suspects**, so the game uses laundering rows: with DP off the attack gets 0.86 accuracy, attack AUC 0.94, which means bank 2 could learn which counterparties bank 1 considers suspicious. With DP on, noise added inside each bank before the update leaves, it drops to 0.52, near chance (the 90 % interval is 0.51 to 0.54, so say "near chance", not "coin flip"; σ 0.5 and 0.8 are true coin flips at 0.50 and 0.49), at a measured model cost of 0.018 AUC (0.988 to 0.970). The formal ε bound is loose at this setting and we say so; the measured attack is the evidence." Point at the privacy meter. (All-rows result is a footnote on the slide, from `state/redteam.json` `target=all`.) |
| 6 | SAR | 2:20–2:40 | P6 | `cat state/sar/{{ALERT_ID}}.md` | "For a flagged chain across {{BANKS_INVOLVED}} banks, a small CPU LLM on the same box writes the suspicious activity report. The model decides, the LLM narrates; every number and id is inserted by code." ({{SAR_ENGINE}}: {{SAR_SECONDS}} s per report) |
| 7 | Close | 2:40–2:55 | P1 | Slide: footprint + links | "IBM AML data, open-source attack tooling, IBM Z. Peak RAM {{PEAK_RSS_MB}} MB across all containers, {{SEC_PER_ROUND}} s per round, {{TOTAL_RUNTIME}} total. What the Dutch banks had to shut down, built so it would have been legal." |

## Placeholders → file of origin
| Placeholder | Source file (on the VM) | Field |
|---|---|---|
| PARAMS_SHARED | `logs/egress/bank_*.jsonl` (via dashboard `/api/state` egress summary) | `totals.params_shared` |
| AUC_R1, AUC_FINAL | `state/status.json` (`eval_banks: [2,3,4]`) | `rounds[0].global_auc`, `rounds[-1].global_auc` |
| 0.988 / 0.986 / 0.152 vs 0.088 / 0.78 (scene 3) | `state/baselines.json`, `state/status_dpoff.json` | DP-off federated AUC and AP; bank 4 logreg `pooled_auc`; `centralized_logreg.ap`; bank 3 best model `pooled_auc`. Live-run 0.970 from `state/status_dpon.json` |
| 10/10 excluded, 0.989 | `state/status_rogue_on.json` | `total_rounds`; rounds with bank 5 in `excluded`; `rounds[-1].global_auc` |
| 0.500 / 0.989 | `state/status_rogue_off.json` / `state/status_rogue_on.json` | `rounds[-1].global_auc` (DP off in both; local-DP run `status_rogue_on_dp.json` is the disclosure) |
| attack 0.86 / 0.52, AUC 0.94 / 0.525, cost 0.018 | `state/redteam.json` (`attack: canary_update`, rows "DP off" / "σ 0.3") | `rows[*].attack_acc`, `attack_auc`, `model_auc`; `row_level` is the footnote |
| ε (formal, loose) ≈ 100 | `state/status_dpon.json`, `state/redteam.json` `rows["σ 0.3"].eps_accountant_total` | say "loose, stated as such; measured attack at chance" |
| ALERT_ID, BANKS_INVOLVED | `state/alerts.json` | first alert with ≥2 banks |
| SAR_ENGINE, SAR_SECONDS | `state/sar/<id>.md` footer; `docs/GENAI.md` | engine line; measured seconds |
| PEAK_RSS_MB, SEC_PER_ROUND, TOTAL_RUNTIME | `state/footprint.json` | sum of `per_container_peak_rss_mb`; `seconds_per_round`; `total_runtime_s` |

## Timing rule
A live 10-round, 5-bank run must finish in **< 15 min** (FEDERATION tunes epochs/row caps). Scene 3 does NOT wait for it:
start the run, talk over rounds 1–3, then cut to a pre-recorded or already-finished dashboard for the final AUC.
Scenes 5 and 6 use models and files produced earlier on the VM; say "produced on this machine earlier today".

## Fallbacks (decide before recording, write the choice here)
- Dashboard not ready → scene 3 shows `tail -f logs/egress/bank_1.jsonl` and `cat state/status.json | python3 -m json.tool`.
- Rogue scene plays from archived DP-off files by decision (16:00 CDT); the live run is `run_demo.sh --no-rogue`. If the archived files are lost, cut scene 4 and give its 30 s to scene 5.
- LLM not running on s390x → `--engine template`, say "template engine" on screen; keep scene 6 at 15 s.
- Live run too slow → `ROUNDS=5 docker compose up`, and state the round count on screen.

## Claims discipline (say these words, not others)
**On the red team:** "near chance" for σ 0.3 (AUC 0.525, CI excludes 0.5); "coin flip" only for σ 0.5 / 0.8; say "AUC", never "detection rate". REDTEAM's 81-word scene-5 script is in `docs/REDTEAM.md`.
**On results (MODELS, final table fcff366):** "matches the best single bank on AUC" and "beats centralized pooling on average precision" are true ONLY for the DP-off model (0.988 / 0.152); the DP-on live run is 0.970 / 0.056, so say "the noise costs about 0.02 AUC and 0.10 AP"; "lifts banks whose own models are weak" holds; call the pooled-raw-data row "centralized pooling", never "ceiling" (bank 1's unlearnable rows are 70 % of its training data).
"sandboxed containers" (not Secure Execution) · "synthetic data, synthetic attacks" · "measured on this VM" · "ε is approximate".

## Rehearsal log
| Take | Time (CDT) | Duration | Notes / fixes |
|---|---|---|---|
| 1 | | | |
| 2 | | | |
