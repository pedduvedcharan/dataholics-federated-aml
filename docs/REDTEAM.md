# Red team: membership inference against the shared AML model

`python -m fedaml.redteam --model-off state/global_final_dpoff.json --model-on state/global_final_dpon.json`
prints the table below and writes `state/redteam.json`. Everything is seeded (`--seed 42`) and
runs in well under two minutes on the 3-core LinuxONE VM (synthetic dry run: 2.5 s).

```
setting                      model AUC  attack acc  attack AUC   verdict
DP off / laundering rows     {{RT_MODEL_AUC_OFF}}   {{RT_ACC_OFF}}   {{RT_AUC_OFF}}   {{RT_VERDICT_OFF}}
DP on  / laundering rows     {{RT_MODEL_AUC_ON}}    {{RT_ACC_ON}}    {{RT_AUC_ON}}    {{RT_VERDICT_ON}}
  footnote, all rows, same-bank non-members:            DP off: {{RT_ALL_OFF}};  DP on: {{RT_ALL_ON}}
  footnote, laundering rows, mixed-bank hold-out:       DP off: {{RT_SHIFT_OFF}}; DP on: {{RT_SHIFT_ON}}
```
Numbers are filled from `state/redteam.json` produced on the VM; nothing here is estimated.
Model AUC is measured on bank 1's own `test.csv` (the coordinator evaluates on per-bank test files too);
the AUC on `global_test.csv` is kept in `redteam.json` under `model_auc_global_test_*`.

## Threat model

The federation never moves a transaction between banks. What does move is the model: every bank
and the coordinator hold the global weights after each round, and anyone who obtains a round file
(`state/global_round_<r>.json`) holds them too. The attacker here is **honest-but-curious**: it
follows the protocol, but uses the model it legitimately receives to learn something about another
bank's customers. Concretely it holds a candidate transaction row (with its label) and asks:
*was this row in bank 1's training set?*

That question matters because of what "in the training set" implies. Bank 1's training rows are
bank 1's customers' transactions. A laundering row in bank 1's training set means bank 1 holds
that account and has it labelled as laundering. If bank 2 can tell, from the shared model alone,
which flagged transactions came from bank 1, it has learned which of its counterparties bank 1
considers suspicious. That is exactly the kind of disclosure that made raw data pooling illegal
in the Netherlands (TMNL) and that bank-secrecy rules forbid. Membership inference is the
standard way the privacy literature measures this leak.

## The attack

**Loss-threshold (Yeom et al., 2018).** Models fit their training rows better than unseen rows,
so the per-row log-loss is lower on members. The attacker computes the loss of a row under the
shared model and says "member" if it falls below a threshold. The threshold is chosen on a
20 % calibration split and accuracy is reported on the other 80 %, so the number is honest.
Attack AUC uses the loss itself as the score and needs no threshold. This is the baseline every
membership-inference paper reports against: it needs nothing but the model and the row, and when
differential privacy is correctly applied it is provably bounded, which is what the DP-on row is
meant to show.

**Shadow model (Shokri et al., 2017), 1-D variant.** A shadow logistic model is trained on bank 2
with the banks' own recipe. Its losses on rows it trained on versus rows it did not train on
teach a tiny 1-D classifier *loss → P(member)*, which is then applied to the target model's
losses. It uses no membership labels from the target, so it models an attacker who has only
public-shaped data of their own.

**ART black box.** When IBM's Adversarial Robustness Toolbox is installed (it is, on the VM:
`adversarial-robustness-toolbox 1.20.1`), `MembershipInferenceBlackBox` with a random-forest
attack model over the target's predicted probability and the true label runs as well. It is
fitted on the calibration split of real members and non-members, so it is the strongest and
least realistic of the three. The CLI prefers ART, then shadow, then loss-threshold, and
`state/redteam.json` records which one produced the headline (`"attack"`); the loss-threshold
baseline is always computed and stored alongside under `detail`.

