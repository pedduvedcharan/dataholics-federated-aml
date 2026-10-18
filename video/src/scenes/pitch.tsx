// Scene 3 (0:28–0:40): title card with the pitch line.
import React from "react";
import { useCurrentFrame } from "remotion";
import { C, fonts } from "../theme";
import { SceneShell } from "../components/SceneShell";
import { ramp, useFadeUp } from "../components/anim";
import { data, fmtInt } from "../data";

const LINE = "What the Dutch banks had to shut down, built so it would have been legal.";

const Stat: React.FC<{ n: string; label: string; delay: number }> = ({ n, label, delay }) => (
  <div style={{ width: 440, borderTop: `4px solid ${C.blue20}`, paddingTop: 18, ...useFadeUp(delay) }}>
    <div style={{ fontFamily: fonts.mono, fontWeight: 600, fontSize: 92, color: C.white, lineHeight: 1 }}>{n}</div>
    <div style={{ fontFamily: fonts.sans, fontSize: 32, color: C.blue20, marginTop: 10 }}>{label}</div>
  </div>
);

export const Pitch: React.FC<{ narration: string }> = ({ narration }) => {
  const frame = useCurrentFrame();
  const words = LINE.split(" ");
  const bankCount = Object.keys(data.partition.banks).length;
  return (
    <SceneShell tone="blue" index={3} kicker="The pitch" narration={narration}>
      <div style={{ position: "absolute", top: 170, left: 120, right: 120 }}>
        <div style={{ fontFamily: fonts.condensed, fontWeight: 600, fontSize: 96, lineHeight: 1.08, color: C.white }}>
          {words.map((w, i) => (
            <span key={i} style={{ opacity: ramp(frame, 8 + i * 4, 20 + i * 4), marginRight: 22, display: "inline-block" }}>
              {w}
            </span>
          ))}
        </div>
        <div style={{ fontFamily: fonts.mono, fontSize: 28, color: C.blue20, marginTop: 30, ...useFadeUp(70) }}>
          Team Dataholics · UT Dallas · IBM Z Datathon 2026
        </div>
      </div>
      <div style={{ position: "absolute", top: 600, left: 120, display: "flex", gap: 80 }}>
        <Stat n={String(bankCount)} label="banks" delay={110} />
        <Stat n="1" label="shared detector" delay={130} />
        <Stat n={fmtInt(data.egress_one_run.rows_shared)} label="customer rows shared" delay={150} />
      </div>
    </SceneShell>
  );
};
