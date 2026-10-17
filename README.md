# Dataholics — Cross-Bank Anti-Money-Laundering via Federated Learning

IBM Z Datathon 2026 · Theme: **AI Secured: Innovation Without Exposure** · Team Dataholics, UT Dallas

> What the Dutch banks had to shut down, built so it would have been legal.

Criminals split one laundering scheme across several banks because each bank can only see its own slice. Pooling raw transactions to fix this was ruled illegal in the EU (TMNL, 2024). This project lets banks train **one shared laundering detector without any transaction leaving a bank**, adds differential privacy so no customer can be recovered from what is shared, detects and excludes a rogue bank, and then **attacks its own model** to prove the protection works. A small CPU LLM writes the suspicious activity report. Everything runs in containers on an IBM LinuxONE (s390x) VM.

Status: under construction during the event (Oct 17–18, 2026). See `STATUS.md`.

- Project context and conventions: `CLAUDE.md`
- Shared interfaces every module obeys: `docs/CONTRACTS.md`
- Agent briefs: `agents/` · Team assignments: `team/`

Dataset: IBM Transactions for Anti Money Laundering (synthetic, Kaggle, HI-Small). Not stored in this repo.
