// The whole video: one <Series> of ten scenes, frame lengths from the script's time slots.
import React from "react";
import { AbsoluteFill, Audio, Series, staticFile } from "remotion";
import { SCENES, SceneId } from "./script";
import { C } from "./theme";
import { Hook } from "./scenes/hook";
import { Problem } from "./scenes/problem";
import { Pitch } from "./scenes/pitch";
import { Architecture } from "./scenes/architecture";
import { Live } from "./scenes/live";
import { Results } from "./scenes/results";
import { Rogue } from "./scenes/rogue";
import { Redteam } from "./scenes/redteam";
import { Report } from "./scenes/report";
import { Close } from "./scenes/close";

export type VideoProps = {
  /** null = auto-detect public/live-demo.mp4 in calculateMetadata (see Root.tsx). */
  hasLiveDemo: boolean | null;
  /** null = auto-detect public/voiceover.mp3. */
  hasVoiceover: boolean | null;
};

const SIMPLE: Record<Exclude<SceneId, "live">, React.FC<{ narration: string }>> = {
  hook: Hook,
  problem: Problem,
  pitch: Pitch,
  architecture: Architecture,
  results: Results,
  rogue: Rogue,
  redteam: Redteam,
  report: Report,
  close: Close,
};

export const Video: React.FC<VideoProps> = ({ hasLiveDemo, hasVoiceover }) => (
  <AbsoluteFill style={{ background: C.gray100 }}>
    <Series>
      {SCENES.map((s) => {
        const len = s.to - s.from;
        if (s.id === "live") {
          return (
            <Series.Sequence key={s.id} durationInFrames={len} name={s.id}>
              <Live narration={s.narration} hasLiveDemo={!!hasLiveDemo} muteDemo={!!hasVoiceover} />
            </Series.Sequence>
          );
        }
        const Scene = SIMPLE[s.id];
        return (
          <Series.Sequence key={s.id} durationInFrames={len} name={s.id}>
            <Scene narration={s.narration} />
          </Series.Sequence>
        );
      })}
    </Series>
    {hasVoiceover ? <Audio src={staticFile("voiceover.mp3")} /> : null}
  </AbsoluteFill>
);
