import Link from "next/link";
import { redirect } from "next/navigation";
import { ApiDown } from "@/components/ApiDown";
import { HabitGrid } from "@/components/HabitGrid";
import { QuestCard } from "@/components/QuestCard";
import { QuestPicker } from "@/components/QuestPicker";
import { ReviewReflection } from "@/components/ReviewReflection";
import { apiGet } from "@/lib/api";
import { hoursMinutes, type QuestResponse, type Review } from "@/lib/habits";
import { addDays, shortDay } from "@/lib/journal";

export const dynamic = "force-dynamic";

function Num({ value, unit, line, note }: { value: string; unit?: string; line: string; note: string }) {
  return (
    <div className="card grid gap-1 p-4">
      <p className="font-display text-[28px] font-semibold leading-none">
        {value}
        {unit && <span className="ml-1 font-sans text-sm font-normal text-ink-3">{unit}</span>}
      </p>
      <p className="text-[13px] text-ink-2">{line}</p>
      <p className="font-mono text-[11px] text-ink-3">{note}</p>
    </div>
  );
}

function delta(minutes: number): string {
  const m = Math.round(Math.abs(minutes));
  return `${m} min ${minutes < 0 ? "less" : "more"} than the week before`;
}

export default async function ReviewPage({ searchParams }: { searchParams: Promise<{ week?: string }> }) {
  const sp = await searchParams;
  const q = sp.week && /^\d{4}-\d{2}-\d{2}$/.test(sp.week) ? `?week=${sp.week}` : "";
  const res = await apiGet<Review>(`/api/review${q}`);
  if (res.status === "unauthorized") redirect("/login");
  if (res.status !== "ok") return <ApiDown />;
  const r = res.data;
  const n = r.numbers;
  // The quest this week was scored against, and the picker for the week the plan below is about.
  const questNow = await apiGet<QuestResponse>(`/api/quest?week=${r.week_start}`);
  const questNext = await apiGet<QuestResponse>(`/api/quest?week=${addDays(r.week_start, 7)}`);
  const scored = questNow.status === "ok" ? questNow.data.quest : null;
  const picker = questNext.status === "ok" && questNext.data.editable ? questNext.data : null;

  const sleepLine =
    n.sleep.avg_seconds !== null && n.sleep.prev_avg_seconds !== null
      ? delta((n.sleep.avg_seconds - n.sleep.prev_avg_seconds) / 60)
      : "No comparison week yet";
  const days = r.habits[0]?.cells.map((c) => c.date) ?? [];

  return (
    <article className="mx-auto flex w-full max-w-[760px] flex-col gap-10">
      <header className="grid gap-3">
        <nav className="flex items-center justify-between font-mono text-xs text-ink-3" aria-label="Week">
          {r.prev_week ? <Link href={`/review?week=${r.prev_week}`} className="hover:text-accent">← Previous week</Link> : <span />}
          {r.next_week ? <Link href={r.next_week === r.week_start ? "/review" : `/review?week=${r.next_week}`} className="hover:text-accent">Next week →</Link> : <span>This week</span>}
        </nav>
        <div>
          <p className="eyebrow">{r.label}</p>
          <h1 className="font-display text-[36px] font-semibold leading-[1.05] tracking-tight sm:text-[46px]">Your week in review</h1>
        </div>
      </header>

      <section className="grid gap-3" aria-labelledby="rv-numbers">
        <h2 id="rv-numbers" className="eyebrow">The week in numbers</h2>
        <div className="grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-3">
          <Num value={hoursMinutes(n.sleep.avg_seconds)} unit="sleep" line={sleepLine} note={`${n.sleep.nights} of ${n.sleep.of} nights recorded`} />
          <Num
            value={n.hrv.avg !== null ? Math.round(n.hrv.avg).toString() : "·"}
            unit="ms HRV"
            line={n.hrv.delta_pct === null ? "No usual to compare with yet" : `${Math.abs(Math.round(n.hrv.delta_pct))}% ${n.hrv.delta_pct < 0 ? "below" : "above"} your usual`}
            note={`${n.hrv.mornings} of ${n.hrv.of} mornings`}
          />
          <Num value={`${n.training.sessions} / ${n.training.target}`} unit="sessions" line="Logged in Lifey or by your watch" note="gym plan target" />
          {n.quit && (
            <Num
              value={`${n.quit.free_days} / ${n.quit.tracked_days}`}
              unit="days free"
              line={n.quit.slips === 0 ? "No slips" : `${n.quit.slips} slip${n.quit.slips === 1 ? "" : "s"}`}
              note={`${n.quit.days_with_entries} of ${n.quit.tracked_days} days have entries`}
            />
          )}
          <Num
            value={n.mood.avg !== null ? n.mood.avg.toFixed(1) : "·"}
            unit="mood"
            line={n.mood.count ? "Average of your check-ins" : "No check-ins this week"}
            note={`${n.mood.count} check-in${n.mood.count === 1 ? "" : "s"}`}
          />
        </div>
      </section>

      {scored && <QuestCard quest={scored} heading={r.is_current ? "This week’s quest" : "Quest that week"} />}

      {r.notes.length > 0 && (
        <section className="grid gap-3" aria-labelledby="rv-notes">
          <h2 id="rv-notes" className="eyebrow">In your words</h2>
          {r.notes.map((note) => (
            <figure key={`${note.date}-${note.time}-${note.text.slice(0, 12)}`} className="card grid gap-1.5 p-4">
              <blockquote className="font-display text-[19px] leading-snug tracking-tight">{note.text}</blockquote>
              <figcaption className="font-mono text-[11.5px] text-ink-3">
                {shortDay(note.date)}{note.time ? ` · ${note.time}` : ""}{note.title !== "Note" ? ` · ${note.title.toLowerCase()}` : ""}
              </figcaption>
            </figure>
          ))}
        </section>
      )}

      {r.habits.length > 0 && days.length > 0 && (
        <section className="card grid gap-3 p-5" aria-labelledby="rv-habits">
          <h2 id="rv-habits" className="eyebrow">Habits this week</h2>
          <HabitGrid days={days} rows={r.habits} />
        </section>
      )}

      {r.patterns.length > 0 && (
        <section className="grid gap-3" aria-labelledby="rv-patterns">
          <h2 id="rv-patterns" className="eyebrow">Worth a look</h2>
          {r.patterns.map((p) => (
            <div key={p.tag} className="card grid gap-3 p-4">
              <p className="text-[15px]"><b>{p.label} and the night after.</b> {p.text}</p>
              <div className="flex flex-wrap items-center gap-3 text-[13px] text-ink-2">
                <span className="inline-flex gap-1" aria-hidden>
                  {Array.from({ length: p.needed }).map((_, i) => (
                    <i key={i} className={`size-2.5 rounded-full ${i < Math.min(p.with_n, p.needed) ? "bg-accent" : "bg-line"}`} />
                  ))}
                </span>
                <span>
                  {p.with_n} of the {p.needed} nights needed
                  {p.enough ? ", enough to call it a pattern." : ". Treat this as a note, not a finding."}
                </span>
              </div>
            </div>
          ))}
        </section>
      )}

      {r.habit_cues.length > 0 && (
        <section className="grid gap-2" aria-labelledby="rv-cues">
          <h2 id="rv-cues" className="eyebrow">Your cues</h2>
          <ul className="grid gap-1.5 text-[15px] text-ink-2">
            {r.habit_cues.map((c) => (
              <li key={c.label}><b className="text-ink">{c.label}:</b> if {c.cue_if || "…"}, then {c.cue_then || "…"}</li>
            ))}
          </ul>
        </section>
      )}

      <section className="grid gap-4" aria-labelledby="rv-reflect">
        <h2 id="rv-reflect" className="eyebrow">Your reflection</h2>
        <ReviewReflection key={r.week_start} weekStart={r.week_start} initial={r.reflection} learning={r.learning} lastPlan={r.last_plan} />
      </section>

      {picker && (
        <section className="grid gap-3" aria-labelledby="rv-quest">
          <h2 id="rv-quest" className="eyebrow">Quest</h2>
          <QuestPicker key={picker.week_start} data={picker} />
        </section>
      )}
    </article>
  );
}
