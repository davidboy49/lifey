export type Category = "tech" | "life" | "sport" | "money" | "investing" | "other";

export const CATEGORY_LABEL: Record<Category, string> = {
  tech: "Tech skill",
  life: "Life skill",
  sport: "Sport",
  money: "Making money",
  investing: "Investing",
  other: "Something else",
};

export const RESULT_LABEL = { met: "Met", partly: "Partly met", not_met: "Not met" } as const;
export type Result = keyof typeof RESULT_LABEL;

export const NEXT_LABEL = { continue: "Continue", switch: "Switch topic", pause: "Pause" } as const;
export type NextStep = keyof typeof NEXT_LABEL;

export interface Focus {
  id: number;
  month: string;
  topic: string;
  topic_key: string;
  category: Category;
  outcome: string;
  plan_if: string;
  plan_then: string;
  why: string;
  habit_tag: string;
  status: "active" | "closed";
  result: Result | null;
  next_step: NextStep | null;
  closed_at: string | null;
}

export interface Sessions {
  entries: number;
  minutes: number;
  days_practised: number;
  days: number;
  unknown_days: number;
}

export interface Study {
  id: number;
  citation: string;
  url: string;
  finding: string;
  retrieved_on: string;
}

export interface StarterStudy {
  id: string;
  citation: string;
  url: string;
  finding: string;
  caveat: string;
  used_for: string;
}

export interface LearningResponse {
  today: string;
  month: string;
  renewal: "set" | "close" | "ok";
  active: Focus | null;
  month_sessions: Sessions | null;
  history: Focus[];
  shelf: Study[];
  starter: StarterStudy[];
  templates: { categories: Category[]; habit: { tag: string; label: string; unit: string } };
}

export interface ReviewLearning {
  focus: Pick<Focus, "id" | "topic" | "category" | "outcome" | "plan_if" | "plan_then" | "month"> | null;
  renewal: "set" | "close" | "ok";
  week: Sessions | null;
  last_recall: string | null;
  last_slot: string | null;
}

/** "3 sessions, 95 minutes on 3 days" without ever turning a gap into a zero. */
export function sessionsLine(s: Sessions): string {
  if (s.entries === 0) {
    return s.unknown_days === s.days ? "Nothing logged yet." : "No sessions logged.";
  }
  const n = `${s.entries} session${s.entries === 1 ? "" : "s"}`;
  const m = s.minutes > 0 ? `, ${s.minutes} minutes` : "";
  return `${n}${m} on ${s.days_practised} day${s.days_practised === 1 ? "" : "s"}`;
}

export function monthName(iso: string): string {
  return new Date(`${iso.slice(0, 7)}-01T00:00:00`).toLocaleDateString("en-GB", { month: "long", year: "numeric" });
}

export interface Proposal {
  id: number;
  kind: "study" | "focus" | "quest";
  why: string;
  created_at: string;
  payload: Record<string, unknown>;
  label?: string;              // quests: the plain-words label
  replaces: string | null;     // quests: what accepting would replace
  blocked: string | null;      // why accepting would fail right now
}

export interface ConnectorActivityRow {
  id: number;
  at: string;
  tool: string;
  summary: string;
  outcome: "ok" | "refused";
  can_undo: boolean;
  undone_at: string | null;
}
