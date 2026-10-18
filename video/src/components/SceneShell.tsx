import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { C, CAPTION_H, fonts } from "../theme";
import { Caption } from "./Caption";
import { useFadeUp } from "./anim";

export type Tone = "light" | "dark" | "blue";

const BG: Record<Tone, string> = { light: C.gray10, dark: C.gray100, blue: C.blue80 };
export const ink = (tone: Tone) => (tone === "light" ? C.gray100 : C.white);
export const subInk = (tone: Tone) => (tone === "light" ? C.gray70 : C.gray30);

/** Common frame for every scene: background, kicker + title, content area, caption, scene fades. */
export const SceneShell: React.FC<{
  tone: Tone;
  index: number;
  kicker: string;
  title?: string;
  narration: string;
  children: React.ReactNode;
}> = ({ tone, index, kicker, title, narration, children }) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const fade = interpolate(frame, [0, 8, durationInFrames - 8, durationInFrames], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const titleStyle = useFadeUp(4);
  return (
    <AbsoluteFill style={{ background: BG[tone], fontFamily: fonts.sans, color: ink(tone) }}>
      <AbsoluteFill style={{ opacity: fade }}>
        {/* header */}
        <div
          style={{
            position: "absolute",
            top: 44,
            left: 80,
            right: 80,
            display: "flex",
            justifyContent: "space-between",
            alignItems: "baseline",
            fontFamily: fonts.mono,
            fontSize: 22,
            letterSpacing: 1,
            color: subInk(tone),
            textTransform: "uppercase",
          }}
        >
          <span>
            <span style={{ color: tone === "light" ? C.blue60 : C.blue20 }}>{String(index).padStart(2, "0")}</span>
            {"  /  "}
            {kicker}
          </span>
          <span>Dataholics · IBM Z Datathon 2026</span>
        </div>
        {title ? (
          <div
            style={{
              position: "absolute",
              top: 92,
              left: 80,
              right: 80,
              fontFamily: fonts.condensed,
              fontWeight: 600,
              fontSize: 58,
              lineHeight: 1.1,
              ...titleStyle,
            }}
          >
            {title}
          </div>
        ) : null}
        <div style={{ position: "absolute", left: 0, right: 0, top: 0, bottom: CAPTION_H }}>{children}</div>
      </AbsoluteFill>
      <Caption text={narration} />
    </AbsoluteFill>
  );
};
