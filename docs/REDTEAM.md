# Red team: can the coordinator tell that one suspect's transaction was used?

```
python -m fedaml.redteam --model-off state/global_final_dpoff.json --model-on state/global_final_dpon_s03.json
```
Writes `state/redteam.json`. Seed 42, deterministic (two runs give identical output). **36 s on the
3-core LinuxONE VM**, live, nothing precomputed. Measured on the VM on Oct 17, 20:51 UTC, against
FEDERATION's 10-round runs (σ 0.3 run in `--dp-mode local`):

```
setting                model AUC  attack acc  attack AUC  90% CI         verdict
DP off                     0.988       0.860       0.937  [0.91, 0.97]   LEAKS
σ 0.3                      0.970       0.518       0.525  [0.51, 0.54]   PROTECTED  <- this run
σ 0.5                          -       0.497       0.503  [0.48, 0.53]   PROTECTED
σ 0.8                          -       0.488       0.485  [0.46, 0.51]   PROTECTED
```
*Model AUC* is the pooled AUC on banks 2, 3, 4 test files from `fedaml.baselines.evaluate_model_pooled`,
the same number as the coordinator's status files. `-` means that σ was scored in the game only; no
model trained at that σ was given to this command.

## Video scene 5 (40 s)

On screen: the LinuxONE terminal running the command above, then the table, then `docker ps`.
Narration, 80 words, about 32 s at 150 words per minute, which leaves about 8 s for the command to visibly run:

> Then we attacked ourselves. The coordinator only ever sees each bank's model update. Can it tell whether one specific suspect's transaction was in bank three's update? That is the secret banks may not share. We ran the test a hundred times with that transaction and a hundred without. Privacy off: the attacker is right eighty-six percent of the time. Turn on bank-side noise: fifty-two percent, near chance. The cost: model AUC drops from point nine nine to point nine seven.

Every number is from `state/redteam.json`: attack acc 0.860 vs 0.518, model AUC 0.988 vs 0.970.
Say "on synthetic data" in the caption. Do not say "detection rate": AUC is a ranking score.
If the demo σ changes, rerun the command and update the two percentages and the AUCs.

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
reused read-only, from the round-1 starting point. Clipping and noise are FEDERATION's
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
update most. With the same training seed, adding it moves bank 3's update by about half of the
update's norm. What hides it is noise, not size.

## Results across banks (robustness)

Same game, `python -m fedaml.redteam_canary --bank <b> --trials 100`, files `state/redteam_canary_bank<b>.json`:

| bank | DP off | σ 0.3 | σ 0.5 | σ 0.8 |
|---|---|---|---|---|
| 2 | 0.862 [0.82, 0.91] LEAKS | 0.492 | 0.495 | 0.505 |
| 3 | 0.937 [0.91, 0.97] LEAKS | 0.525 | 0.503 | 0.485 |
| 4 | 0.865 [0.82, 0.91] LEAKS | 0.528 | 0.517 | 0.477 |

Attack AUC with 90 % CI. Every DP-on cell is PROTECTED, and all nine are within 0.03 of 0.5. At σ 0.3 the interval on banks 3 and 4 just excludes 0.5 (bank 3: 0.51–0.54), so call σ 0.3 "near chance" and keep "coin flip" for σ 0.5 and 0.8, whose intervals include 0.5.

## Footnote 1: row-level attacks on the real data are at chance even without DP

The classic membership-inference attacks were run and are kept in `redteam.json` under `row_level`:
loss-threshold (Yeom et al. 2018), shadow model trained on bank 5 (Shokri et al. 2017), and IBM ART
1.20.1 `MembershipInferenceBlackBox`. Against the final global model they score:

| target | DP off | DP on σ 0.3 |
|---|---|---|
| laundering rows, banks 2–4 train vs same banks' test (64 per class) | 0.544 [0.46, 0.63] | 0.478 [0.39, 0.58] |
| all rows (20 000 per class) | 0.512 | 0.517 |
| laundering rows vs mixed-bank `global_test.csv` (distribution-shift check) | 0.700 | 0.565 |

An attack on the persisted per-round updates (`fedaml.redteam_updates`) scored 0.548 with DP off.
That run reads FEDERATION's central-mode payloads in `state/updates/`.

Why no row-level leak: the shared model is a 21-parameter logistic regression, and the learnable
laundering is about 100 near-identical ACH payments in banks 2–4. The test laundering rows belong
to the same accounts as the training rows, so "member" and "non-member" laundering rows look the
same to any per-row attack. **This is a property of this model and this synthetic data, not a
privacy guarantee.** That is why the headline is the auditing game, which measures what one row
does to what leaves a bank. The 0.700 against `global_test.csv` is distribution shift, not
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

`fedaml.dp` reports approximately ε ≈ 19.1 for one round and ε ≈ 99.7 over 10 rounds at σ 0.3
(δ = 1e-5). Its unit is one bank's whole update. **A formal ε of 100 is a very weak guarantee and we
say so.** The measurement says something different: the strongest standard attacker is at or near chance (AUC 0.48–0.53) for
a single flagged transaction at every σ we tried. From the DP-off attack we also report an empirical
lower bound of ε ≥ 0.84 at 95 % confidence (Clopper-Pearson). That number states how much a single
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
- **Utility cost is real.** Pooled AUC on banks 2–4 is 0.988 with DP off and 0.970 with σ 0.3 local.
  The best single-bank model reaches 0.986 pooled (`state/baselines.json`). With DP on, the federated
  model is close to the best single bank but does not beat it.
- **Attacks are synthetic and self-run.** We attack our own system; no third party audited it.

## Reproduce

```
. ~/fedaml/.venv/bin/activate && cd ~/fedaml
python -m fedaml.redteam --model-off state/global_final_dpoff.json --model-on state/global_final_dpon_s03.json
python -m fedaml.redteam_canary --bank 2 --trials 100            # robustness, per bank
python -m fedaml.redteam --selftest                               # no federated model needed
python -m fedaml.redteam_updates --updates-off state/updates/dpoff --updates-on state/updates/dpon_s03
```
`state/redteam.json` keys: `attack` ("canary_update"), `target`, CONTRACTS §6 `dp_off`/`dp_on`
(`attack_acc`, `attack_auc`, `attack_auc_ci90`, `n`, `verdict`), `model_auc_off`/`model_auc_on`,
`current_sigma`, `current_setting`, `rows` keyed `"DP off"`, `"σ 0.3"`, `"σ 0.5"`, `"σ 0.8"`, each with
`sigma, attack_acc, attack_auc, attack_auc_ci90, tpr, fpr, eps_empirical_lower_95, eps_accountant_1round,
eps_accountant_total, verdict, n, model, model_auc, dp_mode, coordinator_sees_noised_update[, warning]`,
`row_level` (footnote attacks), `game`, `seed`, `runtime_s`.