**Who is a member, who is not.** Members are a seeded sample of bank 1's `train.csv`.
Non-members are rows the model never saw. The primary source is bank 1's own later `test.csv`:
same bank, same customers' habits, later time, featurised together with `train.csv` so the
within-bank account aggregates are consistent. That keeps the comparison about *memorisation*
rather than about which bank a row came from. The footnote repeats the laundering-row attack with
non-members from `data/global_test.csv` (the mixed-bank hold-out, rows dated after bank 1's
training window) to show how much apparent "leak" distribution shift alone creates. Members and
non-members are sampled in **exactly equal numbers**, so 0.5 is the true chance level.

**Two target populations.** The attack is run on *all rows* (20 000 vs 20 000) and on
*laundering rows only* (every laundering row of bank 1's training set against an equal number of
unseen laundering rows). The laundering rows are the headline. With a 1-in-1000 base rate and
`class_weight="balanced"`, the model fits each laundering row roughly a thousand times harder
than a normal payment, so that is where memorisation, and the privacy harm, concentrates:
the people a leak hurts are the ones the model remembers. On all rows the attack sits at chance
even without DP, which `redteam.json` also records.

## Verdicts

| attack AUC | verdict |
|---|---|
| ≥ 0.60 | **LEAKS** |
| 0.55 – 0.60 | WEAK LEAK |
| < 0.55 | **PROTECTED** (indistinguishable from a coin flip at this sample size) |

## Honest limits

- **Synthetic data.** The IBM AML dataset is simulated. The laundering patterns and account
  behaviour are generated, so attack strength on real bank data could be higher or lower.
- **One model family.** The shared model is a 20-feature logistic regression. Convex, low-capacity
  models memorise little; a neural network or a tree ensemble would leak more and would make DP
  look better. We attack the model we actually deploy.
- **One attack family.** All three variants are black-box inference from loss or predicted
  probability. We do not run gradient-based attacks on the per-round updates the coordinator sees,
  attribute inference, or model inversion.
- **Distribution shift is a confound.** Bank 1's rows differ from the mixed-bank hold-out even
  without any memorisation, and a loss threshold can pick that up. On our synthetic dry run the
  hold-out produced an apparent leak (AUC ≈ 0.65) that the same-bank control did not (AUC ≈ 0.50),
  and the number did not move with more training epochs, which is the signature of shift rather
  than memorisation. The headline therefore uses same-bank non-members and the hold-out appears
  only as the footnote.
- **Small positive class.** Each of the four busiest banks has only a few hundred to a few thousand
  laundering rows, so the laundering-row attack is evaluated on hundreds of rows per class. The
  standard error of an AUC at that size is roughly ±0.02–0.03; `redteam.json` records `n`.
- **Epsilon is approximate.** The DP accounting in `fedaml/dp.py` is a Gaussian-mechanism estimate
  over rounds, not a tight composition bound, and the clip norm and noise were chosen for the demo.
  The red-team result is an empirical measurement, not a proof; it shows the attack collapsing, not
  that no attack exists.
- **Selftest model is not the federated model.** `--selftest` trains one bank's local model on the
  member sample only (20 epochs) so the attack can be validated before federated models exist. It
  is deliberately overfit and is never used in the headline table.

## Reproduce

```
. ~/fedaml/.venv/bin/activate && cd ~/fedaml
python -m fedaml.redteam --selftest                                   # no federated model needed
python -m fedaml.redteam --model-off state/global_final_dpoff.json --model-on state/global_final_dpon.json
python -m fedaml.redteam ... --attack loss_threshold                  # baseline only
```
Outputs: `state/redteam.json` (CONTRACTS §6 keys plus `target`, `verdict`, `n_per_class`,
`seed`, `runtime_s`, `model_auc_global_test_*`, and `detail` with every attack variant and all
three populations: `laundering`, `all`, `laundering@global_test`).
