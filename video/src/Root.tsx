// Entry point: registerRoot + the single "Dataholics" composition (1920x1080, 30 fps, 5280 frames).
import React from "react";
import { CalculateMetadataFunction, Composition, registerRoot, staticFile } from "remotion";
import { Video, VideoProps } from "./Video";
import { TOTAL_FRAMES } from "./script";
import { FPS, HEIGHT, WIDTH } from "./theme";

/**
 * Optional media in public/ (gitignored): live-demo.mp4 and voiceover.mp3.
 * We probe them with a HEAD request against Remotion's static server before rendering, so a missing
 * file never crashes the render. Override with --props='{"hasLiveDemo":false,"hasVoiceover":false}'.
 */
const exists = async (name: string): Promise<boolean> => {
  try {
    const res = await fetch(staticFile(name), { method: "HEAD" });
    const type = res.headers.get("content-type") ?? "";
    return res.ok && !type.includes("text/html");
  } catch {
    return false;
  }
};

const calculateMetadata: CalculateMetadataFunction<VideoProps> = async ({ props }) => ({
  props: {
    hasLiveDemo: props.hasLiveDemo ?? (await exists("live-demo.mp4")),
    hasVoiceover: props.hasVoiceover ?? (await exists("voiceover.mp3")),
  },
});

const RemotionRoot: React.FC = () => (
  <Composition
    id="Dataholics"
    component={Video}
    durationInFrames={TOTAL_FRAMES}
    fps={FPS}
    width={WIDTH}
    height={HEIGHT}
    defaultProps={{ hasLiveDemo: null, hasVoiceover: null } as VideoProps}
    calculateMetadata={calculateMetadata}
  />
);

registerRoot(RemotionRoot);
