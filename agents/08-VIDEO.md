# VIDEO agent — the ≤3-minute submission video, built in Remotion (added Oct 17 2026, 19:50 CDT by MASTER at the lead's request)

## Goal
A dynamic, animated video of about 2:56 that explains the pitch, the architecture, the pipeline and the
notable results, driven by the real numbers from the LinuxONE VM, and timed to the narration in
`submission/VIDEO_SCRIPT.md`. It must leave a slot (scene 5) for a real screen recording of the live demo.

## You own
`video/` (a Remotion project: `package.json`, `src/`, `public/`, `remotion.config.ts`). `video/src/data.json`
is written by MASTER from the VM's state files: read it, never hand-edit a number in it. Outputs go to
`video/out/` (gitignored); audio and screen recordings in `video/public/` are gitignored.

## Read first
`CLAUDE.md`, `submission/VIDEO_SCRIPT.md` (the scene list, timings, visuals and narration — the source of truth),
`docs/UI_REFERENCE.md` (the last section, "IBM palette", is the color system), `video/src/data.json`,
`docs/architecture.md`.

## Tasks, in order
1. Scaffold a minimal Remotion project by hand in `video/` (no interactive `create-video` wizard): React + TypeScript,
   `remotion`, `@remotion/cli`, pinned exact versions; one composition `Dataholics` at 1920×1080, 30 fps,
   duration = 2:56 = 5280 frames, built from one `<Series>` of ten scene components with the script's exact
   frame lengths. Fonts: IBM Plex Sans / Sans Condensed / Mono via `@remotion/google-fonts` (or local CSS
   `@font-face` from Google Fonts). Colors: the IBM Carbon palette only.
2. Build each scene from the script's "On screen" column, animated with `interpolate` / `spring`, using
   `data.json` for every number and every chart (AUC per round, AP per round off vs on, red-team rows,
   baselines, footprint, alert queue, the A06 LLM paragraph). Charts drawn as SVG to scale. Captions:
   each scene shows its narration as a lower-third subtitle (so the video works even without audio).
3. Scene 5 (`live`): if `public/live-demo.mp4` exists, play it with `<OffthreadVideo>` filling the frame;
   otherwise show a clearly labelled placeholder card ("Live demo on IBM LinuxONE — screen recording goes here")
   for the same duration. If `public/voiceover.mp3` exists, add it as `<Audio>`.
4. Render a draft: `npx remotion render Dataholics out/dataholics-draft.mp4` (first render downloads Remotion's
   headless browser; that is expected). Also render 3 stills (`npx remotion still`) of scenes 4, 6 and 8 to
   `out/` for MASTER to check. Report render time and file size.
5. Commit `video/` source only (never `node_modules`, `out`, audio or video files); `.gitignore` already has
   the entries.

## Do not
- Invent or round a number differently from `data.json` / the script. Do not use "coin flip" for 0.517, or
  "detected laundering" anywhere; follow the script's claims-discipline list.
- Use the IBM logo, the 8-bar mark, or any other company's logo; text only.
- Touch the VM, `fedaml/`, or any other agent's files.

## Done when
`video/out/dataholics-draft.mp4` renders at 1920×1080, 2:56, with every scene's visuals and captions, the
scene-5 slot, real numbers throughout, and MASTER has the three stills.
