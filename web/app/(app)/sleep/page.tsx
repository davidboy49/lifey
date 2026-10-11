import { redirect } from "next/navigation";
import { ApiDown } from "@/components/ApiDown";
import { SleepBars } from "@/components/SleepBars";
import { apiGet } from "@/lib/api";
import { shortDay } from "@/lib/journal";
import { hm, type SleepResponse } from "@/lib/sleep";

export const dynamic = "force-dynamic";

const CONF: Record<string, string> = {
  strong: "bg-good-soft text-good",
  moderate: "bg-accent-soft text-accent",
  weak: "bg-watch-soft text-watch",
};

function Card({ label, children, note }: { label: string; children: React.ReactNode; note?: React.ReactNode }) {
  return (
    <div className="card grid content-start gap-1.5 p-5">
      <p className="eyebrow">{label}</p>
      {children}
      {note && <p className="text-[13px] text-ink-2">{note}</p>}
    </div>
  );
}

export default async function SleepPage() {
  const res = await apiGet<SleepResponse>("/api/sleep");
  if (res.status === "unauthorized") redirect("/login");
  if (res.status !== "ok") return <ApiDown />;
  const s = res.data;
  const { progress: p, debt: d, regularity: reg, last_night: last } = s;
  const need = s.garmin_need;

  const lastLine =
    last.kind === "missing"
      ? "No sleep recorded for last night."
      : last.kind === "incomplete"
        ? `Only ${hm(last.hours)} recorded. Under ${s.incomplete_below_h} h usually means the watch captured part of the night, so it is left out of the debt.`
        : `${hm(last.hours)}${last.score !== null ? ` · score ${last.score}` : ""}${last.bed && last.wake ? ` · ${last.bed} to ${last.wake}` : ""}`;

  return (
    <div className="flex flex-col gap-8">
      <header className="grid gap-2">
        <p className="eyebrow">Sleep</p>
        <h1 className="font-display text-[34px] font-semibold leading-tight tracking-tight sm:text-[44px]">
          {d.nights_counted === 0
            ? "Not enough nights yet"
            : d.hours < 1
              ? "Close to your target"
              : `${d.hours.toFixed(1)} h short over ${d.window} nights`}
        </h1>
        <p className="max-w-[64ch] text-ink-2">
          Last night: {lastLine}
        </p>
      </header>

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4" aria-label="Summary">
        <Card
          label={`Debt · last ${d.window} nights`}
          note={`${d.nights_short} of ${d.nights_counted} recorded nights under ${d.target_h.toFixed(1)} h${d.nights_under_6 ? `, ${d.nights_under_6} under 6 h` : ""}.${
            d.nights_missing || d.nights_excluded
              ? ` ${d.nights_missing + d.nights_excluded} night${d.nights_missing + d.nights_excluded === 1 ? "" : "s"} left out (${d.nights_missing} not recorded, ${d.nights_excluded} partly recorded).`
              : ""
          }`}
        >
          <p className="font-display text-[36px] font-semibold leading-none">
            {d.hours.toFixed(1)}<span className="ml-1 font-sans text-sm font-normal text-ink-3">h short</span>
          </p>
        </Card>

        <Card
          label={`Average · ${p.window} nights`}
          note={
            p.gap_h === null
              ? "No recorded nights in the window."
              : p.met
                ? `At or above your ${p.target_h.toFixed(1)} h target.`
                : `${p.gap_h.toFixed(1)} h under your ${p.target_h.toFixed(1)} h target. ${p.nights_at_or_above} of ${p.nights} nights reached it.`
          }
        >
          <p className="font-display text-[36px] font-semibold leading-none">
            {p.mean_h !== null ? p.mean_h.toFixed(1) : "·"}<span className="ml-1 font-sans text-sm font-normal text-ink-3">h / {p.target_h.toFixed(1)} h</span>
          </p>
          {p.earlier_mean_h !== null && p.recent_mean_h !== null && (
            <p className="font-mono text-xs text-ink-3">
              {p.earlier_mean_h.toFixed(1)} h earlier, {p.recent_mean_h.toFixed(1)} h recently
            </p>
          )}
        </Card>

        <Card
          label="Timing · last 14 nights"
          note={
            reg.enough
              ? `Usual bed ${reg.usual_bed}, usual wake ${reg.usual_wake}. ${reg.irregular ? `That is uneven (${reg.flag_threshold_min} min or more).` : "That is steady."}`
              : `Only ${reg.nights} nights with timing recorded; at least 7 are needed.`
          }
        >
          <p className="font-display text-[36px] font-semibold leading-none">
            {reg.enough ? `±${reg.wake_sd_min}` : "·"}<span className="ml-1 font-sans text-sm font-normal text-ink-3">min wake time</span>
          </p>
          {reg.enough && <p className="font-mono text-xs text-ink-3">bedtime ±{reg.bed_sd_min} min</p>}
        </Card>

        <Card
          label="Garmin's estimate for tonight"
          note={
            need
              ? `Baseline ${need.baseline_h.toFixed(1)} h, adjusted for recent training load and sleep. An estimate by Garmin, not a measurement.`
              : "Garmin has not supplied a sleep-need estimate."
          }
        >
          <p className="font-display text-[36px] font-semibold leading-none">
            {need ? need.hours.toFixed(1) : "·"}<span className="ml-1 font-sans text-sm font-normal text-ink-3">h</span>
          </p>
        </Card>
      </section>

      <section className="card grid gap-3 p-5 sm:p-6" aria-labelledby="sl-nights">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 id="sl-nights" className="font-display text-xl font-semibold">Night by night</h2>
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-[12.5px] text-ink-3">
            <span className="inline-flex items-center gap-1.5"><i className="inline-block size-2.5 rounded-sm bg-good" />At or above target</span>
            <span className="inline-flex items-center gap-1.5"><i className="inline-block size-2.5 rounded-sm bg-watch" />Under target</span>
            <span className="inline-flex items-center gap-1.5"><i className="inline-block size-2.5 rounded-sm bg-alert" />Under 6 h</span>
            <span className="inline-flex items-center gap-1.5"><i className="hatch inline-block size-2.5 rounded-sm border border-ink-3" />Partly recorded</span>
            <span className="inline-flex items-center gap-1.5"><i className="inline-block size-2.5 rounded-sm border border-dashed border-ink-3" />Not recorded</span>
          </div>
        </div>
        <SleepBars nights={s.nights} target={s.target_h} incompleteBelow={s.incomplete_below_h} />
      </section>

      {s.suggestions.length > 0 && (
        <section className="grid gap-3" aria-labelledby="sl-tips">
          <h2 id="sl-tips" className="eyebrow">What your numbers point to</h2>
          {s.suggestions.map((t) => (
            <article key={t.id} className="card grid gap-2 p-5">
              <h3 className="font-display text-lg font-semibold">{t.title}</h3>
              <p className="max-w-[72ch] text-[15px] text-ink-2">{t.detail}</p>
              {t.evidence.length > 0 && (
                <p className="flex flex-wrap items-center gap-2 text-[12.5px] text-ink-3">
                  Based on
                  {t.evidence.map((id) => (
                    <a key={id} href={`#ev-${id}`} className="rounded-full border border-line bg-panel px-2.5 py-0.5 font-mono text-[11.5px] text-ink-2 hover:border-accent hover:text-accent">
                      {s.evidence[id]?.cite.split(",")[0] ?? id}
                    </a>
                  ))}
                </p>
              )}
            </article>
          ))}
        </section>
      )}

      <section className="grid gap-3" aria-labelledby="sl-perf">
        <div>
          <h2 id="sl-perf" className="eyebrow">How you do after short and adequate nights</h2>
          <p className="mt-1 max-w-[70ch] text-sm text-ink-2">
            From your own days: nights under {s.outcomes.target_h.toFixed(1)} h ({s.outcomes.below_nights} nights) against nights at or above it ({s.outcomes.above_nights}).
            Garmin readiness and Body Battery are left out, because they are calculated from the night itself.
            A row only counts as a pattern with at least {s.outcomes.needed} nights in each group.
          </p>
        </div>
        <div className="overflow-x-auto rounded-2xl border border-line bg-raised">
          <table className="w-full min-w-[560px] border-separate border-spacing-0 text-sm">
            <thead>
              <tr className="font-mono text-[11px] uppercase tracking-wider text-ink-3">
                <th className="border-b border-line bg-panel px-4 py-2.5 text-left font-medium">Measure</th>
                <th className="border-b border-line bg-panel px-4 py-2.5 text-right font-medium">Under target</th>
                <th className="border-b border-line bg-panel px-4 py-2.5 text-right font-medium">At or above</th>
                <th className="border-b border-line bg-panel px-4 py-2.5 text-left font-medium">Reading</th>
              </tr>
            </thead>
            <tbody>
              {s.outcomes.rows.map((r) => (
                <tr key={r.label}>
                  <td className="border-b border-line px-4 py-3 font-medium">{r.label}</td>
                  <td className="border-b border-line px-4 py-3 text-right tabular-nums">
                    {r.below === null ? "·" : `${r.below}${r.unit ? ` ${r.unit}` : ""}`} <span className="font-mono text-xs text-ink-3">n={r.below_n}</span>
                  </td>
                  <td className="border-b border-line px-4 py-3 text-right tabular-nums">
                    {r.above === null ? "·" : `${r.above}${r.unit ? ` ${r.unit}` : ""}`} <span className="font-mono text-xs text-ink-3">n={r.above_n}</span>
                  </td>
                  <td className="border-b border-line px-4 py-3 text-ink-2">
                    {r.enough ? "Enough nights to compare" : "A note, not a finding yet"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="grid gap-3" aria-labelledby="sl-evidence">
        <div>
          <h2 id="sl-evidence" className="eyebrow">What the research says, and how far to trust it</h2>
          <p className="mt-1 max-w-[70ch] text-sm text-ink-2">
            Most of this is lab work on small groups, or population studies that show association. They are reasons to look at your own numbers, not proof of what will work for you.
          </p>
        </div>
        <div className="grid gap-3">
          {Object.entries(s.evidence).map(([id, ev]) => (
            <article key={id} id={`ev-${id}`} className="card grid gap-1.5 p-5 target:border-accent">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h3 className="font-semibold">{ev.cite}</h3>
                <span className={`rounded-full px-2.5 py-0.5 font-mono text-[11px] uppercase tracking-wider ${CONF[ev.confidence]}`}>{ev.confidence}</span>
              </div>
              <p className="text-[15px]">{ev.finding}</p>
              <p className="text-sm text-ink-2"><b className="font-semibold text-ink">Limits:</b> {ev.caveat}</p>
              <a href={ev.url} target="_blank" rel="noopener noreferrer" className="w-fit text-sm text-accent underline underline-offset-2">Source</a>
            </article>
          ))}
        </div>
      </section>

      <p className="max-w-[66ch] text-sm text-ink-3">
        This is a wellness tool, not medical advice. Garmin's sleep figures are estimates from a wrist sensor. If you are
        persistently exhausted, snore heavily or stop breathing at night, talk to a doctor.
      </p>
    </div>
  );
}
