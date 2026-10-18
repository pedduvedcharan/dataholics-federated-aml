// Typed access to data.json (written by MASTER from the VM's state files; never hand-edit it).
// Every number shown in the video is read or derived here. Numbers that are not in data.json
// are marked SCRIPT and come from submission/VIDEO_SCRIPT.md.
import raw from "./data.json";

type Round = { round: number; auc: number; ap: number; accepted: number[]; excluded: number[] };
type RedRow = {
  sigma: number;
  attack_auc: number;
  attack_auc_ci90: number[];
  verdict: string;
};

const d = raw as unknown as {
  dpon: { rounds: Round[]; dp: { sigma: number } };
  dpoff: { rounds: Round[] };
  rogue_on: { rounds: Round[] };
  rogue_off: { rounds: Round[] };
  redteam: { rows: Record<string, RedRow>; current_setting: string };
  baselines: {
    centralized_logreg: { auc: number; ap: number };
    federated: { auc: number; ap: number };
    per_bank: Record<string, Record<string, { pooled_auc: number; pooled_ap: number }>>;
  };
  footprint: {
    total_peak_rss_mb_sum: number;
    seconds_per_round: number;
    total_runtime_s: number;
    cpu_count: number;
    arch: string;
  };
  alerts: {
    meta: { demo_alert_id: string };
    top: { alert_id: string; rank: number; score: number; banks: number }[];
  };
  partition: {
    n_rows_total: number;
    n_laundering_total: number;
    banks: Record<string, { rows_raw: number; role: string; from_bank: string }>;
  };
  sar_A06_llm_paragraph: string;
  egress_one_run: { messages: number; params: number; rows_shared: number; params_per_update: number };
  guardrail: { recorded_reports: number; llm_drafts_rejected: number };
};

export const data = d;

export const fmt3 = (x: number) => x.toFixed(3);
export const fmtInt = (x: number) => Math.round(x).toLocaleString("en-US");

const last = <T,>(a: T[]) => a[a.length - 1];

export const dponAuc = d.dpon.rounds.map((r) => r.auc);
export const dpoffAuc = d.dpoff.rounds.map((r) => r.auc);
export const rogueOffAp = d.rogue_off.rounds.map((r) => r.ap);
export const rogueOnAp = d.rogue_on.rounds.map((r) => r.ap);

export const rogueExcludedRounds = d.rogue_on.rounds.filter((r) => r.excluded.includes(5)).length;
export const rogueRounds = d.rogue_on.rounds.length;
export const honestExcluded = d.rogue_on.rounds.reduce(
  (n, r) => n + r.excluded.filter((b) => b !== 5).length,
  0,
);

export const laundryOneIn = Math.round(d.partition.n_rows_total / d.partition.n_laundering_total);

/**
 * Grouped bars for scene 6. "Best single bank" is the best model per metric, both bank 4:
 * AUC from logistic regression, precision from the tree model (HistGradientBoosting); see footnote.
 */
const bank4 = d.baselines.per_bank["4"];
export const bestSingleBank = { auc: bank4.logreg.pooled_auc, ap: bank4.hgb.pooled_ap };
export const baselineBars = [
  { label: "Best single bank*", auc: bestSingleBank.auc, ap: bestSingleBank.ap, source: "data" },
  {
    label: "Centralized pooling",
    auc: d.baselines.centralized_logreg.auc,
    ap: d.baselines.centralized_logreg.ap,
    source: "data",
  },
  { label: "Ours, no noise", auc: last(d.dpoff.rounds).auc, ap: last(d.dpoff.rounds).ap, source: "data" },
  { label: "Ours, with noise", auc: d.baselines.federated.auc, ap: d.baselines.federated.ap, source: "data" },
];

export const redRows = Object.entries(d.redteam.rows).map(([name, r]) => ({ name, ...r }));
