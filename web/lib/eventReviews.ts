export type LoopTag = "loneliness" | "urge" | "drinking" | "stress" | "pois" | "poor_sleep";

export const LOOP_TAGS: { tag: LoopTag; label: string }[] = [
  { tag: "loneliness", label: "Loneliness" },
  { tag: "urge", label: "Urge" },
  { tag: "drinking", label: "Drinking" },
  { tag: "stress", label: "Stress" },
  { tag: "pois", label: "POIS" },
  { tag: "poor_sleep", label: "Poor sleep" },
];

export const loopLabel = (t: string) => LOOP_TAGS.find((x) => x.tag === t)?.label ?? t;

export interface ReviewPhoto {
  id: number;
  review_id: number;
  filename: string;
  mime: string;
  bytes: number;
  width: number | null;
  height: number | null;
  has_thumb: boolean;
}

export interface EventReview {
  id: number;
  date: string;
  event: string;
  mood: number | null;
  energy: number | null;
  notes: string;
  went_well: string;
  would_change: string;
  loop_tags: LoopTag[];
  lesson: string;
  created_at: string;
  updated_at: string;
  photos: ReviewPhoto[];
}

export interface ReviewList {
  reviews: EventReview[];
  tag_counts: Record<LoopTag, number>;
}

export interface DayData {
  date: string;
  has_data: boolean;
  metrics: {
    sleep_score: number | null;
    sleep_seconds: number | null;
    hrv_ms: number | null;
    hrv_status: string | null;
    resting_hr: number | null;
    training_readiness: number | null;
    body_battery_high: number | null;
    body_battery_low: number | null;
  };
  activities: {
    id: number;
    name: string | null;
    type: string | null;
    start: string | null;
    duration_seconds: number | null;
    distance_meters: number | null;
    avg_hr: number | null;
  }[];
}

/** Today's date where the data lives (Asia/Phnom_Penh), not wherever the phone happens to be. */
export function localToday(): string {
  return new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Phnom_Penh" });
}

export function longDay(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString("en-GB", {
    weekday: "short", day: "numeric", month: "short", year: "numeric", timeZone: "UTC",
  });
}

export function duration(seconds: number | null): string {
  if (seconds === null) return "·";
  const m = Math.round(seconds / 60);
  return m >= 60 ? `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, "0")}m` : `${m} min`;
}

export function distance(meters: number | null): string | null {
  if (meters === null || meters <= 0) return null;
  return meters >= 1000 ? `${(meters / 1000).toFixed(2)} km` : `${Math.round(meters)} m`;
}

export function activityType(t: string | null): string {
  return t ? t.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase()) : "Activity";
}

/** The API's readable message, or a fallback. */
export async function errorText(r: Response, fallback: string): Promise<string> {
  try {
    const body = await r.json();
    return typeof body?.detail === "string" ? body.detail : fallback;
  } catch {
    return fallback;
  }
}
