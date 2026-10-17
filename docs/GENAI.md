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
| A06 (demo) | yes | 29.5 | 30.4 | 80 | 50 |
| A07 | no | 30.7 | 31.6 | 160 | 72 |
| A08 | no | 20.7 | 21.6 | 144 | 94 |

- The `llm` container (1.5B) was healthy 6 s after `docker compose up -d --wait llm`, at about 200 MB RSS plus the
  memory-mapped 1.8 GiB GGUF.
- Qwen 0.5B on the same prompt: 8.6–13.3 s per SAR. The template engine takes under 1 s.
- Building `state/alerts.json` on 200k rows took 5.9 s in its container, including the three-way comparison.
- Every SAR states its trigger's ground-truth label and its rank in the review queue. The footer says the alert
  was ranked for analyst review and is not a finding of laundering.

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
- The verdict filter drops LLM sentences that call an alert laundering. Even so, the paragraph can misstate
  activity. In A06 it says the sender "rarely transacts" while the chain shows two other payments.
- Data are synthetic (IBM AML HI-Small). The outline follows a SAR narrative but is not a legal filing.
- Speed numbers are single runs on one shared VM.
