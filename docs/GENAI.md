# GENAI — the Suspicious Activity Report writer

**Principle: the LLM narrates, the model decides.** The federated logistic model (trained by the
banks without sharing a row) decides *which* transaction is flagged and *why* (feature
contributions). The language model only turns those facts into compliance prose. It never sees
an account number, an amount, a bank id or the model hash: the prompt uses placeholder tokens
(`[SENDER]`, `[TOTAL_AMT]`, ...) and code substitutes the real values after generation.

## Runtime verdict on IBM Z (s390x, big-endian, 3 cores, 8 GB) — measured Oct 17 2026

| Path | Result | Time spent |
|---|---|---|
| (a) `pip install torch` + transformers | **Not available.** PyPI has no s390x wheel and Ubuntu 24.04 s390x has no `python3-torch`; pip fails in under a minute with nothing to compile. | ~1 min |
| (b) llama.cpp from source + big-endian GGUF | **Works. This is the engine.** | build 243 s, download 7 s, conversion 23 s |
| (c) template | Always available; automatic fallback | — |

Details of path (b):
- llama.cpp commit `9d1878a`, CPU backend with VXE2 (`-march=z16 -mvx -mzvector`). The VM is a z17
  (machine 9175); upstream cmake emits `-march=arch15`, which gcc 13.3 does not know, so the flag is
  pinned to `z16` (one `sed` in `fedaml/llm/Dockerfile`).
