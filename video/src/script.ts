// Scene list from submission/VIDEO_SCRIPT.md (the source of truth): ids, time slots, narration.
// Durations in frames at 30 fps; they sum to 5280 (2:56).
export type SceneId =
  | "hook"
  | "problem"
  | "pitch"
  | "architecture"
  | "live"
  | "results"
  | "rogue"
  | "redteam"
  | "report"
  | "close";

const s = (mmss: string) => {
  const [m, sec] = mmss.split(":").map(Number);
  return (m * 60 + sec) * 30;
};

export const SCENES: { id: SceneId; from: number; to: number; narration: string }[] = [
  {
    id: "hook",
    from: s("0:00"),
    to: s("0:14"),
    narration:
      "A criminal moves two million euros through three banks. Each bank sees one transfer, and each transfer looks normal. Nobody sees the scheme.",
  },
  {
    id: "problem",
    from: s("0:14"),
    to: s("0:28"),
    narration:
      "The obvious fix is to pool every bank's data. Five Dutch banks tried exactly that, and regulators shut it down in 2024. So we asked: what if the data never had to move?",
  },
  {
    id: "pitch",
    from: s("0:28"),
    to: s("0:40"),
    narration:
      "We are Dataholics. We built what the Dutch banks had to shut down, so that it would have been legal: five banks, one shared detector, zero customer rows shared.",
  },
  {
    id: "architecture",
    from: s("0:40"),
    to: s("1:06"),
    narration:
      "On IBM's synthetic anti-money-laundering data, five million transactions split across five banks, each bank trains its own copy of one shared model, inside its own container. Only twenty-one numbers leave a bank each round, clipped and noised, through a single audited door that refuses raw data. The coordinator screens for cheaters, averages the rest, and sends the improved model back.",
  },
  {
    id: "live",
    from: s("1:06"),
    to: s("1:40"),
    narration:
      "This is it running on an IBM LinuxONE machine, s390x, in sandboxed containers. Four banks and a coordinator train together. The regulator's dashboard logs every update, with zero transaction rows shared, and counts every blocked attempt to send raw rows. Inside each bank, alerts and reports stay local.",
  },
  {
    id: "results",
    from: s("1:40"),
    to: s("1:58"),
    narration:
      "Without noise, the shared model matches the best single bank, and finds about three times more real laundering per alert than pooling everyone's raw data. Privacy noise costs one point of AUC. We show that price, not hide it.",
  },
  {
    id: "rogue",
    from: s("1:58"),
    to: s("2:14"),
    narration:
      "Now one bank cheats, poisoning its updates to hide its own laundering. Without our defense, most alerts become false alarms. With it, the coordinator throws that bank out in ten of ten rounds, and never touches an honest one.",
  },
  {
    id: "redteam",
    from: s("2:14"),
    to: s("2:34"),
    narration:
      "Then we attacked ourselves. Can the coordinator tell whether one suspect's transaction was in a bank's update? Without noise: ninety-nine percent. Our first noise level still leaked a little, so we raised it. Now it is near chance.",
  },
  {
    id: "report",
    from: s("2:34"),
    to: s("2:48"),
    narration:
      "For each top alert, a small language model running on the same CPU drafts the suspicious activity report. Code writes every fact, and checks every claim the model makes. The model ranks; a person decides.",
  },
  {
    id: "close",
    from: s("2:48"),
    to: s("2:56"),
    narration:
      "All on one IBM LinuxONE machine, measured, not estimated. What the Dutch banks had to shut down, built so it would have been legal.",
  },
];

export const TOTAL_FRAMES = s("2:56"); // 5280
