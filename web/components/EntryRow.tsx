"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { JournalEntry } from "@/lib/journal";

export function EntryRow({ entry }: { entry: JournalEntry }) {
  const router = useRouter();
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);

  async function remove() {
    setBusy(true);
    setFailed(false);
    try {
      const results = await Promise.all(entry.ids.map((id) => fetch(`/api/journal/${id}`, { method: "DELETE" })));
      // 404 means it was already gone, which is the outcome we wanted.
      if (results.some((r) => !r.ok && r.status !== 404)) throw new Error("delete failed");
      router.refresh();
    } catch {
      setFailed(true);
      setBusy(false);
    }
  }

  return (
    <li className={`kind-${entry.kind} grid grid-cols-[48px_1fr_auto] gap-3 rounded-2xl border border-line bg-raised px-4 py-3`}>
      <span
        className={`pt-0.5 font-mono text-[12.5px] ${entry.time_recorded ? "text-ink-2" : "text-ink-3 italic"}`}
        title={entry.time_recorded ? "Time it happened" : "Time it was saved"}
      >
        {entry.time || "·"}
      </span>

      <div className="grid min-w-0 gap-1">
        <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
          <span className="kind-dot size-2 rounded-full" aria-hidden />
          <span className="font-semibold">{entry.title}</span>
          {entry.badges.map((b) => (
            <span key={b} className="kind-badge rounded-full px-2 py-0.5 text-xs font-semibold">{b}</span>
          ))}
          {entry.subtitle && <span className="text-xs text-ink-3">{entry.subtitle}</span>}
          {entry.recalled && (
            <span className="rounded-full bg-watch-soft px-2 py-0.5 font-mono text-[11px] text-watch" title="Added on a later day than it happened">
              recalled
            </span>
          )}
        </div>
        {entry.note && <p className="whitespace-pre-wrap text-[14.5px] text-ink-2">{entry.note}</p>}
        {failed && <p className="text-sm text-alert">Couldn’t remove that. Try again.</p>}
      </div>

      <div className="flex items-start">
        {confirming ? (
          <span className="flex items-center gap-2 text-sm">
            <button type="button" onClick={remove} disabled={busy} className="font-medium text-alert underline underline-offset-2 disabled:opacity-60">
              {busy ? "Removing…" : "Remove"}
            </button>
            <button type="button" onClick={() => setConfirming(false)} className="text-ink-3">Keep</button>
          </span>
        ) : (
          <button
            type="button"
            onClick={() => setConfirming(true)}
            aria-label={`Remove ${entry.title}`}
            className="rounded-lg p-1 text-ink-3 hover:bg-panel hover:text-alert"
          >
            <svg viewBox="0 0 24 24" width={18} height={18} fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
              <path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3" />
            </svg>
          </button>
        )}
      </div>
    </li>
  );
}
