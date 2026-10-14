"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { Quest, QuestResponse } from "@/lib/habits";
import { shortDay } from "@/lib/journal";

type Kind = Quest["kind"];

const KIND_LABEL: Record<Kind, string> = {
  habit_free: "Skip a habit",
  sleep_hours: "Sleep enough",
  bed_before: "In bed on time",
  training: "Train",
};

/** Set, change or clear the quest for one week. Progress is scored by the server from your data. */
export function QuestPicker({ data }: { data: QuestResponse }) {
  const router = useRouter();
  const t = data.templates;
  const current = data.quest;
  const [kind, setKind] = useState<Kind>(current?.kind ?? "bed_before");
  const [tag, setTag] = useState(current?.params.tag ?? t.habits[0]?.tag ?? "");
  const [hours, setHours] = useState(String(current?.params.hours ?? 7));
  const [time, setTime] = useState(current?.params.time ?? "23:00");
  const [target, setTarget] = useState(current?.target ?? t.default_target[current?.kind ?? "bed_before"] ?? 4);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  if (!data.editable) return null;

  function pickKind(k: Kind) {
    setKind(k);
    setTarget(t.default_target[k] ?? 4);
    setSaved(false);
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setSaved(false);
    const params = kind === "habit_free" ? { tag } : kind === "sleep_hours" ? { hours: Number(hours) } : kind === "bed_before" ? { time } : {};
    try {
      const res = await fetch(`/api/quest/${data.week_start}`, {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ kind, target, params }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) return setError(typeof body.detail === "string" ? body.detail : "Couldn’t save the quest.");
      setSaved(true);
      router.refresh();
    } catch {
      setError("Couldn’t reach the server.");
    } finally {
      setBusy(false);
    }
  }

  async function clear() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/quest/${data.week_start}`, { method: "DELETE" });
      if (!res.ok && res.status !== 404) return setError("Couldn’t clear the quest.");
      router.refresh();
    } catch {
      setError("Couldn’t reach the server.");
    } finally {
      setBusy(false);
    }
  }

  const field = "rounded-xl border border-line bg-panel px-3 py-2 text-[15px] text-ink outline-none focus:border-accent";

  return (
    <form onSubmit={submit} className="card grid gap-4 p-5 sm:p-6">
      <div>
        <p className="eyebrow">{data.is_current ? "This week’s quest" : `Quest for the week of ${shortDay(data.week_start)}`}</p>
        <h2 className="font-display text-xl font-semibold">Make the plan something Lifey can check</h2>
        {data.plan && (data.plan.plan_if || data.plan.plan_then) && (
          <p className="mt-1 text-sm text-ink-2">
            Your plan: if {data.plan.plan_if || "…"}, then {data.plan.plan_then || "…"}.
          </p>
        )}
      </div>

      <div role="group" aria-label="Quest type" className="flex flex-wrap gap-1 rounded-xl border border-line bg-raised p-1">
        {(Object.keys(KIND_LABEL) as Kind[]).map((k) => (
          <button
            key={k}
            type="button"
            aria-pressed={kind === k}
            onClick={() => pickKind(k)}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium ${kind === k ? "bg-accent-soft text-accent" : "text-ink-2 hover:text-ink"}`}
          >
            {KIND_LABEL[k]}
          </button>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-3 text-[15px]">
        {kind === "habit_free" && (
          <>
            <span>No</span>
            <select aria-label="Habit" className={field} value={tag} onChange={(e) => setTag(e.target.value)}>
              {t.habits.map((h) => <option key={h.tag} value={h.tag}>{h.label}</option>)}
            </select>
            <span>on</span>
          </>
        )}
        {kind === "sleep_hours" && (
          <>
            <select aria-label="Hours of sleep" className={field} value={hours} onChange={(e) => setHours(e.target.value)}>
              {t.sleep_hours.map((h) => <option key={h} value={h}>{h} hours or more</option>)}
            </select>
            <span>on</span>
          </>
        )}
        {kind === "bed_before" && (
          <>
            <span>In bed before</span>
            <select aria-label="Bedtime" className={field} value={time} onChange={(e) => setTime(e.target.value)}>
              {t.bed_times.map((b) => <option key={b} value={b}>{b}</option>)}
            </select>
            <span>on</span>
          </>
        )}
        {kind === "training" && <span>At least</span>}
        <select aria-label="How many" className={field} value={target} onChange={(e) => setTarget(Number(e.target.value))}>
          {[1, 2, 3, 4, 5, 6, 7].map((n) => <option key={n} value={n}>{n}</option>)}
        </select>
        <span>{kind === "habit_free" ? "of 7 days" : kind === "training" ? (target === 1 ? "session" : "sessions") : "nights"}</span>
      </div>

      <p className="text-xs text-ink-3">
        Days with no entries and nights with no recording are not counted for or against you.
      </p>
      {error && <p role="alert" className="rounded-xl bg-alert-soft px-3.5 py-2.5 text-sm text-alert">{error}</p>}
      <div className="flex flex-wrap items-center gap-3">
        <button type="submit" disabled={busy} className="rounded-xl bg-accent px-5 py-2.5 font-medium text-ground disabled:opacity-60">
          {busy ? "Saving…" : current ? "Update quest" : "Set quest"}
        </button>
        {current && (
          <button type="button" onClick={clear} disabled={busy} className="text-sm text-ink-3 underline underline-offset-2 hover:text-alert">
            Clear
          </button>
        )}
        {saved && <span role="status" className="text-sm text-good">Saved.</span>}
      </div>
    </form>
  );
}
