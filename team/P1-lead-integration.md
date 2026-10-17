# P1 — Lead and integration (Vedcharan)

**Agent brief you drive:** `agents/00-MASTER.md`. You are the human behind the MASTER agent. You make every cut and every contract decision. You do not write feature code unless someone is blocked and nobody else can help.

## Your deliverables
`STATUS.md` kept current, the GitHub repo, `docker-compose.yml`, `README.md`, `submission/DEMO_SCRIPT.md`, the video, the slides, the submission form.

## Hour by hour (CDT)
- **12:00–12:30** Repo already exists and is public: https://github.com/pedduvedcharan/dataholics-federated-aml (this folder). Put the URL in STATUS.md. Add everyone as collaborators. Confirm P2 has the VM host and key path. Confirm who downloads the Kaggle file.
- **12:30–13:00** Make sure every person has started their agent and knows their first deliverable. Fill names into `team/README.md`.
- **13:00, 14:00, 15:00 ... every hour** Read STATUS.md, update "Timeline check", compare with the timeline in CLAUDE.md, resolve blockers, and write each person's next deliverable. Anyone silent for 90 minutes: go talk to them.
- **15:00–17:30** Write `docker-compose.yml`: services `coordinator`, `bank1..bank4`, `rogue`, `dashboard` (profile default) and `attacker`, `genai` (profile `tools`). Same image `fedaml`, volumes `./data`, `./state`, `./logs`, network default, dashboard published on `127.0.0.1:8050`. Get the exact commands from P4, P5, P6.
- **17:30–20:00** `docker compose up` on the VM. Fix wiring. Run the full pipeline once end to end. Have P2 capture footprint and screenshots during this run.
- **20:00–23:00** Write `submission/DEMO_SCRIPT.md` (skeleton in the MASTER brief). Rehearse twice, timed, target 2:40. Write `README.md`: problem, architecture diagram (ask P5 for a draw.io or mermaid), how to run, results table with file-of-origin for every number, library and dataset links, claims-discipline notes.
- **23:00–02:00** Record the video (screen on the VM via SSH tunnel, 1280×720, one take per scene, stitch). Slides: 6 to 8, numbers only from `state/`. Have P6 narrate the red-team scene, P5 the regulator view.
- **02:00–06:00** Buffer. Stretch work only if every acceptance check in the MASTER brief is green.
- **06:00–07:00** Submit. Title `Dataholics_IBM Z Datathon 2026 Project`. Video link, repo link, library list, dataset link, optional diagram. Confirm the repo is public and has no data or key.

## Decisions you own
- Cut order (CLAUDE.md). Announce every cut in STATUS.md.
- Contract changes proposed in STATUS.md: accept or reject within 15 minutes and tell every affected person.
- Renaming `fedaml` before submission (optional).

## Done when
Submission confirmed before 7:00 AM, repo public, video under 3 minutes, every number on a slide traceable to a file.
