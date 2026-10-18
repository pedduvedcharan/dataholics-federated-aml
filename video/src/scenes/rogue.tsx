// Scene 7 (1:58–2:14): bank 5 cheats; AP per round with the defense off vs on; exclusion badge.
import React from "react";
import { interpolate, useCurrentFrame } from "remotion";
import { C, fonts } from "../theme";
import { SceneShell } from "../components/SceneShell";
import { DrawnLine, XRounds, YGrid, scale } from "../components/charts";
import { ramp, useEnter, useFadeUp } from "../components/anim";
import { Pill } from "../components/Pill";
import { fmt3, honestExcluded, rogueExcludedRounds, rogueOffAp, rogueOnAp, rogueRounds } from "../data";

const NODE_X = 120;
const NODE_W = 200;
const NODE_H = 76;
const nodeY = (i: number) => 230 + i * 112;
const CO = { x: 600, y: 360, w: 220, h: 220 };

// chart geometry
const CW = 900;
const CH = 560;
const PL = 90;
const PR = 170;
const PT = 30;
const PB = 60;
const yAp = scale(0, 0.3, CH - PB, PT);
const xR = scale(0, 9, PL, CW - PR);

export const Rogue: React.FC<{ narration: string }> = ({ narration }) => {
  const frame = useCurrentFrame();
  const red = ramp(frame, 25, 45);
  const excl = useEnter(290, 12);
  const off = ramp(frame, 90, 230) * 9;
  const on = ramp(frame, 270, 400) * 9;
  const badge = useFadeUp(400);
  const chart = useFadeUp(70);
  const pulse = 1 + 0.08 * Math.sin(frame / 4) * (1 - ramp(frame, 280, 300));
  const offPts = rogueOffAp.map((v, i) => [xR(i), yAp(v)] as [number, number]);
  const onPts = rogueOnAp.map((v, i) => [xR(i), yAp(v)] as [number, number]);
  const coMid = CO.y + CO.h / 2;
  const rogueColor = interpolate(red, [0, 1], [0, 1]) > 0.5 ? C.red60 : C.blue60;

  return (
    <SceneShell tone="light" index={7} kicker="Rogue bank" title="One bank cheats. The coordinator throws it out." narration={narration}>
      {/* banks → coordinator */}
      <svg width={900} height={890} style={{ position: "absolute", left: 0, top: 0 }}>
        {[0, 1, 2, 3, 4].map((i) => {
          const rogue = i === 4;
          const y = nodeY(i) + NODE_H / 2;
          const x0 = NODE_X + NODE_W;
          const w = rogue ? 4 + 10 * red : 4;
          const cut = rogue ? excl : 0;
          return (
            <g key={i}>
              <line
                x1={x0}
                y1={y}
                x2={CO.x}
                y2={coMid + (i - 2) * 26}
                stroke={rogue ? (cut > 0.5 ? C.gray30 : rogueColor) : C.blue60}
                strokeWidth={w}
                strokeDasharray={rogue && cut > 0.5 ? "14 10" : undefined}
              />
              {rogue && red > 0.5 ? (
                // reversed arrowhead: the poisoned update pushes the model the wrong way
                <polygon
                  points={`${x0 + 6},${y} ${x0 + 40},${y - 18} ${x0 + 40},${y + 18}`}
                  fill={cut > 0.5 ? C.gray30 : C.red60}
                />
              ) : null}
            </g>
          );
        })}
        {excl > 0 ? (
          <g transform={`translate(${(NODE_X + NODE_W + CO.x) / 2}, ${(nodeY(4) + NODE_H / 2 + coMid + 52) / 2}) scale(${excl})`}>
            <line x1={-34} y1={-34} x2={34} y2={34} stroke={C.red60} strokeWidth={12} />
            <line x1={34} y1={-34} x2={-34} y2={34} stroke={C.red60} strokeWidth={12} />
          </g>
        ) : null}
      </svg>
      {[0, 1, 2, 3, 4].map((i) => {
        const rogue = i === 4;
        const bg = rogue && red > 0.5 ? C.red60 : C.blue10;
        return (
          <div
            key={i}
            style={{
              position: "absolute",
              left: NODE_X,
              top: nodeY(i),
              width: NODE_W,
              height: NODE_H,
              background: bg,
              border: `2px solid ${rogue && red > 0.5 ? C.red60 : C.blue20}`,
              color: rogue && red > 0.5 ? C.white : C.gray100,
              display: "flex",
              flexDirection: "column",
              justifyContent: "center",
              paddingLeft: 18,
              boxSizing: "border-box",
              transform: rogue ? `scale(${pulse})` : undefined,
            }}
          >
            <div style={{ fontFamily: fonts.condensed, fontWeight: 600, fontSize: 30 }}>Bank {i + 1}</div>
            <div style={{ fontFamily: fonts.mono, fontSize: 16 }}>{rogue && red > 0.5 ? "rogue · poisoned update" : "honest"}</div>
          </div>
        );
      })}
      <div
        style={{
          position: "absolute",
          left: CO.x,
          top: CO.y,
          width: CO.w,
          height: CO.h,
          background: C.white,
          border: `2px solid ${C.blue60}`,
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          alignItems: "center",
          textAlign: "center",
        }}
      >
        <div style={{ fontFamily: fonts.condensed, fontWeight: 600, fontSize: 32 }}>Coordinator</div>
        <div style={{ fontFamily: fonts.mono, fontSize: 17, color: C.gray70, marginTop: 6 }}>norm clip +</div>
        <div style={{ fontFamily: fonts.mono, fontSize: 17, color: C.gray70 }}>outlier exclusion</div>
      </div>
      <div style={{ position: "absolute", left: NODE_X + NODE_W + 40, top: nodeY(4) + NODE_H + 18, opacity: excl }}>
        <Pill bg={C.red60}>bank 5 EXCLUDED</Pill>
      </div>

      {/* AP per round, defense off vs on */}
      <div style={{ position: "absolute", left: 920, top: 190, width: CW, height: 680, background: C.white, padding: "22px 0 0 0", boxSizing: "border-box", ...chart }}>
        <div style={{ fontFamily: fonts.condensed, fontWeight: 600, fontSize: 32, paddingLeft: 30 }}>Average precision per round, rogue bank present</div>
        <div style={{ display: "flex", gap: 24, paddingLeft: 30, marginTop: 6, fontFamily: fonts.mono, fontSize: 19, color: C.gray70 }}>
          <span><span style={{ color: C.orange40 }}>━━</span> defense off</span>
          <span><span style={{ color: C.green50 }}>━━</span> defense on</span>
        </div>
        <svg width={CW} height={CH}>
          <YGrid ticks={[0, 0.1, 0.2, 0.3]} y={yAp} x0={PL} x1={CW - PR} />
          <XRounds n={10} x={xR} y={CH - PB + 34} />
          <text x={(PL + CW - PR) / 2} y={CH - 2} textAnchor="middle" fontFamily={fonts.mono} fontSize={20} fill={C.gray70}>
            round
          </text>
          <DrawnLine pts={offPts} progress={off} color={C.orange40} width={5} />
          <DrawnLine pts={onPts} progress={on} color={C.green50} width={5} />
          <g opacity={ramp(frame, 225, 240)}>
            <text x={xR(9) + 16} y={yAp(rogueOffAp[9]) + 8} fontFamily={fonts.mono} fontSize={26} fontWeight={600} fill={C.gray100}>
              {fmt3(rogueOffAp[9])}
            </text>
            <text x={xR(9) + 16} y={yAp(rogueOffAp[9]) + 34} fontFamily={fonts.sans} fontSize={18} fill={C.gray70}>
              defense off
            </text>
          </g>
          <g opacity={ramp(frame, 395, 410)}>
            <text x={xR(9) + 16} y={yAp(rogueOnAp[9]) + 8} fontFamily={fonts.mono} fontSize={26} fontWeight={600} fill={C.green50}>
              {fmt3(rogueOnAp[9])}
            </text>
            <text x={xR(9) + 16} y={yAp(rogueOnAp[9]) + 34} fontFamily={fonts.sans} fontSize={18} fill={C.gray70}>
              defense on
            </text>
          </g>
        </svg>
      </div>
      <div style={{ position: "absolute", left: 950, top: 800, ...badge }}>
        <Pill bg={C.green50} size={26}>
          bank 5 excluded {rogueExcludedRounds} / {rogueRounds} rounds · {honestExcluded === 0 ? "no honest bank excluded" : `${honestExcluded} honest exclusions`}
        </Pill>
      </div>
    </SceneShell>
  );
};
