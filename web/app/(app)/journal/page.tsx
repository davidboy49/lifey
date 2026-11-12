import Link from "next/link";
import { redirect } from "next/navigation";
import { ApiDown } from "@/components/ApiDown";
import { Composer } from "@/components/Composer";
import { EntryRow } from "@/components/EntryRow";
import { Memories } from "@/components/Memories";
import { SyncControl } from "@/components/SyncControl";
import { apiGet } from "@/lib/api";
import { addDays, dayName, shortDay, type JournalResponse, type Memory } from "@/lib/journal";

export const dynamic = "force-dynamic";

const RANGES = [
  { days: 1, label: "Today" },
  { days: 7, label: "7 days" },
  { days: 30, label: "30 days" },
];
const MAX_RANGE_DAYS = 366;
const ISO = /^\d{4}-\d{2}-\d{2}$/;

/** A range is either "the last N days" or an explicit from–to (inclusive). */
type Range = { days: number } | { from: string; to: string };

// The journal is notes and photos. Habits, quit and check-in entries live on the Habits page,
// and are only mixed in here through "Everything" (or an old ?kind=habit link).
const KINDS = [
  { key: "note", label: "Notes" },
  { key: "photos", label: "Photos" },
  { key: "all", label: "Everything" },
];
const LEGACY_KINDS = ["habit", "quit", "checkin", "training"];

function pill(on: boolean) {
  return `rounded-lg px-3 py-1.5 text-sm font-medium ${on ? "bg-accent-soft text-accent" : "text-ink-2 hover:text-ink"}`;
}

/** Today in the person's time zone, used only to sanity-check the URL before the API answers. */
function todayLocal(): string {
  return new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Phnom_Penh" });
}

function href(range: Range, kind: string) {
  const q = new URLSearchParams();
  if ("from" in range) {
    q.set("from", range.from);
    q.set("to", range.to);
  } else if (range.days !== 7) q.set("days", String(range.days));
  if (kind !== "note") q.set("kind", kind);
  const s = q.toString();
  return s ? `/journal?${s}` : "/journal";
}

function spanDays(from: string, to: string): number {
  return Math.round((Date.parse(`${to}T00:00:00Z`) - Date.parse(`${from}T00:00:00Z`)) / 86_400_000) + 1;
}

function monthStart(iso: string, delta = 0): string {
  const [y, m] = iso.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1 + delta, 1)).toISOString().slice(0, 10);
}

function monthEnd(iso: string): string {
  return addDays(monthStart(iso, 1), -1);
}

function monthLabel(iso: string): string {
  const [y, m] = iso.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, 1)).toLocaleDateString("en-GB", { month: "long", year: "numeric", timeZone: "UTC" });
}

/** Read the range from the URL, falling back to 7 days for anything malformed. */
function parseRange(sp: { days?: string; from?: string; to?: string }, today: string): Range {
  if (sp.from && ISO.test(sp.from)) {
    let to = sp.to && ISO.test(sp.to) ? sp.to : today;
    if (to > today) to = today;
    let from = sp.from;
    if (from > to) [from, to] = [to, from];
    if (spanDays(from, to) > MAX_RANGE_DAYS) from = addDays(to, -(MAX_RANGE_DAYS - 1));
    return { from, to };
  }
  const days = Number(sp.days);
  return { days: [1, 7, 30].includes(days) ? days : 7 };
}

