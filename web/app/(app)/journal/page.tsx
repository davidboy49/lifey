import Link from "next/link";
import { redirect } from "next/navigation";
import { ApiDown } from "@/components/ApiDown";
import { Composer } from "@/components/Composer";
import { EntryRow } from "@/components/EntryRow";
import { SyncControl } from "@/components/SyncControl";
import { apiGet } from "@/lib/api";
import { dayName, shortDay, type JournalResponse } from "@/lib/journal";

export const dynamic = "force-dynamic";

const RANGES = [
  { days: 1, label: "Today" },
  { days: 7, label: "7 days" },
  { days: 30, label: "30 days" },
];
const KINDS = [
  { key: "all", label: "All" },
  { key: "habit", label: "Habits" },
  { key: "quit", label: "Quit" },
  { key: "note", label: "Notes" },
  { key: "checkin", label: "Check-ins" },
  { key: "training", label: "Training" },
];

function href(days: number, kind: string) {
  const q = new URLSearchParams();
  if (days !== 7) q.set("days", String(days));
  if (kind !== "all") q.set("kind", kind);
  const s = q.toString();
  return s ? `/journal?${s}` : "/journal";
}

export default async function JournalPage({ searchParams }: { searchParams: Promise<{ days?: string; kind?: string }> }) {
  const sp = await searchParams;
  const days = [1, 7, 30].includes(Number(sp.days)) ? Number(sp.days) : 7;
  const kind = KINDS.some((k) => k.key === sp.kind) ? (sp.kind as string) : "all";

  const res = await apiGet<JournalResponse>(`/api/journal?days=${days}&kind=${kind}`);
  if (res.status === "unauthorized") redirect("/login");
  if (res.status !== "ok") return <ApiDown />;
  const j = res.data;
  const sync = await apiGet<{ last_run: { finished_at: string | null } | null }>("/api/health/sync");
  const catalog = await apiGet<{ label: string; unit: string }[]>("/api/habits/catalog");
  const syncedAt = sync.status === "ok" ? sync.data.last_run?.finished_at ?? null : null;

  const nowTime = new Date().toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "Asia/Phnom_Penh" });
  const { name, sub } = dayName(j.today, j.today);

  return (
    <div className="flex flex-col gap-7">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow">Journal</p>
          <h1 className="font-display text-[34px] font-semibold leading-tight tracking-tight sm:text-[44px]">
            {name}, <span className="text-ink-3">{sub}</span>
          </h1>
        </div>
        <SyncControl syncedAt={syncedAt} />
      </header>

      <section className="grid grid-cols-2 gap-3 sm:grid-cols-4" aria-label="Today at a glance">
        <div className="card p-4"><p className="eyebrow">Mood</p><p className="font-display text-[28px] font-semibold leading-tight">{j.summary.mood ?? "·"}<span className="text-sm font-normal text-ink-3">{j.summary.mood !== null ? " / 5" : ""}</span></p></div>
        <div className="card p-4"><p className="eyebrow">Energy</p><p className="font-display text-[28px] font-semibold leading-tight">{j.summary.energy ?? "·"}<span className="text-sm font-normal text-ink-3">{j.summary.energy !== null ? " / 5" : ""}</span></p></div>
        <div className="card p-4"><p className="eyebrow">Habits today</p><p className="font-display text-[28px] font-semibold leading-tight">{j.summary.habits_today.length}</p><p className="truncate text-xs text-ink-3">{j.summary.habits_today.join(" · ") || "None logged"}</p></div>
        <div className="card p-4"><p className="eyebrow">Days free</p><p className="font-display text-[28px] font-semibold leading-tight">{j.summary.days_free ?? "·"}</p><p className="text-xs text-ink-3">{j.summary.best_run !== null ? `best ${j.summary.best_run}` : "Not tracking yet"}</p></div>
      </section>

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_380px]">
        <div className="order-2 grid min-w-0 gap-5 lg:order-1">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <nav aria-label="Kind" className="flex flex-wrap gap-2">
              {KINDS.map((k) => (
                <Link
                  key={k.key}
                  href={href(days, k.key)}
                  aria-current={kind === k.key ? "true" : undefined}
                  className={`rounded-full border px-3 py-1.5 text-sm font-medium ${kind === k.key ? "border-accent bg-accent-soft text-accent" : "border-line bg-raised text-ink-2 hover:text-ink"}`}
                >
                  {k.label}
                </Link>
              ))}
            </nav>
            <nav aria-label="Range" className="flex gap-1 rounded-xl border border-line bg-raised p-1">
              {RANGES.map((r) => (
                <Link
                  key={r.days}
                  href={href(r.days, kind)}
                  aria-current={days === r.days ? "true" : undefined}
                  className={`rounded-lg px-3 py-1.5 text-sm font-medium ${days === r.days ? "bg-accent-soft text-accent" : "text-ink-2 hover:text-ink"}`}
                >
                  {r.label}
                </Link>
              ))}
            </nav>
          </div>

          {j.count === 0 && !j.groups.some((g) => g.empty) && (
            <div className="hatch card p-6 text-ink-2">No {kind === "all" ? "entries" : kind} in this range. Try another filter or range.</div>
          )}

          {j.groups.map((g) =>
            g.empty ? (
              <section key={`${g.first}-${g.last}`} className="grid gap-2 sm:grid-cols-[96px_1fr] sm:gap-4">
                <h2 className="font-display text-lg font-semibold">
                  {g.first === g.last ? shortDay(g.first) : `${shortDay(g.first)} – ${shortDay(g.last)}`}
                </h2>
                <p className="hatch rounded-2xl border border-dashed border-ink-3/50 px-4 py-3 text-sm text-ink-2">
                  Nothing logged. Counted as unknown, not as a clean day.
                </p>
              </section>
            ) : (
              <section key={g.date} className="grid gap-2 sm:grid-cols-[96px_1fr] sm:gap-4">
                <div>
                  <h2 className="font-display text-lg font-semibold">{dayName(g.date, j.today).name}</h2>
                  <p className="text-xs text-ink-3">{dayName(g.date, j.today).sub || `${g.entries.length} ${g.entries.length === 1 ? "entry" : "entries"}`}</p>
                </div>
                <ol className="grid gap-2">
                  {g.entries.map((e) => (
                    <EntryRow key={e.ids.join("-")} entry={e} />
                  ))}
                </ol>
              </section>
            ),
          )}
        </div>

        <div className="order-1 lg:order-2">
          <Composer today={j.today} nowTime={nowTime} habits={catalog.status === "ok" ? catalog.data : undefined} />
        </div>
      </div>
    </div>
  );
}