- Little-endian GGUFs are rejected on big-endian hosts ("is there a mismatch between the host and model
  endianness?"). `Qwen/Qwen2.5-0.5B-Instruct-GGUF` `q8_0` (644 MB) is converted with llama.cpp's
  `gguf_convert_endian.py` (patched for numpy 1.26: drop `reshape(..., copy=False)`). `convert_hf_to_gguf.py
  --bigendian` was not used because it imports torch.
- Model: Qwen2.5-0.5B-Instruct, 630 M parameters, Q8_0, 639 MiB on disk, ~0.7 GB RSS plus KV cache.

Measured speed (`state/llm_runtime.json`, `python -m fedaml.llm.runtime_test --tokens 100 --runs 2`):

| Metric | Value |
|---|---|
| Server startup | 1.0 s |
| 100 completion tokens, run 1 / run 2 | 4.33 s / 3.17 s |
| Tokens per second over HTTP (mean) | 27.3 |
| `llama-bench` prompt processing (128 tok) | 95.8 tok/s |
| `llama-bench` generation (100 tok) | 38.9 tok/s |

## Components
- `fedaml/llm/client.py` — urllib client for `llama-server` (`/health`, `/v1/chat/completions`), hard timeout,
  spawns a server from `LLM_MODEL_PATH` if none answers at `LLM_URL`.
- `fedaml/llm/runtime_test.py` — the benchmark above; writes `state/llm_runtime.json`.
- `fedaml/alerts.py` — scores `data/global_test.csv` with `state/global_final.json` (same sigmoid as
  `fedaml.baselines.predict_proba_json`), keeps the top 20, gathers each chain (trigger, sender's other
  payments, receiver's onward payments, ≤10 rows), banks involved, top-5 contributions → `state/alerts.json`.
- `fedaml/llm/facts.py` — placeholder facts, feature glossary, template sentences.
- `fedaml/llm/narrate.py` — prompt and JSON parsing for the LLM engine.
- `fedaml/sar.py` — CLI, fixed outline, guardrails, markdown output `state/sar/<alert_id>.md`.
- `fedaml/llm/Dockerfile`, `fedaml/llm/fetch_model.sh` — the `llm` container (llama.cpp built from source)
  and the one-off model download + big-endian conversion into the `./models` volume.

## SAR outline (fixed) and who writes what
| Section | Written by |
|---|---|
| Subject | code |
| Summary of activity | LLM prose (placeholders) → values inserted by code; template otherwise |
| Pattern indicators | LLM prose per top feature → code; template otherwise |
| Institutions involved | code (table of bank ids, roles, chain rows) |
| Recommended action | LLM prose → code; template otherwise |
| Model attribution | code: model sha256, round, score, value × weight table |
| Footer | code: engine, seconds, tokens, fallback reason if any |

## Guardrails and fallback rule
- `max_tokens 400`, `temperature 0.2`, `seed 42`, JSON-constrained output (`response_format: json_object`).
- 60 s timeout; on timeout, transport error, malformed JSON, missing keys, unknown placeholder or any
  account-like token (hex ≥ 6 chars or ≥ 7 digits) that is not in the alert record, the engine falls back to
  the template and the footer says so with the reason.
- `--engine template` never touches the network and must always work; it is a legitimate deliverable.
- The final document is post-checked for account ids regardless of engine.

## Usage
```
python -m fedaml.alerts --test data/global_test.csv --model state/global_final.json --out state/alerts.json
python -m fedaml.sar --list
python -m fedaml.sar --alert-id A01 --engine llm        # falls back to template automatically
python -m fedaml.sar --alert-id A01 --engine template
python -m fedaml.sar --all --engine llm
```
Env: `LLM_URL` (default `http://127.0.0.1:8080`), `LLM_MODEL_PATH` + `LLAMA_SERVER_BIN` to auto-spawn, `LLM_THREADS`.

## Seconds per SAR (measured on the VM, `state/sar/_runs.jsonl`, synthetic fixture alerts A01–A03)
| Alert | Engine | Prompt tokens | Completion tokens | LLM seconds | Wall seconds (process) | Peak RSS |
|---|---|---|---|---|---|---|
| A01 | llm | 588 | 346 | 23.5 | 24.9 | 789 MB |
| A02 | llm | 588 | 346 | 23.2 | 24.6 | 789 MB |
| A03 | llm | 588 | 346 | 24.2 | 25.6 | 789 MB |
| any | template | — | — | — | < 1 | ~90 MB |

Wall time includes spawning `llama-server` (1 s) and loading the model; with the `llm` container already
running, a SAR takes the LLM seconds only. The 60 s timeout leaves more than 2× headroom. All three LLM SARs
passed the account-id post-check (no fallback).

## Container
`fedaml/llm/Dockerfile` builds llama.cpp from source in a multi-stage image (`fedaml-llm`, 289 MB, built on the
VM in 330 s). Weights live in the `./models` volume, not in the image. Measured: container reports healthy
6.4 s after `docker run`; the server process RSS is ~85 MB in `docker stats` because the 639 MiB GGUF is
memory-mapped (page cache), so budget ~0.8 GB while it answers.

```
docker build -f fedaml/llm/Dockerfile -t fedaml-llm .                  # once, ~5.5 min on the VM
docker run --rm -v ./models:/models fedaml-llm /app/fetch_model.sh     # once: download + big-endian convert (~1 min)
docker run -d --name llm -p 127.0.0.1:8080:8080 -v ./models:/models fedaml-llm
curl -s localhost:8080/health
```
Proposed `docker-compose.yml` fragment (MASTER owns the file):
```yaml
  llm:
    build: { context: ., dockerfile: fedaml/llm/Dockerfile }
    image: fedaml-llm
    container_name: llm
    profiles: ["tools"]
    volumes: ["./models:/models"]
    ports: ["127.0.0.1:8080:8080"]
    environment: { LLM_MODEL_FILE: qwen2.5-0.5b-instruct-q8_0-be.gguf, LLM_THREADS: "3" }
  genai:
    environment: { LLM_URL: http://llm:8080 }     # instead of host.docker.internal
    depends_on: { llm: { condition: service_healthy } }
```
Demo sequence: training finishes → `docker compose up -d llm` → `ALERT_ID=A01 SAR_ENGINE=llm docker compose run --rm genai`.
Never run the LLM while the five banks train: a parallel CPU-bound job cut generation from 39 to 6 tok/s in our test.

## Honest limits
- Qwen2.5-0.5B is a 0.5 B-parameter model: fluent but shallow. It is used for narration only; nothing it writes
  changes a score, an id or a number.
- Data are synthetic (IBM AML HI-Small). The SAR language is modelled on a FinCEN SAR narrative but is not a legal filing.
- Speed numbers are from one VM and one quantisation; DP, rounds and model quality are measured elsewhere.
