"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { CatalogHabit } from "@/lib/habits";

const field = "w-full rounded-xl border border-line bg-panel px-3.5 py-2.5 text-[15px] text-ink outline-none focus:border-accent";

export function HabitManager({ habits }: { habits: CatalogHabit[] }) {
  const router = useRouter();
  const custom = habits.filter((h) => !h.builtin);
  const [label, setLabel] = useState("");
  const [unit, setUnit] = useState("times");
  const [cueIf, setCueIf] = useState("");
  const [cueThen, setCueThen] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    if (!label.trim()) return setError("Give the habit a name.");
    setBusy(true);
    setError(null);
    try {
      const r = await fetch("/api/habits", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ label, unit: unit || "times", cue_if: cueIf || null, cue_then: cueThen || null }),
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) return setError(typeof body.detail === "string" ? body.detail : "Couldn’t add that habit.");
      setLabel(""); setCueIf(""); setCueThen(""); setUnit("times");
      router.refresh();
    } catch {
      setError("Couldn’t reach the server.");
    } finally {
      setBusy(false);
    }
  }

  async function archive(tag: string) {
    await fetch(`/api/habits/${tag}`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ archived: true }),
    });
    router.refresh();
  }

  return (
    <section className="card grid gap-5 p-5 sm:p-6">
      <div>
        <h2 className="font-display text-xl font-semibold">Your habits</h2>
        <p className="mt-1 max-w-[62ch] text-sm text-ink-2">
          The built-in list covers sleep disruptors. Add anything else you want to watch. A cue is optional: say when it tends to happen
          and what you would do instead, and it appears in your weekly review.
        </p>
      </div>

      {custom.length > 0 && (
        <ul className="grid gap-2">
          {custom.map((h) => (
            <li key={h.tag} className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-line bg-raised px-4 py-3">
              <div className="min-w-0">
                <p className="font-medium">{h.label} <span className="text-sm font-normal text-ink-3">· {h.unit}</span></p>
                {(h.cue_if || h.cue_then) && (
                  <p className="text-sm text-ink-2">If {h.cue_if || "…"}, then {h.cue_then || "…"}</p>
                )}
              </div>
              <button type="button" onClick={() => archive(h.tag)} className="text-sm text-ink-3 underline underline-offset-2 hover:text-alert">
                Archive
              </button>
            </li>
          ))}
        </ul>
      )}

      <form onSubmit={add} className="grid gap-3 sm:grid-cols-2">
        <label className="grid gap-1.5 text-sm font-medium" htmlFor="h-label">
          Name
          <input id="h-label" className={field} value={label} onChange={(e) => setLabel(e.target.value)} placeholder="e.g. Cold plunge" maxLength={48} />
        </label>
        <label className="grid gap-1.5 text-sm font-medium" htmlFor="h-unit">
          Counted in
          <input id="h-unit" className={field} value={unit} onChange={(e) => setUnit(e.target.value)} placeholder="times" maxLength={24} />
        </label>
        <label className="grid gap-1.5 text-sm font-medium" htmlFor="h-if">
          When this tends to happen (optional)
          <input id="h-if" className={field} value={cueIf} onChange={(e) => setCueIf(e.target.value)} placeholder="I wake up tired" maxLength={200} />
        </label>
        <label className="grid gap-1.5 text-sm font-medium" htmlFor="h-then">
          What I will do (optional)
          <input id="h-then" className={field} value={cueThen} onChange={(e) => setCueThen(e.target.value)} placeholder="have water and stretch" maxLength={200} />
        </label>
        <div className="flex flex-wrap items-center gap-3 sm:col-span-2">
          <button type="submit" disabled={busy} className="rounded-xl bg-accent px-5 py-2.5 font-medium text-ground hover:opacity-90 disabled:opacity-60">
            {busy ? "Adding…" : "Add habit"}
          </button>
          <p role="alert" className={error ? "text-sm text-alert" : "sr-only"}>{error}</p>
        </div>
      </form>
    </section>
  );
}
