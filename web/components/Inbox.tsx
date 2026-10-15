"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { CATEGORY_LABEL, type Category, type Proposal } from "@/lib/learning";

const KIND = { study: "Study", focus: "Monthly focus", quest: "Weekly quest" } as const;

function str(v: unknown): string {
  return typeof v === "string" ? v : "";
}

/** Suggestions from Claude. Nothing here has taken effect; each one waits for an explicit accept. */
export function Inbox({ items }: { items: Proposal[] }) {
  const router = useRouter();
  const [busy, setBusy] = useState<number | null>(null);
  const [errors, setErrors] = useState<Record<number, string>>({});

  async function decide(id: number, action: "accept" | "reject") {
    setBusy(id);
    setErrors((e) => ({ ...e, [id]: "" }));
    try {
      const res = await fetch(`/api/proposals/${id}/${action}`, { method: "POST" });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setErrors((e) => ({ ...e, [id]: typeof body.detail === "string" ? body.detail : "Couldn’t do that." }));
        return;
      }
      router.refresh();
    } catch {
      setErrors((e) => ({ ...e, [id]: "Couldn’t reach the server." }));
    } finally {
      setBusy(null);
    }
  }

  if (items.length === 0) return null;
  return (
    <section className="grid gap-3" aria-labelledby="inbox-h">
      <div>
        <h2 id="inbox-h" className="eyebrow">Suggested by Claude · {items.length} waiting</h2>
        <p className="mt-1 text-sm text-ink-2">None of these has taken effect. Accept the ones you want; check any link before you do.</p>
      </div>
      {items.map((p) => {
        const d = p.payload;
        return (
          <div key={p.id} className="card kind-note grid gap-2 p-4">
            <p className="font-mono text-[11px] uppercase tracking-wide text-ink-3">{KIND[p.kind]}</p>
            {p.kind === "study" && (
              <>
                <p className="text-[15px]">
                  <b>
                    <a href={str(d.url)} target="_blank" rel="noopener noreferrer" className="text-accent underline underline-offset-2">
                      {str(d.citation)}
                    </a>
                  </b>
                </p>
                <p className="text-[15px] text-ink-2">{str(d.finding)}</p>
                <p className="break-all font-mono text-[11px] text-ink-3">{str(d.url)}</p>
              </>
            )}
            {p.kind === "focus" && (
              <>
                <p className="font-display text-lg font-semibold">
                  {str(d.topic)} <span className="font-sans text-sm font-normal text-ink-3">· {CATEGORY_LABEL[str(d.category) as Category] ?? str(d.category)}</span>
                </p>
                <p className="text-[15px]"><b>By the end of the month, I can</b> {str(d.outcome)}</p>
                {(str(d.plan_if) || str(d.plan_then)) && (
                  <p className="text-[15px] text-ink-2">If {str(d.plan_if) || "…"}, then I will {str(d.plan_then) || "…"}.</p>
                )}
              </>
            )}
            {p.kind === "quest" && (
              <>
                <p className="font-display text-lg font-semibold">{p.label}</p>
                <p className="text-sm text-ink-2">For the week of {str(d.week_start)}.</p>
                {p.replaces && <p className="text-sm text-alert">Replaces this week’s current quest: {p.replaces}</p>}
              </>
            )}
            {p.why && <p className="text-sm text-ink-3">Why: {p.why}</p>}
            {p.blocked && <p className="text-sm text-alert">{p.blocked}</p>}
            {errors[p.id] && <p role="alert" className="rounded-xl bg-alert-soft px-3.5 py-2 text-sm text-alert">{errors[p.id]}</p>}
            <div className="flex flex-wrap items-center gap-4 pt-1">
              <button type="button" disabled={busy === p.id || !!p.blocked} onClick={() => decide(p.id, "accept")}
                className="rounded-xl bg-accent px-5 py-2 font-medium text-ground hover:opacity-90 disabled:opacity-50">Accept</button>
              <button type="button" disabled={busy === p.id} onClick={() => decide(p.id, "reject")}
                className="text-sm text-ink-3 underline underline-offset-2 hover:text-alert">Reject</button>
            </div>
          </div>
        );
      })}
    </section>
  );
}
