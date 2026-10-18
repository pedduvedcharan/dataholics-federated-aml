// Scene 5 (1:06–1:40): the real screen recording from the VM, or a labelled placeholder.
import React from "react";
import { AbsoluteFill, Img, OffthreadVideo, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { C, fonts } from "../theme";
import { SceneShell } from "../components/SceneShell";
import { Caption } from "../components/Caption";
import { useFadeUp } from "../components/anim";

const SHOTS = [
  "uname -m  →  s390x",
  "docker ps  →  bank1–4 + coordinator",
  "DP-on federated run starting",
  "dashboard: AUC curve filling, rows shared 0",
  "docker compose run --rm tryleak  →  BLOCKED, counter +1",
];

export const Live: React.FC<{ narration: string; hasLiveDemo: boolean; muteDemo: boolean }> = ({
  narration,
  hasLiveDemo,
  muteDemo,
}) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const card = useFadeUp(6);

  if (hasLiveDemo) {
    return (
      <AbsoluteFill style={{ background: C.gray100 }}>
        <OffthreadVideo
          src={staticFile("live-demo.mp4")}
          muted={muteDemo}
          style={{ width: "100%", height: "100%", objectFit: "contain" }}
        />
        <Caption text={narration} />
      </AbsoluteFill>
    );
  }

  // Fallback (MASTER, 05:55 CDT): no screen recording exists, so show real evidence captured on the VM,
  // labelled as screenshots of the running system (never "live").
  void SHOTS;
  const seg = Math.floor(durationInFrames / 4);
  const idx = Math.min(3, Math.floor(frame / seg));
  const local = frame - idx * seg;
  const zoom = 1 + 0.04 * (local / seg);
  const fadeIn = Math.min(1, local / 10);
  const images = ["fallback/dashboard_regulator.png", "fallback/dashboard_training.png", "fallback/dashboard_alerts_report.png"];
  const captions = [
    "IBM LinuxONE (s390x): four bank containers + coordinator training",
    "Regulator view: transaction rows shared 0, every update logged",
    "Shared model quality per round, measured on the VM",
    "Inside the bank: alert queue and the LLM-drafted report",
  ];
  const terminal = [
    "$ uname -a",
    "Linux dataholics 6.8.0-147-generic … s390x s390x s390x GNU/Linux",
    "$ lscpu | head",
    "Architecture: s390x   Byte Order: Big Endian   CPU(s): 3",
    "Vendor ID: IBM/S390   Machine type: 9175   Hypervisor: z/VM 7.3.0",
    "$ docker ps            # 2026-10-17 22:03 UTC, during training",
    "bank1         fedaml   Up 4 seconds",
    "bank2         fedaml   Up 4 seconds",
    "bank3         fedaml   Up 4 seconds",
    "bank4         fedaml   Up 4 seconds",
    "coordinator   fedaml   Up 10 seconds (healthy)   127.0.0.1:8000",
    "dashboard     fedaml   Up 33 minutes             127.0.0.1:8050",
    "$ docker stats --no-stream",
    "bank1  65.67% CPU  314.3MiB / 7.821GiB    coordinator  10.61% CPU  122.8MiB",
  ];
  return (
    <SceneShell tone="dark" index={5} kicker="Running on IBM LinuxONE" narration={narration}>
      <div style={{ position: "absolute", left: 120, right: 120, top: 120, bottom: 40, ...card }}>
        <div
          style={{
            position: "absolute",
            inset: 0,
            overflow: "hidden",
            borderRadius: 8,
            border: `2px solid ${C.gray60}`,
            background: idx === 0 ? C.gray100 : C.white,
            opacity: fadeIn,
          }}
        >
          {idx === 0 ? (
            <div style={{ padding: "40px 56px", fontFamily: fonts.mono, fontSize: 30, lineHeight: 1.5, color: C.gray30, transform: `scale(${zoom})`, transformOrigin: "top left" }}>
              {terminal.map((l) => (
                <div key={l} style={{ color: l.startsWith("$") ? C.blue20 : C.white, whiteSpace: "pre" }}>{l}</div>
              ))}
            </div>
          ) : (
            <Img
              src={staticFile(images[idx - 1])}
              style={{ width: "100%", height: "100%", objectFit: "contain", transform: `scale(${zoom})`, transformOrigin: "center top" }}
            />
          )}
        </div>
        <div style={{ position: "absolute", left: 0, top: -54, fontFamily: fonts.mono, fontSize: 24, color: C.yellow30 }}>
          Recorded on IBM LinuxONE (s390x), 17 Oct 2026 · screenshots of the running system
        </div>
        <div style={{ position: "absolute", left: 0, bottom: -40, fontFamily: fonts.mono, fontSize: 22, color: C.gray30 }}>
          {captions[idx]}
        </div>
      </div>
    </SceneShell>
  );
};
