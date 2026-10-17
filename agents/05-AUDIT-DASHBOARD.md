# AUDIT agent — egress audit function and the regulator dashboard (addition #2)

## Goal
Prove, visibly and continuously, that no transaction row ever leaves a bank. One function is the only door out of a bank; it refuses raw data and logs everything. A dashboard turns those logs plus `state/*.json` into the "regulator view" the video shows.

## You own
`fedaml/egress.py`, `fedaml/dashboard/` (Flask app + one HTML page), `logs/egress/`.

## Tasks, in order
1. **egress.py (by 14:00, highest priority — FEDERATION blocks on it).** Implement CONTRACTS §5 exactly. `send(coordinator_url, payload, bank_id, round) -> dict`. Checks: forbidden keys (case-insensitive, also nested one level), no list longer than `len(FEATURE_NAMES)+1`, payload must be JSON-serialisable and under 64 KB. On violation raise `EgressViolation` and ALSO log a line with `"kind":"blocked"`. Append the audit line, POST with `requests`, return the JSON response. Unit test file `tests/test_egress.py`: a payload containing a `rows` key raises; a valid update is logged with `rows_shared: 0`.
2. **Egress summary helper.** `summarize(logs_dir) -> {"per_bank": {id: {"messages","bytes","params_shared","rows_shared","blocked"}}, "totals": {...}}`.
3. **Dashboard v1 (by 17:30).** `python -m fedaml.dashboard --port 8050`, Flask, binds 127.0.0.1 inside the container, exposed via compose on the VM's localhost, reached from the Mac by `ssh -L 8050:localhost:8050 dataholics`. One page, auto-refresh every 3 s via `fetch('/api/state')` which returns a merge of `state/status.json`, `state/redteam.json`, `state/baselines.json`, `state/footprint.json`, and the egress summary. Panels, top to bottom:
   - **Regulator view**: big counters "Transaction rows shared: 0", "Model parameters shared: N", "Messages: N", "Blocked attempts: N", and a live tail of the last 10 egress lines.
   - **Training**: global AUC per round (line), horizontal reference lines for each bank's best single-model AUC and the centralized ceiling from baselines.json.
   - **Privacy budget meter**: epsilon_spent vs a chosen budget (e.g. 8), as a gauge/bar; sigma and clip shown.
   - **Rogue bank**: per round, which banks were accepted/excluded with reasons.
   - **Red team**: the redteam.json table, with a green/red verdict.
   - **Footprint**: per-container peak RSS and seconds per round.
   Use plain HTML + inline JS; Chart.js from a CDN is fine (the browser is on the Mac). No Streamlit, no pyarrow.
4. **Blocked-attempt demo hook.** A tiny script `scripts/try_leak.py` that calls `egress.send` with a payload containing 5 raw rows, so the demo can show the red "blocked" counter increment live.
5. **Screenshots** of every panel into `submission/screenshots/dashboard_*.png` once real data flows.

## Pitfalls
- Read JSON files defensively (they may be mid-rename); never crash the page on a missing file, show "waiting".
- Keep the page readable at 1280×720, since the video will be recorded at that size.

## Done when
`tests/test_egress.py` passes, FEDERATION's banks log through `egress.send`, and the dashboard shows all six panels with real data from the VM.
