# Presentation website — spec for the 4-tab redesign (lead's brief, Oct 17 2026 20:55 CDT)

The localhost dashboard (`fedaml/dashboard/static/`) becomes the whole 3-minute recorded presentation:
**The Problem → Our Architecture → Results & Dashboard → Live Workflow**. The previous version is saved as git tag
`website-v1-five-sections` and `submission/website_snapshots/index_v1_five_sections_64d86a5.html`.
The lead's full brief is the source of truth; this file records the verified facts and the decisions.

## Verified facts to use
- **Size of the problem.** IMF *Finance & Development*, Dec 2018, "Straight Talk: Cleaning Up" (Rhoda Weeks-Brown):
  the **United Nations** estimate of laundered proceeds is **2–5 % of global GDP, $1.6–4 trillion a year**.
  Display: "UP TO 5% OF GLOBAL GDP" with "up to $4 trillion a year" and the attribution
  "UN estimate, cited by the International Monetary Fund (F&D, Dec 2018)". Do **not** show $5 trillion.
- Dataset: "IBM Synthetic AML Dataset — HI-Small", IBM-published, 5,078,345 simulated transactions,
  5,177 labelled laundering. Never "IBM certified".
- Model: 20 engineered features → logistic regression → 21 learned parameters. 10 federated rounds.
  Bank-side L2 clipping (1.0) + Gaussian noise (σ 0.5) + audited egress. FedAvg with cheater screening.
- Measured results (VM files, models `f12fcda7` no noise / `16ef90c0` with noise): pooled AUC 0.992 / 0.982,
  AP 0.248 / 0.065; best single bank 0.986 AUC (bank 4 logreg), 0.405 AP (bank 4 trees); centralized pooling
  0.983 / 0.088 (experimental comparison); rogue defense off 0.953 / 0.071 vs on 0.992 / 0.250, bank 5 excluded
  10/10; membership attack AUC 0.994 (no noise) → 0.517 (σ 0.5); ε ≈ 46 (approximate, loose); 1,880 MB all
  containers, 2.12 s per round, s390x, 3 CPUs; docker ps capture with 4 banks training at 22:03 UTC.

## Measured vs simulated (must be labelled on the page)
| Element | Kind |
|---|---|
| Problem statistic | sourced external estimate (UN via IMF, 2018) |
| Criminal-network vs fragmented-banks animation | illustrative |
| Architecture steps | illustrative of the implemented system |
| Training-round counter animation | illustrative replay of the recorded 10 rounds (real per-round numbers) |
| Page 3 metrics, charts, attack AUC, rogue results, footprint | measured, live from `/api/state` |
| Page 4 transaction | a real row from a bank's synthetic test set (not a live banking transaction) |
| Page 4 risk score, features, contributions | computed from the saved federated model (`/api/bank/<b>/demo`) |
| Page 4 alert, report | produced by the bank-local pipeline; LLM vs template labelled per report |
| Page 4 regulator view | aggregates only (`alerts_aggregate`) |
