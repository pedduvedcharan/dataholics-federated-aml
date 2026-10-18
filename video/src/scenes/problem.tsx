// Scene 2 (0:14–0:28): pooled database forms, then a red stamp "Shut down · TMNL · 2024".
import React from "react";
import { useCurrentFrame } from "remotion";
import { C, fonts } from "../theme";
import { SceneShell } from "../components/SceneShell";
import { lerp, ramp, useEnter, useFadeUp } from "../components/anim";
import { Stamp } from "../components/Pill";

const DB_X = 560;
const DB_Y = 470;

const Cylinder: React.FC<{ p: number }> = ({ p }) => (
  <svg width={360} height={300} style={{ position: "absolute", left: DB_X - 180, top: DB_Y - 150, opacity: p }}>
    <g transform={`translate(30,30) scale(${0.8 + 0.2 * p})`}>
      <path d="M0,40 L0,200 A150,40 0 0 0 300,200 L300,40" fill={C.gray90} stroke={C.gray30} strokeWidth={4} />
      <ellipse cx={150} cy={40} rx={150} ry={40} fill={C.gray70} stroke={C.gray30} strokeWidth={4} />
      <path d="M0,120 A150,40 0 0 0 300,120" fill="none" stroke={C.gray60} strokeWidth={3} />
    </g>
  </svg>
);

const Note: React.FC<{ delay: number; head: string; body: string; y: number }> = ({ delay, head, body, y }) => (
  <div
    style={{
      position: "absolute",
      left: 1080,
      top: y,
      width: 760,
      background: C.gray90,
      borderLeft: `6px solid ${C.gray60}`,
      padding: "22px 30px",
      ...useFadeUp(delay),
    }}
  >
    <div style={{ fontFamily: fonts.condensed, fontWeight: 600, fontSize: 36, color: C.white }}>{head}</div>
    <div style={{ fontFamily: fonts.sans, fontSize: 28, color: C.gray30, marginTop: 6 }}>{body}</div>
  </div>
);

export const Problem: React.FC<{ narration: string }> = ({ narration }) => {
  const frame = useCurrentFrame();
  const db = useEnter(70);
  const stamp = useEnter(150, 12);
  const q = useFadeUp(300);
  const banks = [0, 1, 2, 3, 4];
  return (
    <SceneShell tone="dark" index={2} kicker="The obvious fix" title="Pool everyone's data?" narration={narration}>
      {banks.map((i) => {
        const t = ramp(frame, 15 + i * 8, 95 + i * 8);
        const sx = 120 + i * 180;
        const sy = 250;
        const x = lerp(sx, DB_X - 60 + (i - 2) * 22, t);
        const y = lerp(sy, DB_Y - 40, t);
        return (
          <div
            key={i}
            style={{
              position: "absolute",
              left: x,
              top: y,
              width: 120,
              height: 64,
              background: C.blue60,
              color: C.white,
              fontFamily: fonts.mono,
              fontSize: 22,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              opacity: 1 - ramp(frame, 90 + i * 8, 110 + i * 8),
              transform: `scale(${1 - 0.5 * t})`,
            }}
          >
            bank {i + 1}
          </div>
        );
      })}
      <Cylinder p={db} />
      <div
        style={{
          position: "absolute",
          left: DB_X - 360,
          width: 720,
          top: DB_Y + 160,
          textAlign: "center",
          fontFamily: fonts.mono,
          fontSize: 26,
          color: C.gray30,
          opacity: db,
        }}
      >
        one pooled database of raw transactions
      </div>
      <div style={{ position: "absolute", left: DB_X - 330, width: 660, top: DB_Y - 60, textAlign: "center" }}>
        {frame >= 150 ? (
          <Stamp p={stamp} color={C.red60} size={52}>
            Shut down · TMNL · 2024
          </Stamp>
        ) : null}
      </div>
      <Note delay={200} y={250} head="Netherlands · TMNL" body="Five banks pooled monitoring data; shut down in 2024." />
      <Note delay={225} y={410} head="Singapore · COSMIC" body="Banks share only after a suspicion already exists." />
      <Note delay={250} y={570} head="United States · 314(b)" body="Voluntary information sharing, barely used." />
      <div
        style={{
          position: "absolute",
          top: 760,
          width: "100%",
          textAlign: "center",
          fontFamily: fonts.condensed,
          fontWeight: 600,
          fontSize: 58,
          color: C.white,
          ...q,
        }}
      >
        What if the data <span style={{ color: C.blue20 }}>never had to move?</span>
      </div>
    </SceneShell>
  );
};
