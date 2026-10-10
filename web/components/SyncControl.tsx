"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import type { SyncSource, SyncStatus } from "@/lib/journal";

const STATUS_TEXT: Record<SyncSource["status"], { text: string; tone: "ok" | "gap" | "bad" }> = {
  available: { text: "Up to date", tone: "ok" },
  not_recorded: { text: "Not recorded", tone: "gap" },
  unavailable: { text: "No data", tone: "gap" },
  stale: { text: "Not refreshed", tone: "gap" },
  fetch_failed: { text: "Failed, kept earlier value", tone: "bad" },
  parse_failed: { text: "Unreadable, kept earlier value", tone: "bad" },
};

function ago(iso: string | null, now: number): string {
  if (!iso) return "never";
  const mins = Math.max(0, Math.round((now - new Date(iso).getTime()) / 60000));
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const h = Math.round(mins / 60);
  return h < 24 ? `${h} h ago` : `${Math.round(h / 24)} d ago`;
}

const POLL_MS = 1500;
const GIVE_UP_MS = 150_000;

export function SyncControl({ syncedAt }: { syncedAt: string | null }) {
  const router = useRouter();
  const [now, setNow] = useState<number | null>(null);
  const [last, setLast] = useState<string | null>(syncedAt);
  const [phase, setPhase] = useState<"idle" | "running" | "done" | "error">("idle");
  const [message, setMessage] = useState<string | null>(null);
  const [sources, setSources] = useState<SyncSource[]>([]);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    setNow(Date.now());
    const t = setInterval(() => setNow(Date.now()), 30_000);
    return () => {
      clearInterval(t);
      if (timer.current) clearTimeout(timer.current);
    };
  }, []);

  async function status(): Promise<SyncStatus | null> {
    try {
      const r = await fetch("/api/health/sync", { cache: "no-store" });
      return r.ok ? ((await r.json()) as SyncStatus) : null;
    } catch {
      return null;
    }
  }

  async function poll(startedAt: number) {
    const s = await status();
    if (s && !s.running) {
      const failed = s.last_run?.status === "failed";
      setSources(s.sources);
      setLast(new Date().toISOString());
      setMessage(
        failed
          ? "The sync could not complete. Earlier values are unchanged. Check that Garmin is reachable and try again."
          : s.last_run?.status === "partial"
            ? "Partly updated. The sources below say what each one did."
            : "Everything is up to date.",
      );
      setPhase(failed ? "error" : "done");
      router.refresh();
      return;
    }
    if (Date.now() - startedAt > GIVE_UP_MS) {
      setMessage("This is taking longer than usual. It may still finish; check back in a minute.");
      setPhase("error");
      return;
    }
    timer.current = setTimeout(() => poll(startedAt), POLL_MS);
  }

  async function start() {
    setPhase("running");
    setMessage(null);
    setSources([]);
    try {
      const r = await fetch("/api/health/sync", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ days: 3 }),
      });
      if (r.status === 409) {
        setMessage("A sync is already running. Waiting for it to finish.");
      } else if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        setPhase("error");
        setMessage(body.detail ?? "Could not start the sync.");
        return;
      }
      void poll(Date.now());
    } catch {
      setPhase("error");
      setMessage("Couldn’t reach the server. Check your connection.");
    }
  }

  const busy = phase === "running";
  return (
    <div className="flex flex-col items-end gap-2">
      <div className="flex flex-wrap items-center justify-end gap-2">
        <p className="flex items-center gap-2 rounded-full border border-line bg-raised px-3 py-1.5 font-mono text-xs text-ink-2" aria-live="polite">
          <span className={`size-1.5 rounded-full ${busy ? "animate-pulse bg-accent" : phase === "error" ? "bg-alert" : "bg-good"}`} aria-hidden />
          {busy ? "Syncing the last 3 days…" : `Synced ${now ? ago(last, now) : "…"}`}
        </p>
        <button
          type="button"
          onClick={start}
          disabled={busy}
          className="rounded-full border border-line bg-raised px-3.5 py-1.5 text-sm font-medium text-ink hover:border-accent hover:text-accent disabled:cursor-wait disabled:opacity-60"
        >
          {busy ? "Syncing" : "Sync now"}
        </button>
      </div>

      {(message || sources.length > 0) && phase !== "running" && (
        <div className="card w-full max-w-[420px] p-4 text-left">
          {message && <p className={`text-sm ${phase === "error" ? "text-alert" : "text-ink-2"}`}>{message}</p>}
          {sources.length > 0 && (
            <ul className="mt-3 grid gap-1.5">
              {sources.map((s) => {
                const t = STATUS_TEXT[s.status] ?? { text: s.status, tone: "gap" as const };
                return (
                  <li key={s.key} className="flex justify-between gap-3 text-sm">
                    <span>{s.label}</span>
                    <span className={t.tone === "ok" ? "text-good" : t.tone === "bad" ? "font-medium text-alert" : "text-ink-3"}>{t.text}</span>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
