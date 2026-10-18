// Scene 8 (2:14–2:34): membership-inference red team, dot-and-whisker with 90% CI, coin-flip line.
import React from "react";
import { useCurrentFrame } from "remotion";
import { C, fonts } from "../theme";
import { SceneShell } from "../components/SceneShell";
import { scale } from "../components/charts";
import { ramp, useEnter, useFadeUp } from "../components/anim";
import { Pill } from "../components/Pill";
import { data, fmt3, redRows } from "../data";

const W = 1760;
const H = 640;
const X0 = 420;
const X1 = 1340;
const x = scale(0.45, 1.0, X0, X1);
const rowY = (i: number) => 120 + i * 120;
const AXIS_Y = 590;

const label = (name: string) => (name === "DP off" ? "No noise" : `Noise ${name}`);

const verdict = (name: string, v: string, auc: number) => {
  if (v === "LEAKS") return { bg: C.red60, fg: C.white, text: "LEAKS", note: "" };
  if (v === "WEAK LEAK") return { bg: C.yellow30, fg: C.gray100, text: "WEAK LEAK", note: "first noise level" };
  const current = name === data.redteam.current_setting;
  // claims discipline: "near chance" for the current run (0.517), "coin flip" only for 0.497
  const note = current ? "near chance (this run)" : auc < 0.5 ? "at a coin flip" : "";
  return { bg: C.green50, fg: C.white, text: "PROTECTED", note };
};

const Row: React.FC<{ i: number }> = ({ i }) => {
  const frame = useCurrentFrame();
  const r = redRows[i];
  const delay = 60 + i * 110;
  const p = useEnter(delay);
  const wh = ramp(frame, delay + 10, delay + 40);
  const vp = useEnter(delay + 35);
  const y = rowY(i);
  const [lo, hi] = r.attack_auc_ci90;
  const cx = x(r.attack_auc);
  const v = verdict(r.name, r.verdict, r.attack_auc);
  const current = r.name === data.redteam.current_setting;
  return (
    <g opacity={p}>
      {current ? <rect x={20} y={y - 52} width={W - 40} height={104} fill={C.blue10} /> : null}
      <text x={60} y={y + 10} fontFamily={fonts.condensed} fontWeight={600} fontSize={36} fill={C.gray100}>
        {label(r.name)}
      </text>
      <line x1={cx - (cx - x(lo)) * wh} x2={cx + (x(hi) - cx) * wh} y1={y} y2={y} stroke={C.gray100} strokeWidth={4} />
      <line x1={cx - (cx - x(lo)) * wh} x2={cx - (cx - x(lo)) * wh} y1={y - 16} y2={y + 16} stroke={C.gray100} strokeWidth={4} opacity={wh} />
      <line x1={cx + (x(hi) - cx) * wh} x2={cx + (x(hi) - cx) * wh} y1={y - 16} y2={y + 16} stroke={C.gray100} strokeWidth={4} opacity={wh} />
      <circle cx={cx} cy={y} r={16 * p} fill={v.bg} stroke={C.gray100} strokeWidth={3} />
      {/* value label beside the whisker, never across the coin-flip line: right of it, or left for high values */}
      <text
        x={r.attack_auc > 0.75 ? x(lo) - 22 : x(hi) + 22}
        y={y + 10}
        textAnchor={r.attack_auc > 0.75 ? "end" : "start"}
        fontFamily={fonts.mono}
        fontWeight={600}
        fontSize={28}
        fill={C.gray100}
        opacity={wh}
      >
        {fmt3(r.attack_auc)}
      </text>
      <foreignObject x={1390} y={y - 40} width={360} height={90} opacity={vp}>
        <div>
          <Pill bg={v.bg} fg={v.fg} size={24}>
            {v.text}
          </Pill>
          {v.note ? <div style={{ fontFamily: fonts.sans, fontSize: 22, color: C.gray70, marginTop: 6 }}>{v.note}</div> : null}
        </div>
      </foreignObject>
    </g>
  );
};

export const Redteam: React.FC<{ narration: string }> = ({ narration }) => {
  const frame = useCurrentFrame();
  const card = useFadeUp(6);
  const coin = ramp(frame, 20, 50);
  const ticks = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0];
  return (
    <SceneShell tone="light" index={8} kicker="Red team" title="We attacked ourselves: membership inference" narration={narration}>
      <div style={{ position: "absolute", left: 80, top: 210, width: W, height: H + 20, background: C.white, ...card }}>
        <div style={{ position: "absolute", left: 60, top: 20, fontFamily: fonts.mono, fontSize: 20, color: C.gray70 }}>
          membership-inference attack AUC · dot = estimate, whiskers = 90% CI · an attack we wrote ourselves, on synthetic data
        </div>
        <svg width={W} height={H} style={{ position: "absolute", left: 0, top: 20 }}>
          {ticks.map((t) => (
            <g key={t}>
              <line x1={x(t)} x2={x(t)} y1={60} y2={AXIS_Y} stroke={C.gray20} strokeWidth={2} />
              <text x={x(t)} y={AXIS_Y + 34} textAnchor="middle" fontFamily={fonts.mono} fontSize={22} fill={C.gray70}>
                {t.toFixed(1)}
              </text>
            </g>
          ))}
          <line x1={X0} x2={X1} y1={AXIS_Y} y2={AXIS_Y} stroke={C.gray30} strokeWidth={2} />
          {redRows.map((_, i) => (
            <Row key={i} i={i} />
          ))}
          <line
            x1={x(0.5)}
            x2={x(0.5)}
            y1={60}
            y2={60 + (AXIS_Y - 60) * coin}
            stroke={C.blue60}
            strokeWidth={4}
            strokeDasharray="12 8"
          />
          <text x={x(0.5) + 12} y={76} fontFamily={fonts.mono} fontSize={22} fill={C.blue60} opacity={coin}>
            coin flip = 0.5
          </text>
          <text x={X0 - 40} y={AXIS_Y + 34} textAnchor="end" fontFamily={fonts.mono} fontSize={20} fill={C.gray70}>
            attack AUC
          </text>
        </svg>
      </div>
    </SceneShell>
  );
};
