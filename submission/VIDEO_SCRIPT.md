# Video script — Dataholics — 2:56, hard cap 3:00

Built for the Remotion video in `video/` (scene ids match `video/src/scenes/`). Narration is written at
about 150 words per minute; each scene's word count fits its slot. Every number is from a file on the
LinuxONE VM (integration run, 17 Oct 2026, 21:10–21:13 UTC; rehearsal run 22:02 UTC, same models).

**Two kinds of footage.** Scenes 1–4 and 6–10 are animated in Remotion from the real numbers. **Scene 5 is
a real screen recording from the VM** (the judges require a live demo on LinuxONE). Record it separately
and drop the file in as `video/public/live-demo.mp4`; until then the video shows a labelled placeholder.

Narrator: P1 by default; P5 can take scenes 4–5, P6 scenes 8–9 (marked). Speak to the timing marks;
the animation waits for nobody.

| # | Scene id | Time | On screen | Narration (say this) |
|---|---|---|---|---|
| 1 | `hook` | 0:00–0:14 | Three bank cards light up one by one; a red line of money hops A → B → C; each card says "looks normal". | "A criminal moves two million euros through three banks. Each bank sees one transfer, and each transfer looks normal. Nobody sees the scheme." (≈ 25 words) |
| 2 | `problem` | 0:14–0:28 | A pooled database icon forms, then a red stamp: "Shut down · TMNL · 2024". Two smaller notes: Singapore COSMIC, US 314(b). | "The obvious fix is to pool every bank's data. Five Dutch banks tried exactly that, and regulators shut it down in 2024. So we asked: what if the data never had to move?" (≈ 32 words) |
| 3 | `pitch` | 0:28–0:40 | Title card: "What the Dutch banks had to shut down, built so it would have been legal." Team, IBM Z Datathon 2026. | "We are Dataholics. We built what the Dutch banks had to shut down, so that it would have been legal: five banks, one shared detector, zero customer rows shared." (≈ 28 words) |
| 4 | `architecture` | 0:40–1:06 | The architecture diagram builds left to right: five bank boxes (data · train · clip + noise), the egress door, the coordinator (screen · average · send back), then dashboard, red team, AI report writer. A counter: "rows shared 0", "21 numbers per round". Dataset strip: 5,078,345 synthetic transactions, 1 in 981 laundering. *(P5 may narrate.)* | "On IBM's synthetic anti-money-laundering data, five million transactions split across five banks, each bank trains its own copy of one shared model, inside its own container. Only twenty-one numbers leave a bank each round, clipped and noised, through a single audited door that refuses raw data. The coordinator screens for cheaters, averages the rest, and sends the improved model back." (≈ 62 words) |
| 5 | `live` | 1:06–1:40 | **REAL SCREEN RECORDING** (34 s): VM terminal `uname -m` → s390x; `docker ps` with bank1–4 + coordinator; the DP-on run starting; cut to the dashboard: AUC curve filling, "rows shared 0"; `docker compose run --rm tryleak` → BLOCKED, counter goes up by one. Time-lapse label on any wait. *(P5 may narrate.)* | "This is it running live on an IBM LinuxONE machine, s390x, in sandboxed containers. Four banks and a coordinator train together. The regulator's dashboard shows every update arriving, and zero transaction rows shared. Now a bank tries to send five raw rows: the door blocks it, and the regulator sees the attempt." (≈ 55 words) |
| 6 | `results` | 1:40–1:58 | Line chart: pooled AUC per round, 0.844 → 0.982 (DP on). Then grouped bars, AUC and precision: best single bank 0.986 / 0.405, centralized pooling 0.983 / 0.088, ours no noise 0.992 / 0.248, ours with noise 0.982 / 0.065. | "Without noise, the shared model matches the best single bank, and finds about three times more real laundering per alert than pooling everyone's raw data. Privacy noise costs one point of AUC. We show that price, not hide it." (≈ 39 words) |
| 7 | `rogue` | 1:58–2:14 | Bank 5 turns red, its arrow thick and reversed. AP-per-round chart: defense off falls to 0.071, defense on climbs to 0.250. Badge: "bank 5 excluded 10 / 10 rounds · no honest bank excluded". | "Now one bank cheats, poisoning its updates to hide its own laundering. Without our defense, most alerts become false alarms. With it, the coordinator throws that bank out in ten of ten rounds, and never touches an honest one." (≈ 39 words) |
| 8 | `redteam` | 2:14–2:34 | Dot-and-whisker chart builds row by row: no noise 0.994 LEAKS, σ 0.3 0.551 weak leak, σ 0.5 0.517 near chance (this run), σ 0.8 0.497. Coin-flip line at 0.5. *(P6 may narrate.)* | "Then we attacked ourselves. Can the coordinator tell whether one suspect's transaction was in a bank's update? Without noise: ninety-nine percent. Our first noise level still leaked a little, so we raised it. Now it is near chance." (≈ 40 words) |
| 9 | `report` | 2:34–2:48 | The alert queue; A06 highlighted; its report card; the "written by the LLM" paragraph types out in purple; a stamp: "claim check rejected 2 of 3 LLM drafts". *(P6 may narrate.)* | "For each top alert, a small language model running on the same CPU drafts the suspicious activity report. Code writes every fact, and checks every claim the model makes. The model ranks; a person decides." (≈ 35 words) |
| 10 | `close` | 2:48–2:56 | Four numbers: 0 rows shared · 1,880 MB all containers · 2.1 s per round · 127 s end to end. Stack line: scikit-learn · Flask · IBM ART · llama.cpp · Qwen2.5 · Docker · IBM LinuxONE. Repo URL. | "All on one IBM LinuxONE machine, measured, not estimated. What the Dutch banks had to shut down, built so it would have been legal." (≈ 24 words) |

Total narration ≈ 379 words in 2:56.

## Claims discipline for the voice-over
Say "sandboxed containers" (not Secure Execution) · "synthetic data", "an attack we wrote ourselves" ·
"near chance" for 0.517, "coin flip" only for 0.497 · "matches the best single bank" only for the no-noise
model · "ranked for analyst review", never "detected laundering" · ε is never spoken as a guarantee.

## What the video agent needs from the humans
1. **Scene 5 screen recording**, 30–40 s, 1920×1080 if possible: follow `submission/DEMO_SCRIPT.md` pre-flight
   (archive egress logs only, `image_fresh.sh --rebuild`, `preflight_check.sh` GO), then terminal +
   dashboard through the SSH tunnel. Save as `video/public/live-demo.mp4`.
2. **The voice-over**, recorded as one audio file per scene or one take, saved as `video/public/voiceover.mp3`
   (optional: the video renders silent with on-screen captions if no audio is given).
3. After rendering, upload the MP4 (YouTube unlisted or Google Drive), and put the link in the deck's last
   slide, `README.md` and the submission form.
