# Red team: can the coordinator tell that one suspect's transaction was used?

```
python -m fedaml.redteam --model-off state/global_final_dpoff.json --model-on state/global_final_dpon.json
```
Writes `state/redteam.json`. Seed 42, deterministic (two runs give identical output). **38 s on the
3-core LinuxONE VM**, live, nothing precomputed. Written by the integration run's attacker step on
Oct 17, 21:13 UTC, against the final 10-round models (μ 0.1, `--dp-mode local`, DP-on σ 0.5):

```
setting                model AUC  attack acc  attack AUC  90% CI         verdict
DP off                     0.992       0.940       0.994  [0.99, 1.00]   LEAKS
σ 0.3                          -       0.533       0.551  [0.53, 0.57]   WEAK LEAK
σ 0.5                      0.982       0.512       0.517  [0.50, 0.54]   PROTECTED  <- this run
σ 0.8                          -       0.500       0.497  [0.48, 0.52]   PROTECTED
```
*Model AUC* is the pooled AUC on banks 2, 3, 4 test files from `fedaml.baselines.evaluate_model_pooled`,
the same number as the coordinator's status files. `-` means that σ was scored in the game only; no
model trained at that σ was given to this command.

## Video scene 5 (40 s)

On screen: the LinuxONE terminal running the command above, the table with the σ 0.5 row marked
"this run" and the σ 0.3 row reading WEAK LEAK, then `docker ps`.
Narration, 80 words, about 32 s at 150 words per minute:

> Then we attacked ourselves. The coordinator only ever sees each bank's model update. Can it tell whether one specific suspect's transaction was in bank three's update? We ran the test a hundred times with that transaction and a hundred without. Privacy off: the attacker is right ninety-four percent of the time. Our first noise level still leaked a little, so we raised it. Now: fifty-one percent, near chance. The cost: model AUC from point nine nine to point nine eight.

Every number is from `state/redteam.json` (21:13 UTC): attack accuracy 0.940 vs 0.512, model AUC
0.992 vs 0.982. "Still leaked a little" is the σ 0.3 row: attack AUC 0.551, 90 % CI 0.53–0.57.
Say "near chance" for σ 0.5, not "coin flip". Do not say "detection rate": AUC is a ranking score.
Caption: "synthetic data, attack run by us".

## What is attacked, and by whom

**Threat model.** An honest-but-curious coordinator. It follows the protocol but studies the one thing
that leaves a bank each round: the bank's model update, `delta = local weights - global weights`.
The question is the one bank secrecy actually cares about. Take a single real flagged transaction,
here bank 3's held-out laundering row #3627. Can the coordinator tell from bank 3's update whether
that transaction was in bank 3's training data? If yes, the coordinator learns that bank 3 holds and
has flagged that customer, which is exactly what TMNL-style pooling was stopped for.

**The game** (DP auditing, Jagielski et al. 2020; Nasr et al. 2021). World IN: bank 3 computes its
round update on its data plus the target row. World OUT: the same, without it. Each trial uses a
fresh random 90 % of bank 3's other rows, in both worlds, so the attacker does not know the bank's
exact data. Training is FEDERATION's own default trainer: FedProx-style L-BFGS from `fedaml.bank`,
reused read-only, with the banks' μ 0.1 (env `MU`), from the round-1 starting point. Clipping and noise are FEDERATION's
`fedaml.dp.privatize`, clip norm 1.0. 100 trials per world.

**The attacker** is the strongest standard one: it knows the training recipe. On the 50 calibration
trials it simulates noise-free training to learn the direction in which the target row moves the
clipped update. For Gaussian noise, projecting onto that direction is the likelihood-ratio test.
It sets a threshold on the calibration trials and is scored on the other 50 trials per world. With
DP on, every update is released 20 times with fresh noise. Confidence intervals bootstrap over
trials, not over noise draws, so the repeats cannot fake precision. The noise is seeded per
(seed, bank, σ), so banks are independent evidence.

