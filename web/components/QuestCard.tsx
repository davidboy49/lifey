import type { Quest, QuestState } from "@/lib/habits";
import { shortDay } from "@/lib/journal";

const CELL: Record<QuestState, string> = {
  pass: "cell cell-clean",
  fail: "cell cell-slip",
  unknown: "cell cell-unknown",
  pending: "cell",
  rest: "cell cell-unchecked",
};
const STATE_TEXT: Record<QuestState, string> = {
  pass: "done",
  fail: "missed",
  unknown: "no data",
  pending: "still to come",
  rest: "rest day",
};
const VERDICT: Record<Quest["status"], string> = {
  met: "Met.",
  missed: "Missed.",
  at_risk: "At risk: every remaining day has to count.",
  on_track: "On track.",
};

/** One week's quest and how the days scored. A day with no data is dashed, never counted as a pass. */
export function QuestCard({ quest, heading = "Quest" }: { quest: Quest; heading?: string }) {
  const weekday = (iso: string) => shortDay(iso).slice(0, 3);
  return (
    <section className="card kind-quit grid gap-4 p-5 sm:p-6" aria-label={heading}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <div>
          <p className="eyebrow">{heading}</p>
          <h2 className="font-display text-xl font-semibold">{quest.label}</h2>
        </div>
        <p className="font-display text-2xl font-semibold" style={{ color: "var(--c)" }}>
          {quest.passed}
          <span className="text-base text-ink-3"> / {quest.target}</span>
        </p>
      </div>
      <div className="grid grid-cols-7 gap-1.5" role="list" aria-label="Days of the week">
        {quest.days.map((d) => (
          <div key={d.date} role="listitem" className="grid justify-items-center gap-1" title={`${shortDay(d.date)} · ${STATE_TEXT[d.state]}`}>
            <i className={`${CELL[d.state]} w-full max-w-[44px]`} />
            <span className="font-mono text-[11px] text-ink-3">{weekday(d.date)}</span>
          </div>
        ))}
      </div>
      <p className="text-sm text-ink-2">
        {VERDICT[quest.status]}
        {quest.failed > 0 && ` ${quest.failed} missed.`}
        {quest.unknown > 0 && ` ${quest.unknown} with no data, which counts neither way.`}
        {quest.pending > 0 && ` ${quest.pending} to go.`}
      </p>
    </section>
  );
}
