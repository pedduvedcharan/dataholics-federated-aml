# Walkthrough script — the 3-minute recording of the presentation website

Record the browser at http://localhost:8050 (SSH tunnel: `ssh -L 8050:localhost:8050 dataholics`), 1920×1080,
press **F** for full screen and **T** to start the on-screen timer. Keys: **→ / ←** next/back (on the Architecture tab
they step through the diagram), **1–4** jump to a tab, **Space** pauses the page-4 demo.
About 400 words at ~150 words per minute. Every number below is on screen and comes from a file on the VM.

**Before recording (VM):** nothing to do; it is already in the recording state (one clean run: 40 messages, 840 numbers,
0 rows, 0 blocked; model 16ef90c0; bank-local files present). If a training run happens again, archive
`logs/egress/*.jsonl` first and run one `TAG=dpon` run (see `submission/DEMO_SCRIPT.md`).

| Time | Tab / action | Say this |
|---|---|---|
| 0:00 | **1 · The Problem** (opens on the statistic) | "Money laundering is estimated at up to five percent of global GDP, up to four trillion dollars a year: a United Nations estimate, cited by the IMF. Criminals move it across banks. Each bank sees one harmless-looking fragment." |
| 0:12 | point at *connected vs fragmented* | "Financial crime is connected. Why isn't our defense? Banks can't simply pool customer records: privacy, confidentiality and regulation make that hard. So we built Federated AML Sentinel." |
| 0:20 | **Discover Our Solution →** (tab 2), step 1 | "Four banks, each with its own private data: IBM's synthetic anti-money-laundering dataset, five million simulated transactions." |
| 0:26 | → step 2 | "Each bank trains the same small model on its own data: twenty transaction features, twenty-one learned numbers." |
| 0:32 | → step 3 | "Before anything leaves, the bank clips its update, adds noise, and sends it through one audited door that refuses raw records." |
| 0:38 | → step 4 | "On IBM LinuxONE, the coordinator averages only those numbers into one shared model." |
| 0:44 | → step 5 (optionally Accelerate) | "It sends the improved model back, ten rounds, and each round builds on the last." |
| 0:50 | → step 6 | "And we attack it ourselves: a cheating bank, and a privacy attack. After training, every bank scores, alerts and reports on its own transactions, locally." |
| 0:55 | **See the results →** (tab 3) | "These are measured results from our run on LinuxONE. Alone, each bank reaches up to 0.986. Shared, without noise, 0.992. With privacy noise on, 0.982, and not one transaction row shared." |
| 1:15 | privacy card | "Did the privacy work? Without noise our attacker identifies training data with an AUC of 0.994. With noise, 0.517: close to chance. That costs one point of model accuracy, and we show the price." |
| 1:35 | rogue / LinuxONE panels | "A bank that poisons its updates is screened out in every round. Everything here was built and evaluated on IBM LinuxONE: s390x, in containers, under two gigabytes of memory." |
| 1:50 | **4 · Live Workflow**, click **Run End-to-End Demonstration** | "Now the part that matters to a bank. Training is done. Inside bank four, one transaction arrives: a synthetic, replayed transfer of 25.6 million euros." |
| 2:00 | stage 2–3 (score appears) | "Bank four's own copy of the shared model scores it: 0.9998, above this bank's alert threshold. The score is computed from the saved model, feature by feature." |
| 2:15 | stage 4 (alert) | "A local alert, top of the bank's queue, with the related payments the bank itself can see." |
| 2:25 | stage 5 (report) | "A small language model running on the same CPU drafts the investigator's report. Code writes every fact; the model writes one paragraph, and its claims are checked." |
| 2:37 | stage 6 (investigator → regulator) | "A person decides: flagged for human review, nothing is filed automatically. The regulator sees only aggregates: alert counts, model quality, logged transfers. No accounts, no amounts." |
| 2:50 | end line on screen | "Shared intelligence. Local decisions. Protected customer data. Federated AML Sentinel, by Dataholics." |

**Words to keep:** "estimated", "UN estimate cited by the IMF" · "synthetic", "replayed", "simulated banks" ·
"near chance" (0.517) · "measured on IBM LinuxONE" · "flagged for human review" · "logical boundary, one VM" if asked.
**Never say:** "IBM certified", "guaranteed private", "zero leakage", "illegal to share", "live bank data".
