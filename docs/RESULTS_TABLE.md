# Results table skeleton for the README (MODELS → MASTER)

All AUC/AP values on the **pooled basis**: each bank's `test.csv` featurized within
that bank, predictions pooled over the evaluation banks **2, 3, 4**
(`fedaml.baselines.evaluate_model_pooled`, CONTRACTS §4/§6). Bank 1 (code 070, 69% of
all rows) is kept in the per-bank rows at its own-test score to show it at chance: its
laundering (cheque / card / cash from a handful of hub sender accounts, never ACH, never
within-bank) is invisible to per-row features, for every model, so it is excluded from
the pooled basis and the centralized model is still trained on its rows.
Positives are ~1 in 1,000, so AP (average precision) is the number that matters;
AUC is shown because judges expect it. Every number must be copied from the file
in the last column as produced on the LinuxONE VM. Replace `{{...}}` only from those files.

| Model | Who sees the rows | AUC | AP | File of origin (on VM) |
|---|---|---|---|---|
| Bank 1 logistic regression (own test; at chance, see note) | bank 1 only | {{B1_LR_AUC}} | {{B1_LR_AP}} | `state/baselines.json` → `per_bank.1.logreg` (`auc`,`ap`) |
| Bank 1 random forest (own test) | bank 1 only | {{B1_RF_AUC}} | {{B1_RF_AP}} | `state/baselines.json` → `per_bank.1.rf` (`auc`,`ap`) |
| Bank 1 hist. gradient boosting (own test) | bank 1 only | {{B1_HGB_AUC}} | {{B1_HGB_AP}} | `state/baselines.json` → `per_bank.1.hgb` (`auc`,`ap`) |
| Bank 2 logistic regression | bank 2 only | {{B2_LR_AUC}} | {{B2_LR_AP}} | `state/baselines.json` → `per_bank.2.logreg` |
| Bank 2 random forest | bank 2 only | {{B2_RF_AUC}} | {{B2_RF_AP}} | `state/baselines.json` → `per_bank.2.rf` (`pooled_auc`,`pooled_ap`) |
| Bank 2 hist. gradient boosting | bank 2 only | {{B2_HGB_AUC}} | {{B2_HGB_AP}} | `state/baselines.json` → `per_bank.2.hgb` (`pooled_auc`,`pooled_ap`) |
| Bank 3 logistic regression | bank 3 only | {{B3_LR_AUC}} | {{B3_LR_AP}} | `state/baselines.json` → `per_bank.3.logreg` |
| Bank 3 random forest | bank 3 only | {{B3_RF_AUC}} | {{B3_RF_AP}} | `state/baselines.json` → `per_bank.3.rf` (`pooled_auc`,`pooled_ap`) |
| Bank 3 hist. gradient boosting | bank 3 only | {{B3_HGB_AUC}} | {{B3_HGB_AP}} | `state/baselines.json` → `per_bank.3.hgb` (`pooled_auc`,`pooled_ap`) |
| Bank 4 logistic regression | bank 4 only | {{B4_LR_AUC}} | {{B4_LR_AP}} | `state/baselines.json` → `per_bank.4.logreg` |
| Bank 4 random forest | bank 4 only | {{B4_RF_AUC}} | {{B4_RF_AP}} | `state/baselines.json` → `per_bank.4.rf` (`pooled_auc`,`pooled_ap`) |
| Bank 4 hist. gradient boosting | bank 4 only | {{B4_HGB_AUC}} | {{B4_HGB_AP}} | `state/baselines.json` → `per_bank.4.hgb` (`pooled_auc`,`pooled_ap`) |
| **Centralized logistic regression (the illegal ceiling)** | all four banks' raw rows pooled | {{CENT_AUC}} | {{CENT_AP}} | `state/baselines.json` → `centralized_logreg` |
| **Federated logistic regression, DP off** | no row leaves any bank | {{FED_OFF_AUC}} | {{FED_OFF_AP}} | `python -m fedaml.baselines --evaluate state/global_final_dpoff.json` or `state/status_dpoff.json` → last round `global_auc`/`global_ap` |
| **Federated logistic regression, DP on (σ={{SIGMA}}, ε≈{{EPSILON}})** | no row leaves any bank, updates clipped + noised | {{FED_ON_AUC}} | {{FED_ON_AP}} | `state/baselines.json` → `federated` (attached from `global_final_dpon.json`); ε from `state/status_dpon.json` → `dp.epsilon_spent` |
| Federated, rogue bank 5 present, defense **off** | bank 5 sends poisoned updates | {{ROGUE_OFF_AUC}} | {{ROGUE_OFF_AP}} | `python -m fedaml.baselines --evaluate state/global_final_rogue_off.json` |
| Federated, rogue bank 5 present, defense **on** | bank 5 detected and excluded | {{ROGUE_ON_AUC}} | {{ROGUE_ON_AP}} | `python -m fedaml.baselines --evaluate state/global_final_rogue_on.json`; exclusions in `state/status.json` → `rounds[*].excluded` |

Two sentences for the slide (fill after the VM run):
- "The best any single bank can do alone is {{BEST_SINGLE_MODEL}} at AP {{BEST_SINGLE_AP}}; pooling raw data would reach AP {{CENT_AP}}, but that pooling is what regulators shut down."
- "The federated model reaches AP {{FED_ON_AP}} with differential privacy on, without a single transaction leaving a bank; the rogue bank drops it to {{ROGUE_OFF_AP}} until the defense excludes it ({{ROGUE_ON_AP}})."

Control column (not for the README table, for the red-team write-up): the same models
scored on `data/global_test.csv` are in `global_auc` / `global_ap` next to each entry.
They read lower because that file's within-frame account aggregates are computed on a
200k mixed-bank sample, not a 500k single-bank file.

FEDERATION: the file names `global_final_dpoff.json`, `global_final_dpon.json`,
`global_final_rogue_off.json`, `global_final_rogue_on.json` are a proposal;
tell MODELS/MASTER if your runs write different names.
