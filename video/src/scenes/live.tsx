// Scene 5 (1:06–1:40): the real screen recording from the VM, or a labelled placeholder.
import React from "react";
import { AbsoluteFill, OffthreadVideo, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { C, fonts } from "../theme";
import { SceneShell } from "../components/SceneShell";
import { Caption } from "../components/Caption";
import { useFadeUp } from "../components/anim";

const SHOTS = [
  "uname -m  →  s390x",
  "docker ps  →  bank1–4 + coordinator",
  "DP-on federated run starting",
  "dashboard: AUC curve filling, rows shared 0",
  "docker compose run --rm tryleak  →  BLOCKED, counter +1",
];

export const Live: React.FC<{ narration: string; hasLiveDemo: boolean; muteDemo: boolean }> = ({
  narration,
  hasLiveDemo,
  muteDemo,
}) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const card = useFadeUp(6);

  if (hasLiveDemo) {
    return (
      <AbsoluteFill style={{ background: C.gray100 }}>
        <OffthreadVideo
          src={staticFile("live-demo.mp4")}
          muted={muteDemo}
          style={{ width: "100%", height: "100%", objectFit: "contain" }}
        />
        <Caption text={narration} />
      </AbsoluteFill>
    );
  }

  const secs = Math.floor(frame / fps);
  const total = Math.round(durationInFrames / fps);
  return (
    <SceneShell tone="dark" index={5} kicker="Live on IBM LinuxONE" narration={narration}>
      <div
        style={{
          position: "absolute",
          left: 160,
          right: 160,
          top: 130,
          bottom: 30,
          border: `4px dashed ${C.gray60}`,
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          padding: "0 80px",
          ...card,
        }}
      >
        <div style={{ fontFamily: fonts.mono, fontSize: 24, color: C.yellow30, letterSpacing: 1 }}>PLACEHOLDER</div>
        <div style={{ fontFamily: fonts.condensed, fontWeight: 600, fontSize: 64, color: C.white, marginTop: 10 }}>
          Live demo on IBM LinuxONE — screen recording goes here ({total} s)
        </div>
        <div style={{ fontFamily: fonts.mono, fontSize: 24, color: C.gray30, marginTop: 14 }}>
          drop the file at video/public/live-demo.mp4 and render again
        </div>
        <div style={{ marginTop: 34 }}>
          {SHOTS.map((s, i) => (
            <div key={s} style={{ fontFamily: fonts.mono, fontSize: 28, color: C.white, marginTop: 10, display: "flex", gap: 18 }}>
              <span style={{ color: C.blue20 }}>{String(i + 1).padStart(2, "0")}</span>
              <span>{s}</span>
            </div>
          ))}
        </div>
        <div style={{ position: "absolute", right: 40, bottom: 30, fontFamily: fonts.mono, fontSize: 30, color: C.gray30 }}>
          00:{String(secs).padStart(2, "0")} / 00:{String(total).padStart(2, "0")}
        </div>
      </div>
    </SceneShell>
  );
};
