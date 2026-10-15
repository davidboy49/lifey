import type { ReviewLearning } from "./learning";

export type CellState = "unknown" | "none" | "logged";

export interface HabitCell {
  date: string;
  state: CellState;
  amount?: number;
  level?: number;
}

export interface HabitRow {
  tag: string;
  label: string;
  unit: string;
  cells: HabitCell[];
  days: number;
  total: number;
  builtin: boolean;
}

export interface WellbeingRow {
  tag: "mood" | "energy" | "wake";
  label: string;
  cells: { date: string; state: CellState; value?: number; level?: number }[];
  average: number | null;
  count: number;
}

export interface QuitCell {
  date: string;
  state: "unknown" | "slip" | "clean" | "unchecked";
  urge?: boolean;
}

export interface QuitCard {
  current_run: number;
  best_run: number;
  urges_this_run: number;
  slips_7d: number;
  slips_30d: number;
  free_days_30: number;
  tracked_days_30: number;
  free_pct_30: number | null;
  tracking_since: string;
  relapsed_today: boolean;
}

export interface QuitComeback {
  window_days: number;
  episodes: number;
  next_day: number;
  unknown: number;
  longest: number | null;
  ongoing: boolean;
  text: string | null;
}

export interface CatalogHabit {
  tag: string;
  label: string;
  unit: string;
  builtin: boolean;
  cue_if: string | null;
  cue_then: string | null;
}

export interface HabitsResponse {
  today: string;
  weeks: number;
  days: string[];
  habits: HabitRow[];
  wellbeing: WellbeingRow[];
  quit: { card: QuitCard | null; strip: QuitCell[]; comeback: QuitComeback };
  catalog: CatalogHabit[];
  feeling: { today: number | null; ratings: Record<string, number>; by_run: FeelingByRun };
}

export interface FeelingByRun {
  rows: { label: string; n: number; mean: number | null; enough: boolean }[];
  rated_days: number;
  placed: number;
  needed: number;
}

export interface Review {
  week_start: string;
  week_end: string;
  label: string;
  is_current: boolean;
  prev_week: string | null;
  next_week: string | null;
  numbers: {
    sleep: { avg_seconds: number | null; prev_avg_seconds: number | null; nights: number; of: number };
    hrv: { avg: number | null; usual: number | null; mornings: number; of: number; delta_pct: number | null };
    training: { sessions: number; target: number };
    quit: { free_days: number; tracked_days: number; slips: number; days_with_entries: number } | null;
    mood: { avg: number | null; count: number };
  };
  notes: { date: string; time: string; kind: string; title: string; text: string }[];
  habits: HabitRow[];
  patterns: {
    tag: string;
    label: string;
    metric: string;
    with_n: number;
    without_n: number;
    with_avg: number;
    without_avg: number | null;
    needed: number;
    enough: boolean;
    text: string;
  }[];
  min_nights: number;
  reflection: {
    went_well: string; got_in_way: string; learned: string; plan_if: string; plan_then: string;
    recall?: string; learn_slot?: string;
  } | null;
  learning: ReviewLearning;
  last_plan: { plan_if: string; plan_then: string } | null;
  habit_cues: { label: string; cue_if: string | null; cue_then: string | null }[];
}

export interface DataColumn {
  key: string;
  label: string;
  kind: "text" | "number" | "date" | "time" | "chip";
  hidden: boolean;
}

export interface DataTableResponse {
  key: string;
  label: string;
  total: number;
  limit: number;
  offset: number;
  columns: DataColumn[];
  rows: Record<string, string | number | boolean | null>[];
}

export interface DatasetInfo {
  key: string;
  label: string;
  rows: number;
}

export type QuestState = "pass" | "fail" | "unknown" | "pending" | "rest";

export interface Quest {
  week_start: string;
  kind: "habit_free" | "sleep_hours" | "bed_before" | "training" | "learning_sessions";
  target: number;
  params: { tag?: string; hours?: number; time?: string };
  label: string;
  status: "met" | "missed" | "at_risk" | "on_track";
  passed: number;
  failed: number;
  unknown: number;
  pending: number;
  days: { date: string; state: QuestState }[];
}

export interface QuestResponse {
  week_start: string;
  is_current: boolean;
  editable: boolean;
  quest: Quest | null;
  plan: { plan_if: string; plan_then: string } | null;
  templates: {
    habits: { tag: string; label: string }[];
    sleep_hours: number[];
    bed_times: string[];
    default_target: Record<string, number>;
  };
}

export function hoursMinutes(seconds: number | null): string {
  if (seconds === null) return "·";
  const m = Math.round(seconds / 60);
  return `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, "0")}m`;
}
