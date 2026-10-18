import React from "react";
import { C, fonts } from "../theme";

/** Linear scale from a data domain to a pixel range. */
export const scale = (d0: number, d1: number, r0: number, r1: number) => (v: number) =>
  r0 + ((v - d0) / (d1 - d0)) * (r1 - r0);

/**
 * Polyline that draws itself: `progress` runs 0 → (n-1) in "points revealed", fractional values
 * interpolate the last segment, so the line is exact to the data at every frame.
 */
export const DrawnLine: React.FC<{
  pts: [number, number][];
  progress: number;
  color: string;
  width?: number;
  dash?: string;
  dots?: boolean;
}> = ({ pts, progress, color, width = 5, dash, dots = true }) => {
  const p = Math.max(0, Math.min(pts.length - 1, progress));
  const k = Math.floor(p);
  const shown = pts.slice(0, k + 1);
  if (k < pts.length - 1) {
    const t = p - k;
    const [x0, y0] = pts[k];
    const [x1, y1] = pts[k + 1];
    shown.push([x0 + (x1 - x0) * t, y0 + (y1 - y0) * t]);
  }
  return (
    <g>
      <polyline
        points={shown.map(([x, y]) => `${x},${y}`).join(" ")}
        fill="none"
        stroke={color}
        strokeWidth={width}
        strokeLinejoin="round"
        strokeLinecap="round"
        strokeDasharray={dash}
      />
      {dots
        ? pts.slice(0, k + 1).map(([x, y], i) => <circle key={i} cx={x} cy={y} r={width + 2} fill={color} />)
        : null}
    </g>
  );
};

/** Horizontal grid lines with tick labels on the left. */
export const YGrid: React.FC<{
  ticks: number[];
  y: (v: number) => number;
  x0: number;
  x1: number;
  label?: (v: number) => string;
  color?: string;
  textColor?: string;
}> = ({ ticks, y, x0, x1, label = (v) => v.toFixed(2), color = C.gray20, textColor = C.gray70 }) => (
  <g>
    {ticks.map((t) => (
      <g key={t}>
        <line x1={x0} x2={x1} y1={y(t)} y2={y(t)} stroke={color} strokeWidth={2} />
        <text
          x={x0 - 14}
          y={y(t) + 8}
          textAnchor="end"
          fontFamily={fonts.mono}
          fontSize={22}
          fill={textColor}
        >
          {label(t)}
        </text>
      </g>
    ))}
  </g>
);

/** Round labels 1..n along the x axis. */
export const XRounds: React.FC<{ n: number; x: (i: number) => number; y: number; color?: string }> = ({
  n,
  x,
  y,
  color = C.gray70,
}) => (
  <g>
    {Array.from({ length: n }, (_, i) => (
      <text key={i} x={x(i)} y={y} textAnchor="middle" fontFamily={fonts.mono} fontSize={22} fill={color}>
        {i + 1}
      </text>
    ))}
  </g>
);