**Target row choice.** DP must protect every row, so the honest test is the worst case. The target is
the held-out laundering row the starting model scores lowest, the suspect whose inclusion moves the
update most. At μ 0.1 a bank's raw update has norm about 1.39, so the clip at 1.0 is active, and the
target row moves the update by 0.075 on average (`raw_in_minus_out_norm_mean` in
`state/redteam_canary_bank3.json`). DP noise at σ 0.5 has standard deviation 0.5 per coordinate.

## Results across banks (robustness)

Same game at μ 0.1, `python -m fedaml.redteam_canary --bank <b> --trials 100 --mu 0.1`, files
`state/redteam_canary_bank<b>.json` (VM, 21:16 UTC):

| bank | DP off | σ 0.3 | σ 0.5 | σ 0.8 |
|---|---|---|---|---|
| 2 | 0.791 [0.75, 0.84] LEAKS | 0.493 | 0.492 | 0.503 |
| 3 | 0.994 [0.99, 1.00] LEAKS | **0.551 [0.53, 0.57] WEAK LEAK** | 0.517 [0.50, 0.54] | 0.497 |
| 4 | 0.890 [0.84, 0.94] LEAKS | 0.537 [0.52, 0.56] | 0.528 [0.51, 0.55] | 0.487 |

Attack AUC with 90 % CI. **We tuned σ by attacking ourselves.** At μ 0.5 every σ ≥ 0.3 was
protected. Moving to μ 0.1 made updates larger and σ 0.3 leaked a little on bank 3, so the demo
uses σ 0.5. All σ 0.5 and 0.8 cells are PROTECTED. Bank 4's σ 0.5 interval excludes 0.5 by 0.01,
so the honest word is "near chance".

## Footnote 1: row-level attacks on the real data are at chance even without DP

The classic membership-inference attacks were run and are kept in `redteam.json` under `row_level`:
loss-threshold (Yeom et al. 2018), shadow model trained on bank 5 (Shokri et al. 2017), and IBM ART
1.20.1 `MembershipInferenceBlackBox`. Against the final global model they score:

| target | DP off | DP on σ 0.5 |
|---|---|---|
| laundering rows, banks 2–4 train vs same banks' test (64 per class) | 0.520 [0.43, 0.63] | 0.505 [0.41, 0.61] |

These are ART black-box results from `row_level` in `state/redteam.json`. The command also prints
two footnote populations that the JSON does not store. All rows (20 000 per class) score about 0.51.
Laundering rows against the mixed-bank `global_test.csv` score about 0.70 with DP off. Those two were
measured on the earlier μ 0.5 models, so do not put them on a slide.

An attack on the persisted per-round updates (`fedaml.redteam_updates`) scored 0.548 with DP off.
That run reads FEDERATION's central-mode payloads in `state/updates/`.

Why no row-level leak: the shared model is a 21-parameter logistic regression, and the learnable
laundering is about 100 near-identical ACH payments in banks 2–4. The test laundering rows belong
to the same accounts as the training rows, so "member" and "non-member" laundering rows look the
same to any per-row attack. **This is a property of this model and this synthetic data, not a
privacy guarantee.** That is why the headline is the auditing game, which measures what one row
does to what leaves a bank. The ~0.70 against `global_test.csv` is distribution shift, not
memorisation: the same-bank control shows nothing, and the number does not grow with training. It
is shown so nobody mistakes it for a leak.

## Which banks, and how many rows

- **Bank 1 is excluded from every red-team population.** Its laundering is invisible to per-row
  features. Logistic regression reaches 0.530 test AUC on bank 1 and HistGradientBoosting 0.522; the
  federated model scores 0.46 on bank 1. Its 511 training laundering rows come from 15 accounts.
  Nothing a model cannot fit can be memorised, so attacking bank 1 would be chance by construction.
  Bank 1 still trains in the federation.
