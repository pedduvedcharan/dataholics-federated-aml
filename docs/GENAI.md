# GENAI — the Suspicious Activity Report writer

**Principle: the LLM narrates, the model decides.** The federated logistic model, trained by the banks
without sharing a row, decides which transaction is flagged and why (feature value × weight). Code writes
every factual sentence of the SAR from `state/alerts.json`: ids, amounts, banks, counts, the model hash.
The language model adds exactly one paragraph, marked **"Analyst assessment (LLM)"**, that explains in
compliance language why the pattern is suspicious. It is given qualitative facts and the model's top
reasons only. It never sees an account id, an amount, a date or a bank id, so it cannot leak or invent one.

## Runtime verdict on IBM Z (s390x, big-endian, 3 cores, 8 GB), measured Oct 17 2026

| Path | Result | Time spent |
|---|---|---|
| (a) `pip install torch` + transformers | Not available. PyPI has no s390x wheel and Ubuntu 24.04 s390x has no `python3-torch`. pip fails in under a minute with nothing to compile. | ~1 min |
| (b) llama.cpp from source + big-endian GGUF | **Works. This is the engine.** | build 243 s, download 7 s, conversion 23 s |
| (c) template | Always available; automatic fallback | none |

Details of path (b):
- llama.cpp commit `9d1878a`, CPU backend with VXE2 vector instructions (`-march=z16 -mvx -mzvector`). The VM
  is a z17 (machine 9175). Upstream cmake emits `-march=arch15`, which gcc 13.3 rejects, so the flag is
  pinned to `z16` by one `sed` in `fedaml/llm/Dockerfile`.
