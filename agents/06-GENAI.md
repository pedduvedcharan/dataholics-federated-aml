# GENAI agent — the generative layer: Suspicious Activity Report writer

## Goal
Satisfy the mandatory generative-AI lab with something a compliance officer would actually use: a one-page SAR for a flagged cross-bank chain, written by a small CPU LLM running on the LinuxONE VM, with a template fallback that always works.

## You own
`fedaml/sar.py`, `fedaml/llm/`, `state/alerts.json`, `state/sar/`, `docs/GENAI.md`.

## Tasks, in order
1. **Runtime verdict on s390x (by 14:00, before anything else).** Try, in this order, each with a 20-minute cap, and record the result in STATUS.md:
   a. `pip install torch` in the venv (check whether an s390x wheel exists; if it starts compiling, abort). If torch imports, `pip install transformers` and run `Qwen/Qwen2.5-0.5B-Instruct` (or `ibm-granite/granite-3.1-1b-a400m-instruct` if it loads) for a 100-token generation; record seconds.
   b. Build `llama.cpp` from source on the VM (`cmake`, CPU only) and convert a small instruct model to GGUF with the big-endian flag (`convert_hf_to_gguf.py --bigendian`). Record tokens/s.
   c. If both fail, the engine is `template` and that is acceptable. Say so plainly in docs/GENAI.md.
2. **alerts.json.** Score `data/global_test.csv` with `state/global_final.json` (use MODELS' evaluator or the same logistic formula). Take the top 20 rows by score; for each, gather the chain: the sender's other transactions and the receiver's onward transactions in `global_test.csv` (regulator-side data in the demo), across banks where present. Write `state/alerts.json`: `[{"alert_id","score","rows":[...≤10 rows...],"banks_involved":[...],"top_features":[{"name","value","weight"}]}]`. `top_features` = feature value × coefficient, top 5 by absolute contribution.
3. **sar.py.** `python -m fedaml.sar --alert-id <id> --engine llm|template`. Build a strict prompt: the alert JSON, `docs/FEATURES.md` one-liners, and a fixed SAR outline (Subject, Summary of activity, Pattern indicators, Institutions involved, Recommended action, Model attribution with model sha256 and feature contributions). The LLM may only fill the prose fields; numbers, ids, and the model hash are inserted by code after generation. Output `state/sar/<alert_id>.md`. Template engine fills the same outline with sentences generated from the top features.
4. **Guardrails.** Max 400 tokens, temperature 0.2, 60 s timeout then fall back to template automatically and note it in the file footer. Never let the LLM invent account numbers: post-check that every account id in the output exists in the alert JSON, else fall back.
5. **docs/GENAI.md.** Which runtime ran on s390x, model name and size, seconds per SAR, the fallback rule, and the "LLM narrates, model decides" principle.
6. **Containerise** as the `genai` service (`docker compose run genai python -m fedaml.sar --alert-id ...`). If the model weights are large, keep them in a volume, not in the image.

## Pitfalls
- Big-endian: HF safetensors load fine through torch if torch itself works; GGUF must be converted big-endian. Do not spend more than the caps above; the template path is a legitimate deliverable.
- RAM: a 0.5B model in fp32 is ~2 GB; do not run it while all five banks train. Schedule SAR generation after training in the demo.

## Done when
`state/sar/<id>.md` exists for at least 3 alerts generated on the VM, and docs/GENAI.md states the runtime verdict.
