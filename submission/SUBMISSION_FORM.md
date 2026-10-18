# Submission form — ready to paste (IBM Z Datathon 2026, deadline 07:00 CDT Sunday)

**Title:** Dataholics_IBM Z Datathon 2026 Project

**Project name:** Federated AML Sentinel

**One-line summary:** Banks train one money-laundering detector together on IBM LinuxONE without pooling customer
transactions, prove the privacy by attacking their own model, screen out a cheating bank, and score, alert and draft
investigator reports locally inside each bank.

**Description (≈ 120 words):**
Criminals split laundering schemes across banks, and each bank sees only a fragment; pooling customer records to see the
whole picture is hard under privacy and regulatory constraints. Federated AML Sentinel lets banks train one shared
logistic-regression detector by exchanging only 21 clipped, noised numbers per round through an audited door; raw rows
never leave a bank. We attack ourselves: a membership-inference attack drops from AUC 0.994 to 0.517 with bank-side
noise, and a poisoning bank is excluded in 10 of 10 rounds. After training, each bank scores its own transactions,
builds its own alert queue and gets an investigator report drafted by a small LLM on the same CPU, with every claim
checked. Everything runs in containers on IBM LinuxONE (s390x). Data and attacks are synthetic.

**Theme fit (AI Secured: Innovation Without Exposure):** data never leaves a bank; the regulator API is aggregate-only;
the model is attacked by us to measure leakage; the LLM never sees account ids; sandboxed containers on LinuxONE.

**Both IBM labs:** Predictive multi-model (logistic regression, random forest, gradient boosting per bank, centralized
pooling and the federated model compared) · Predictive + Generative AI (federated model + Qwen2.5 on llama.cpp built for
big-endian s390x).

**Links**
- Video (≤ 3 min): `[VIDEO LINK]` ← upload `video/out/dataholics-submission.mp4` (2:56, 1920×1080, 8.4 MB; scene 5 = screenshots of the running system on LinuxONE, labelled as such)
- Public repository: https://github.com/pedduvedcharan/dataholics-federated-aml
- Dataset: https://www.kaggle.com/datasets/ealtman2019/ibm-transactions-for-anti-money-laundering-aml
- Open-source libraries: see `submission/LIBRARIES.md` (paste the list) and README §5
- Architecture diagram: `docs/architecture.svg` (or a screenshot of the website's Architecture tab, step 6 / Show Full)
- Optional: slide deck PDF `submission/slides.pdf`

**Screenshots for criterion 3** (in `submission/screenshots/`): `01_vm_facts.txt` (uname, lscpu s390x), `02_docker_ps.txt`
(docker ps + stats with 4 banks training), `dashboard_*.png` (regulator panels, red team, rogue, footprint, alerts).

**Before pressing submit:** repo is public (yes, verified); no data, `.pem` or secrets in git; README links work; the video
is under 3:00 and playable without sign-in.
