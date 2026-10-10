"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

interface Props {
  weekStart: string;
  initial: { went_well: string; got_in_way: string; learned: string; plan_if: string; plan_then: string } | null;
  lastPlan: { plan_if: string; plan_then: string } | null;
}

const field = "w-full rounded-xl border border-line bg-panel px-3.5 py-2.5 text-[15px] text-ink outline-none focus:border-accent";

export function ReviewReflection({ weekStart, initial, lastPlan }: Props) {
  const router = useRouter();
  const start = useRef(JSON.stringify(initial ?? {}));
  const [form, setForm] = useState({
    went_well: initial?.went_well ?? "",
    got_in_way: initial?.got_in_way ?? "",
    learned: initial?.learned ?? "",
    plan_if: initial?.plan_if ?? "",
    plan_then: initial?.plan_then ?? "",
  });
  const [state, setState] = useState<"idle" | "saving" | "saved" | "error">(initial ? "saved" : "idle");
  const dirty = JSON.stringify(form) !== JSON.stringify({ ...JSON.parse(start.current || "{}") });

  function set<K extends keyof typeof form>(k: K, v: string) {
    setForm((f) => ({ ...f, [k]: v }));
    setState("idle");
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setState("saving");
    try {
      const r = await fetch(`/api/review/${weekStart}`, {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(form),
      });
      if (!r.ok) throw new Error();
      start.current = JSON.stringify(form);
      setState("saved");
      router.refresh();
    } catch {
      setState("error");
    }
  }

  return (
    <form onSubmit={save} className="grid gap-6">
      {lastPlan && (
        <div className="rounded-2xl bg-accent-soft px-4 py-3.5">
          <p className="eyebrow text-accent">Your plan from last week</p>
          <p className="mt-1 text-[15px]">
            If <b>{lastPlan.plan_if || "…"}</b>, then I will <b>{lastPlan.plan_then || "…"}</b>.
          </p>
          <p className="mt-1 text-sm text-ink-2">How did it go? Say so in the first box below.</p>
        </div>
      )}

      {([
        ["went_well", "What went well?", "Two or three sentences is plenty."],
        ["got_in_way", "What got in the way?", "Name the situation, not the kind of person you were that day."],
        ["learned", "What did you learn about yourself this week?", ""],
      ] as const).map(([key, label, hint]) => (
        <label key={key} className="grid gap-1.5" htmlFor={`rv-${key}`}>
          <span className="font-semibold">{label}</span>
          <textarea
            id={`rv-${key}`}
            className={`${field} min-h-[88px] resize-y`}
            value={form[key]}
            onChange={(e) => set(key, e.target.value)}
            placeholder={hint}
            maxLength={4000}
          />
        </label>
      ))}

      <fieldset className="grid gap-2">
        <legend className="font-semibold">One change for next week</legend>
        <div className="grid items-center gap-2 sm:grid-cols-[auto_1fr]">
          <label htmlFor="rv-if" className="font-display font-semibold">If</label>
          <input id="rv-if" className={field} value={form.plan_if} onChange={(e) => set("plan_if", e.target.value)} placeholder="it’s 3pm and I want a coffee" maxLength={300} />
          <label htmlFor="rv-then" className="font-display font-semibold">then I will</label>
          <input id="rv-then" className={field} value={form.plan_then} onChange={(e) => set("plan_then", e.target.value)} placeholder="make tea and take a 10 minute walk" maxLength={300} />
        </div>
        <p className="text-sm text-ink-3">Next week’s review opens with this sentence and asks how it went.</p>
      </fieldset>

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="submit"
          disabled={state === "saving" || (!dirty && state === "saved")}
          className="rounded-xl bg-accent px-6 py-3 font-medium text-ground hover:opacity-90 disabled:opacity-60"
        >
          {state === "saving" ? "Saving…" : state === "saved" && !dirty ? "Saved" : "Save review"}
        </button>
        <p role="status" aria-live="polite" className={`text-sm ${state === "error" ? "text-alert" : "text-ink-3"}`}>
          {state === "error" ? "Couldn’t save. Your text is still here; try again." : state === "saved" ? "Saved. You can edit it any time." : ""}
        </p>
      </div>
    </form>
  );
}
