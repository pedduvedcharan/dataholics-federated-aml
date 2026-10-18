# Dataholics video (Remotion)

The ≤3-minute submission video: composition `Dataholics`, 1920×1080, 30 fps, 5280 frames (2:56).
Scene list, timings and narration come from `submission/VIDEO_SCRIPT.md`; every number comes from
`src/data.json` (written by MASTER from the LinuxONE VM's state files; never hand-edit it).

## Render

```bash
cd video
npm install                      # first time only
npx tsc --noEmit                 # type check
npm run stills                   # out/still-architecture.png, still-results.png, still-redteam.png
npm run render                   # out/dataholics-draft.mp4   (~2 min on a laptop)
npm run studio                   # live preview in the browser
```

The first render downloads Remotion's headless Chrome. Fonts (IBM Plex Sans / Sans Condensed / Mono) load
from Google Fonts through `@remotion/google-fonts`, so rendering needs network access.

## Optional media (gitignored)

| File | Effect when present |
|---|---|
| `public/live-demo.mp4` | Scene 5 (`live`, 1:06–1:40, 34 s) plays it full frame with `<OffthreadVideo>`. Otherwise a labelled placeholder card. |
| `public/voiceover.mp3` | Added as one `<Audio>` track from 0:00. The live demo's own audio is then muted. |

Detection: `calculateMetadata` in `src/Root.tsx` sends a `HEAD` request for each file to Remotion's static
server before rendering; a 404 means "absent" and nothing crashes (the 404 lines in the render log are
expected). To force a choice, pass props:
`npx remotion render Dataholics out/x.mp4 --props='{"hasLiveDemo":false,"hasVoiceover":true}'`.
Just drop the file in `public/` and render again; no code change.

## Layout

- `src/Root.tsx` registerRoot + Composition; `src/Video.tsx` the `<Series>` of ten scenes.
- `src/script.ts` scene ids, time slots and narration (copied from the script; captions are generated from it).
- `src/data.ts` typed access to `data.json` plus derived values (1 in 981, exclusion counts, AP ratio).
- `src/theme.ts` IBM Carbon palette tokens (docs/UI_REFERENCE.md, "IBM palette") and fonts.
- `src/components/` Caption (lower third, timed by word count), SceneShell, chart helpers, Pill/Stamp.
- `src/scenes/<id>.tsx` one file per scene.

## Numbers not in data.json

Only "best single bank 0.986 / 0.405" in scene 6 comes from the script (`baselineBars` in `src/data.ts`);
everything else is read from `data.json`.
