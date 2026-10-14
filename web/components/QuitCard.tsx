import type { QuitCard as Card, QuitCell, QuitComeback } from "@/lib/habits";
import { shortDay } from "@/lib/journal";
import { Legend } from "./HabitGrid";

const CELL: Record<QuitCell["state"], string> = {
  clean: "cell cell-clean",
  slip: "cell cell-slip",
  unchecked: "cell cell-unchecked",
  unknown: "cell cell-unknown",
};

function title(c: QuitCell): string {
  const day = shortDay(c.date);
  if (c.state === "unknown") return `${day} · nothing logged (unknown)`;
  if (c.state === "slip") return `${day} · slip`;
  if (c.state === "clean") return `${day} · ${c.urge ? "urge resisted" : "clean day checked"}`;
  return `${day} · logged, not checked`;
}

// A slip is one amber day inside a long run of violet ones. The big number is
// "days free of the last 30", so a slip never turns the headline into a zero.
export function QuitCard({ card, strip, comeback }: { card: Card | null; strip: QuitCell[]; comeback?: QuitComeback }) {
  if (!card) {
    return (
      <section className="card kind-quit p-6">
        <h2 className="font-display text-xl font-semibold">Quit tracker</h2>
        <p className="mt-1 text-ink-2">Nothing tracked yet. Log a resisted urge, a clean day or a slip from the journal or the bot and it begins.</p>
      </section>
    );
  }
  const slipNote = card.relapsed_today
    ? `One slip today. ${card.free_days_30} of the last ${card.tracked_days_30} days are still free, and your best run of ${card.best_run} days is kept.`
    : null;

  return (
    <section className="card kind-quit grid gap-5 p-5 sm:p-6 md:grid-cols-[minmax(170px,230px)_1fr] md:gap-8">
      <div className="grid content-start gap-1">
        <p className="eyebrow">Quit tracker</p>
        <p className="font-display text-[56px] font-semibold leading-none" style={{ color: "var(--c)" }}>
          {card.free_days_30}
          <span className="text-[26px] text-ink-3"> / {card.tracked_days_30}</span>
        </p>
        <p className="text-sm text-ink-2">days free in the last 30</p>
      </div>

      <div className="grid min-w-0 gap-4">
        <div className="grid gap-[3px]" style={{ gridTemplateColumns: `repeat(${strip.length}, minmax(0, 1fr))` }} aria-label="Last 30 days">
          {strip.map((c) => (
            <i key={c.date} className={`${CELL[c.state]} ${c.urge ? "cell-urge" : ""}`} title={title(c)} />
          ))}
        </div>
        <Legend
          items={[
            { cls: "cell cell-clean", text: "Free, checked" },
            { cls: "cell cell-slip", text: "Slip" },
            { cls: "cell cell-unchecked", text: "Logged, not checked" },
            { cls: "cell cell-unknown", text: "Nothing logged" },
          ]}
        />
        <dl className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-4">
          <div><dt className="eyebrow">Current run</dt><dd className="font-display text-xl font-semibold">{card.current_run} {card.current_run === 1 ? "day" : "days"}</dd></div>
          <div><dt className="eyebrow">Best run</dt><dd className="font-display text-xl font-semibold">{card.best_run} days</dd></div>
          <div><dt className="eyebrow">Urges resisted</dt><dd className="font-display text-xl font-semibold">{card.urges_this_run}<span className="text-sm font-normal text-ink-3"> this run</span></dd></div>
          <div><dt className="eyebrow">Slips</dt><dd className="font-display text-xl font-semibold">{card.slips_7d}<span className="text-sm font-normal text-ink-3"> 7d · </span>{card.slips_30d}<span className="text-sm font-normal text-ink-3"> 30d</span></dd></div>
        </dl>
        {slipNote && <p className="rounded-xl bg-panel px-3.5 py-2.5 text-sm text-ink-2">{slipNote}</p>}
        {comeback?.text && (
          <p className="text-sm text-ink-2">
            <span className="eyebrow mr-2">Comeback</span>
            {comeback.text}
          </p>
        )}
        <p className="text-xs text-ink-3">Tracking since {shortDay(card.tracking_since)}</p>
      </div>
    </section>
  );
}
