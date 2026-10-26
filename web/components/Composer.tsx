"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { addDays, shortDay } from "@/lib/journal";

type Kind = "habit" | "quit" | "checkin" | "note";

const MAX_FILE = 10 * 1024 * 1024;
const MAX_FILES = 6;
const NOTE_MAX = 2000;          // same limit as the API; never trim silently
const UPLOAD_TIMEOUT_MS = 120_000;
const ACCEPT = "image/jpeg,image/png,image/webp,application/pdf";

/** A readable reason for a failed request, whatever the server (or a proxy in front of it) answered. */
function describeFailure(res: Response, body: { detail?: unknown }): string {
  if (typeof body.detail === "string") return body.detail;
  if (Array.isArray(body.detail) && body.detail.length) {
    const first = body.detail[0] as { msg?: string };
    if (first?.msg) return first.msg.replace(/^Value error, /, "");
  }
  if (res.status === 413) return "That upload is bigger than the server accepts (about 12 MB). Nothing was saved.";
  if (res.status === 401) return "Your session has ended. Sign in again, then retry. Nothing was saved.";
  if (res.status >= 500) return "The server had a problem. Nothing was saved. Try again in a moment.";
  return "Couldn’t save that entry. Check the fields and try again.";
}

function fileSize(bytes: number): string {
  return bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

const KINDS: { key: Kind; label: string }[] = [
  { key: "note", label: "Note" },
  { key: "habit", label: "Bad habit" },
  { key: "quit", label: "Quit" },
  { key: "checkin", label: "Check-in" },
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
  const [kind, setKind] = useState<Kind>("note");
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
  const [files, setFiles] = useState<File[]>([]);
  const picker = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<{ text: string; ids: number[] } | null>(null);
  const alertRef = useRef<HTMLParagraphElement>(null);

  useEffect(() => {
    if (window.matchMedia("(max-width: 1023px)").matches) setOpen(false);
  }, []);

  // A failure must never hide below the fold or behind a long form.
  useEffect(() => {
    if (error) alertRef.current?.scrollIntoView({ block: "nearest" });   // instant: reliable, and respects reduced motion
  }, [error]);

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
    if (isHabit && !habitName) return "Name the bad habit first.";
    if (kind === "note" && !note.trim() && files.length === 0) return "Write the note first, or attach a file.";
    if (kind === "checkin" && mood === null && energy === null) return "Pick a mood or an energy level.";
    if (day > today) return "That date is in the future.";
    if (note.trim().length > NOTE_MAX) {
      return `Your note is ${note.trim().length} characters; the limit is ${NOTE_MAX}. Shorten it by ${note.trim().length - NOTE_MAX}. Nothing was cut.`;
    }
    return null;
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const problem = validate();
    if (problem) return setError(problem);
    setBusy(true);
    setError(null);
    const timer = new AbortController();
    const timeout = setTimeout(() => timer.abort(), UPLOAD_TIMEOUT_MS);
    try {
      const withFiles = kind === "note" && files.length > 0;
      let res: Response;
      if (withFiles) {
        const form = new FormData();
        form.append("files", files[0]);
        form.append("note", note.trim());
        form.append("date", day);
        form.append("time", time);
        res = await fetch("/api/attachments", { method: "POST", body: form, signal: timer.signal });
      } else {
        res = await fetch("/api/journal", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(payload()),
          signal: timer.signal,
        });
      }
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(describeFailure(res, body));
        return;
      }
      let extraProblem: string | null = null;
      if (withFiles && files.length > 1) {
        // One request per extra file keeps each upload under the server's body limit.
        for (const f of files.slice(1)) {
          const form = new FormData();
          form.append("files", f);
          const more = await fetch(`/api/attachments/${body.ids[0]}`, { method: "POST", body: form, signal: timer.signal });
          if (!more.ok) {
            const b = await more.json().catch(() => ({}));
            extraProblem = `${f.name}: ${describeFailure(more, b)}`;
          }
        }
      }
      if (extraProblem) setError(extraProblem);
      const label = kind === "habit" ? habitName : kind === "quit" ? QUIT.find((q) => q.key === action)!.label : kind === "checkin" ? "Check-in" : "Note";
      setSaved({ text: `Saved ${label} for ${shortDay(body.date)} at ${body.time}.`, ids: body.ids });
      setNote("");
      setFiles([]);
      if (picker.current) picker.current.value = "";
      setMood(null);
      setEnergy(null);
      router.refresh();
    } catch (err) {
      setError(
        err instanceof DOMException && err.name === "AbortError"
          ? "The upload took too long and was stopped. Check your connection. The entry may not have been saved."
          : "Couldn’t reach the server. Nothing was saved.",
      );
    } finally {
      clearTimeout(timeout);
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
        <form onSubmit={submit} className="grid gap-4 px-5 pb-5 [&>*]:min-w-0">
          <Seg label="Entry type" value={kind} options={KINDS} onChange={(k) => { setKind(k); setError(null); }} />

          {kind === "habit" && (
            <>
              <div className="flex flex-wrap gap-2" role="group" aria-label="Bad habit">
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
                <input className={field} value={custom} onChange={(e) => setCustom(e.target.value)} placeholder="e.g. doomscrolling, energy drink, night snacking" aria-label="Bad habit name" maxLength={48} />
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
              aria-describedby="note-count"
              placeholder={kind === "note" ? "Write it down while you remember it" : "Anything you want to remember about it"}
            />
          </label>

          {note.length > NOTE_MAX * 0.8 && (
            <p id="note-count" aria-live="polite" className={`-mt-2 text-right font-mono text-xs ${note.trim().length > NOTE_MAX ? "text-alert" : "text-ink-3"}`}>
              {note.trim().length} / {NOTE_MAX}
            </p>
          )}

          {kind === "note" && (
            <div className="grid min-w-0 gap-2">
              <input
                ref={picker}
                type="file"
                multiple
                accept={ACCEPT}
                className="sr-only"
                id="attach"
                onChange={(e) => {
                  const picked = Array.from(e.target.files ?? []);
                  const tooBig = picked.find((f) => f.size > MAX_FILE);
                  if (tooBig) {
                    setError(`${tooBig.name} is larger than 10 MB.`);
                    e.target.value = "";
                    return;
                  }
                  setError(null);
                  setFiles((prev) => [...prev, ...picked].slice(0, MAX_FILES));
                  e.target.value = "";
                }}
              />
              <label
                htmlFor="attach"
                className="inline-flex w-fit cursor-pointer items-center gap-2 rounded-xl border border-line bg-raised px-3.5 py-2 text-sm font-medium text-ink-2 hover:text-ink"
              >
                <svg viewBox="0 0 24 24" width={18} height={18} fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                  <path d="m21 11-8.6 8.6a5 5 0 0 1-7-7l9-9a3.5 3.5 0 0 1 5 5l-9 9a2 2 0 0 1-3-3l8-8" />
                </svg>
                Attach photo or PDF
              </label>
              {files.length > 0 && (
                <ul className="grid min-w-0 gap-1.5" aria-label="Attached files">
                  {files.map((f, i) => (
                    <li key={`${f.name}-${i}`} className="flex min-w-0 items-center justify-between gap-2 rounded-xl border border-line bg-panel px-3 py-2 text-sm">
                      <span className="min-w-0 flex-1 truncate" title={f.name}>{f.name}</span>
                      <span className="shrink-0 text-ink-3">{fileSize(f.size)}</span>
                      <button
                        type="button"
                        onClick={() => setFiles((all) => all.filter((_, j) => j !== i))}
                        aria-label={`Remove ${f.name}`}
                        className="shrink-0 text-ink-3 hover:text-alert"
                      >
                        Remove
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              <p className="text-xs text-ink-3">Photos and PDFs, up to 10 MB each. Location data is removed from photos.</p>
            </div>
          )}

          <p ref={alertRef} role="alert" aria-live="polite" className={error ? "break-words rounded-xl bg-alert-soft px-3.5 py-2.5 text-sm text-alert" : "sr-only"}>{error}</p>

          <button
            type="submit"
            disabled={busy}
            className="rounded-xl bg-accent px-5 py-3 font-medium text-ground transition-opacity hover:opacity-90 disabled:cursor-wait disabled:opacity-60"
          >
            {busy ? (files.length > 0 && kind === "note" ? "Uploading…" : "Saving…") : "Save entry"}
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
