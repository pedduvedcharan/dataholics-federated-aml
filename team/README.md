# Team assignments (6 people)

| Person | Role | Drives these agent briefs | Waits on | Others wait on them for |
|---|---|---|---|---|
| P1 | Lead and integration | `agents/00-MASTER.md` | everyone | decisions, compose, demo, submission |
| P2 | Infra and data | `agents/01-INFRA.md` | Kaggle file | VM, partitioned data, sample CSV |
| P3 | Features and models | `agents/02-MODELS.md` | P2 (sample, then full data) | `features.py`, evaluator, baselines |
| P4 | Federation | `agents/03-FEDERATION.md` | P3 (features), P5 (egress) | global models, status.json |
| P5 | Audit and dashboard | `agents/05-AUDIT-DASHBOARD.md` | P4 (status files) | `egress.py` (early), dashboard |
| P6 | Red team and GenAI | `agents/04-REDTEAM.md`, `agents/06-GENAI.md` | P4 (dp-off/dp-on models), P3 (evaluator) | redteam table, SAR |

How to work: open your `team/P<n>-*.md`, then start a Claude session in `~/Documents/dataholics` and tell it "You are the <AGENT> agent, read CLAUDE.md, docs/CONTRACTS.md and agents/<brief>.md". You direct the agent; you review and commit what it produces. Post in `STATUS.md` every time you finish a task or get stuck, using the one-line format at the bottom of `agents/00-MASTER.md`.

Fill in names here once assigned:
- P1: Vedcharan Peddu
- P2:
- P3:
- P4:
- P5:
- P6:
