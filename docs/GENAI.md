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
   sigmoid as `fedaml.baselines.predict_proba_json`. It keeps the top 20 and gathers each chain: the trigger,
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
- The footer always states the engine and, on fallback, the reason.
- The finished document is post-checked for account ids against the alert record whatever the engine.
- `--engine template` never touches the network and always works. It is a legitimate deliverable.

## Measured on the VM (real data)
Interim model `state/global_final.json`, round 5, banks 1–2; `state/sar/_runs.jsonl`.

| Alert | Engine | LLM seconds | Completion tokens | Assessment words |
|---|---|---|---|---|
| A01 | llm (Qwen 0.5B) | 13.3 | 141 | 100 |
| A02 | llm (Qwen 0.5B) | 8.6 | 159 | 83 |
| A03 | llm (Qwen 0.5B) | 9.6 | 141 | 100 |
| A04 | template | under 1 s | none | none |

- Building `state/alerts.json` from 200,000 rows: 2.1 s, 203 MB peak RSS.
- `llm` container: healthy 7 s after `docker compose up -d llm`. 124 MB RSS for 0.5B and 661 MB for 1.5B per
  `docker stats`; the GGUF is memory-mapped, so add its size in page cache.
- SAR process (client side): 74 MB peak RSS.

## Container
```
docker build -f fedaml/llm/Dockerfile -t fedaml-llm .           # ~5.5 min on the VM, 289 MB image
docker compose run --rm llm /app/fetch_model.sh                 # once: download + big-endian convert into ./models
docker compose up -d llm                                        # llama-server on 127.0.0.1:8080, healthcheck /health
ALERT_ID=A01 docker compose run --rm genai                      # SAR_ENGINE=llm by default, falls back to template
docker compose stop llm
```
Weights live in the `./models` volume, not in the image. To use Qwen 1.5B, the `llm` service needs
`LLM_MODEL_FILE: ${LLM_MODEL_FILE:-qwen2.5-0.5b-instruct-q8_0-be.gguf}` in its environment; the 1.5B file is
already in `~/fedaml/models` on the VM. `fetch_model.sh` takes `MODEL_REPO` and `MODEL_FILE` for other models.

## Honest limits
- The assessment is narration by a 0.5–1.5 B parameter model. It reads fluently but can overstate or
  misattribute a reason, for example calling a sender frequent when the sample shows no other payments. The
  facts it might contradict sit directly above it, written by code. It never changes a score, an id or a number.
- The interim alerts come from a round-5, two-bank model. None of the top 20 triggers is labelled laundering in
  the synthetic ground truth, and some chains are a single row because `global_test.csv` is a 200k sample.
  Regenerate after the final federated run.
- Data are synthetic (IBM AML HI-Small). The outline follows a SAR narrative but is not a legal filing.
- Speed numbers are single runs on one shared VM.
