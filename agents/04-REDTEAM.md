# REDTEAM agent — membership inference attacker and the `redteam` command

## Goal
The most memorable 40 seconds of the video: a table showing the attacker reads training membership when DP is off and is reduced to a coin flip when DP is on. Also the attacking half of the rogue-bank demo, with FEDERATION.

## You own
`fedaml/redteam.py`, `state/redteam.json`, `docs/REDTEAM.md` (what the attack is, why it is a fair test, and the honest limits).

## Tasks, in order
1. **Attack v1, loss-threshold (by 15:00).** Given a model JSON (`coef`, `intercept`, `feature_names`), a set of known members (bank 1's train rows, sample 20k) and non-members (`global_test.csv` rows not from bank 1's training window, sample 20k): compute per-row log-loss under the model; predict "member" if loss < threshold chosen on a small calibration split. Report attack accuracy and AUC. Develop against any logreg from MODELS first, then the federated models.
2. **Attack v2, shadow model (if ART installs).** `art.attacks.inference.membership_inference.MembershipInferenceBlackBox` over a `ScikitlearnLogisticRegression` wrapper, trained on shadow data from bank 2. If ART fails on s390x, implement a tiny shadow attack: train a shadow logreg on bank 2, use its member/non-member losses to train a 1-D logistic classifier, apply to the target. Keep v1 as the fallback and state which one ran.
3. **The `redteam` command.** `python -m fedaml.redteam --model-off state/global_final_dpoff.json --model-on state/global_final_dpon.json` runs the attack against both models, prints a table like:
   ```
   setting   model AUC   attack acc   attack AUC   verdict
   DP off      0.93        0.74         0.80       LEAKS
   DP on       0.91        0.52         0.53       PROTECTED
   ```
   and writes `state/redteam.json` per CONTRACTS §6. Must finish in under 2 minutes on the VM.
4. **Rogue-bank evidence.** With FEDERATION, produce the two-line table "defense off: global AUC X; defense on: global AUC Y, bank 5 excluded in N/10 rounds" and put it in STATUS.md with the file paths.
5. **docs/REDTEAM.md.** Half a page: the threat model (honest-but-curious coordinator or any bank that obtains the global model), what membership inference means for a bank customer, why loss-threshold is a standard baseline, and the honest limits: synthetic data, logistic model, one attack family, epsilon is approximate.

## Pitfalls
- If attack accuracy with DP off is barely above 0.5, increase overfitting signal: more local epochs for the dp-off run (ask FEDERATION for `--epochs 5` on that run) or attack a single bank's local model first and say so.
- Balance members and non-members exactly so 0.5 is the true chance level.
- Seeded sampling; the table in the video must reproduce.

## Done when
`state/redteam.json` exists from a run on the VM, the command prints the table in under 2 minutes, and `docs/REDTEAM.md` is written.
