# P6 — Red team and GenAI

**Agent briefs you drive:** `agents/04-REDTEAM.md` and `agents/06-GENAI.md`. Two jobs: the attack table that is the video's centerpiece, and the LLM-written suspicious activity report that satisfies the generative lab. Do the LLM runtime test first because it has hard time caps and tells us early which path we have.

## Your deliverables
`fedaml/redteam.py`, `state/redteam.json`, `docs/REDTEAM.md`, `fedaml/sar.py`, `fedaml/llm/`, `state/alerts.json`, `state/sar/*.md`, `docs/GENAI.md`.

## Hour by hour
- **12:00–13:00** LLM runtime verdict on the VM (ask P2 for the venv). Try `pip install torch` (abort if it starts compiling), then transformers with a 0.5B instruct model; else llama.cpp built from source with a big-endian GGUF; else template. 20 minutes per path, hard stop. Record the verdict and seconds per 100 tokens in STATUS.md and `docs/GENAI.md`.
- **13:00–15:00** Red team v1: loss-threshold membership inference against any logreg from P3 (members = a sample of bank 1 train rows, non-members = matched sample from `global_test.csv`, balanced). Report attack accuracy and AUC. Then ART's black-box attack if it installed, else the tiny shadow attack. Keep v1 as fallback.
- **15:00–16:30** The `redteam` command and table per the brief, writing `state/redteam.json`, under 2 minutes on the VM. Run it on P4's `global_final_dpoff.json` and `global_final_dpon.json` as soon as they exist. If DP off barely leaks, ask P4 for a 5-epoch dp-off run and say so in the docs.
- **16:30–18:00** `state/alerts.json` with P3 (top-20 scored rows, chain rows, banks involved, top-5 feature contributions). `sar.py` with the strict outline; LLM fills prose only, code inserts numbers and the model hash; 60 s timeout and account-id post-check, template fallback. Generate SARs for 3 alerts on the VM.
- **18:00–20:00** `docs/REDTEAM.md` (threat model, what membership inference means for a customer, honest limits) and finish `docs/GENAI.md`. Rogue-bank evidence line with P4 in STATUS.md.
- **20:00–23:00** Rehearse your two scenes: the redteam table and one SAR. Time them, 40 s and 20 s.
- **23:00 onward** Narrate the red-team scene in the video. Then on call.

## Done when
`state/redteam.json` and three `state/sar/*.md` exist from VM runs, both docs are written, and your scenes fit their time slots.
