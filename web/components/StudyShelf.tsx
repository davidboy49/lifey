"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { LearningResponse } from "@/lib/learning";

const field = "w-full rounded-xl border border-line bg-panel px-3.5 py-2.5 text-[15px] text-ink outline-none focus:border-accent";

function Link({ href, children }: { href: string; children: React.ReactNode }) {
  return <a href={href} target="_blank" rel="noopener noreferrer" className="text-accent underline underline-offset-2">{children}</a>;
}

/** Studies kept for the current topic, a way to add one, and the research behind Lifey's own design. */
export function StudyShelf({ data }: { data: LearningResponse }) {
  const router = useRouter();
  const [v, setV] = useState({ citation: "", url: "", finding: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function pin(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/learning/studies", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(v),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        return setError(typeof body.detail === "string" ? body.detail : "Couldn’t keep that study.");
      }
      setV({ citation: "", url: "", finding: "" });
      router.refresh();
    } catch {
      setError("Couldn’t reach the server.");
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: number) {
    const res = await fetch(`/api/learning/studies/${id}`, { method: "DELETE" }).catch(() => null);
    if (res && (res.ok || res.status === 404)) router.refresh();
  }

  const a = data.active;
  return (
    <div className="grid gap-8">
      <section className="grid gap-3" aria-labelledby="sh-mine">
        <h2 id="sh-mine" className="eyebrow">{a ? `Studies kept for “${a.topic}”` : "Studies for your topic"}</h2>
        {!a && <p className="text-sm text-ink-2">Set a focus first. The shelf belongs to the topic you are learning.</p>}
        {a && data.shelf.length === 0 && (
          <p className="text-sm text-ink-2">Nothing kept yet. Ask Claude through the Lifey connector, for example:
            <i> “Look at my Lifey learning focus and find studies on how to learn it better. Give a working link for each.”</i>
            Claude reads your topic and outcome, never your notes. If you allowed capture when you connected, it sends studies to the inbox above for you to accept; otherwise keep the ones you trust below.</p>
        )}
        {data.shelf.map((s) => (
          <div key={s.id} className="card grid gap-1.5 p-4">
            <p className="text-[15px]"><b><Link href={s.url}>{s.citation}</Link></b></p>
            <p className="text-[15px] text-ink-2">{s.finding}</p>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="font-mono text-[11px] text-ink-3">Research, not advice · retrieved {s.retrieved_on}</p>
              <button type="button" onClick={() => remove(s.id)} className="text-xs text-ink-3 underline underline-offset-2 hover:text-alert">Remove</button>
            </div>
          </div>
        ))}
        {a && (
          <form onSubmit={pin} className="card grid gap-3 p-4">
            <p className="font-semibold">Keep a study</p>
            <input className={field} placeholder="Authors, year, title" value={v.citation} maxLength={300} required
              onChange={(e) => setV({ ...v, citation: e.target.value })} aria-label="Citation" />
            <input className={field} placeholder="https://…" value={v.url} maxLength={500} required inputMode="url"
              onChange={(e) => setV({ ...v, url: e.target.value })} aria-label="Link" />
            <input className={field} placeholder="What it found, in one sentence" value={v.finding} maxLength={400} required
              onChange={(e) => setV({ ...v, finding: e.target.value })} aria-label="Finding" />
            <p className="text-xs text-ink-3">Lifey stores exactly what you type with the date. Open the link and check it says this before you keep it.</p>
            {error && <p role="alert" className="rounded-xl bg-alert-soft px-3.5 py-2.5 text-sm text-alert">{error}</p>}
            <div><button type="submit" disabled={busy} className="rounded-xl bg-accent px-5 py-2.5 font-medium text-ground disabled:opacity-60">{busy ? "Keeping…" : "Keep study"}</button></div>
          </form>
        )}
      </section>

      <section className="grid gap-3" aria-labelledby="sh-starter">
        <div>
          <h2 id="sh-starter" className="eyebrow">The research behind this page</h2>
          <p className="mt-1 text-sm text-ink-2">Why Lifey asks for one outcome, a slot, a weekly check and a recall. Figures are as the sources report them.</p>
        </div>
        {data.starter.map((s) => (
          <div key={s.id} className="card grid gap-1 p-4">
            <p className="font-mono text-[11px] uppercase tracking-wide text-ink-3">{s.used_for}</p>
            <p className="text-[15px]"><b><Link href={s.url}>{s.citation}</Link></b></p>
            <p className="text-[15px] text-ink-2">{s.finding}</p>
            <p className="text-[13px] text-ink-3">Caveat: {s.caveat}</p>
          </div>
        ))}
      </section>
    </div>
  );
}
