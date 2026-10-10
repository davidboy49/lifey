"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { addDays, shortDay } from "@/lib/journal";

type Kind = "habit" | "quit" | "checkin" | "note";

const KINDS: { key: Kind; label: string }[] = [
  { key: "habit", label: "Habit" },
  { key: "quit", label: "Quit" },
  { key: "checkin", label: "Check-in" },
  { key: "note", label: "Note" },
];
const DEFAULT_HABITS = [
  { label: "Alcohol", unit: "drinks" }, { label: "Late caffeine", unit: "times" }, { label: "Late meal", unit: "times" },
  { label: "Late screen", unit: "times" }, { label: "Nicotine", unit: "times" }, { label: "High stress", unit: "times" },
];
const QUIT: { key: "slip" | "urge" | "clean"; label: string; hint: string }[] = [
  { key: "urge", label: "Urge resisted", hint: "A win. The streak is untouched." },
  { key: "clean", label: "Clean day", hint: "The nightly check-in." },
  { key: "slip", label: "Slip", hint: "Restarts the streak. Your best run is kept." },
];

function Seg<T extends string>({ value, options, onChange, label }: {
  value: T; options: { key: T; label: string }[]; onChange: (v: T) => void; label: string;
}) {
  return (
    <div role="group" aria-label={label} className="flex flex-wrap gap-1 rounded-xl border border-line bg-raised p-1">
      {options.map((o) => (
        <button
          key={o.key}
          type="button"
          aria-pressed={value === o.key}
          onClick={() => onChange(o.key)}
          className={`rounded-lg px-3 py-1.5 text-sm font-medium ${value === o.key ? "bg-accent-soft text-accent" : "text-ink-2 hover:text-ink"}`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

function Scale({ value, onChange, label }: { value: number | null; onChange: (v: number | null) => void; label: string }) {
  return (
    <div role="group" aria-label={label} className="flex gap-1.5">
      {[1, 2, 3, 4, 5].map((n) => (
        <button
          key={n}
          type="button"
          aria-pressed={value === n}
          onClick={() => onChange(value === n ? null : n)}
          className={`size-10 rounded-xl border text-sm font-semibold ${value === n ? "border-accent bg-accent-soft text-accent" : "border-line bg-raised text-ink-2 hover:text-ink"}`}
        >
          {n}
        </button>
      ))}
    </div>
  );
}

export function Composer({ today, nowTime, habits = DEFAULT_HABITS }: {
  today: string; nowTime: string; habits?: { label: string; unit: string }[];
}) {
  const router = useRouter();
  const [open, setOpen] = useState(true);
  const [kind, setKind] = useState<Kind>("habit");
  const [habit, setHabit] = useState(habits[0]?.label ?? "Alcohol");
  const [custom, setCustom] = useState("");
  const [amount, setAmount] = useState("1");
  const [action, setAction] = useState<"slip" | "urge" | "clean">("urge");
  const [mood, setMood] = useState<number | null>(null);
  const [energy, setEnergy] = useState<number | null>(null);
  const [note, setNote] = useState("");
  const [ago, setAgo] = useState<0 | 1 | 2 | "pick">(0);
  const [picked, setPicked] = useState(today);
  const [time, setTime] = useState(nowTime);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<{ text: string; ids: number[] } | null>(null);

  useEffect(() => {
    if (window.matchMedia("(max-width: 1023px)").matches) setOpen(false);
  }, []);

  const day = ago === "pick" ? picked : addDays(today, -ago);
  const isHabit = kind === "habit";
  const habitName = habit === "Custom" ? custom.trim() : habit;
  const unit = habits.find((h) => h.label === habit)?.unit ?? "times";
  const recalled = day < today;
  const hint = useMemo(
    () =>
      recalled
        ? `This is for ${shortDay(day)} at ${time}. It will be marked as recalled, since you are adding it later.`
        : `Saved as happening on ${shortDay(day)} at ${time}.`,
    [recalled, day, time],
  );

  function payload() {
    const base = { note: note.trim(), date: day, time };
    if (kind === "habit") return { kind, habit: habitName, amount: Number(amount) || 1, ...base };
    if (kind === "quit") return { kind, action, ...base };
    if (kind === "checkin") return { kind, mood, energy, ...base };
    return { kind, ...base };
  }

  function validate(): string | null {
    if (isHabit && !habitName) return "Name the habit first.";
    if (kind === "note" && !note.trim()) return "Write the note first.";
    if (kind === "checkin" && mood === null && energy === null) return "Pick a mood or an energy level.";
    if (day > today) return "That date is in the future.";
    return null;
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const problem = validate();
    if (problem) return setError(problem);
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/journal", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(payload()),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(typeof body.detail === "string" ? body.detail : "Couldn’t save that entry. Check the fields and try again.");
        return;
      }
      const label = kind === "habit" ? habitName : kind === "quit" ? QUIT.find((q) => q.key === action)!.label : kind === "checkin" ? "Check-in" : "Note";
      setSaved({ text: `Saved ${label} for ${shortDay(body.date)} at ${body.time}.`, ids: body.ids });
      setNote("");
      setMood(null);
      setEnergy(null);
      router.refresh();
    } catch {
      setError("Couldn’t reach the server. Nothing was saved.");
    } finally {
      setBusy(false);
    }
  }

  async function undo() {
    if (!saved) return;
    await Promise.all(saved.ids.map((id) => fetch(`/api/journal/${id}`, { method: "DELETE" })));
    setSaved(null);
    router.refresh();
  }

  const field = "w-full rounded-xl border border-line bg-panel px-3.5 py-2.5 text-[15px] text-ink outline-none focus:border-accent";

  return (
    <aside className="card lg:sticky lg:top-6">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex w-full items-center justify-between px-5 py-4 text-left lg:pointer-events-none"
      >
        <span className="font-display text-xl font-semibold">New entry</span>
        <span className="font-mono text-xs text-ink-3 lg:hidden">{open ? "Hide" : "Show"}</span>
      </button>

      {open && (
        <form onSubmit={submit} className="grid gap-4 px-5 pb-5">
          <Seg label="Entry type" value={kind} options={KINDS} onChange={(k) => { setKind(k); setError(null); }} />

          {kind === "habit" && (
            <>
              <div className="flex flex-wrap gap-2" role="group" aria-label="Habit">
                {[...habits.map((x) => x.label), "Custom"].map((h) => (
                  <button
                    key={h}
                    type="button"
                    aria-pressed={habit === h}
                    onClick={() => setHabit(h)}
                    className={`rounded-full border px-3 py-1.5 text-sm font-medium ${habit === h ? "border-accent bg-accent-soft text-accent" : "border-line bg-raised text-ink-2 hover:text-ink"}`}
                  >
                    {h}
                  </button>
                ))}
              </div>
              {habit === "Custom" && (
                <input className={field} value={custom} onChange={(e) => setCustom(e.target.value)} placeholder="e.g. sauna, cold plunge, fasting" aria-label="Habit name" maxLength={48} />
              )}
              <label className="grid gap-1.5 text-sm font-medium" htmlFor="amount">
                How much ({unit})
                <input id="amount" type="number" inputMode="decimal" min="0.5" step="0.5" className={field} value={amount} onChange={(e) => setAmount(e.target.value)} />
              </label>
            </>
          )}

          {kind === "quit" && (
            <div className="grid gap-2" role="radiogroup" aria-label="What happened">
              {QUIT.map((q) => (
                <button
                  key={q.key}
                  type="button"
                  role="radio"
                  aria-checked={action === q.key}
                  onClick={() => setAction(q.key)}
                  className={`rounded-xl border px-3.5 py-2.5 text-left ${action === q.key ? "border-accent bg-accent-soft" : "border-line bg-raised"}`}
                >
                  <span className="block text-sm font-semibold">{q.label}</span>
                  <span className="block text-[13px] text-ink-2">{q.hint}</span>
                </button>
              ))}
            </div>
          )}

          {kind === "checkin" && (
            <div className="grid gap-3">
              <div className="grid gap-1.5"><span className="text-sm font-medium">Mood · 1 low, 5 great</span><Scale label="Mood" value={mood} onChange={setMood} /></div>
              <div className="grid gap-1.5"><span className="text-sm font-medium">Energy · 1 drained, 5 full</span><Scale label="Energy" value={energy} onChange={setEnergy} /></div>
            </div>
          )}

          <div className="grid gap-2">
            <span className="text-sm font-medium">When did it happen?</span>
            <div className="flex flex-wrap gap-2" role="group" aria-label="Day">
              {([[0, "Today"], [1, "Yesterday"], [2, "2 days ago"], ["pick", "Pick a date"]] as const).map(([v, label]) => (
                <button
                  key={String(v)}
                  type="button"
                  aria-pressed={ago === v}
                  onClick={() => setAgo(v)}
                  className={`rounded-full border px-3 py-1.5 text-sm font-medium ${ago === v ? "border-accent bg-accent-soft text-accent" : "border-line bg-raised text-ink-2 hover:text-ink"}`}
                >
                  {label}
                </button>
              ))}
            </div>
            <div className="grid grid-cols-[1fr_130px] gap-2">
              <input
                type="date"
                aria-label="Date"
                className={field}
                value={day}
                max={today}
                onChange={(e) => { if (e.target.value) { setPicked(e.target.value); setAgo("pick"); } }}
              />
              <input type="time" aria-label="Time it happened" className={field} value={time} onChange={(e) => setTime(e.target.value)} />
            </div>
            <p className={`rounded-xl border px-3 py-2 text-[13px] ${recalled ? "border-transparent bg-watch-soft text-watch" : "border-line bg-panel text-ink-2"}`}>{hint}</p>
          </div>

          <label className="grid gap-1.5 text-sm font-medium" htmlFor="note">
            {kind === "note" ? "Note" : "Note (optional)"}
            <textarea
              id="note"
              className={`${field} min-h-[88px] resize-y font-normal`}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              maxLength={2000}
              placeholder={kind === "note" ? "Write it down while you remember it" : "Anything you want to remember about it"}
            />
          </label>

          <p role="alert" aria-live="polite" className={error ? "rounded-xl bg-alert-soft px-3.5 py-2.5 text-sm text-alert" : "sr-only"}>{error}</p>

          <button
            type="submit"
            disabled={busy}
            className="rounded-xl bg-accent px-5 py-3 font-medium text-ground transition-opacity hover:opacity-90 disabled:cursor-wait disabled:opacity-60"
          >
            {busy ? "Saving…" : "Save entry"}
          </button>

          {saved && (
            <p className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-good-soft px-3.5 py-2.5 text-sm font-medium text-good" role="status">
              <span>{saved.text}</span>
              <button type="button" onClick={undo} className="underline underline-offset-2">Undo</button>
            </p>
          )}
        </form>
      )}
    </aside>
  );
}
