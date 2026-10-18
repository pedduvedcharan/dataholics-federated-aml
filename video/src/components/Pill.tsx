import React from "react";
import { C, fonts } from "../theme";

/** Status chip: color always carries a text label (palette rule). */
export const Pill: React.FC<{
  bg: string;
  fg?: string;
  children: React.ReactNode;
  size?: number;
  style?: React.CSSProperties;
}> = ({ bg, fg = C.white, children, size = 22, style }) => (
  <span
    style={{
      display: "inline-block",
      background: bg,
      color: fg,
      fontFamily: fonts.mono,
      fontWeight: 600,
      fontSize: size,
      letterSpacing: 0.5,
      padding: `${size * 0.25}px ${size * 0.6}px`,
      whiteSpace: "nowrap",
      ...style,
    }}
  >
    {children}
  </span>
);

/** Rotated rubber stamp that slams in. `p` is 0 → 1 (spring). */
export const Stamp: React.FC<{ p: number; color: string; children: React.ReactNode; rotate?: number; size?: number }> = ({
  p,
  color,
  children,
  rotate = -8,
  size = 44,
}) => (
  <div
    style={{
      display: "inline-block",
      border: `6px solid ${color}`,
      color,
      fontFamily: fonts.condensed,
      fontWeight: 700,
      fontSize: size,
      textTransform: "uppercase",
      letterSpacing: 2,
      padding: "10px 28px",
      transform: `rotate(${rotate}deg) scale(${2.2 - 1.2 * p})`,
      opacity: Math.min(1, p * 1.6),
      whiteSpace: "nowrap",
      lineHeight: 1.15,
      textAlign: "center",
    }}
  >
    {children}
  </div>
);