- Row-level members are banks 2, 3, 4's training laundering rows: 102 in total, 45 / 33 / 24. Their
  test files hold 64 laundering rows, so the laundering population is **64 members vs 64 non-members**.
  The all-rows population is 20 000 vs 20 000. The shadow bank is bank 5.
- The game uses one target row per bank and 100 trials per world. 50 calibrate, and 50 per world are
  scored.

## Verdicts

| attack AUC | verdict |
|---|---|
| ≥ 0.60 | **LEAKS** |
| 0.55–0.60 | WEAK LEAK |
| < 0.55 | **PROTECTED** (near chance; "coin flip" only when the 90 % CI includes 0.5) |

## Epsilon, honestly

`fedaml.dp` reports approximately ε ≈ 10.0 for one round and ε ≈ 46.2 over 10 rounds at σ 0.5
(δ = 1e-5). Its unit is one bank's whole update. **A formal ε of 46 is a very weak guarantee and we
say so.** The measurement says something different: the strongest standard attacker is at or near chance (AUC 0.49–0.53) for
a single flagged transaction at σ 0.5 and 0.8 on every bank; σ 0.3 leaked a little on bank 3. From the DP-off attack we also report an empirical
lower bound of ε ≥ 1.34 at 95 % confidence (bank 3) (Clopper-Pearson). That number states how much a single
row demonstrably leaks without noise, not a property of the DP-on system. The gap is expected: the
guarantee covers a bank's entire update, and one row is a tiny part of it.

## What this does not show

- **Synthetic data.** IBM's AML dataset is simulated, so real bank data may behave differently.
- **One model family.** A logistic regression memorises little. A neural network or a tree ensemble
  would leak more at the row level, and DP would matter more there.
- **One round, one target per bank, round-1 start.** Ten rounds give the attacker ten looks, and the
  formal ε composes for that. Empirically we score a single round. The target is the worst-case row
  of each bank's test file, not every row.
- **DP mode matters.** In `--dp-mode central` the coordinator adds the noise, so it receives the
  un-noised update and sits on the DP-off row. The command prints a warning when a model was trained
  in central mode. The demo runs `--dp-mode local`, where banks noise before `egress.send`.
- **Utility cost is real.** Pooled AUC on banks 2–4 is 0.992 with DP off and 0.982 with σ 0.5 local
  (`state/redteam.json`). The best single-bank model reaches 0.986 pooled (`state/baselines.json`).
  With DP on, the federated model is just below the best single bank and does not beat it.
- **Attacks are synthetic and self-run.** We attack our own system; no third party audited it.

## Reproduce

```
. ~/fedaml/.venv/bin/activate && cd ~/fedaml
python -m fedaml.redteam --model-off state/global_final_dpoff.json --model-on state/global_final_dpon.json
python -m fedaml.redteam_canary --bank 2 --trials 100 --mu 0.1   # robustness, per bank
python -m fedaml.redteam --selftest                               # no federated model needed
python -m fedaml.redteam_updates --updates-off state/updates/dpoff --updates-on state/updates/dpon_s03
```
`state/redteam.json` keys: `attack` ("canary_update"), `target`, CONTRACTS §6 `dp_off`/`dp_on`
(`attack_acc`, `attack_auc`, `attack_auc_ci90`, `n`, `verdict`), `model_auc_off`/`model_auc_on`,
`current_sigma`, `current_setting`, `rows` keyed `"DP off"`, `"σ 0.3"`, `"σ 0.5"`, `"σ 0.8"`, each with
`sigma, attack_acc, attack_auc, attack_auc_ci90, tpr, fpr, eps_empirical_lower_95, eps_accountant_1round,
eps_accountant_total, verdict, n, model, model_auc, dp_mode, coordinator_sees_noised_update[, warning]`,
`row_level` (footnote attacks), `game`, `seed`, `runtime_s`.