export default async function JournalPage({ searchParams }: {
  searchParams: Promise<{ days?: string; kind?: string; from?: string; to?: string }>;
}) {
  const sp = await searchParams;
  const today = todayLocal();
  const range = parseRange(sp, today);
  const known = [...KINDS.map((k) => k.key), ...LEGACY_KINDS];
  const kind = known.includes(sp.kind ?? "") ? (sp.kind as string) : "note";

  // "Photos" is a notes view narrowed to entries that carry a file; the API has no filter for it.
  const rangeQuery = "from" in range ? `from=${range.from}&to=${range.to}` : `days=${range.days}`;
  const res = await apiGet<JournalResponse>(`/api/journal?${rangeQuery}&kind=${kind === "photos" ? "note" : kind}`);
  if (res.status === "unauthorized") redirect("/login");
  if (res.status !== "ok") return <ApiDown />;
  const j: JournalResponse = kind === "photos"
    ? {
        ...res.data,
        groups: res.data.groups
          .map((g) => (g.empty ? g : { ...g, entries: g.entries.filter((e) => (e.attachments?.length ?? 0) > 0) }))
          .filter((g) => !g.empty && g.entries.length > 0),
      }
    : res.data;
  if (kind === "photos") j.count = j.groups.reduce((n, g) => n + (g.empty ? 0 : g.entries.length), 0);
  const photoCount = j.groups.reduce(
    (n, g) => n + (g.empty ? 0 : g.entries.reduce((m, e) => m + (e.attachments?.filter((a) => a.has_thumb).length ?? 0), 0)),
    0,
  );
  // Month shortcuts are built from the API's "today" (the person's local day), not the server clock.
  const thisMonth = { from: monthStart(j.today), to: j.today };
  const lastMonth = { from: monthStart(j.today, -1), to: monthEnd(monthStart(j.today, -1)) };
  const thisYear = { from: `${j.today.slice(0, 4)}-01-01`, to: j.today };
  const isRange = (r: { from: string; to: string }) => "from" in range && range.from === r.from && range.to === r.to;
  const presets = [
    { key: "month", label: "This month", range: thisMonth },
    { key: "last-month", label: "Last month", range: lastMonth },
    { key: "year", label: "This year", range: thisYear },
  ];
  const activePreset = presets.find((p) => isRange(p.range));
  const isCustom = "from" in range && !activePreset;
  // A whole calendar month (or this month so far) gets a ‹ month › stepper.
  const shownMonth = "from" in range && range.from === monthStart(range.from)
    && (range.to === monthEnd(range.from) || (range.to === j.today && monthStart(j.today) === range.from))
    ? range.from : null;
  const monthRange = (start: string) => ({ from: start, to: monthEnd(start) > j.today ? j.today : monthEnd(start) });
  const rangeLabel = "from" in range
    ? activePreset?.label.toLowerCase() ?? (range.from === range.to ? shortDay(range.from) : `${shortDay(range.from)} – ${shortDay(range.to)}`)
    : RANGES.find((r) => r.days === range.days)?.label.toLowerCase() ?? `${range.days} days`;
  const sync = await apiGet<{ last_run: { finished_at: string | null } | null }>("/api/health/sync");
  const catalog = await apiGet<{ label: string; unit: string }[]>("/api/habits/catalog");
  const mem = await apiGet<{ memories: Memory[] }>("/api/journal/memories");
  const memories = mem.status === "ok" ? mem.data.memories : [];
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
        <div className="flex items-center gap-2">
          <Link href="/journal/book" className="rounded-xl border border-line bg-raised px-3 py-2 text-sm font-medium text-ink-2 hover:text-ink">
            Open as book
          </Link>
          <SyncControl syncedAt={syncedAt} />
        </div>
      </header>

      <section className="grid grid-cols-2 gap-3 sm:grid-cols-4" aria-label="Today at a glance">
        <div className="card p-4"><p className="eyebrow">Mood</p><p className="font-display text-[28px] font-semibold leading-tight">{j.summary.mood ?? "·"}<span className="text-sm font-normal text-ink-3">{j.summary.mood !== null ? " / 5" : ""}</span></p></div>
        <div className="card p-4"><p className="eyebrow">Energy</p><p className="font-display text-[28px] font-semibold leading-tight">{j.summary.energy ?? "·"}<span className="text-sm font-normal text-ink-3">{j.summary.energy !== null ? " / 5" : ""}</span></p></div>
        <div className="card p-4"><p className="eyebrow">Notes today</p><p className="font-display text-[28px] font-semibold leading-tight">{j.summary.notes_today}</p></div>
        <div className="card p-4"><p className="eyebrow">Photos</p><p className="font-display text-[28px] font-semibold leading-tight">{photoCount}</p><p className="text-xs text-ink-3">{rangeLabel}</p></div>
      </section>

      <Memories items={memories} />

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_380px]">
        <div className="order-2 grid min-w-0 gap-5 lg:order-1">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <nav aria-label="Kind" className="flex flex-wrap gap-2">
              {KINDS.map((k) => (
                <Link
                  key={k.key}
                  href={href(range, k.key)}
                  aria-current={kind === k.key ? "true" : undefined}
                  className={`rounded-full border px-3 py-1.5 text-sm font-medium ${kind === k.key ? "border-accent bg-accent-soft text-accent" : "border-line bg-raised text-ink-2 hover:text-ink"}`}
                >
                  {k.label}
                </Link>
              ))}
            </nav>
            <nav aria-label="Range" className="flex flex-wrap gap-1 rounded-xl border border-line bg-raised p-1">
              {RANGES.map((r) => {
                const on = "days" in range && range.days === r.days;
                return (
                  <Link key={r.days} href={href({ days: r.days }, kind)} aria-current={on ? "true" : undefined} className={pill(on)}>
                    {r.label}
                  </Link>
                );
              })}
              {presets.map((p) => (
                <Link key={p.key} href={href(p.range, kind)} aria-current={activePreset?.key === p.key ? "true" : undefined}
                      className={pill(activePreset?.key === p.key)}>
                  {p.label}
                </Link>
              ))}
            </nav>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3">
            {shownMonth ? (
              <nav aria-label="Month" className="flex items-center gap-1">
                <Link href={href(monthRange(monthStart(shownMonth, -1)), kind)} aria-label="Previous month"
                      className="grid size-9 place-items-center rounded-lg border border-line bg-raised text-ink-2 hover:text-ink">‹</Link>
                <span className="min-w-[9.5rem] text-center font-display text-lg font-semibold">{monthLabel(shownMonth)}</span>
                {monthStart(shownMonth, 1) <= j.today ? (
                  <Link href={href(monthRange(monthStart(shownMonth, 1)), kind)} aria-label="Next month"
                        className="grid size-9 place-items-center rounded-lg border border-line bg-raised text-ink-2 hover:text-ink">›</Link>
                ) : <span className="size-9" aria-hidden />}
              </nav>
            ) : (
              <p className="text-sm text-ink-2">
                {"from" in range ? `${shortDay(range.from)} – ${shortDay(range.to)}` : `Last ${range.days === 1 ? "day" : `${range.days} days`}`}
                {" · "}{j.count} {j.count === 1 ? "entry" : "entries"}
              </p>
            )}
            <details className="group relative" open={isCustom || undefined}>
              <summary className={`${pill(isCustom)} cursor-pointer list-none rounded-xl border border-line bg-raised`}>Custom range</summary>
              <form action="/journal" method="get"
                    className="mt-2 flex flex-wrap items-end gap-2 rounded-xl border border-line bg-raised p-3 sm:absolute sm:right-0 sm:z-10 sm:shadow-[var(--shadow)]">
                {kind !== "note" && <input type="hidden" name="kind" value={kind} />}
                <label className="grid gap-1 text-xs text-ink-3">From
                  <input type="date" name="from" required max={j.today} defaultValue={"from" in range ? range.from : j.start}
                         className="rounded-lg border border-line bg-panel px-2 py-1.5 text-sm text-ink" />
                </label>
                <label className="grid gap-1 text-xs text-ink-3">To
                  <input type="date" name="to" required max={j.today} defaultValue={"from" in range ? range.to : j.today}
                         className="rounded-lg border border-line bg-panel px-2 py-1.5 text-sm text-ink" />
                </label>
                <button type="submit" className="rounded-lg bg-accent px-3 py-1.5 text-sm font-semibold text-white">Show</button>
                <p className="basis-full text-xs text-ink-3">Up to a year at a time.</p>
              </form>
            </details>
          </div>

          {j.count === 0 && !j.groups.some((g) => g.empty) && (
            <div className="hatch card p-6 text-ink-2">No {kind === "all" ? "entries" : kind === "photos" ? "photos" : kind === "note" ? "notes" : kind} in this range. Try another filter or range.</div>
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
