export type NightKind = "recorded" | "incomplete" | "missing";

export interface SleepNight {
  date: string;
  hours: number | null;
  kind: NightKind;
  score: number | null;
  bed: string | null;
  wake: string | null;
  hrv: number | null;
}

export interface Evidence {
  cite: string;
  finding: string;
  caveat: string;
  confidence: "strong" | "moderate" | "weak";
  url: string;
}

export interface SleepResponse {
  today: string;
  target_h: number;
  incomplete_below_h: number;
  last_night: SleepNight;
  nights: SleepNight[];
  progress: {
    window: number;
    target_h: number;
    mean_h: number | null;
    gap_h: number | null;
    nights: number;
    met: boolean | null;
    nights_at_or_above: number;
    earlier_mean_h: number | null;
    recent_mean_h: number | null;
  };
  debt: {
    window: number;
    target_h: number;
    hours: number;
    nights_counted: number;
    nights_short: number;
    nights_under_6: number;
    nights_missing: number;
    nights_excluded: number;
    average_shortfall_h: number | null;
  };
  regularity:
    | { enough: false; nights: number }
    | {
        enough: true;
        nights: number;
        wake_sd_min: number;
        bed_sd_min: number;
        usual_wake: string;
        usual_bed: string;
        flag_threshold_min: number;
        irregular: boolean;
      };
  weekend:
    | { enough: false; weekend_n: number; weekday_n: number }
    | { enough: true; weekend_n: number; weekday_n: number; weekend_h: number; weekday_h: number; difference_h: number };
  outcomes: {
    target_h: number;
    below_nights: number;
    above_nights: number;
    needed: number;
    rows: {
      label: string;
      unit: string;
      better: "higher" | "lower";
      below: number | null;
      below_n: number;
      above: number | null;
      above_n: number;
      enough: boolean;
    }[];
  };
  garmin_need: { hours: number; baseline_h: number; feedback: string | null; as_of: string } | null;
  suggestions: { id: string; title: string; detail: string; evidence: string[]; enough?: boolean }[];
  walker: {
    source: string;
    critique: string;
    window_days: number;
    tips: {
      id: string;
      topic: string;
      advice: string;
      state: "look" | "fine" | "unknown" | "not_measured" | "info";
      data: string | null;
    }[];
  };
  doctor: { source: string; topics: string[]; flags: string[]; summary: string };
  evidence: Record<string, Evidence>;
  evidence_used: string[];
}

export function hm(hours: number | null): string {
  if (hours === null) return "·";
  const m = Math.round(hours * 60);
  return `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, "0")} m`;
}
