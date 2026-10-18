import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { C, CAPTION_H, fonts } from "../theme";

/** Split narration into caption chunks of whole sentences/clauses, at most ~20 words each. */
const chunk = (text: string, maxWords = 18): string[] => {
  const sentences = text.match(/[^.!?]+[.!?]+|[^.!?]+$/g) ?? [text];
  const out: string[] = [];
  let cur = "";
  for (const raw of sentences) {
    const sent = raw.trim();
    const n = (cur + " " + sent).trim().split(/\s+/).length;
    if (cur && n > maxWords) {
      out.push(cur);
      cur = sent;
    } else {
      cur = (cur + " " + sent).trim();
    }
  }
  if (cur) out.push(cur);
  // long single sentences: split at a comma near the middle
  return out.flatMap((c) => {
    const words = c.split(/\s+/);
    if (words.length <= maxWords + 6) return [c];
    const mid = c.indexOf(", ", Math.floor(c.length / 2) - 30);
    return mid > 0 ? [c.slice(0, mid + 1), c.slice(mid + 2)] : [c];
  });
};

/** Lower-third caption: the scene's narration, timed in proportion to word count. */
export const Caption: React.FC<{ text: string; dark?: boolean }> = ({ text }) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const parts = chunk(text);
  const words = parts.map((p) => p.split(/\s+/).length);
  const total = words.reduce((a, b) => a + b, 0);
  const lead = 6;
  const usable = durationInFrames - lead - 10;
  let acc = lead;
  const spans = parts.map((p, i) => {
    const len = (words[i] / total) * usable;
    const span = { p, start: acc, end: acc + len };
    acc += len;
    return span;
  });
  const current = spans.find((s) => frame >= s.start && frame < s.end) ?? spans[spans.length - 1];
  const fadeIn = interpolate(frame, [current.start, current.start + 6], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const sceneFade = interpolate(frame, [0, lead], [0, 1], { extrapolateRight: "clamp" });

  return (
    <AbsoluteFill style={{ justifyContent: "flex-end", alignItems: "center", pointerEvents: "none" }}>
      <div
        style={{
          height: CAPTION_H,
          width: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          opacity: sceneFade,
        }}
      >
        <div
          style={{
            maxWidth: 1580,
            background: "rgba(38,38,38,0.94)",
            borderLeft: `6px solid ${C.blue60}`,
            padding: "18px 34px",
            color: C.white,
            fontFamily: fonts.sans,
            fontSize: 36,
            lineHeight: 1.32,
            fontWeight: 400,
            opacity: fadeIn,
            textAlign: "left",
          }}
        >
          {current.p}
        </div>
      </div>
    </AbsoluteFill>
  );
};
