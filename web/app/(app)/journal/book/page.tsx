import Link from "next/link";
import { Newsreader } from "next/font/google";
import { redirect } from "next/navigation";
import { ApiDown } from "@/components/ApiDown";
import { JournalBook, type BookChapter, type BookDay } from "@/components/JournalBook";
import { apiGet } from "@/lib/api";
import { addDays, type JournalEntry, type JournalResponse } from "@/lib/journal";

export const dynamic = "force-dynamic";

const serif = Newsreader({ subsets: ["latin"], variable: "--font-book", style: ["normal", "italic"], axes: ["opsz"] });
const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/;
const ISO_MONTH = /^\d{4}-\d{2}$/;

interface PagesResponse {
  today: string;
  pages: { date: string; notes: number; photos: number }[];
}

function monthOf(iso: string) {
  return iso.slice(0, 7);
}

function monthTitle(month: string) {
  const [y, m] = month.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, 1)).toLocaleDateString("en-GB", { month: "long", year: "numeric", timeZone: "UTC" });
}

function lastDayOf(month: string) {
  const [y, m] = month.split("-").map(Number);
  return new Date(Date.UTC(y, m, 0)).toISOString().slice(0, 10);
}

export default async function JournalBookPage({ searchParams }: {
  searchParams: Promise<{ month?: string; date?: string; at?: string }>;
}) {
  const sp = await searchParams;
  const idx = await apiGet<PagesResponse>("/api/journal/pages");
  if (idx.status === "unauthorized") redirect("/login");
  if (idx.status !== "ok") return <ApiDown />;
  const { today, pages } = idx.data;

  // Chapters are the months that have at least one page; this month always has one (today's page).
  const chapters: BookChapter[] = [];
  for (const p of pages) {
    const m = monthOf(p.date);
    const last = chapters[chapters.length - 1];
    if (last?.month === m) {
      last.days += 1;
      last.notes += p.notes;
      last.photos += p.photos;
    } else {
      chapters.push({ month: m, title: monthTitle(m), days: 1, notes: p.notes, photos: p.photos });
    }
  }

  const wantedDay = sp.date && ISO_DAY.test(sp.date) && sp.date <= today ? sp.date : null;
  const wantedMonth = wantedDay ? monthOf(wantedDay) : sp.month && ISO_MONTH.test(sp.month) ? sp.month : monthOf(today);
  // An empty month is skipped: fall forward to the next chapter that has pages, else the newest.
  const chapter = chapters.find((c) => c.month >= wantedMonth) ?? chapters[chapters.length - 1];
  const i = chapters.indexOf(chapter);

  const from = `${chapter.month}-01`;
  const end = lastDayOf(chapter.month);
  const to = end > today ? today : end;
  const res = await apiGet<JournalResponse>(`/api/journal?from=${from}&to=${to}&kind=all`);
  if (res.status === "unauthorized") redirect("/login");
  if (res.status !== "ok") return <ApiDown />;

  const pageDays = new Set(pages.filter((p) => monthOf(p.date) === chapter.month).map((p) => p.date));
  const days: BookDay[] = [];
  // The book reads forward: oldest day first, and each day's notes in the order they were written.
  for (const g of [...res.data.groups].reverse()) {
    if (g.empty || !pageDays.has(g.date)) continue;
    const chrono = [...g.entries].reverse();
    const notes = chrono.filter((e) => e.kind === "note");
    const checkin = chrono.find((e) => e.kind === "checkin");
    days.push({ date: g.date, notes, feeling: checkin?.badges ?? [], isToday: g.date === today });
  }
  if (chapter.month === monthOf(today) && !days.some((d) => d.isToday)) {
    days.push({ date: today, notes: [] as JournalEntry[], feeling: [], isToday: true });
  }

  const startAt = sp.at === "end" ? "end" : wantedDay ?? (chapter.month === monthOf(today) ? today : null);

  return (
    <div className={`${serif.variable} flex flex-col gap-4`}>
      <header className="book-chrome flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="eyebrow"><Link href="/journal" className="hover:text-ink">Journal</Link> · Book</p>
          <h1 className="font-display text-[28px] font-semibold leading-tight tracking-tight sm:text-[34px]">{chapter.title}</h1>
        </div>
        <details className="relative">
          <summary className="cursor-pointer list-none rounded-xl border border-line bg-raised px-3 py-1.5 text-sm font-medium text-ink-2 hover:text-ink">
            Contents
          </summary>
          <ol className="absolute right-0 z-20 mt-2 max-h-[60dvh] w-64 overflow-auto rounded-xl border border-line bg-raised p-2 shadow-[var(--shadow)]">
            {[...chapters].reverse().map((c) => (
              <li key={c.month}>
                <Link href={`/journal/book?month=${c.month}`} aria-current={c.month === chapter.month ? "page" : undefined}
                      className={`flex items-baseline justify-between gap-3 rounded-lg px-3 py-2 text-sm ${c.month === chapter.month ? "bg-accent-soft text-accent" : "text-ink-2 hover:text-ink"}`}>
                  <span className="font-medium">{c.title}</span>
                  <span className="text-xs text-ink-3">{c.days} {c.days === 1 ? "page" : "pages"}</span>
                </Link>
              </li>
            ))}
          </ol>
        </details>
      </header>

      <JournalBook
        key={chapter.month}
        chapter={chapter}
        days={days}
        today={today}
        startAt={startAt}
        prevHref={i > 0 ? `/journal/book?month=${chapters[i - 1].month}&at=end` : null}
        nextHref={i < chapters.length - 1 ? `/journal/book?month=${chapters[i + 1].month}` : null}
        yesterday={addDays(today, -1)}
      />
    </div>
  );
}
