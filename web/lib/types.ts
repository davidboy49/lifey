export type Status = "good" | "watch" | "alert" | "unknown";
export type Provenance = "measured" | "estimate" | "score" | "not_recorded";

export interface Metric {
  key: string;
  label: string;
  unit: string;
  value: number | null;
  baseline: number | null;
  baseline_sd: number | null;
  delta_pct: number | null;
  status: Status;
  provenance: Provenance;
  source_status: string | null;
  coverage: string;
  series: (number | null)[];
}

export interface Today {
  date: string;
  source: "demo" | "garmin";
  synced_at: string | null;
  readiness: {
    score: number | null;
    label: string;
    summary: string;
    action: string;
    confidence: "high" | "medium" | "low";
  };
  metrics: Metric[];
  reasons: { text: string; evidence: string[] }[];
}
