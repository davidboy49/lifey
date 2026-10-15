"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import {
  CATEGORY_LABEL, NEXT_LABEL, RESULT_LABEL, monthName, sessionsLine,
  type Category, type LearningResponse, type NextStep, type Result,
} from "@/lib/learning";

const field = "w-full rounded-xl border border-line bg-panel px-3.5 py-2.5 text-[15px] text-ink outline-none focus:border-accent";
const button = "rounded-xl bg-accent px-5 py-2.5 font-medium text-ground hover:opacity-90 disabled:opacity-60";

async function send(url: string, method: string, body?: unknown): Promise<string | null> {
  try {
    const res = await fetch(url, {
      method,
      headers: { "content-type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (res.ok) return null;
    const data = await res.json().catch(() => ({}));
    return typeof data.detail === "string" ? data.detail : "Couldn’t save that.";
  } catch {
    return "Couldn’t reach the server.";
  }
}

interface FormProps {
  categories: Category[];
  initial?: { topic: string; category: Category; outcome: string; plan_if: string; plan_then: string; why: string };
  submitLabel: string;
  onSubmit: (v: NonNullable<FormProps["initial"]>) => Promise<string | null>;
  onCancel?: () => void;
}

function FocusForm({ categories, initial, submitLabel, onSubmit, onCancel }: FormProps) {
  const [v, setV] = useState(initial ?? { topic: "", category: "tech" as Category, outcome: "", plan_if: "", plan_then: "", why: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const set = <K extends keyof typeof v>(k: K, val: (typeof v)[K]) => setV((s) => ({ ...s, [k]: val }));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(await onSubmit(v));
    setBusy(false);
  }

  return (
    <form onSubmit={submit} className="grid gap-4">
      <div className="grid gap-3 sm:grid-cols-[1fr_auto]">
        <label className="grid gap-1.5">
          <span className="font-semibold">What are you learning?</span>
          <input className={field} value={v.topic} onChange={(e) => set("topic", e.target.value)} maxLength={80} required
            placeholder="Time-series cross-validation, Spanish, dividend investing, swimming…" />
        </label>
        <label className="grid gap-1.5">
          <span className="font-semibold">Kind</span>
          <select className={field} value={v.category} onChange={(e) => set("category", e.target.value as Category)}>
            {categories.map((c) => <option key={c} value={c}>{CATEGORY_LABEL[c]}</option>)}
          </select>
        </label>
      </div>
      <label className="grid gap-1.5">
        <span className="font-semibold">By the end of the month, I can…</span>
        <input className={field} value={v.outcome} onChange={(e) => set("outcome", e.target.value)} maxLength={240} required
          placeholder="explain it in two sentences and use it on my own data" />
        <span className="text-sm text-ink-3">Something you can check yourself. Lifey does not grade it.</span>
      </label>
      <fieldset className="grid gap-2">
        <legend className="font-semibold">Practice slot</legend>
        <div className="grid items-center gap-2 sm:grid-cols-[auto_1fr]">
          <label htmlFor="lf-if" className="font-display font-semibold">If</label>
          <input id="lf-if" className={field} value={v.plan_if} onChange={(e) => set("plan_if", e.target.value)} maxLength={200} placeholder="it is 20:00 on Tuesday or Thursday" />
          <label htmlFor="lf-then" className="font-display font-semibold">then I will</label>
          <input id="lf-then" className={field} value={v.plan_then} onChange={(e) => set("plan_then", e.target.value)} maxLength={200} placeholder="open the notebook for 30 minutes" />
        </div>
      </fieldset>
      <label className="grid gap-1.5">
        <span className="font-semibold">Why now <span className="font-normal text-ink-3">(optional)</span></span>
        <input className={field} value={v.why} onChange={(e) => set("why", e.target.value)} maxLength={200} />
      </label>
      {error && <p role="alert" className="rounded-xl bg-alert-soft px-3.5 py-2.5 text-sm text-alert">{error}</p>}
      <div className="flex flex-wrap items-center gap-3">
        <button type="submit" disabled={busy} className={button}>{busy ? "Saving…" : submitLabel}</button>
        {onCancel && <button type="button" onClick={onCancel} className="text-sm text-ink-3 underline underline-offset-2 hover:text-ink">Cancel</button>}
      </div>
    </form>
  );
}

function CloseMonth({ focusId, onDone }: { focusId: number; onDone: () => void }) {
  const [result, setResult] = useState<Result | "">("");
  const [next, setNext] = useState<NextStep | "">("");
  const [outcome, setOutcome] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    const err = await send(`/api/learning/focus/${focusId}/close`, "POST", {
      result, next_step: next, next_outcome: outcome,
    });
    setBusy(false);
    if (err) return setError(err);
    onDone();
  }

  const pill = (active: boolean) =>
    `rounded-lg px-3 py-1.5 text-sm font-medium ${active ? "bg-accent-soft text-accent" : "text-ink-2 hover:text-ink"}`;

  return (
    <form onSubmit={submit} className="grid gap-4 border-t border-line pt-4">
      <p className="text-sm text-ink-2">Close the month. A “not met” month is information, not a failure.</p>
      <div role="group" aria-label="Result" className="flex flex-wrap gap-1 rounded-xl border border-line bg-raised p-1">
        {(Object.keys(RESULT_LABEL) as Result[]).map((r) => (
          <button key={r} type="button" aria-pressed={result === r} onClick={() => setResult(r)} className={pill(result === r)}>
            {RESULT_LABEL[r]}
          </button>
        ))}
      </div>
      <div role="group" aria-label="Next" className="flex flex-wrap gap-1 rounded-xl border border-line bg-raised p-1">
        {(Object.keys(NEXT_LABEL) as NextStep[]).map((n) => (
          <button key={n} type="button" aria-pressed={next === n} onClick={() => setNext(n)} className={pill(next === n)}>
            {NEXT_LABEL[n]}
          </button>
        ))}
      </div>
      {next === "continue" && (
        <label className="grid gap-1.5">
          <span className="font-semibold">Outcome for the new month</span>
          <input className={field} value={outcome} onChange={(e) => setOutcome(e.target.value)} maxLength={240} required />
        </label>
      )}
      {error && <p role="alert" className="rounded-xl bg-alert-soft px-3.5 py-2.5 text-sm text-alert">{error}</p>}
      <div>
        <button type="submit" disabled={busy || !result || !next} className={button}>{busy ? "Closing…" : "Close this focus"}</button>
      </div>
    </form>
  );
}

/** The active focus (or the form to set one), with edit and close. */
export function LearningFocus({ data }: { data: LearningResponse }) {
  const router = useRouter();
  const [editing, setEditing] = useState(false);
  const [closing, setClosing] = useState(false);
  const refresh = () => { setEditing(false); setClosing(false); router.refresh(); };
  const a = data.active;
  const cats = data.templates.categories;

  if (!a) {
    return (
      <section className="card grid gap-4 p-5 sm:p-6" aria-labelledby="lf-set">
        <div>
          <p className="eyebrow">{monthName(data.month)}</p>
          <h2 id="lf-set" className="font-display text-xl font-semibold">What do you want to be better at this month?</h2>
          <p className="mt-1 text-sm text-ink-2">One thing at a time, with an outcome you can check at the end of the month.</p>
        </div>
        <FocusForm categories={cats} submitLabel="Set this month’s focus"
          onSubmit={async (v) => { const err = await send("/api/learning/focus", "PUT", v); if (!err) refresh(); return err; }} />
      </section>
    );
  }

  const s = data.month_sessions;
  return (
    <section className="card grid gap-4 p-5 sm:p-6" aria-labelledby="lf-active">
      {data.renewal === "close" && (
        <p role="status" className="rounded-xl bg-accent-soft px-3.5 py-2.5 text-sm text-accent">
          This focus started in {monthName(a.month)}. Close it, then continue, switch or pause.
        </p>
      )}
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <div>
          <p className="eyebrow">{CATEGORY_LABEL[a.category]} · since {monthName(a.month)}</p>
          <h2 id="lf-active" className="font-display text-2xl font-semibold">{a.topic}</h2>
        </div>
        {s && <p className="font-mono text-xs text-ink-3">{sessionsLine(s)} this month</p>}
      </div>
      {editing ? (
        <FocusForm categories={cats} initial={{ topic: a.topic, category: a.category, outcome: a.outcome, plan_if: a.plan_if, plan_then: a.plan_then, why: a.why }}
          submitLabel="Save changes" onCancel={() => setEditing(false)}
          onSubmit={async (v) => { const err = await send(`/api/learning/focus/${a.id}`, "PATCH", v); if (!err) refresh(); return err; }} />
      ) : (
        <div className="grid gap-2 text-[15px]">
          <p><b>By the end of the month, I can</b> {a.outcome}</p>
          {(a.plan_if || a.plan_then) && <p><b>Slot:</b> if {a.plan_if || "…"}, then I will {a.plan_then || "…"}.</p>}
          {a.why && <p className="text-ink-2"><b className="text-ink">Why now:</b> {a.why}</p>}
          {s && s.unknown_days > 0 && (
            <p className="text-sm text-ink-3">{s.unknown_days} day{s.unknown_days === 1 ? "" : "s"} this month with nothing logged at all. Those are unknown, not missed.</p>
          )}
          <p className="text-sm text-ink-3">Log a session from the Journal as the “{data.templates.habit.label}” habit, in {data.templates.habit.unit}.</p>
          <div className="flex flex-wrap gap-4 pt-1 text-sm">
            <button type="button" onClick={() => setEditing(true)} className="text-ink-2 underline underline-offset-2 hover:text-ink">Edit</button>
            <button type="button" onClick={() => setClosing((c) => !c)} className="text-ink-2 underline underline-offset-2 hover:text-ink">
              {closing ? "Keep going" : "Close this month"}
            </button>
          </div>
        </div>
      )}
      {closing && !editing && <CloseMonth focusId={a.id} onDone={refresh} />}
    </section>
  );
}
