// Scene 1 (0:00–0:14): three bank cards light up; a red line of money hops A → B → C.
import React from "react";
import { useCurrentFrame } from "remotion";
import { C, fonts } from "../theme";
import { SceneShell } from "../components/SceneShell";
import { DrawnLine } from "../components/charts";
import { ramp, useEnter, useFadeUp } from "../components/anim";
import { Pill } from "../components/Pill";

const CARD_W = 420;
const CARD_H = 270;
const CY = 470;
const XS = [380, 960, 1540];

const arc = (x0: number, x1: number, y: number, lift: number): [number, number][] =>
  Array.from({ length: 41 }, (_, i) => {
    const t = i / 40;
    const cx = (x0 + x1) / 2;
    const cy = y - lift;
    const x = (1 - t) ** 2 * x0 + 2 * (1 - t) * t * cx + t ** 2 * x1;
    const yy = (1 - t) ** 2 * y + 2 * (1 - t) * t * cy + t ** 2 * y;
    return [x, yy];
  });

const BankCard: React.FC<{ name: string; delay: number; sees: string; lit: boolean }> = ({ name, delay, sees, lit }) => {
  const p = useEnter(delay, 14);
  const i = XS[["Bank A", "Bank B", "Bank C"].indexOf(name)];
  return (
    <div
      style={{
        position: "absolute",
        left: i - CARD_W / 2,
        top: CY - CARD_H / 2,
        width: CARD_W,
        height: CARD_H,
        background: C.gray90,
        border: `3px solid ${lit ? C.blue60 : C.gray70}`,
        boxShadow: lit ? `0 0 60px rgba(15,98,254,0.35)` : "none",
        padding: 30,
        opacity: p,
        transform: `scale(${0.85 + 0.15 * p})`,
        color: C.white,
      }}
    >
      <div style={{ fontFamily: fonts.condensed, fontWeight: 600, fontSize: 46 }}>{name}</div>
      <div style={{ fontFamily: fonts.mono, fontSize: 24, color: C.gray30, marginTop: 10 }}>sees 1 transfer</div>
      <div style={{ fontFamily: fonts.mono, fontSize: 26, marginTop: 6 }}>{sees}</div>
      <div style={{ marginTop: 26 }}>
        <Pill bg={C.green50}>looks normal</Pill>
      </div>
    </div>
  );
};

export const Hook: React.FC<{ narration: string }> = ({ narration }) => {
  const frame = useCurrentFrame();
  const a1 = ramp(frame, 120, 165) * 40;
  const a2 = ramp(frame, 185, 230) * 40;
  const arc1 = arc(XS[0] + 120, XS[1] - 120, CY - CARD_H / 2 - 10, 150);
  const arc2 = arc(XS[1] + 120, XS[2] - 120, CY - CARD_H / 2 - 10, 150);
  const dot = (pts: [number, number][], prog: number) => pts[Math.min(40, Math.round(prog))];
  const scheme = useFadeUp(270);
  const bracket = ramp(frame, 260, 300);
  return (
    <SceneShell tone="dark" index={1} kicker="The blind spot" narration={narration}>
      <div style={{ position: "absolute", top: 110, left: 80, fontFamily: fonts.condensed, fontWeight: 600, fontSize: 60, ...useFadeUp(6) }}>
        One scheme, three banks, three normal-looking transfers.
      </div>
      <BankCard name="Bank A" delay={20} sees="€2.0M  out → Bank B" lit={frame > 20 && frame < 120 + 60} />
      <BankCard name="Bank B" delay={55} sees="€2.0M  in → out" lit={frame > 140 && frame < 250} />
      <BankCard name="Bank C" delay={90} sees="€2.0M  in" lit={frame > 210} />
      <svg width={1920} height={890} style={{ position: "absolute", left: 0, top: 0 }}>
        <DrawnLine pts={arc1} progress={a1} color={C.red60} width={6} dots={false} />
        <DrawnLine pts={arc2} progress={a2} color={C.red60} width={6} dots={false} />
        {a1 > 0 && a1 < 40 ? <circle cx={dot(arc1, a1)[0]} cy={dot(arc1, a1)[1]} r={14} fill={C.red60} /> : null}
        {a2 > 0 && a2 < 40 ? <circle cx={dot(arc2, a2)[0]} cy={dot(arc2, a2)[1]} r={14} fill={C.red60} /> : null}
        {/* the whole scheme, visible to nobody */}
        <rect
          x={XS[0] - CARD_W / 2 - 24}
          y={CY + CARD_H / 2 + 34}
          width={(XS[2] - XS[0] + CARD_W + 48) * bracket}
          height={6}
          fill={C.red60}
        />
      </svg>
      <div
        style={{
          position: "absolute",
          top: CY + CARD_H / 2 + 64,
          width: "100%",
          textAlign: "center",
          fontFamily: fonts.condensed,
          fontWeight: 600,
          fontSize: 50,
          color: C.white,
          ...scheme,
        }}
      >
        The scheme: <span style={{ color: C.red60 }}>visible to no single bank</span>
      </div>
      <div style={{ position: "absolute", right: 80, top: 190, fontFamily: fonts.mono, fontSize: 20, color: C.gray60 }}>
        illustration
      </div>
    </SceneShell>
  );
};

