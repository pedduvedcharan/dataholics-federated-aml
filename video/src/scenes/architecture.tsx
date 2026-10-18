// Scene 4 (0:40–1:06): the architecture builds left to right, with live egress counters.
import React from "react";
import { interpolate, useCurrentFrame } from "remotion";
import { C, fonts } from "../theme";
import { SceneShell } from "../components/SceneShell";
import { DrawnLine } from "../components/charts";
import { ramp, useEnter, useFadeUp } from "../components/anim";
import { Pill } from "../components/Pill";
import { data, fmtInt, laundryOneIn } from "../data";

// layout (content area is 1920 x 890)
const BANK_X = 110;
const BANK_W = 530;
const BANK_H = 92;
const BANK_Y0 = 318;
const BANK_GAP = 14;
const DOOR = { x: 720, y: 420, w: 260, h: 300 };
const COORD = { x: 1130, y: 360, w: 330, h: 420 };
const OUT_X = 1540;
const OUT_W = 290;
const OUTS = [
  { name: "Regulator dashboard", sub: "live egress audit", y: 360 },
  { name: "Red team", sub: "membership inference", y: 510 },
  { name: "AI report writer", sub: "small CPU LLM drafts SARs", y: 660 },
];

const bankY = (i: number) => BANK_Y0 + i * (BANK_H + BANK_GAP);
const bankMid = (i: number) => bankY(i) + BANK_H / 2;
const doorMid = DOOR.y + DOOR.h / 2;

const Box: React.FC<{
  x: number;
  y: number;
  w: number;
  h: number;
  p: number;
  border?: string;
  bg?: string;
  children: React.ReactNode;
}> = ({ x, y, w, h, p, border = C.gray30, bg = C.white, children }) => (
  <div
    style={{
      position: "absolute",
      left: x,
      top: y,
      width: w,
      height: h,
      background: bg,
      border: `2px solid ${border}`,
      opacity: p,
      transform: `translateX(${(1 - p) * -30}px)`,
      boxSizing: "border-box",
    }}
  >
    {children}
  </div>
);

const STEPS = ["data", "train", "clip + noise"];

const Bank: React.FC<{ i: number; delay: number }> = ({ i, delay }) => {
  const frame = useCurrentFrame();
  const p = useEnter(delay);
  const b = data.partition.banks[String(i + 1)];
  return (
    <Box x={BANK_X} y={bankY(i)} w={BANK_W} h={BANK_H} p={p} border={C.blue20} bg={C.blue10}>
      <div style={{ display: "flex", alignItems: "center", height: "100%", padding: "0 18px", gap: 14 }}>
        <div style={{ width: 150, whiteSpace: "nowrap" }}>
          <div style={{ fontFamily: fonts.condensed, fontWeight: 600, fontSize: 32 }}>Bank {i + 1}</div>
          <div style={{ fontFamily: fonts.mono, fontSize: 17, color: C.gray70 }}>{fmtInt(b.rows_raw)} rows</div>
        </div>
        {STEPS.map((s, k) => {
          const on = ramp(frame, delay + 90 + k * 25, delay + 100 + k * 25);
          return (
            <div
              key={s}
              style={{
                fontFamily: fonts.mono,
                fontSize: 19,
                padding: "6px 10px",
                background: on > 0.5 ? C.blue60 : C.white,
                color: on > 0.5 ? C.white : C.gray70,
                border: `1px solid ${C.blue20}`,
                whiteSpace: "nowrap",
              }}
            >
              {s}
            </div>
          );
        })}
      </div>
    </Box>
  );
};

const Counter: React.FC<{ label: string; value: string; color: string; p: number }> = ({ label, value, color, p }) => (
  <div style={{ opacity: p, padding: "0 22px", borderLeft: `2px solid ${C.gray20}` }}>
    <div style={{ fontFamily: fonts.mono, fontSize: 18, color: C.gray70, textTransform: "uppercase" }}>{label}</div>
    <div style={{ fontFamily: fonts.mono, fontWeight: 600, fontSize: 46, color, lineHeight: 1.1 }}>{value}</div>
  </div>
);

