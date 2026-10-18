import { interpolate, spring, useCurrentFrame, useVideoConfig, Easing } from "remotion";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

/** 0 → 1 linear ramp between frames a and b (clamped), eased in-out. */
export const ramp = (frame: number, a: number, b: number) =>
  interpolate(frame, [a, b], [0, 1], { ...clamp, easing: Easing.inOut(Easing.cubic) });

/** A damped spring that starts at `delay` frames. */
export const useEnter = (delay = 0, damping = 200) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return spring({ frame: frame - delay, fps, config: { damping } });
};

/** Style for an element that fades and rises in at `delay`. */
export const useFadeUp = (delay = 0, dist = 24) => {
  const p = useEnter(delay);
  return { opacity: p, transform: `translateY(${(1 - p) * dist}px)` };
};

export const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
