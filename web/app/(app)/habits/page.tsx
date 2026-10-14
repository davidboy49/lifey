import Link from "next/link";
import { redirect } from "next/navigation";
import { ApiDown } from "@/components/ApiDown";
import { HabitGrid, Legend, WellbeingGrid } from "@/components/HabitGrid";
import { HabitManager } from "@/components/HabitManager";
import { FeelingByRun } from "@/components/FeelingByRun";
import { QuestCard } from "@/components/QuestCard";
import { QuitCard } from "@/components/QuitCard";
import { WakeFeeling } from "@/components/WakeFeeling";
import { apiGet } from "@/lib/api";
import type { HabitsResponse, QuestResponse } from "@/lib/habits";
import { shortDay } from "@/lib/journal";

export const dynamic = "force-dynamic";

const RANGES = [2, 5, 12];

export default async function HabitsPage({ searchParams }: { searchParams: Promise<{ weeks?: string }> }) {
  const sp = await searchParams;
  const weeks = RANGES.includes(Number(sp.weeks)) ? Number(sp.weeks) : 5;
  const res = await apiGet<HabitsResponse>(`/api/habits?weeks=${weeks}`);
  if (res.status === "unauthorized") redirect("/login");
  if (res.status !== "ok") return <ApiDown />;
  const d = res.data;
  const shown = d.habits.filter((h) => h.builtin || h.days > 0);
  const questRes = await apiGet<QuestResponse>("/api/quest");
  const quest = questRes.status === "ok" ? questRes.data.quest : null;

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow">Habits</p>
          <h1 className="font-display text-[34px] font-semibold leading-tight tracking-tight sm:text-[44px]">
            {shortDay(d.days[0])} <span className="text-ink-3">to {shortDay(d.today)}</span>
          </h1>
        </div>
        <nav aria-label="Range" className="flex gap-1 rounded-xl border border-line bg-raised p-1">
          {RANGES.map((w) => (
            <Link
              key={w}
              href={w === 5 ? "/habits" : `/habits?weeks=${w}`}
              aria-current={weeks === w ? "true" : undefined}
              className={`rounded-lg px-3 py-1.5 text-sm font-medium ${weeks === w ? "bg-accent-soft text-accent" : "text-ink-2 hover:text-ink"}`}
            >
              {w} weeks
            </Link>
          ))}
        </nav>
      </header>

      {quest ? (
        <QuestCard quest={quest} heading="This week’s quest" />
      ) : (
        <p className="rounded-2xl border border-dashed border-line px-4 py-3 text-sm text-ink-2">
          No quest this week. <Link href="/review" className="font-medium text-accent underline underline-offset-2">Set one on the Review page</Link>.
        </p>
      )}

      <QuitCard card={d.quit.card} strip={d.quit.strip} comeback={d.quit.comeback} />

      <section className="card kind-checkin grid gap-4 p-5 sm:p-6">
        <div>
          <h2 className="font-display text-xl font-semibold">How did you wake up?</h2>
          <p className="mt-1 text-sm text-ink-2">
            One tap a morning, before the watch numbers. Over time it shows how you feel on a slip day, the days after,
            and deep into a run.
          </p>
        </div>
        <WakeFeeling today={d.today} ratings={d.feeling.ratings} />
        <div className="grid gap-2 border-t border-line pt-4">
          <h3 className="font-medium">Waking feeling by days since a slip</h3>
          <FeelingByRun data={d.feeling.by_run} />
        </div>
      </section>

      <section className="card kind-habit grid gap-4 p-5 sm:p-6">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-display text-xl font-semibold">Sleep disruptors</h2>
          <Legend
            items={[
              { cls: "cell", text: "Not logged" },
              { cls: "cell cell-h1", text: "Some" },
              { cls: "cell cell-h3", text: "More" },
              { cls: "cell cell-unknown", text: "Nothing logged that day" },
            ]}
          />
        </div>
        <HabitGrid days={d.days} rows={shown} />
        <p className="rounded-xl bg-panel px-3.5 py-2.5 text-sm text-ink-2">
          Dashed days had no journal entries at all, so they are unknown rather than clean.
        </p>
      </section>

      <section className="card kind-checkin grid gap-4 p-5 sm:p-6">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-display text-xl font-semibold">Waking feeling, mood and energy</h2>
          <Legend
            items={[
              { cls: "cell cell-s1", text: "1" },
              { cls: "cell cell-s3", text: "3" },
              { cls: "cell cell-s5", text: "5" },
              { cls: "cell cell-unknown", text: "Nothing logged" },
            ]}
          />
        </div>
        <WellbeingGrid days={d.days} rows={d.wellbeing} />
      </section>

      <HabitManager habits={d.catalog} />
    </div>
  );
}
