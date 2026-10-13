"use client";

import { useState } from "react";

interface Reminder {
  key: string;
  label: string;
  enabled: boolean;
  time: string;
}

const HELP: Record<string, string> = {
  morning_feeling: "One message asking how you woke up. Best sent before you look at your watch.",
  evening_checkin: "Four quick questions about the day: alcohol, caffeine, late meal, workout effort.",
};

export function ReminderSettings({ initial, timezone }: { initial: Reminder[]; timezone: string }) {
  const [items, setItems] = useState(initial);
  const [saving, setSaving] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function save(key: string, patch: Partial<Pick<Reminder, "enabled" | "time">>) {
    setSaving(key);
    setError(null);
    setMessage(null);
    try {
      const r = await fetch("/api/settings/reminders", {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ [key]: patch }),
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) return setError(typeof body.detail === "string" ? body.detail : "Couldn’t save that.");
      setItems(body.reminders);
      setMessage("Saved. The bot picks this up within a minute.");
    } catch {
      setError("Couldn’t reach the server.");
    } finally {
      setSaving(null);
    }
  }

  function edit(key: string, time: string) {
    setItems((all) => all.map((i) => (i.key === key ? { ...i, time } : i)));
  }

  return (
    <div className="grid gap-4">
      {items.map((it) => (
        <section key={it.key} className="card grid gap-3 p-5 sm:p-6">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="max-w-[46ch]">
              <h2 className="font-display text-xl font-semibold">{it.label}</h2>
              <p className="mt-1 text-sm text-ink-2">{HELP[it.key]}</p>
            </div>
            <label className="flex cursor-pointer items-center gap-2 text-sm font-medium">
              <input
                type="checkbox"
                checked={it.enabled}
                disabled={saving === it.key}
                onChange={(e) => save(it.key, { enabled: e.target.checked })}
                className="size-5 accent-accent"
              />
              {it.enabled ? "On" : "Off"}
            </label>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <label htmlFor={`t-${it.key}`} className="text-sm text-ink-2">Send at</label>
            <input
              id={`t-${it.key}`}
              type="time"
              value={it.time}
              disabled={!it.enabled}
              onChange={(e) => edit(it.key, e.target.value)}
              className="rounded-xl border border-line bg-panel px-3 py-2 text-[15px] text-ink outline-none focus:border-accent disabled:opacity-50"
            />
            <button
              type="button"
              disabled={!it.enabled || saving === it.key || !it.time}
              onClick={() => save(it.key, { time: it.time })}
              className="rounded-xl bg-accent px-4 py-2 text-sm font-medium text-ground hover:opacity-90 disabled:opacity-50"
            >
              Save time
            </button>
          </div>
        </section>
      ))}
      <p role="status" aria-live="polite" className={`min-h-5 text-sm ${error ? "text-alert" : "text-ink-2"}`}>
        {error ?? message ?? `Times are in ${timezone}. If the bot was offline it catches up for up to 3 hours, then skips the day.`}
      </p>
    </div>
  );
}
