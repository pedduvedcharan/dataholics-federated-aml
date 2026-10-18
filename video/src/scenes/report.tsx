// Scene 9 (2:34–2:48): alert queue, A06 highlighted, its report; the LLM paragraph types out in purple.
import React from "react";
import { useCurrentFrame } from "remotion";
import { C, fonts } from "../theme";
import { SceneShell } from "../components/SceneShell";
import { ramp, useEnter, useFadeUp } from "../components/anim";
import { Pill, Stamp } from "../components/Pill";
import { data } from "../data";

const ROWS = data.alerts.top.slice(0, 10);
const DEMO = data.alerts.meta.demo_alert_id;

export const Report: React.FC<{ narration: string }> = ({ narration }) => {
  const frame = useCurrentFrame();
  const queue = useFadeUp(4);
  const sel = ramp(frame, 40, 55);
  const card = useFadeUp(60);
  const para = data.sar_A06_llm_paragraph;
  const typed = Math.floor(ramp(frame, 110, 320) * para.length);
  const stamp = useEnter(330, 12);
  const demo = data.alerts.top.find((a) => a.alert_id === DEMO)!;
  const cursorOn = typed < para.length && Math.floor(frame / 8) % 2 === 0;
  const closing = useFadeUp(360);

  return (
    <SceneShell tone="light" index={9} kicker="AI report writer" title="Code writes the facts. The LLM drafts the prose." narration={narration}>
      {/* alert queue */}
      <div style={{ position: "absolute", left: 80, top: 190, width: 640, height: 680, background: C.white, ...queue }}>
        <div style={{ padding: "20px 24px 10px" }}>
          <div style={{ fontFamily: fonts.condensed, fontWeight: 600, fontSize: 32 }}>Alert queue</div>
          <div style={{ fontFamily: fonts.mono, fontSize: 18, color: C.gray70 }}>ranked for analyst review · not a verdict</div>
        </div>
        <div style={{ display: "flex", background: C.gray100, color: C.white, fontFamily: fonts.mono, fontSize: 19, padding: "8px 24px" }}>
          <span style={{ width: 90 }}>rank</span>
          <span style={{ width: 130 }}>alert</span>
          <span style={{ width: 200 }}>score</span>
          <span>banks in chain</span>
        </div>
        {ROWS.map((a) => {
          const hl = a.alert_id === DEMO;
          return (
            <div
              key={a.alert_id}
              style={{
                display: "flex",
                fontFamily: fonts.mono,
                fontSize: 24,
                padding: "10px 24px",
                borderBottom: `1px solid ${C.gray20}`,
                background: hl ? `rgba(208,226,255,${sel})` : "transparent",
                borderLeft: `6px solid ${hl ? `rgba(15,98,254,${sel})` : "transparent"}`,
                fontWeight: hl && sel > 0.5 ? 600 : 400,
              }}
            >
              <span style={{ width: 90 }}>{a.rank}</span>
              <span style={{ width: 130, color: C.blue60 }}>{a.alert_id}</span>
              <span style={{ width: 200 }}>{a.score.toFixed(6)}</span>
              <span>{a.banks}</span>
            </div>
          );
        })}
      </div>

      {/* report card */}
      <div style={{ position: "absolute", left: 770, top: 190, width: 1070, height: 680, background: C.white, borderTop: `6px solid ${C.blue60}`, padding: "22px 36px", boxSizing: "border-box", ...card }}>
        <div style={{ fontFamily: fonts.mono, fontSize: 19, color: C.gray70 }}>SUSPICIOUS ACTIVITY REPORT · DRAFT FOR ANALYST</div>
        <div style={{ fontFamily: fonts.condensed, fontWeight: 600, fontSize: 40, marginTop: 4 }}>Alert {DEMO}</div>
        <div style={{ marginTop: 14, fontFamily: fonts.mono, fontSize: 18, color: C.gray70 }}>FACTS · written by code</div>
        <div style={{ display: "flex", gap: 40, marginTop: 6, fontFamily: fonts.mono, fontSize: 26 }}>
          <span>rank <b>{demo.rank}</b></span>
          <span>score <b>{demo.score}</b></span>
          <span>banks in chain <b>{demo.banks}</b></span>
        </div>
        <div style={{ marginTop: 22, display: "flex", alignItems: "center", gap: 14 }}>
          <Pill bg={C.purple60}>written by the LLM</Pill>
          <span style={{ fontFamily: fonts.mono, fontSize: 18, color: C.gray70 }}>small CPU model, same machine</span>
        </div>
        <div
          style={{
            marginTop: 12,
            background: C.purple10,
            borderLeft: `6px solid ${C.purple60}`,
            padding: "18px 24px",
            color: C.purple60,
            fontFamily: fonts.sans,
            fontSize: 28,
            lineHeight: 1.42,
            minHeight: 250,
          }}
        >
          {para.slice(0, typed)}
          <span style={{ opacity: cursorOn ? 1 : 0 }}>▍</span>
        </div>
        <div style={{ marginTop: 18, fontFamily: fonts.condensed, fontWeight: 600, fontSize: 32, color: C.gray100, ...closing }}>
          The model ranks; a person decides.
        </div>
        <div style={{ position: "absolute", right: 30, bottom: 30 }}>
          {frame >= 330 ? (
            <Stamp p={stamp} color={C.red60} size={34} rotate={-6}>
              claim check rejected
              <br />
              {data.guardrail.llm_drafts_rejected} of {data.guardrail.recorded_reports} LLM drafts
            </Stamp>
          ) : null}
        </div>
      </div>
    </SceneShell>
  );
};
