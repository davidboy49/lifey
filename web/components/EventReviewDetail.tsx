"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { DayDataPanel } from "./DayData";
import { EventReviewForm } from "./EventReviewForm";
import { errorText, longDay, loopLabel, type EventReview } from "@/lib/eventReviews";

function Block({ label, text }: { label: string; text: string }) {
  if (!text) return null;
  return (
    <section className="grid gap-1">
      <h2 className="eyebrow">{label}</h2>
      <p className="whitespace-pre-wrap text-[16px] leading-relaxed">{text}</p>
    </section>
  );
}

export function EventReviewDetail({ initial }: { initial: EventReview }) {
  const router = useRouter();
  const [review, setReview] = useState(initial);
  const [editing, setEditing] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [error, setError] = useState("");

  async function remove() {
    setError("");
    const r = await fetch(`/api/event-reviews/${review.id}`, { method: "DELETE" });
    if (r.ok || r.status === 404) {
      router.replace("/reviews");
      router.refresh();
    } else {
      setError(await errorText(r, "Couldn’t delete it. Try again."));
    }
  }

  if (editing) {
    return (
      <EventReviewForm
        initial={review}
        onCancel={() => setEditing(false)}
        onSaved={(saved) => { setReview(saved); setEditing(false); router.refresh(); }}
      />
    );
  }

  return (
    <div className="grid gap-7">
      <header className="grid gap-2">
        <p className="eyebrow">{longDay(review.date)}</p>
        <h1 className="font-display text-[32px] font-semibold leading-[1.05] tracking-tight sm:text-[42px]">{review.event}</h1>
        <div className="flex flex-wrap gap-2 text-[14px]">
          <span className="rounded-lg bg-raised px-2.5 py-1 text-ink-2">Mood <b className="text-ink">{review.mood ?? "·"}</b>/5</span>
          <span className="rounded-lg bg-raised px-2.5 py-1 text-ink-2">Energy <b className="text-ink">{review.energy ?? "·"}</b>/5</span>
          {review.loop_tags.map((t) => (
            <span key={t} className="kind-habit kind-badge rounded-lg px-2.5 py-1 font-medium">{loopLabel(t)}</span>
          ))}
        </div>
      </header>

      {review.lesson && (
        <p className="rounded-2xl bg-accent-soft px-4 py-3.5 text-[17px]">
          <span className="eyebrow mb-1 block text-accent">Lesson</span>
          {review.lesson}
        </p>
      )}

      <section className="card grid gap-3 p-4" aria-label="That day’s data">
        <h2 className="eyebrow">That day’s data</h2>
        <DayDataPanel date={review.date} />
      </section>

      <Block label="Notes" text={review.notes} />
      <Block label="What went well" text={review.went_well} />
      <Block label="What I’d change" text={review.would_change} />

      {review.photos.length > 0 && (
        <section className="grid gap-2">
          <h2 className="eyebrow">Photos</h2>
          <ul className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {review.photos.map((p) => (
              <li key={p.id}>
                <a href={`/api/event-reviews/photos/${p.id}`} target="_blank" rel="noopener noreferrer"
                  className="block overflow-hidden rounded-xl border border-line bg-panel">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={`/api/event-reviews/photos/${p.id}/thumb`} alt={p.filename} loading="lazy"
                    className="block aspect-square w-full object-cover" />
                </a>
              </li>
            ))}
          </ul>
        </section>
      )}

      <div className="flex flex-wrap items-center gap-3 border-t border-line pt-5">
        <button type="button" onClick={() => setEditing(true)}
          className="rounded-xl bg-accent px-6 py-3 font-medium text-ground hover:opacity-90">Edit</button>
        {confirm ? (
          <>
            <button type="button" onClick={remove}
              className="rounded-xl bg-alert px-4 py-3 font-medium text-ground hover:opacity-90">Delete for good</button>
            <button type="button" onClick={() => setConfirm(false)} className="rounded-xl px-4 py-3 font-medium text-ink-2">Keep it</button>
          </>
        ) : (
          <button type="button" onClick={() => setConfirm(true)}
            className="rounded-xl px-4 py-3 font-medium text-alert hover:opacity-80">Delete</button>
        )}
        <p role="status" aria-live="polite" className="text-sm text-alert">{error}</p>
      </div>
    </div>
  );
}
