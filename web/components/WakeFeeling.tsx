"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

const FACES = [
  { n: 1, icon: "😫", name: "Awful" },
  { n: 2, icon: "😕", name: "Rough" },
  { n: 3, icon: "😐", name: "Okay" },
  { n: 4, icon: "🙂", name: "Good" },
  { n: 5, icon: "😄", name: "Great" },
];

// Rate how you woke up. The date can be a past day, for the mornings you forgot.
export function WakeFeeling({ today, ratings }: { today: string; ratings: Record<string, number> }) {
  const router = useRouter();
  const [day, setDay] = useState(today);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const current = ratings[day] ?? null;

  async function rate(n: number) {
    setBusy(true);
    setError(null);
    setSaved(null);
    try {
      const r = await fetch("/api/habits/feeling", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ rating: n, date: day }),
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) return setError(typeof body.detail === "string" ? body.detail : "Couldn’t save that.");
      setSaved(`${FACES[n - 1].icon} ${FACES[n - 1].name} saved for ${day}.`);
      router.refresh();
    } catch {
      setError("Couldn’t reach the server.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <label className="text-sm text-ink-2" htmlFor="wake-day">Morning of</label>
        <input
          id="wake-day"
          type="date"
          value={day}
          max={today}
          onChange={(e) => setDay(e.target.value || today)}
          className="rounded-xl border border-line bg-panel px-3 py-2 text-[15px] text-ink outline-none focus:border-accent"
        />
      </div>
      <div className="grid grid-cols-5 gap-2" role="group" aria-label="How did you wake up?">
        {FACES.map((f) => (
          <button
            key={f.n}
            type="button"
            disabled={busy}
            onClick={() => rate(f.n)}
            aria-pressed={current === f.n}
            className={`grid justify-items-center gap-1 rounded-xl border px-2 py-3 text-sm font-medium transition-colors disabled:opacity-60 ${
              current === f.n ? "border-accent bg-accent-soft text-accent" : "border-line bg-panel text-ink-2 hover:border-accent"
            }`}
          >
            <span className="text-2xl" aria-hidden>{f.icon}</span>
            <span>{f.name}</span>
          </button>
        ))}
      </div>
      <p role="status" aria-live="polite" className={`min-h-5 text-sm ${error ? "text-alert" : "text-ink-2"}`}>
        {error ?? saved ?? (current ? `Rated ${current}/5 for this day. Tap another to change it.` : "Not rated for this day.")}
      </p>
    </div>
  );
}
