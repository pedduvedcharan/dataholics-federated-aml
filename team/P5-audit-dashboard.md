# P5 — Audit and dashboard (the regulator view)

**Agent brief you drive:** `agents/05-AUDIT-DASHBOARD.md`. Your first hour unblocks P4; your afternoon builds the screen the video is filmed on.

## Your deliverables
`fedaml/egress.py`, `tests/test_egress.py`, `fedaml/dashboard/`, `scripts/try_leak.py`, dashboard screenshots, the architecture diagram for the README.

## Hour by hour
- **12:00–13:00** `egress.py` per CONTRACTS §5: forbidden-key check (case-insensitive, one level nested), list-length check, 64 KB cap, `EgressViolation`, audit line with `rows_shared: 0` and `params_shared`, POST with `requests`. `tests/test_egress.py` with the two cases. Push it and tell P4 immediately.
- **13:00–13:30** `summarize(logs_dir)` helper and `scripts/try_leak.py` (sends 5 raw rows, must be blocked and logged as `blocked`).
- **13:30–17:30** Dashboard: Flask on :8050, `/api/state` merging `status.json`, `redteam.json`, `baselines.json`, `footprint.json` and the egress summary; one HTML page, auto-refresh 3 s, Chart.js from CDN. Panels in order: regulator view counters and live egress tail, training AUC per round with baseline reference lines, privacy budget meter, rogue bank accept/exclude per round, red team table with verdict, footprint. Read files defensively; show "waiting" rather than crash. Test through `ssh -L 8050:localhost:8050 dataholics`.
- **17:30–20:00** Run the dashboard inside compose; make sure it reads the shared volumes; fix layout at 1280×720.
- **20:00–23:00** Architecture diagram (mermaid in the README is fine, or draw.io exported to PNG): banks, coordinator, rogue, attacker, dashboard, genai, with the single egress arrow labelled "model updates only". Screenshots of every panel with real data into `submission/screenshots/`.
- **23:00 onward** You present the regulator view scene in the video: counters, the live blocked attempt from `try_leak.py`, the privacy meter.

## Done when
Tests pass, P4's banks send through `egress.send`, all six panels show real VM data, screenshots and diagram are in `submission/`.
