// IBM Carbon palette (docs/UI_REFERENCE.md, last section "IBM palette") and IBM Plex fonts.
// These are the only colors used in the video. No logos anywhere: text only.
import { loadFont as loadSans } from "@remotion/google-fonts/IBMPlexSans";
import { loadFont as loadCondensed } from "@remotion/google-fonts/IBMPlexSansCondensed";
import { loadFont as loadMono } from "@remotion/google-fonts/IBMPlexMono";

const sans = loadSans("normal", { weights: ["400", "500", "600", "700"], subsets: ["latin"] });
const condensed = loadCondensed("normal", { weights: ["500", "600", "700"], subsets: ["latin"] });
const mono = loadMono("normal", { weights: ["400", "500", "600"], subsets: ["latin"] });

export const fonts = {
  sans: sans.fontFamily,
  condensed: condensed.fontFamily,
  mono: mono.fontFamily,
};

export const C = {
  gray10: "#F4F4F4", // page background
  white: "#FFFFFF", // surface / cards
  blue10: "#EDF5FF", // raised panel
  blue20: "#D0E2FF", // raised panel border, selected row
  gray100: "#161616", // ink, dark slides
  gray90: "#262626", // second dark
  gray70: "#525252", // secondary text
  gray60: "#6F6F6F", // tertiary text
  gray20: "#E0E0E0", // hairlines
  gray30: "#C6C6C6", // strong hairlines
  blue60: "#0F62FE", // primary
  blue70: "#0043CE",
  blue80: "#002D9C",
  green50: "#24A148", // success / PROTECTED / defense on
  green10: "#DEFBE6",
  yellow30: "#F1C21B", // warning / WEAK LEAK (Gray 100 text on it)
  orange40: "#FF832B", // rogue-off line
  red60: "#DA1E28", // error / LEAKS / rogue / blocked
  red10: "#FFF1F1",
  purple60: "#8A3FFC", // LLM-written marking
  purple10: "#F6F2FF",
  purple70: "#6929C4", // chart series 2
  teal60: "#007D79", // chart series 3
  magenta60: "#D02670", // chart series 4
  cyan50: "#1192E8", // chart extra
};

export const FPS = 30;
export const WIDTH = 1920;
export const HEIGHT = 1080;
/** Height reserved at the bottom of every scene for the lower-third caption. */
export const CAPTION_H = 190;
