// Scene 10 (2:48–2:56): measured footprint numbers, stack line, repo, pitch line.
import React from "react";
import { C, fonts } from "../theme";
import { SceneShell } from "../components/SceneShell";
import { useEnter, useFadeUp } from "../components/anim";
import { data, fmtInt } from "../data";

const STACK = "scikit-learn · Flask · IBM ART · llama.cpp · Qwen2.5 · Docker · IBM LinuxONE";
const REPO = "github.com/pedduvedcharan/dataholics-federated-aml";

const Num: React.FC<{ n: string; unit: string; label: string; delay: number }> = ({ n, unit, label, delay }) => {
  const p = useEnter(delay, 14);
  return (
    <div style={{ width: 400, opacity: p, transform: `translateY(${(1 - p) * 30}px)`, borderTop: `4px solid ${C.blue60}`, paddingTop: 16 }}>
      <div style={{ fontFamily: fonts.mono, fontWeight: 600, fontSize: 88, color: C.white, lineHeight: 1 }}>
        {n}
        <span style={{ fontSize: 40, color: C.blue20, marginLeft: 10 }}>{unit}</span>
      </div>
      <div style={{ fontFamily: fonts.sans, fontSize: 28, color: C.gray30, marginTop: 10 }}>{label}</div>
    </div>
  );
};

export const Close: React.FC<{ narration: string }> = ({ narration }) => {
  const f = data.footprint;
  const stack = useFadeUp(70);
  const line = useFadeUp(100);
  return (
    <SceneShell tone="dark" index={10} kicker="Measured on IBM LinuxONE, not estimated" narration={narration}>
      <div style={{ position: "absolute", left: 120, top: 150, display: "flex", gap: 30 }}>
        <Num n={fmtInt(data.egress_one_run.rows_shared)} unit="rows" label="customer rows shared" delay={4} />
        <Num n={fmtInt(f.total_peak_rss_mb_sum)} unit="MB" label="all containers, peak RAM" delay={16} />
        <Num n={f.seconds_per_round.toFixed(1)} unit="s" label="per federated round" delay={28} />
        <Num n={String(f.total_runtime_s)} unit="s" label="end to end" delay={40} />
      </div>
      <div style={{ position: "absolute", left: 120, top: 440, fontFamily: fonts.mono, fontSize: 28, color: C.gray30, ...stack }}>
        {STACK} · {f.arch} · {f.cpu_count} cores
      </div>
      <div style={{ position: "absolute", left: 120, top: 500, fontFamily: fonts.mono, fontSize: 28, color: C.blue20, ...stack }}>{REPO}</div>
      <div style={{ position: "absolute", left: 120, right: 120, top: 600, fontFamily: fonts.condensed, fontWeight: 600, fontSize: 64, color: C.white, lineHeight: 1.1, ...line }}>
        What the Dutch banks had to shut down, built so it would have been legal.
      </div>
    </SceneShell>
  );
};
