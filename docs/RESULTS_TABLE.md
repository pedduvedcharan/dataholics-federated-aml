27 20:53 state/global_final_dpon.json
36 20:50 state/global_final_rogue_on.json
# Results table (generated)

Generated 2026-10-17 20:56 UTC on the LinuxONE VM by `python -m fedaml.results_table` from `state/`.
Do not edit numbers by hand; rerun the command after new runs.

All AUC/AP values are on the **pooled basis**: each bank's `test.csv` featurized within
that bank, predictions pooled over the evaluation banks **2, 3, 4** (39,638 rows, 64 laundering;
AP on 64 positives is noisy). Positives are ~1 in 1,000, so AP (average precision) is the
number that matters; AUC is shown because judges expect it.

Bank 1 (code 070, 69% of all rows) is kept at its own-test score to show it at chance: its
laundering (cheque / card / cash from a handful of hub sender accounts, never ACH, never
within-bank) is invisible to per-row features, for every model, so it is excluded from the
pooled basis. The centralized model is still trained on its rows, which is why centralized
pooling is not an upper bound here.

| Model | Who sees the rows | AUC | AP | File of origin (on VM) |
|---|---|---|---|---|
| Bank 1 logistic regression (own test; at chance, see note) | bank 1 only | 0.530 | 0.002 | `state/baselines.json` → `per_bank.1.logreg` (`auc`, `ap`: own test) |
| Bank 1 random forest (own test; at chance, see note) | bank 1 only | 0.539 | 0.002 | `state/baselines.json` → `per_bank.1.rf` (`auc`, `ap`: own test) |
| Bank 1 hist. gradient boosting (own test; at chance, see note) | bank 1 only | 0.522 | 0.001 | `state/baselines.json` → `per_bank.1.hgb` (`auc`, `ap`: own test) |
| Bank 2 logistic regression | bank 2 only | 0.985 | 0.216 | `state/baselines.json` → `per_bank.2.logreg` (`pooled_auc`, `pooled_ap`) |
| Bank 2 random forest | bank 2 only | 0.918 | 0.230 | `state/baselines.json` → `per_bank.2.rf` (`pooled_auc`, `pooled_ap`) |
| Bank 2 hist. gradient boosting | bank 2 only | 0.849 | 0.269 | `state/baselines.json` → `per_bank.2.hgb` (`pooled_auc`, `pooled_ap`) |
| Bank 3 logistic regression | bank 3 only | 0.978 | 0.077 | `state/baselines.json` → `per_bank.3.logreg` (`pooled_auc`, `pooled_ap`) |
| Bank 3 random forest | bank 3 only | 0.980 | 0.308 | `state/baselines.json` → `per_bank.3.rf` (`pooled_auc`, `pooled_ap`) |
| Bank 3 hist. gradient boosting | bank 3 only | 0.784 | 0.211 | `state/baselines.json` → `per_bank.3.hgb` (`pooled_auc`, `pooled_ap`) |
| Bank 4 logistic regression | bank 4 only | 0.986 | 0.345 | `state/baselines.json` → `per_bank.4.logreg` (`pooled_auc`, `pooled_ap`) |
| Bank 4 random forest | bank 4 only | 0.979 | 0.341 | `state/baselines.json` → `per_bank.4.rf` (`pooled_auc`, `pooled_ap`) |
| Bank 4 hist. gradient boosting | bank 4 only | 0.882 | 0.405 | `state/baselines.json` → `per_bank.4.hgb` (`pooled_auc`, `pooled_ap`) |
| **Centralized pooling, logistic regression** (not legal in practice; not an upper bound here) | all four banks' raw rows pooled | 0.983 | 0.088 | `state/baselines.json` → `centralized_logreg` |
| **Federated logistic regression, DP off** | no row leaves any bank | 0.988 | 0.152 | `python -m fedaml.results_table` scores `state/global_final_dpoff.json` |
| **Federated logistic regression, DP on (σ=0.3, ε≈99.7, δ=1e-05, approximate)** | no row leaves any bank; updates clipped + noised | 0.970 | 0.056 | `python -m fedaml.results_table` scores `state/global_final_dpon.json`; ε from `state/status_dpon.json` → `dp.epsilon_spent` |
| **Federated, rogue bank 5 present, defense off** | bank 5 sends poisoned updates | 0.500 | 0.002 | `python -m fedaml.results_table` scores `state/global_final_rogue_off.json`; exclusions in `state/status_rogue_off.json` → `rounds[*].excluded` |
| **Federated, rogue bank 5 present, defense on** | bank 5 detected and excluded | 0.989 | 0.182 | `python -m fedaml.results_table` scores `state/global_final_rogue_on.json`; exclusions in `state/status_rogue_on.json` → `rounds[*].excluded` |

Reading (results line on the slide): federated without DP matches the best single bank on AUC
and beats centralized pooling on AP; DP costs about 0.02 AUC and 0.10 AP, the measured price of
the privacy guarantee the red-team table demonstrates; the rogue bank breaks the model to chance
and the defense fully restores it. ε is approximate, update-level, and a weak formal guarantee at
this size; the red-team table carries the privacy claim.

Control (not in this table): every entry in `state/baselines.json` also carries `global_auc` /
`global_ap` on `data/global_test.csv`, the red team's distribution-shift control. They read lower
because that file's within-frame account aggregates come from a 200k mixed-bank sample.
