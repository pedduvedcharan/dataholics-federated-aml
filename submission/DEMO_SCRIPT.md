# Demo script — Dataholics — target 2:40, hard cap 3:00

Every number below is filled from a file produced on the LinuxONE VM. The "source" column is the file of
origin; if the file does not exist, the number does not go on screen. Recording: 1280×720, one take per scene,
stitched. Narrators: P1 (scenes 1, 2, 7), P5 (scene 3, 4), P6 (scenes 5, 6).

## Pre-flight (15 min before recording)
```
# Mac terminal A: tunnel for dashboard + coordinator
ssh -L 8050:localhost:8050 -L 8000:localhost:8000 dataholics
# VM: fresh state (nothing else running: no host-side llama-server, no stray python; `uptime` load < 0.5)
cd ~/fedaml && git pull
mkdir -p archive/egress_$(date -u +%H%M%S) && mv logs/egress/*.jsonl archive/egress_$(date -u +%H%M%S)/ 2>/dev/null; true
# ^ archive ONLY the egress logs so the dashboard counters start at 0 (AUDIT 17:10). Do NOT run reset_run.sh before a take:
#   it archives state/, which scenes 5 and 6 need (global_final_dpoff.json, redteam.json, alerts.json, sar/A06.md).
scripts/image_fresh.sh --rebuild                       # ALWAYS (not a bare `docker compose build`): rebuilds only if fedaml/ changed and labels the image with the commit
docker compose run --rm tryleak                        # warm the tryleak layer once (first run ~2 s), reset_run.sh wipes the log after
docker compose up -d dashboard                         # dashboard first, so it is already open (recreated from the fresh image)
scripts/preflight_check.sh                             # must print GO
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
| 3 | Dashboard, training | 0:30–1:10 | P5 | `TAG=dpon BANKS=1,2,3,4 docker compose up -d coordinator bank1 bank2 bank3 bank4` then browser (39 s live; time-lapse in the edit) | "Each bank trains locally; only clipped and noised model updates leave through one audited function. Regulator view: transaction rows shared: **0**. Model parameters shared: twenty-one numbers per bank per round, eight hundred forty in this run, forty messages, zero rows. Global AUC rises from 0.84 to 0.98 over ten rounds with privacy noise on, as it is here; the noise makes the curve wobble. Without the noise the same model reaches 0.992: it matches the best bank's own detector (0.986) and finds far more true laundering per alert than pooling everyone's raw rows would, the thing TMNL did (average precision 0.25 versus 0.09). The noise costs about one point of AUC; that is the price of the guarantee you will see tested in a minute. Banks whose own detectors are weak, like bank 3 at 0.78, get the strong model for free. Bank 1 sits at chance, marked with a star: its laundering is cheque, card and cash from fifteen accounts, invisible to per-row features, so it trains with us but is scored on its own." Then [VM terminal] `docker compose run --rm tryleak` → prints `[try_leak] BLOCKED by egress: forbidden key 'rows' at top level`; [browser] within 3 s the red "Blocked attempts" tile goes **up by one** and the egress tail shows the red BLOCKED line. Say: "Here a bank tries to push five raw transaction rows through the same door. The egress function refuses them, logs the attempt, and the regulator sees it live. Rows shared stays at zero." (~8 s) |
| 4 | Rogue bank | 1:10–1:40 | P5 | Dashboard rogue panel from `status_rogue_off.json` / `status_rogue_on.json` (header: "defense evaluated with DP off") | "Bank 5 poisons its updates to hide its own laundering, a synthetic attack we wrote ourselves. Three layers stop it. Clipping and a cap on claimed sample counts mean one bank cannot reverse the model: even with the screen off, AUC only slips from 0.99 to 0.95. But precision collapses, 0.25 to 0.07, three of four alerts become false. Turn the screen on: the coordinator scores every update against the median, bank 5 is excluded in 10 of 10 rounds, no honest bank is touched, precision is back to 0.25. One honest note: this screen is evaluated without privacy noise, because bank-side noise also hides the poisoned direction." |
| 5 | Red team | 1:40–2:20 | P6 | VM terminal: `docker compose run --rm attacker` (≈39 s on the VM; start it, talk over it; numbers from `state/redteam.json` after the post-run rerun; REDTEAM's 76-word script in `docs/REDTEAM.md`) | "Now we attack our own model. Membership inference: the coordinator, the one party that sees each bank's update, asks whether one real laundering transaction was in bank 3's update this round. **The rows the model remembers are the suspects**, so the game uses laundering rows: with DP off the attacker is right 94 percent of the time, attack AUC 0.99, which means bank 2 could learn which counterparties bank 1 considers suspicious. With DP on, noise added inside each bank before the update leaves, it drops to 51 percent, near chance (σ 0.5, attack AUC 0.517, 90 % interval 0.50 to 0.54; say "near chance", "coin flip" only for σ 0.8). Our first noise level, σ 0.3, still leaked a little at 0.55, so we raised it: we tuned privacy by attacking ourselves. Model cost: 0.992 to 0.982 AUC. The formal ε bound is loose at this setting and we say so; the measured attack is the evidence." Point at the privacy meter. (All-rows result is a footnote on the slide, from `state/redteam.json` `target=all`.) |
| 6 | SAR | 2:20–2:40 | P6 | `cat state/sar/A06.md` (= `meta.demo_alert_id` in `state/alerts.json`; rank 6, 10.8 M Euro ACH) | "For a flagged chain, a small language model running on the LinuxONE CPU writes the analyst's note. It never sees an account number or amount; code writes every fact and checks every claim. This is alert six, a ten-million-euro ACH payment across four banks, ranked for analyst review and labelled laundering in the synthetic data. The queue's top 20 holds two such cases." (~20 s; Qwen2.5-1.5B on llama.cpp, s390x, 35.8 s for this report, `state/sar/_runs.jsonl`. If asked: on our three recorded reports the claim check rejected two LLM drafts and the template wrote them.) |
| 7 | Close | 2:40–2:55 | P1 | Slide: footprint + links | "IBM AML data, open-source attack tooling, IBM Z. Every container together peaks under 1.9 gigabytes, a federated round takes about two seconds, and the whole pipeline runs in just over two minutes. What the Dutch banks had to shut down, built so it would have been legal." |

## Placeholders → file of origin
| Placeholder | Source file (on the VM) | Field |
|---|---|---|
| 21 per update; one live 10-round, 4-bank run = 40 messages, 840 params, 0 rows; blocked 0 → 1 after tryleak | `logs/egress/bank_*.jsonl` (dashboard egress summary) | `totals.params_shared`, `messages`, `rows_shared`, `blocked` |
| AUC_R1, AUC_FINAL | `state/status.json` (`eval_banks: [2,3,4]`) | `rounds[0].global_auc`, `rounds[-1].global_auc` |
| 0.992 / 0.986 / 0.248 vs 0.088 / 0.78 (scene 3) | `state/baselines.json`, `state/status_dpoff.json` | DP-off federated AUC and AP; bank 4 logreg `pooled_auc`; `centralized_logreg.ap`; bank 3 best model `pooled_auc`. Live-run 0.982 from `state/status_dpon.json` |
| 10/10 excluded, 0.992 / 0.250 | `state/status_rogue_on.json` | rounds with bank 5 in `excluded`; `rounds[-1].global_auc`, `.global_ap` |
| 0.953 / 0.071 → 0.992 / 0.250 | `state/status_rogue_off.json` / `state/status_rogue_on.json` | AUC / AP, DP off in both; μ 0.5 archive (`archive/finals_mu05`) shows 0.500 for the footnote |
| attack ~94 % / ~51 %, AUC 0.994 / 0.517, σ 0.3 weak-leak row 0.551 | `state/redteam.json` (`attack: canary_update`, rows "DP off" / "σ 0.3" / "σ 0.5" / "σ 0.8") | `rows[*].attack_acc`, `attack_auc`, `model_auc`; `row_level` is the footnote |
| ε (formal, loose) ≈ 46 | `state/status_dpon.json`, `state/redteam.json` `rows["σ 0.5"].eps_accountant_total` | say "loose, stated as such; measured attack near chance" |
| ALERT_ID, BANKS_INVOLVED | `state/alerts.json` | first alert with ≥2 banks |
| SAR_ENGINE, SAR_SECONDS | `state/sar/<id>.md` footer; `docs/GENAI.md` | engine line; measured seconds |
| 1,880 MB, 2.12 s, 127 s | `state/footprint.json` (21:13 UTC) | `total_peak_rss_mb_sum`; `seconds_per_round`; `total_runtime_s` |

## Timing rule
A live 10-round, 4-bank DP-on run takes **≈ 40 s** (2.12 s per round, measured), so scene 3 can show the whole run live: start it, and the AUC curve fills while you talk.
Scenes 5 and 6 use models and files produced earlier on the VM; say "produced on this machine earlier today".

## Fallbacks (decide before recording, write the choice here)
- Dashboard not ready → scene 3 shows `tail -f logs/egress/bank_1.jsonl` and `cat state/status.json | python3 -m json.tool`.
- Rogue scene plays from archived DP-off files by decision (16:00 CDT); the live run is `run_demo.sh --no-rogue`. If the archived files are lost, cut scene 4 and give its 30 s to scene 5.
- LLM not running on s390x → `--engine template`, say "template engine" on screen; keep scene 6 at 15 s.
- Live run too slow → `ROUNDS=5 docker compose up`, and state the round count on screen.

## Claims discipline (say these words, not others)
**On the amount-feature flaw (if a judge asks):** "The AUC and AP are measured on this model with the flaw included, so they stand. AUC barely moves because it covers the whole ranking. The flaw hurts precision at the top of the queue, which also pulls AP down, so fixing it would likely raise our numbers, not lower them." Never say it has no effect on AP. Future fix: USD conversion with a fixed published rate table, then a fixed cap, then retrain (`docs/FEATURES.md`).
**On the red team:** "near chance" for σ 0.5 (AUC 0.517); "weak leak" for σ 0.3 (0.551); "coin flip" only for σ 0.8; say "AUC", never "detection rate". REDTEAM's 81-word scene-5 script is in `docs/REDTEAM.md`.
**On results (MODELS, final table fcff366):** "matches the best single bank on AUC" (0.992 vs 0.986, slightly above) and "beats centralized pooling on both metrics" are true for the DP-off model (0.992 / 0.248; honest bank 1 sidelined 3/10 rounds, disclosed); the DP-on live run is 0.982 / 0.065, which ties centralized pooling on AUC and trails it on AP, so say "the noise costs about 0.01 AUC and 0.18 AP"; never say "drops to chance" for the rogue (it is 0.953 at μ 0.1); federated trails the best single-bank tree on AP (0.405); "lifts banks whose own models are weak" holds; call the pooled-raw-data row "centralized pooling", never "ceiling" (bank 1's unlearnable rows are 70 % of its training data).
"sandboxed containers" (not Secure Execution) · "synthetic data, synthetic attacks" · "measured on this VM" · "ε is approximate".

## Timing rule for the edit (from rehearsal 1)
The live commands take 39 s (scene 3 run) and 40 s (scene 5 attacker). Played in real time with narration, the cut runs about 3:05, over the 3:00 limit. **Record both waits live, then time-lapse them in the edit with an on-screen label "time-lapse, 39 s real time" / "40 s real time".** Narration drives the scene length, not the command. Never cut away from a command without the label.

## Rehearsal log
| Take | Time (CDT) | Duration | Notes / fixes |
|---|---|---|---|
| 1 (technical, MASTER, commands only) | 16:58–17:06 | commands: scene 2 instant; scene 3 run 39 s + tryleak 0.9 s; scene 5 40 s; scene 6 instant | **Fixed:** scene 3 command `docker compose up --scale rogue=0 <services>` fails ("no such service: rogue: disabled") → list the four banks explicitly. Live DP-on run reproduced model sha `16ef90c0` (bit-identical). `docker ps` capture fired with 4 banks (`submission/screenshots/02_docker_ps.txt`). Dashboard was running a stale untagged image → recreated. Narration timing not yet measured (needs the human narrators). |
| 2 | | | |
