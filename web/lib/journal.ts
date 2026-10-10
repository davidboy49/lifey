export type EntryKind = "habit" | "quit" | "reason" | "checkin" | "training" | "note";

export interface JournalEntry {
  date: string;
  kind: EntryKind;
  title: string;
  subtitle: string;
  badges: string[];
  note: string;
  ids: number[];
  time: string;
  time_recorded: boolean;
  recalled: boolean;
}

export type JournalGroup =
  | { empty: true; first: string; last: string }
  | { empty: false; date: string; entries: JournalEntry[] };

export interface JournalResponse {
  today: string;
  start: string;
  days: number;
  kind: string;
  count: number;
  summary: {
    mood: number | null;
    energy: number | null;
    habits_today: string[];
    notes_today: number;
    days_free: number | null;
    best_run: number | null;
  };
  groups: JournalGroup[];
}

export interface SyncSource {
  key: string;
  label: string;
  status: "available" | "not_recorded" | "fetch_failed" | "parse_failed" | "stale" | "unavailable";
  fetched_at: string | null;
  attempted_at: string | null;
  retained: boolean;
}

export interface SyncStatus {
  running: boolean;
  last_run: { id: number; status: string; started_at: string; finished_at: string | null } | null;
  sources: SyncSource[];
}

/** "Sat 10 Oct" from an ISO date, without time-zone drift. */
export function shortDay(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString("en-GB", {
    weekday: "short", day: "numeric", month: "short", timeZone: "UTC",
  });
}

export function addDays(iso: string, delta: number): string {
  const [y, m, d] = iso.split("-").map(Number);
  const t = new Date(Date.UTC(y, m - 1, d + delta));
  return t.toISOString().slice(0, 10);
}

export function dayName(iso: string, today: string): { name: string; sub: string } {
  if (iso === today) return { name: "Today", sub: shortDay(iso) };
  if (iso === addDays(today, -1)) return { name: "Yesterday", sub: shortDay(iso) };
  return { name: shortDay(iso), sub: "" };
}
