// Remotion CLI config. Entry point is src/Root.tsx (registerRoot + Composition).
import { Config } from "@remotion/cli/config";

Config.setEntryPoint("./src/Root.tsx");
Config.setVideoImageFormat("jpeg");
Config.setOverwriteOutput(true);
Config.setConcurrency(4);
