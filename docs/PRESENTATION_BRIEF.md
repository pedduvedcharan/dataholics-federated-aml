# Lead's brief: redesign the existing website into a 3-minute interactive IBM Datathon presentation (Oct 17 2026, 20:55 CDT)

Verbatim summary of the team lead's requirements; the decisions and verified facts are in `docs/PRESENTATION_SITE.md`,
the data contract in `docs/CONTRACTS.md` §9.

- Redesign and extend the EXISTING Flask dashboard (`fedaml/dashboard/static/index.html`, `fedaml/dashboard/__init__.py`,
  `/api/state`); keep functionality, API integrations, backend services and security tests intact. No separate app.
- The webpage is the entire ≤ 3-minute recorded presentation: four tabs **The Problem → Our Architecture →
  Results & Dashboard → Live Workflow**, presenter-controlled next/back, subtle progress indicator, optional
  elapsed timer toward 3:00, full-screen mode if practical, optimized for a 1920×1080 recording.
- **Page 1 — The Problem (0:00–0:20):** huge sourced statistic ("UP TO 5% OF GLOBAL GDP", up to $4 trillion a year,
  UN estimate cited by the IMF) with a subtle animated counter and a restrained global-network background; an
  animated "CRIMINAL NETWORKS — CONNECTED" vs "BANK INTELLIGENCE — FRAGMENTED" visual readable in 5–7 s;
  line "Financial crime is connected. Why isn't our defense?"; then "DATAHOLICS PRESENTS — FEDERATED AML
  SENTINEL", subtitle "Collaborative financial crime detection without pooling private banking records". Do not
  say all sharing is illegal; the challenge is privacy, confidentiality, security and regulatory constraints that
  make unrestricted pooling difficult. Button "Discover Our Solution →".
- **Page 2 — Interactive architecture (0:20–0:55):** reveals ONE step per click, 6 steps with "1 of 6" counter,
  Next/Previous, arrow keys, only active components highlighted, 300–500 ms transitions, "Show Full Architecture",
  "Reset Animation", button to the dashboard. Steps: (1) four private bank environments with dataset, local model
  ("IBM Synthetic AML Dataset — HI-Small", ≈ 5.08 M simulated transactions; never "certified"); (2) local training
  "20 engineered transaction features → Logistic Regression → 21 learned parameters" with tooltip; (3) privacy
  layer "L2 Clipping → Gaussian Noise → Audited Egress" with tooltips and locks, no claim of strong formal
  record-level guarantees; (4) update packets to "IBM LinuxONE — Federated Learning Coordinator", "FedAvg combines
  the banks' accepted model updates into one shared model", parameters vs raw records; (5) global model back to the
  banks, "10 Federated Training Rounds", training-loop counter with accelerate option, banks don't restart from
  scratch; (6) security: rogue-bank poisoning simulation, coordinator screening, membership-inference red team; and
  "Global model → Bank-local transaction scoring → Bank-local alerts → Bank-local GenAI reports". Distinguish
  completed from planned features. Lightweight HTML/CSS/SVG/JS only.
- **Page 3 — Results & Dashboard (0:55–1:50, the most time after page 4):** Before (isolated banks) vs After
  (Federated AML Sentinel) comparison without implying reconstruction of cross-bank networks; real ML performance
  (per-bank, federated, centralized baseline clearly labelled as an experimental comparison, training per round,
  ROC-AUC, average precision, privacy on vs off) from the state files/APIs, never invented; "BEFORE PRIVACY →
  AFTER PRIVACY" membership-attack AUC with the explanation "Lower attack AUC means the tested attacker has more
  difficulty identifying training membership. Approximately 0.5 is chance-level discrimination."; rogue screening,
  audited messages, raw rows exchanged through training egress, privacy/performance trade-off; an IBM LinuxONE
  platform panel ("Built and evaluated on IBM LinuxONE.": s390x, containers, CPU/memory measured). Must feel like a
  functioning banking AI monitoring product.
- **Page 4 — Live Workflow (1:50–3:00, the most important):** after training is finished: "Bank Transaction →
  Local Model → Risk Score → Local Alert → Local GenAI Report → Bank Investigator", all inside a simulated private
  bank environment; outside only the coordinator and permitted aggregates; NO arrow carrying private transaction
  details to the coordinator. One button "Run End-to-End Demonstration" with pause / restart / skip, 40–55 s,
  deterministic, clearly a replay of a synthetic transaction, not live banking. Stages: (1) transaction (from the
  synthetic IBM data, labelled); (2) local ML scoring with the real model score and threshold (never invented);
  (3) bank-local alert (id, score, indicators, related same-bank transactions, priority) or a correct non-alert;
  (4) bank-local GenAI report (reason, context, indicators, next steps; LLM vs template labelled); (5) investigator
  review "Flagged for human review" — no automatic guilt or filing; (6) zoom out to the regulator view with
  aggregates only (alert counts, model metrics, round status, logged update transfers), no ids, amounts or histories;
  end with "Shared intelligence. Local decisions. Protected customer data."
- **Design:** IBM-inspired blue, deep navy, white, neutral gray; strong typography, large readable numbers, clean
  diagrams with meaningful arrows, minimal text, subtle motion, professional banking/cybersecurity language,
  high contrast for screen sharing. Not a generic fintech template, not static slides pretending to be an app.
- **Engineering:** don't retrain or replace models; reuse `/api/state`; no raw transaction data in the central API;
  bank-scoped endpoint with a boundary for local investigation demos (or clearly labelled demo data); preserve
  s390x; low CPU/RAM (3 cores, 8 GB); keep working when a state file or API is missing; never substitute fake
  success values; keep tests passing and add tests for new interactions and data-exposure boundaries.
- **Deliverables:** implement in the repo; preserve backend and ML; four pages; click-through architecture; improved
  real dashboard; end-to-end bank-local workflow; verify on LinuxONE; document changed files and commands; identify
  measured vs simulated elements; explain anything unfinished.
