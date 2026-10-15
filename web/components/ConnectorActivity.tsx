"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { ConnectorActivityRow } from "@/lib/learning";

function when(iso: string): string {
  return new Date(iso).toLocaleString("en-GB", {
    day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: "Asia/Phnom_Penh",
  });
}

/** What the Claude connector wrote, newest first, with undo for sessions and pending suggestions. */
export function ConnectorActivity({ rows }: { rows: ConnectorActivityRow[] }) {
  const router = useRouter();
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function undo(id: number) {
    setBusy(id);
    setError(null);
    try {
      const res = await fetch(`/api/connector/activity/${id}/undo`, { method: "POST" });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        return setError(typeof body.detail === "string" ? body.detail : "Couldn’t undo that.");
      }
      router.refresh();
    } catch {
      setError("Couldn’t reach the server.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="card grid gap-4 p-5 sm:p-6" aria-labelledby="ca-h">
      <div>
        <h2 id="ca-h" className="font-display text-xl font-semibold">Claude connector activity</h2>
        <p className="mt-1 max-w-[62ch] text-sm text-ink-2">
          Everything Claude wrote through the connector. It can log learning sessions and suggest studies, a focus
          or a quest; it cannot edit or delete anything else. To change what it may do, reconnect Lifey in Claude and
          choose on the sign-in page.
        </p>
      </div>
      {error && <p role="alert" className="rounded-xl bg-alert-soft px-3.5 py-2.5 text-sm text-alert">{error}</p>}
      {rows.length === 0 ? (
        <p className="text-sm text-ink-3">Nothing yet.</p>
      ) : (
        <ul className="grid divide-y divide-line">
          {rows.map((r) => (
            <li key={r.id} className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 py-2.5">
              <div className="min-w-0">
                <p className={`text-[15px] ${r.undone_at || r.outcome === "refused" ? "text-ink-3 line-through" : ""}`}>{r.summary}</p>
                <p className="font-mono text-[11px] text-ink-3">
                  {when(r.at)}{r.outcome === "refused" ? " · refused" : ""}{r.undone_at ? " · undone" : ""}
                </p>
              </div>
              {r.can_undo && (
                <button type="button" disabled={busy === r.id} onClick={() => undo(r.id)}
                  className="text-sm text-ink-2 underline underline-offset-2 hover:text-alert">Undo</button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