export const Architecture: React.FC<{ narration: string }> = ({ narration }) => {
  const frame = useCurrentFrame();
  const eg = data.egress_one_run;
  const strip = useFadeUp(10);
  const vm = useEnter(30);
  const door = useEnter(200);
  const coord = useEnter(300);
  const counters = useEnter(330);

  // counters tick through one run's egress log: messages and parameters grow, rows stay 0
  const tick = interpolate(frame, [340, 740], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const msgs = Math.round(tick * eg.messages);
  const params = msgs * eg.params_per_update;

  // arrows
  const inArrows = [0, 1, 2, 3, 4].map((i) => ramp(frame, 230 + i * 8, 280 + i * 8));
  const mainArrow = ramp(frame, 330, 370);
  const outArrows = OUTS.map((_, k) => ramp(frame, 440 + k * 30, 480 + k * 30));
  const back = ramp(frame, 600, 660);

  // raw-row packet bounces off the door (sentence 2: "a single audited door that refuses raw data")
  const blockT = interpolate(frame, [470, 520, 545, 575], [0, 1, 1, 0.6], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const blockedVisible = frame >= 470 && frame < 640;
  const blockedLabel = ramp(frame, 518, 530) * (1 - ramp(frame, 620, 640));

  // update particles: bank → door → coordinator, looping once the pipe is open
  const particles = frame > 360
    ? [0, 1, 2, 3, 4].map((i) => {
        const cycle = 60;
        const t = (((frame - 360 + i * 12) % cycle) + cycle) % cycle / cycle;
        const sx = BANK_X + BANK_W;
        const sy = bankMid(i);
        const [x, y] =
          t < 0.6
            ? [sx + (DOOR.x - sx) * (t / 0.6), sy + (doorMid - sy) * (t / 0.6)]
            : [DOOR.x + DOOR.w + (COORD.x - DOOR.x - DOOR.w) * ((t - 0.6) / 0.4), doorMid];
        return { x, y, show: t < 0.6 || (t >= 0.6 && true) };
      })
    : [];

  const arrow = (x0: number, y0: number, x1: number, y1: number): [number, number][] => [
    [x0, y0],
    [x1, y1],
  ];

  return (
    <SceneShell tone="light" index={4} kicker="Architecture" title="One shared model. No shared data." narration={narration}>
      {/* counters, top right */}
      <div style={{ position: "absolute", right: 80, top: 92, display: "flex", background: C.white, padding: "10px 0", border: `2px solid ${C.gray20}`, opacity: counters }}>
        <Counter label="rows shared" value={fmtInt(eg.rows_shared)} color={C.green50} p={1} />
        <Counter label="numbers / update" value={String(eg.params_per_update)} color={C.blue60} p={1} />
        <Counter label="messages" value={String(msgs)} color={C.gray100} p={1} />
        <Counter label="parameters shared" value={fmtInt(params)} color={C.gray100} p={1} />
      </div>

      {/* dataset strip */}
      <div
        style={{
          position: "absolute",
          left: 80,
          right: 80,
          top: 196,
          height: 54,
          background: C.gray90,
          color: C.white,
          display: "flex",
          alignItems: "center",
          gap: 34,
          padding: "0 26px",
          fontFamily: fonts.mono,
          fontSize: 24,
          ...strip,
        }}
      >
        <span style={{ color: C.blue20 }}>DATA</span>
        <span>IBM AML HI-Small</span>
        <span>{fmtInt(data.partition.n_rows_total)} synthetic transactions</span>
        <span>1 in {laundryOneIn} laundering</span>
        <span>split by sending bank</span>
      </div>

      {/* the VM boundary */}
      <div
        style={{
          position: "absolute",
          left: 80,
          right: 80,
          top: 270,
          bottom: 14,
          border: `2px dashed ${C.gray30}`,
          opacity: vm,
        }}
      >
        <div style={{ position: "absolute", top: -2, right: 0, transform: "translateY(-100%)" }} />
        <div style={{ position: "absolute", left: 20, top: 10, fontFamily: fonts.mono, fontSize: 19, color: C.gray70 }}>
          IBM LinuxONE · s390x · docker compose · sandboxed containers
        </div>
      </div>

      {[0, 1, 2, 3, 4].map((i) => (
        <Bank key={i} i={i} delay={60 + i * 18} />
      ))}

      <svg width={1920} height={890} style={{ position: "absolute", left: 0, top: 0 }}>
        <defs>
          <marker id="ah" markerUnits="userSpaceOnUse" markerWidth="26" markerHeight="26" refX="22" refY="13" orient="auto">
            <path d="M0,0 L26,13 L0,26 z" fill={C.blue60} />
          </marker>
          <marker id="ahg" markerUnits="userSpaceOnUse" markerWidth="22" markerHeight="22" refX="18" refY="11" orient="auto">
            <path d="M0,0 L22,11 L0,22 z" fill={C.gray60} />
          </marker>
        </defs>
        {inArrows.map((p, i) =>
          p > 0 ? (
            <DrawnLine key={i} pts={arrow(BANK_X + BANK_W, bankMid(i), DOOR.x - 6, doorMid - 60 + i * 30)} progress={p} color={C.blue60} width={3} dots={false} />
          ) : null,
        )}
        {mainArrow > 0 ? (
          <line
            x1={DOOR.x + DOOR.w}
            y1={doorMid}
            x2={DOOR.x + DOOR.w + (COORD.x - DOOR.x - DOOR.w - 8) * mainArrow}
            y2={doorMid}
            stroke={C.blue60}
            strokeWidth={8}
            markerEnd="url(#ah)"
          />
        ) : null}
        {outArrows.map((p, k) =>
          p > 0 ? (
            <line
              key={k}
              x1={COORD.x + COORD.w}
              y1={OUTS[k].y + 55}
              x2={COORD.x + COORD.w + (OUT_X - COORD.x - COORD.w - 8) * p}
              y2={OUTS[k].y + 55}
              stroke={C.gray60}
              strokeWidth={3}
              markerEnd="url(#ahg)"
            />
          ) : null,
        )}
        {back > 0 ? (
          <path
            d={`M ${COORD.x + 60} ${COORD.y + COORD.h} Q 900 880 ${BANK_X + BANK_W + 8} ${bankMid(4) + 10}`}
            fill="none"
            stroke={C.blue60}
            strokeWidth={4}
            strokeDasharray="12 10"
            opacity={back}
            markerEnd="url(#ah)"
          />
        ) : null}
        {particles.map((pt, i) => (
          <rect key={i} x={pt.x - 9} y={pt.y - 9} width={18} height={18} fill={C.blue60} stroke={C.white} strokeWidth={2} />
        ))}
        {blockedVisible ? (
          <g transform={`translate(${BANK_X + BANK_W + (DOOR.x - BANK_X - BANK_W - 40) * blockT}, ${bankMid(1) + (doorMid - 120 - bankMid(1)) * blockT})`}>
            <rect x={-30} y={-22} width={60} height={44} fill={C.red60} />
            <text x={0} y={7} textAnchor="middle" fontFamily={fonts.mono} fontSize={16} fill={C.white}>
              rows
            </text>
          </g>
        ) : null}
      </svg>

      {/* egress door */}
      <Box x={DOOR.x} y={DOOR.y} w={DOOR.w} h={DOOR.h} p={door} border={C.gray100} bg={C.white}>
        <div style={{ padding: 22 }}>
          <div style={{ fontFamily: fonts.mono, fontSize: 26, fontWeight: 600, color: C.blue60 }}>egress.send()</div>
          <div style={{ fontFamily: fonts.condensed, fontWeight: 600, fontSize: 30, marginTop: 8, whiteSpace: "nowrap" }}>the only door out</div>
          <div style={{ fontFamily: fonts.sans, fontSize: 22, color: C.gray70, marginTop: 10, lineHeight: 1.35 }}>
            refuses raw rows
            <br />
            logs every message
            <br />
            clipped + noised updates only
          </div>
        </div>
      </Box>
      <div style={{ position: "absolute", left: DOOR.x - 10, top: DOOR.y - 56, opacity: blockedLabel }}>
        <Pill bg={C.red60}>BLOCKED · raw rows</Pill>
      </div>
      <div
        style={{
          position: "absolute",
          left: DOOR.x + DOOR.w + 6,
          width: COORD.x - DOOR.x - DOOR.w - 12,
          top: doorMid - 72,
          textAlign: "center",
          whiteSpace: "nowrap",
          fontFamily: fonts.mono,
          fontSize: 19,
          color: C.blue60,
          opacity: mainArrow,
        }}
      >
        {data.egress_one_run.params_per_update} numbers
        <br />
        per round
      </div>

      {/* coordinator */}
      <Box x={COORD.x} y={COORD.y} w={COORD.w} h={COORD.h} p={coord} border={C.blue60} bg={C.white}>
        <div style={{ padding: 24 }}>
          <div style={{ fontFamily: fonts.condensed, fontWeight: 600, fontSize: 40 }}>Coordinator</div>
          <div style={{ fontFamily: fonts.mono, fontSize: 18, color: C.gray70, whiteSpace: "nowrap" }}>FedAvg · diff. privacy</div>
          {[
            ["screen", "norm + direction checks drop cheaters"],
            ["average", "weighted by bank size"],
            ["send back", "the improved model"],
          ].map(([h, s], k) => {
            const p = ramp(frame, 360 + k * 50, 380 + k * 50);
            return (
              <div key={h} style={{ marginTop: 14, opacity: 0.25 + 0.75 * p, display: "flex", gap: 14, alignItems: "flex-start" }}>
                <div style={{ fontFamily: fonts.mono, fontSize: 22, color: C.white, background: C.blue60, width: 34, height: 34, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                  {k + 1}
                </div>
                <div>
                  <div style={{ fontFamily: fonts.condensed, fontWeight: 600, fontSize: 30 }}>{h}</div>
                  <div style={{ fontFamily: fonts.sans, fontSize: 20, color: C.gray70 }}>{s}</div>
                </div>
              </div>
            );
          })}
        </div>
      </Box>

      {OUTS.map((o, k) => (
        <Box key={o.name} x={OUT_X} y={o.y} w={OUT_W} h={116} p={outArrows[k]} border={C.gray30}>
          <div style={{ padding: "16px 20px" }}>
            <div style={{ fontFamily: fonts.condensed, fontWeight: 600, fontSize: 28, whiteSpace: "nowrap" }}>{o.name}</div>
            <div style={{ fontFamily: fonts.sans, fontSize: 20, color: k === 2 ? C.purple60 : C.gray70 }}>{o.sub}</div>
          </div>
        </Box>
      ))}
      <div
        style={{
          position: "absolute",
          left: 700,
          top: 770,
          fontFamily: fonts.mono,
          fontSize: 19,
          color: C.blue60,
          opacity: back,
        }}
      >
        global model back to every bank
      </div>
    </SceneShell>
  );
};
