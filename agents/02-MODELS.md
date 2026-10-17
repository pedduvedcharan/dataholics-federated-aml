# MODELS agent — features and the multi-model comparison

## Goal
A single `features.py` every other module imports, plus the per-bank baseline table that satisfies the "compare several predictive models" lab requirement and proves the federated model beats every single-bank model.

## You own
`fedaml/features.py`, `fedaml/baselines.py`, `state/baselines.json`, a short `docs/FEATURES.md` explaining each feature in one line (used in the README and the SAR).

## Tasks, in order
1. **features.py** (by 13:00, develop on `data/sample_50k.csv`): implement CONTRACTS §3 exactly. `FEATURE_NAMES: list[str]`, `featurize(df: pd.DataFrame) -> np.ndarray` (float32), `load_bank(bank_id, split) -> (X, y)`, `feature_names_sha256()`. The account-level aggregates are computed **inside the given dataframe only** (one bank's data). Unit-check: featurize twice gives identical arrays; no NaN/inf; shape `[n, len(FEATURE_NAMES)]`.
2. **baselines.py** (by 15:00, run on the VM): for each bank 1..4 train on `train.csv`, evaluate on that bank's `test.csv` AND on `data/global_test.csv`: `LogisticRegression(class_weight="balanced", max_iter=200)`, `RandomForestClassifier(n_estimators=100, n_jobs=2, class_weight="balanced_subsample")`, `HistGradientBoostingClassifier(class_weight="balanced")`. Also a **centralized logreg** on all four banks' train rows concatenated (the illegal upper bound). Metrics: ROC AUC and average precision. Write `state/baselines.json` per CONTRACTS §6 and print a markdown table.
3. **Hook for the federated score.** Expose `evaluate_model_json(path) -> {"auc","ap"}` that loads a `state/global_*.json` model and scores `global_test.csv`, so FEDERATION and the dashboard reuse one evaluator.
4. **Hand the table to MASTER** with one sentence: which single-bank model is best, what the centralized ceiling is. The federated model should land between the best single bank and the centralized ceiling; if it does not, tell FEDERATION which features look unstable.

## Pitfalls
- Class imbalance ~1:1000: always report AP, never accuracy. Use `stratify` when subsampling.
- Keep RF modest (100 trees, `max_depth=12`) on 3 cores; cap train rows at 500k.
- No `StandardScaler`, no target encoding, no cross-bank statistics. If a feature needs global info, it does not exist.

## Done when
`state/baselines.json` exists on the VM with every bank and model, and `docs/FEATURES.md` is written.
