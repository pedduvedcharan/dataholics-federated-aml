# P3 — Features and models

**Agent brief you drive:** `agents/02-MODELS.md`. You own the one module everybody imports, `fedaml/features.py`, and the multi-model comparison that the mandatory lab requires.

## Your deliverables
`fedaml/features.py`, `fedaml/baselines.py`, `state/baselines.json`, `docs/FEATURES.md`, the shared evaluator `evaluate_model_json`.

## Hour by hour
- **12:00–13:00** Write `features.py` against the first 50k rows you can get (ask P2 for `data/sample_50k.csv`; until then, use the Kaggle preview or synthesize 1,000 rows with the same columns). `FEATURE_NAMES`, `featurize`, `load_bank`, `feature_names_sha256`, exactly as CONTRACTS §3. Push it as soon as it runs; P4 and P6 import it.
- **13:00–13:30** Quick checks: deterministic output, no NaN or inf, aggregates computed within the given dataframe only. Write `docs/FEATURES.md`, one line per feature in plain English (P6 feeds this to the LLM, P1 puts it in the README).
- **13:30–15:00** `baselines.py` on the VM once P2 has partitioned: per bank 1..4, logreg, random forest, hist gradient boosting, evaluated on the bank's own test set and on `global_test.csv`. Plus the centralized logreg ceiling. Write `state/baselines.json` and paste the markdown table in STATUS.md.
- **15:00–15:30** `evaluate_model_json(path)` so P4's coordinator and P5's dashboard score any `state/global_*.json` the same way.
- **15:30–17:30** Help P6 build `state/alerts.json` (top-20 scored rows from `global_test.csv` with chains and top-feature contributions). You know the features best.
- **17:30–20:00** Sanity check the federated AUC against your table. It should sit between the best single bank and the centralized ceiling. If not, look at feature scale with P4.
- **20:00 onward** Results table for the README with P1; explain the comparison on the slide in two sentences; stay available for debugging.

## Done when
`state/baselines.json` on the VM has every bank and model, `docs/FEATURES.md` exists, and the federated model's AUC lands where expected.
