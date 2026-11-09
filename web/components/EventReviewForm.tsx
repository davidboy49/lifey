"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { DayDataPanel } from "./DayData";
import { errorText, LOOP_TAGS, localToday, type EventReview, type LoopTag, type ReviewPhoto } from "@/lib/eventReviews";

const field = "w-full rounded-xl border border-line bg-panel px-3.5 py-2.5 text-[16px] text-ink outline-none focus:border-accent";

function Scale({ value, onChange, label, low, high }: {
  value: number | null; onChange: (v: number | null) => void; label: string; low: string; high: string;
}) {
  return (
    <div className="grid gap-1.5">
      <span className="font-semibold">{label}</span>
      <div role="group" aria-label={label} className="grid grid-cols-5 gap-2 sm:max-w-[340px]">
        {[1, 2, 3, 4, 5].map((n) => (
          <button
            key={n}
            type="button"
            aria-pressed={value === n}
            onClick={() => onChange(value === n ? null : n)}
            className={`h-12 rounded-xl border text-[17px] font-semibold ${value === n ? "border-accent bg-accent-soft text-accent" : "border-line bg-raised text-ink-2 hover:text-ink"}`}
          >
            {n}
          </button>
        ))}
      </div>
      <div className="flex justify-between text-[12px] text-ink-3 sm:max-w-[340px]"><span>{low}</span><span>{high}</span></div>
    </div>
  );
}

function Box({ id, label, value, onChange, hint, max = 2000 }: {
  id: string; label: string; value: string; onChange: (v: string) => void; hint?: string; max?: number;
}) {
  return (
    <label className="grid gap-1.5" htmlFor={id}>
      <span className="font-semibold">{label}</span>
      <textarea id={id} className={`${field} min-h-[76px] resize-y`} value={value} onChange={(e) => onChange(e.target.value)}
        placeholder={hint} maxLength={max} rows={2} />
    </label>
  );
}

type Form = {
  date: string; event: string; mood: number | null; energy: number | null; notes: string; went_well: string;
  would_change: string; loop_tags: LoopTag[]; lesson: string;
};