- Little-endian GGUFs are rejected on big-endian hosts ("is there a mismatch between the host and model
  endianness?"). Published GGUFs are converted with llama.cpp's `gguf_convert_endian.py`, patched for numpy 1.26
  (drop `reshape(..., copy=False)`), answering its confirmation prompt with `YES`. `convert_hf_to_gguf.py
  --bigendian` was not used because it imports torch.

## Models tried on the VM

`llama-bench -p 128 -n 100 -t 3`, one run each, files `state/llm_bench*.json` on the VM.

| Model (GGUF, big-endian) | Size | Prompt tok/s | Generation tok/s | Seconds per SAR (real alerts) | Verdict |
|---|---|---|---|---|---|
| Qwen2.5-0.5B-Instruct Q8_0 | 639 MiB | 96.2 | 39.2 | 8.6 – 13.3 | **default**: fast; prose is generic and sometimes misattributes a reason |
| Qwen2.5-1.5B-Instruct Q8_0 | 1.8 GiB | 28.5 | 8.9 | 40.1 – 43.2 | most coherent prose; within the 60 s cap with ~1.4× headroom |
| Granite-3.1-1B-A400M-Instruct Q8_0 (MoE) | 1.4 GiB | 49.4 | 24.9 | not measured with the final prompt | earlier prompt: terse, renamed placeholders |
| Granite-3.3-2B-Instruct Q4_K_M | 1.5 GiB | 12.4 | 6.2 | > 120 s (timed out) | too slow on 3 cores |

Speed drops sharply under contention: during a parallel Docker build, Qwen 0.5B generation fell from 39 to
6 tok/s. That is why the LLM never runs while the banks train.

## How a SAR is produced
1. `python -m fedaml.alerts` scores `data/global_test.csv` with `state/global_final.json` using the same
   sigmoid as `fedaml.baselines.predict_proba_json`, with `log_amt` capped for ranking (see "The alert queue").
   It skips same-account transfers and single-bank chains, keeps the top 20 and gathers each chain: the trigger,
   the sender's other payments and the receiver's onward payments, at most 10 rows. It adds the banks involved
   (labelled with federation ids from `data/bank_map.json`) and the top-5 contributions. Output `state/alerts.json`.
2. `python -m fedaml.sar --alert-id A01` fills the fixed outline with code (template sentences built from the
   alert), then asks the LLM for the assessment paragraph and inserts it after the code-written summary.
3. Every section except the assessment paragraph is always code-written, whatever the engine.

| Section | Written by |
|---|---|
| Subject | code |
| Summary of activity | code facts, then the LLM's "Analyst assessment" paragraph |
| Pattern indicators | code (one bullet per top feature, with its contribution) |
| Institutions involved | code (bank code, federation label, role, rows) and the chain table |
| Recommended action | code |
| Model attribution | code: model sha256, round, score, value × weight table |
| Footer | code: engine, model file, seconds, tokens, fallback reason if any |

## Guardrails and fallback rule
- `max_tokens 400`, `temperature 0.2`, `seed 42`, 60 s timeout.
- The assessment is dropped and the whole SAR falls back to the template if the server is unreachable or
  times out, if the output is empty, if it repeats the prompt's instructions, if it is under 25 words once
  sentences copied from the one-shot example are removed, if it contains an unknown placeholder, or if it
  contains anything shaped like an account id (hex of 6+ characters or 7+ digits) that is not in the alert.
- Sentences in which the LLM calls the activity laundering ("likely", "consistent with money laundering", ...)
  are removed before the length check: alerts are ranked for review, never declared laundering.
- The footer always states the engine and, on fallback, the reason.
- The finished document is post-checked for account ids against the alert record whatever the engine.
- `--engine template` never touches the network and always works. It is a legitimate deliverable. The module's
  CLI defaults to `llm`; the compose `genai` service defaults to `template`, so pass `SAR_ENGINE=llm` there.

## The alert queue (final DP-on model, measured on the VM)
Model `state/global_final.json` = `global_final_dpon.json`, round 10, sha256 `16ef90c0…`, scored on
`data/global_test.csv` (200,000 rows, 354 labelled laundering, prevalence 0.177%). Alerts are **ranked for
analyst review**; they are not detected laundering. Source: `state/alerts.json` → `meta`.

Labelled-laundering triggers among the top k (`meta.ablation_true_laundering_at_k`):

| Ranking rule | Top 20 | Top 50 | Top 100 |
|---|---|---|---|
| (a) Raw model score | 0 | 2 | 4 |
| (b) Filters only: drop same-account transfers, require ≥ 2 banks in the chain | 0 | 3 | 4 |
| (c) **`log_amt` cap + filters (used)** | **2** | **3** | **7** |

- Under (c), top-20 precision is 2/20 = 10%, about 56× the 0.177% base rate. Top-100 precision is 7%.
- While ranking the queue, the filters removed 56 same-account transfers and 6 single-bank chains. The sample
  holds 4,287 same-account rows, of which 2 are laundering.
- **Why the raw top is empty.** `log_amt` is the log of the amount in the payment's own currency, and the DP-on
  model's largest positive weight is `fmt_ACH` (+2.29). Nominally huge ACH payments in Rupee, Ruble, Yen or Yuan
  (0.2–7.6 billion) therefore saturate the score at 0.99999.
- **The cap.** MODELS' `fedaml.features.cap_for_alerts` clips `log_amt` at log1p(10,000,000), a fixed domain
  constant and not a statistic of any bank's data. It is applied to ranking and to the SAR's contribution table
  only. **It is a post-hoc ranking rule, chosen after we saw the saturation, and evaluated on the same data**, so
  the numbers above are optimistic for unseen data. Model AUC/AP are unchanged because they are reported on raw
  features. The real fix is converting amounts to USD before the log, which needs retraining (future work).
- **Demo alert.** `meta.demo_alert_id` = **A06**, the highest-ranked alert whose trigger is labelled laundering in
  the synthetic data. It is a 10.8 M Euro ACH payment in a 3-row chain across 4 banks. The scene says: "a true
  positive from the queue ranked for analyst review, rank 6; the queue's top-20 precision is 2 in 20."

## Recorded demo SARs (Qwen2.5-1.5B, via `docker compose run --rm genai`)
From `state/sar/_runs.jsonl`. "Wall" includes the `docker compose run` container start.

| Alert | Trigger labelled laundering? | LLM seconds | Wall seconds | Completion tokens | Assessment words |
|---|---|---|---|---|---|
| A06 (demo, regenerated 16:35 after the fact-check fixes) | yes | 34.9 | 35.8 | 120 | 49 |
| A07 | no | 34.9, then fell back | 35.6 | — | — |
| A08 | no | template (LLM draft rejected in review) | under 1 | — | — |

- The `llm` container (1.5B) was healthy 6 s after `docker compose up -d --wait llm`, at about 200 MB RSS plus the
  memory-mapped 1.8 GiB GGUF.
- Qwen 0.5B on the same prompt: 8.6–13.3 s per SAR. The template engine takes under 1 s.
- Building `state/alerts.json` on 200k rows took 5.9 s in its container, including the three-way comparison.
- Every SAR states its trigger's ground-truth label and its rank in the review queue. The footer says the alert
  was ranked for analyst review and is not a finding of laundering.

## Bank-local scoring, alerts and reports (CONTRACTS §9.1, Oct 17 21:00 redesign)
`python -m fedaml.bank_local --banks 1,2,3,4 --sar-engine llm|template|none` runs inside the compose image:
```
LLM_MODEL_FILE=qwen2.5-1.5b-instruct-q8_0-be.gguf docker compose up -d --wait llm
docker compose run --rm genai python3 -m fedaml.bank_local --banks 1,2,3,4 --sar-engine llm
docker compose stop llm
```
- Each bank scores **its own** `data/banks/bank_<b>/test.csv` with `state/global_final_dpon.json`, featurized
  within the bank. Ranking uses `cap_for_alerts` and drops same-account transfers. Single-bank chains are fine.
- It writes `state/bank_local/bank_<b>/alerts.json` (top 20, ids `B<b>-A<nn>`, threshold = the score at rank 20),
  `demo.json` (the bank's top labelled-laundering alert, else its top alert) and `sar/B<b>-A<nn>.md`.
  `state/bank_local/summary.json` holds aggregates only.
- The walkthrough's arithmetic is asserted in code: `sigmoid(intercept + Σ value × weight)` equals `score`.
- The reports use only the bank's own rows. They say "bank <b>'s own test-period records" and carry a scope note.
- The boundary is logical: separate files and routes on one VM, not network isolation.

Measured on the VM (Oct 17, image `b8c92e2`; reports from `--sar-engine llm` with Qwen 1.5B, 181.9 s for six):

| Bank | Rows scored | Labelled laundering in top 20 | Prevalence | Threshold (rank-20 score) | Same-account skipped | Demo alert | Report engine |
|---|---|---|---|---|---|---|---|
| 1 | 89,972 | 0 | 0.136% | 0.995263 | 0 | B1-A01 (not labelled) | template (fallback) |
| 2 | 14,236 | 1 | 0.190% | 0.999487 | 6 | B2-A19 | llm, 29.7 s |
| 3 | 12,959 | 2 | 0.085% | 0.998214 | 9 | B3-A04 | llm, 31.3 s |
| 4 | 12,443 | **7** | 0.209% | 0.998881 | 19 | **B4-A01 (walkthrough)** | llm, 29.6 s |

- **Walkthrough: bank 4, B4-A01.** Rank 1, score 0.999823 (uncapped 0.999873), threshold 0.998881, priority high,
  labelled laundering in the synthetic data. It is a 25.6 M EUR ACH payment; the sender made 8 other payments
  to 3 other receivers in bank 4's records.
- Bank 4's queue holds 7 labelled cases in 20 (35%), about 167× its prevalence. The same post-hoc cap caveat
  applies as for the central queue.
- **Claim check of the six reports.** The walkthrough B4-A01 passes: ACH, large amount, no onward movement;
  the "layered" typology is described, not asserted. B4-A02, B3-A04 and B2-A19 pass; their quoted counts match.
  B4-A03 is borderline: it says the receiver "collects payments from multiple unrelated payers". The receiver
  collected 3, and "unrelated" is copied from the example. B1-A01 fell back to the template because the count
  check wrongly rejected "873 distinct receivers", which was correct. Fixed in `60bccec`; not rerun, since bank
  1 is not the walkthrough.
- **Fixes found by this run.** The sender's other-receiver count is now computed from the bank's full records,
  not the 10 displayed rows. The verdict filter also drops "suspicion of laundering", "part of a … scheme" and
  "the same receiver".

## Container
```
docker build -f fedaml/llm/Dockerfile -t fedaml-llm .           # ~5.5 min on the VM, 289 MB image
docker compose run --rm llm /app/fetch_model.sh                 # once: download + big-endian convert into ./models
docker compose up -d --wait llm                                 # llama-server on 127.0.0.1:8080, waits for /health
SAR_ENGINE=llm ALERT_ID=A01 docker compose run --rm genai       # LLM engine, falls back to template on any failure
ALERT_ID=A01 docker compose run --rm genai                      # compose default engine is template: never needs the LLM
docker compose stop llm
```
Weights live in the `./models` volume, not in the image. `fetch_model.sh` takes `MODEL_REPO` and `MODEL_FILE`
for other models.

## Which model, when (MASTER decision, Oct 17 16:00)
| Use | Model | Command | Seconds per SAR |
|---|---|---|---|
| Anything live, default | Qwen2.5-0.5B-Instruct Q8_0 | `docker compose up -d --wait llm` | about 10 |
| The three recorded demo SARs A01–A03 | Qwen2.5-1.5B-Instruct Q8_0 | `LLM_MODEL_FILE=qwen2.5-1.5b-instruct-q8_0-be.gguf docker compose up -d --wait llm` | about 41 |

Each SAR footer names the engine, the model file and the LLM seconds, so a reader can tell which one wrote it.
Both GGUFs are in `~/fedaml/models` on the VM.

Run order after the integration run's training phase ends:
```
docker compose run --rm alerts
LLM_MODEL_FILE=qwen2.5-1.5b-instruct-q8_0-be.gguf docker compose up -d --wait llm
for a in A01 A02 A03; do SAR_ENGINE=llm ALERT_ID=$a docker compose run --rm genai; done
docker compose stop llm
```

## Honest limits
- The assessment is narration by a 0.5–1.5 B parameter model. It reads fluently but can overstate or
  misattribute a reason, for example calling a sender frequent when the sample shows no other payments. The
  facts it might contradict sit directly above it, written by code. It never changes a score, an id or a number.
- The review queue is noisy: 2 of the top 20 triggers are labelled laundering, consistent with the DP-on
  model's AP of about 0.065. Some chains are a single row because `global_test.csv` is a 200k sample.
- Fact-check fixes after the first A06 draft. That draft said the sender "rarely transacts" (the chain shows
  two other payments), that ACH is "less common" and that the sender paid "many" accounts (it paid 3). Now the
  prompt carries the decoded counts, and the indicators state numbers instead of "many". Code drops LLM
  sentences with frequency, prevalence or size-of-count words (rarely, often, less common, many distinct, ...).
  The regenerated A06 paragraph was checked sentence by sentence against the code-written facts.
- A count check drops any LLM sentence whose number contradicts the facts. "N other payments" must equal the
  sender's other-payment count, and any other count must match one the report states. The verdict filter also
  catches "launder", "laundering operation", "series of transactions" and "sophisticated".
- **Outcome for the three recorded reports.** A06 kept its LLM paragraph after a claim-by-claim check.
  A07's LLM draft claimed "two other payments" (the facts show 1); the count check removed that sentence, which
  left 15 words, so it fell back to the template automatically. A08's LLM draft called a one-row chain "a
  sophisticated attempt to launder funds through a series of transactions". After the filter, it still
  speculated about a "larger money laundering or fraud scheme" and "layering" with no onward movement, so we
  regenerated it with the template engine. Both A07 and A08 say "template engine" in their footers.
- The lesson: a 1.5 B model's narration needs fact checks in code. Two of three drafts on real alerts made a
  claim the facts contradict; the guardrails caught both, and the template always produces a correct report.
- The A06 paragraph is still vague ("raise significant concerns").
- Data are synthetic (IBM AML HI-Small). The outline follows a SAR narrative but is not a legal filing.
- Speed numbers are single runs on one shared VM.
