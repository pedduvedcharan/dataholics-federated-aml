// Scene 6 (1:40–1:58): pooled AUC per round (DP on vs no noise), then AUC / AP bars vs baselines.
import React from "react";
import { useCurrentFrame } from "remotion";
import { C, fonts } from "../theme";
import { SceneShell } from "../components/SceneShell";
import { DrawnLine, XRounds, YGrid, scale } from "../components/charts";
import { ramp, useFadeUp } from "../components/anim";
import { baselineBars, dpoffAuc, dponAuc, fmt3 } from "../data";

// line chart geometry (SVG coordinates inside the left card)
const LW = 800;
const LH = 560;
const PL = 90;
const PR = 150;
const PT = 56;
const PB = 60;
const yAuc = scale(0.8, 1.0, LH - PB, PT);
const xR = scale(0, 9, PL, LW - PR);

const AucChart: React.FC = () => {
  const frame = useCurrentFrame();
  const on = ramp(frame, 20, 200) * 9;
  const off = ramp(frame, 60, 220) * 9;
  const onPts = dponAuc.map((v, i) => [xR(i), yAuc(v)] as [number, number]);
  const offPts = dpoffAuc.map((v, i) => [xR(i), yAuc(v)] as [number, number]);
  const endOn = ramp(frame, 195, 215);
  const endOff = ramp(frame, 215, 235);
  return (
    <svg width={LW} height={LH}>
      <YGrid ticks={[0.8, 0.85, 0.9, 0.95, 1.0]} y={yAuc} x0={PL} x1={LW - PR} />
      <XRounds n={10} x={xR} y={LH - PB + 34} />
      <text x={(PL + LW - PR) / 2} y={LH - 2} textAnchor="middle" fontFamily={fonts.mono} fontSize={20} fill={C.gray70}>
        round
      </text>
      <DrawnLine pts={offPts} progress={off} color={C.purple70} width={3} dash="10 8" dots={false} />
      <DrawnLine pts={onPts} progress={on} color={C.blue60} width={5} />
      <text x={xR(0) + 14} y={yAuc(dponAuc[0]) + 30} fontFamily={fonts.mono} fontSize={24} fill={C.blue60} opacity={ramp(frame, 20, 35)}>
        {fmt3(dponAuc[0])}
      </text>
      <text x={xR(9) + 14} y={yAuc(dponAuc[9]) + 26} fontFamily={fonts.mono} fontSize={24} fontWeight={600} fill={C.blue60} opacity={endOn}>
        {fmt3(dponAuc[9])}
      </text>
      <text x={xR(9) + 14} y={yAuc(dponAuc[9]) + 50} fontFamily={fonts.sans} fontSize={18} fill={C.blue60} opacity={endOn}>
        with noise
      </text>
      <text x={xR(9) + 14} y={yAuc(dpoffAuc[9]) - 12} fontFamily={fonts.mono} fontSize={24} fill={C.purple70} opacity={endOff}>
        {fmt3(dpoffAuc[9])}
      </text>
      <text x={xR(9) + 14} y={yAuc(dpoffAuc[9]) - 40} fontFamily={fonts.sans} fontSize={18} fill={C.purple70} opacity={endOff}>
        no noise
      </text>
    </svg>
  );
};

const Bar: React.FC<{ v: number; max: number; w: number; color: string; p: number }> = ({ v, max, w, color, p }) => (
  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
    <div style={{ width: w, height: 34, background: C.gray10, position: "relative" }}>
      <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: (v / max) * w * p, background: color }} />
    </div>
    <div style={{ fontFamily: fonts.mono, fontSize: 24, width: 74, opacity: p }}>{fmt3(v)}</div>
  </div>
);

export const Results: React.FC<{ narration: string }> = ({ narration }) => {
  const frame = useCurrentFrame();
  const left = useFadeUp(6);
  const right = useFadeUp(200);
  const ours = baselineBars[2];
  const pooled = baselineBars[1];
  const noisy = baselineBars[3];
  const ratio = ours.ap / pooled.ap;
  const note = useFadeUp(400);
  return (
    <SceneShell tone="light" index={6} kicker="Results · pooled test set" title="The shared model, and what privacy noise costs" narration={narration}>
      <div style={{ position: "absolute", left: 80, top: 190, width: 830, height: 680, background: C.white, padding: "22px 14px 0 14px", boxSizing: "border-box", ...left }}>
        <div style={{ fontFamily: fonts.condensed, fontWeight: 600, fontSize: 32, paddingLeft: 16 }}>Pooled AUC per training round</div>
        <div style={{ display: "flex", gap: 24, paddingLeft: 16, marginTop: 6, fontFamily: fonts.mono, fontSize: 19, color: C.gray70 }}>
          <span><span style={{ color: C.blue60 }}>━━</span> ours, with privacy noise (σ 0.5)</span>
          <span><span style={{ color: C.purple70 }}>╍╍</span> ours, no noise</span>
        </div>
        <AucChart />
      </div>
      <div style={{ position: "absolute", left: 950, top: 190, width: 890, height: 680, background: C.white, padding: "22px 30px", boxSizing: "border-box", ...right }}>
        <div style={{ fontFamily: fonts.condensed, fontWeight: 600, fontSize: 32 }}>Against the baselines</div>
        <div style={{ display: "flex", marginTop: 16, fontFamily: fonts.mono, fontSize: 19, color: C.gray70 }}>
          <div style={{ width: 250 }} />
          <div style={{ width: 300, whiteSpace: "nowrap" }}>AUC (scale 0 – 1)</div>
          <div style={{ width: 300, whiteSpace: "nowrap" }}>avg. precision (0 – 0.5)</div>
        </div>
        {baselineBars.map((b, i) => {
          const p = ramp(frame, 220 + i * 35, 280 + i * 35);
          const hl = i === 2;
          return (
            <div
              key={b.label}
              style={{
                display: "flex",
                alignItems: "center",
                marginTop: 14,
                padding: "14px 0",
                background: hl ? C.blue20 : "transparent",
                borderLeft: hl ? `6px solid ${C.blue60}` : "6px solid transparent",
              }}
            >
              <div style={{ width: 244, paddingLeft: 10, fontFamily: fonts.condensed, fontWeight: hl ? 700 : 500, fontSize: 26 }}>{b.label}</div>
              <div style={{ width: 300 }}>
                <Bar v={b.auc} max={1} w={200} color={C.blue60} p={p} />
              </div>
              <div style={{ width: 300 }}>
                <Bar v={b.ap} max={0.5} w={200} color={C.purple70} p={p} />
              </div>
            </div>
          );
        })}
        <div style={{ marginTop: 26, fontFamily: fonts.sans, fontSize: 24, lineHeight: 1.5, ...note }}>
          <div>
            Avg. precision, no noise vs pooling raw data:{" "}
            <b style={{ fontFamily: fonts.mono, color: C.blue60 }}>
              {fmt3(ours.ap)} vs {fmt3(pooled.ap)} ({ratio.toFixed(1)}×)
            </b>
          </div>
          <div>
            Price of privacy noise:{" "}
            <b style={{ fontFamily: fonts.mono, color: C.gray100 }}>
              AUC {fmt3(ours.auc)} → {fmt3(noisy.auc)}
            </b>
          </div>
        </div>
      </div>
    </SceneShell>
  );
};