/** New review when `initial` is absent; otherwise edits it in place. */
export function EventReviewForm({ initial, onSaved, onCancel }: {
  initial?: EventReview; onSaved?: (r: EventReview) => void; onCancel?: () => void;
}) {
  const router = useRouter();
  const today = localToday();
  const [form, setForm] = useState<Form>({
    date: initial?.date ?? today,
    event: initial?.event ?? "",
    mood: initial?.mood ?? null,
    energy: initial?.energy ?? null,
    notes: initial?.notes ?? "",
    went_well: initial?.went_well ?? "",
    would_change: initial?.would_change ?? "",
    loop_tags: initial?.loop_tags ?? [],
    lesson: initial?.lesson ?? "",
  });
  const [photos, setPhotos] = useState<ReviewPhoto[]>(initial?.photos ?? []);
  const [files, setFiles] = useState<File[]>([]);
  const [state, setState] = useState<"idle" | "saving" | "error">("idle");
  const [message, setMessage] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);

  function set<K extends keyof Form>(k: K, v: Form[K]) {
    setForm((f) => ({ ...f, [k]: v }));
    if (state === "error") setState("idle");
  }

  function toggle(tag: LoopTag) {
    set("loop_tags", form.loop_tags.includes(tag) ? form.loop_tags.filter((t) => t !== tag) : [...form.loop_tags, tag]);
  }

  async function removePhoto(id: number) {
    const r = await fetch(`/api/event-reviews/photos/${id}`, { method: "DELETE" });
    if (r.ok || r.status === 404) setPhotos((p) => p.filter((x) => x.id !== id));
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!form.event.trim()) { setState("error"); setMessage("Name the event."); return; }
    setState("saving");
    setMessage("");
    try {
      const r = await fetch(initial ? `/api/event-reviews/${initial.id}` : "/api/event-reviews", {
        method: initial ? "PUT" : "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(form),
      });
      if (!r.ok) throw new Error(await errorText(r, "Couldn’t save. Your text is still here; try again."));
      const saved = (await r.json()) as EventReview;
      let problems: string[] = [];
      if (files.length) {
        const body = new FormData();
        files.forEach((f) => body.append("files", f));
        const up = await fetch(`/api/event-reviews/${saved.id}/photos`, { method: "POST", body });
        if (up.ok) {
          const res = (await up.json()) as { photos: ReviewPhoto[]; problems: string[] };
          saved.photos = [...photos, ...res.photos];
          problems = res.problems;
        } else {
          saved.photos = photos;
          problems = [await errorText(up, "The photos couldn’t be added.")];
        }
      } else {
        saved.photos = photos;
      }
      setFiles([]);
      if (problems.length) {
        // The review itself is saved; say what happened to the photos and stay on it.
        setState("error");
        setMessage(`Review saved. ${problems.join(" ")}`);
        if (!initial) { router.replace(`/reviews/${saved.id}`); router.refresh(); }
        else { setPhotos(saved.photos); onSaved?.(saved); }
        return;
      }
      setState("idle");
      if (onSaved) onSaved(saved);
      else { router.push(`/reviews/${saved.id}`); router.refresh(); }
    } catch (err) {
      setState("error");
      setMessage(err instanceof Error && err.message ? err.message : "Couldn’t save. Your text is still here; try again.");
    }
  }

  return (
    <form onSubmit={submit} className="grid gap-7">
      <section className="grid gap-3" aria-labelledby="er-event">
        <h2 id="er-event" className="eyebrow">Event</h2>
        <div className="grid gap-3 sm:grid-cols-[1fr_180px]">
          <label className="grid gap-1.5" htmlFor="er-name">
            <span className="font-semibold">What was it?</span>
            <input id="er-name" className={field} value={form.event} onChange={(e) => set("event", e.target.value)}
              placeholder="10 km race, night out…" maxLength={120} required autoComplete="off" enterKeyHint="next" />
          </label>
          <label className="grid gap-1.5" htmlFor="er-date">
            <span className="font-semibold">Date</span>
            <input id="er-date" type="date" className={field} value={form.date} max={today}
              onChange={(e) => set("date", e.target.value)} required />
          </label>
        </div>
      </section>

      <section className="card grid gap-3 p-4" aria-labelledby="er-day">
        <h2 id="er-day" className="eyebrow">That day’s data</h2>
        <DayDataPanel date={form.date} />
      </section>

      <section className="grid gap-4" aria-labelledby="er-how">
        <h2 id="er-how" className="eyebrow">How it went</h2>
        <Scale label="Mood" value={form.mood} onChange={(v) => set("mood", v)} low="Low" high="Great" />
        <Scale label="Energy" value={form.energy} onChange={(v) => set("energy", v)} low="Drained" high="Full" />
        <Box id="er-notes" label="Notes" value={form.notes} onChange={(v) => set("notes", v)} hint="A line or two." />
      </section>

      <Box id="er-well" label="What went well" value={form.went_well} onChange={(v) => set("went_well", v)} />
      <Box id="er-change" label="What I’d change" value={form.would_change} onChange={(v) => set("would_change", v)} />

      <fieldset className="grid gap-2">
        <legend className="mb-2 font-semibold">Loop check</legend>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {LOOP_TAGS.map(({ tag, label }) => {
            const on = form.loop_tags.includes(tag);
            return (
              <label key={tag} className={`flex min-h-12 cursor-pointer items-center gap-3 rounded-xl border px-3.5 text-[15px] font-medium ${on ? "border-accent bg-accent-soft text-accent" : "border-line bg-raised text-ink-2"}`}>
                <input type="checkbox" checked={on} onChange={() => toggle(tag)} className="size-5 accent-[var(--accent)]" />
                {label}
              </label>
            );
          })}
        </div>
      </fieldset>

      <label className="grid gap-1.5" htmlFor="er-lesson">
        <span className="font-semibold">Lesson</span>
        <input id="er-lesson" className={field} value={form.lesson} onChange={(e) => set("lesson", e.target.value)}
          placeholder="One line to carry forward" maxLength={200} autoComplete="off" />
      </label>

      <section className="grid gap-3" aria-labelledby="er-photos">
        <h2 id="er-photos" className="eyebrow">Photos (optional)</h2>
        {photos.length > 0 && (
          <ul className="grid grid-cols-3 gap-2 sm:grid-cols-4">
            {photos.map((p) => (
              <li key={p.id} className="relative overflow-hidden rounded-xl border border-line bg-panel">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={`/api/event-reviews/photos/${p.id}/thumb`} alt={p.filename} className="block aspect-square w-full object-cover" />
                <button type="button" onClick={() => removePhoto(p.id)} aria-label={`Remove ${p.filename}`}
                  className="absolute right-1 top-1 rounded-lg bg-ink/70 px-2 py-1 text-[12px] font-medium text-ground">
                  Remove
                </button>
              </li>
            ))}
          </ul>
        )}
        <input ref={fileInput} type="file" accept="image/jpeg,image/png,image/webp" multiple className="hidden"
          onChange={(e) => setFiles(Array.from(e.target.files ?? []))} />
        <div className="flex flex-wrap items-center gap-3">
          <button type="button" onClick={() => fileInput.current?.click()}
            className="rounded-xl border border-line bg-raised px-4 py-2.5 text-[15px] font-medium text-ink-2 hover:text-ink">
            {files.length ? "Choose other photos" : "Add photos"}
          </button>
          {files.length > 0 && (
            <span className="text-sm text-ink-2">{files.length} photo{files.length === 1 ? "" : "s"} will be added when you save.</span>
          )}
        </div>
      </section>

      <div className="flex flex-wrap items-center gap-3">
        <button type="submit" disabled={state === "saving"}
          className="rounded-xl bg-accent px-6 py-3 font-medium text-ground hover:opacity-90 disabled:opacity-60">
          {state === "saving" ? "Saving…" : initial ? "Save changes" : "Save review"}
        </button>
        {onCancel && (
          <button type="button" onClick={onCancel} className="rounded-xl px-4 py-3 font-medium text-ink-2 hover:text-ink">Cancel</button>
        )}
        <p role="status" aria-live="polite" className={`text-sm ${state === "error" ? "text-alert" : "text-ink-3"}`}>{message}</p>
      </div>
    </form>
  );
}
