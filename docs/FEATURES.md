# Feature vector (`fedaml/features.py`)

20 features per transaction, fixed order, float32. Every feature is computed from
the transaction row itself or from counts **inside the bank's own data**. Nothing
needs a scaler, a vocabulary learned from data, or any statistic from another
bank, which is what lets one global logistic model be averaged across banks.

The sha256 of the ordered name list (`feature_names_sha256()`) rides along with
every model update so the coordinator can reject an update built on a different
vector.

| # | Name | Plain English |
|---|---|---|
| 1 | `log_amt` | Size of the payment, log-scaled (`log1p(amt_paid)`) so a $10 and a $10M transfer both fit on one axis. |
| 2 | `is_usd` | 1 if the payment was made in US dollars, else 0. |
| 3 | `cur_mismatch` | 1 if the currency paid differs from the currency received (a conversion happened). |
| 4 | `same_bank` | 1 if sender and receiver are at the same bank (internal transfer), else 0. |
| 5 | `round_amt` | 1 if the amount is an exact multiple of 100 (round "structured" amounts are a classic red flag). |
| 6 | `hour_sin` | Hour of day on a circle (sine part), so 23:00 and 01:00 are close. |
| 7 | `hour_cos` | Hour of day on a circle (cosine part). |
| 8 | `dow_sin` | Day of week on a circle (sine part), so Sunday and Monday are close. |
| 9 | `dow_cos` | Day of week on a circle (cosine part). |
| 10 | `fmt_ACH` | 1 if the payment format is ACH. |
| 11 | `fmt_Credit_Card` | 1 if paid by credit card. |
| 12 | `fmt_Cheque` | 1 if paid by cheque. |
| 13 | `fmt_Wire` | 1 if paid by wire transfer. |
| 14 | `fmt_Reinvestment` | 1 if the payment is a reinvestment. |
| 15 | `fmt_Bitcoin` | 1 if paid in Bitcoin. |
| 16 | `fmt_Cash` | 1 if paid in cash. |
| 17 | `snd_txn_cnt_log` | How many payments this sender account made in this bank's data, log-scaled. |
| 18 | `snd_uniq_rcv_log` | How many *different* accounts this sender paid, log-scaled (fan-out / smurfing signal). |
| 19 | `rcv_in_deg_log` | How many payments the receiving account collected in this bank's data, log-scaled (fan-in / collection account). |
| 20 | `snd_amt_mean_log` | The sender's average payment size in this bank's data, log-scaled (is this payment typical for them?). |

Notes
- Payment formats outside the fixed vocabulary (ACH, Credit Card, Cheque, Wire,
  Reinvestment, Bitcoin, Cash) get all seven one-hot columns = 0.
- Account aggregates (17-20) key on `(bank, account)` and are counted only
  within the dataframe passed to `featurize`. A bank never sees another bank's
  counts; the federated model learns from each bank's *local* view of fan-in and
  fan-out.
- Missing or malformed values are mapped to 0 before the log, so the matrix
  never contains NaN or inf.
- **Known limit, `log_amt` is in the payment's own currency and unbounded.** `log_amt = log1p(amt_paid)`
  uses the nominal amount in `cur_paid`, so ¥1B and $1B look identical, and the logistic model extrapolates
  linearly on the extreme tail. On `global_test.csv` the DP-on model's top 20 are all ACH transfers of $12M to
  $1.4B nominal (median ~1.0B): 15 are paid in Rupee / Ruble / Yen / Mexican Peso, and 4 are genuinely huge
  US Dollar / Euro transfers. None of the 20 is laundering.
  Mitigation used now, ranking only: `cap_for_alerts` clips `log_amt` at a fixed $10M (`LOG_AMT_ALERT_CAP`). With the
  self-transfer filter, the top 20 / 50 / 100 then contain 2 / 3 / 7 true laundering rows, against a base rate of
  0.18%. The model and every reported AUC/AP use the raw feature.
  Real fix, future work, **requires retraining**: convert `amt_paid` to USD with a fixed, published rate table
  (a constant, not learned from any bank's data) before `log1p`, and cap the result at a fixed bound. Both
  steps are needed: currency conversion alone leaves the 4 genuine $1B+ transfers on top.
  Effect on reported metrics: AUC and AP were measured on this model with this flaw included, so they stand as
  measured. AUC is a whole-ranking statistic and barely moves. AP weights the top of the ranking, so it is
  depressed by these rows. A corrected feature would most likely raise AP, not lower it.
- For a logistic model, `contributions(X, coef)` returns `X * coef` per feature,
  which the SAR generator uses to name the top reasons a transaction was flagged.
