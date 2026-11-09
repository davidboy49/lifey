import Link from "next/link";
import { redirect } from "next/navigation";
import { ApiDown } from "@/components/ApiDown";
import { apiGet } from "@/lib/api";
import { LOOP_TAGS, loopLabel, type ReviewList } from "@/lib/eventReviews";
import { shortDay } from "@/lib/journal";

export const dynamic = "force-dynamic";

const chip = (on: boolean) =>
  `rounded-lg px-3 py-2 text-sm font-medium whitespace-nowrap ${on ? "bg-accent-soft text-accent" : "bg-raised text-ink-2 hover:text-ink"}`;

export default async function ReviewsPage({ searchParams }: { searchParams: Promise<{ tag?: string }> }) {
  const sp = await searchParams;
  const tag = LOOP_TAGS.some((t) => t.tag === sp.tag) ? sp.tag : undefined;
  const res = await apiGet<ReviewList>(`/api/event-reviews${tag ? `?tag=${tag}` : ""}`);
  if (res.status === "unauthorized") redirect("/login");
  if (res.status !== "ok") return <ApiDown />;
  const { reviews, tag_counts } = res.data;
  // Counts over everything, so the filter row stays the same while one tag is picked.
  const all = tag ? await apiGet<ReviewList>("/api/event-reviews") : res;
  const counts = all.status === "ok" ? all.data.tag_counts : tag_counts;

  return (
    <article className="mx-auto flex w-full max-w-[760px] flex-col gap-8">
      <header className="grid gap-4">
        <div className="grid gap-1">
          <p className="eyebrow">Event review</p>
          <h1 className="font-display text-[36px] font-semibold leading-[1.05] tracking-tight sm:text-[46px]">Looking back</h1>
        </div>
        <div className="flex flex-wrap gap-3">
          <Link href="/reviews/new" className="rounded-xl bg-accent px-5 py-3 font-medium text-ground hover:opacity-90">New review</Link>
          <Link href="/reviews/lessons" className="rounded-xl border border-line bg-raised px-5 py-3 font-medium text-ink-2 hover:text-ink">Lessons</Link>
        </div>
      </header>

      <nav aria-label="Filter by loop" className="-mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0">
        <div className="flex gap-2">
          <Link href="/reviews" className={chip(!tag)} aria-current={!tag ? "page" : undefined}>All</Link>
          {LOOP_TAGS.map((t) => (
            <Link key={t.tag} href={`/reviews?tag=${t.tag}`} className={chip(tag === t.tag)} aria-current={tag === t.tag ? "page" : undefined}>
              {t.label} <span className="font-mono text-[12px] opacity-70">{counts[t.tag] ?? 0}</span>
            </Link>
          ))}
        </div>
      </nav>

      {reviews.length === 0 ? (
        <p className="text-ink-2">
          {tag ? `No reviews ticked ${loopLabel(tag)} yet.` : "No reviews yet. After your next event, take two minutes to look back."}
        </p>
      ) : (
        <ul className="grid gap-3">
          {reviews.map((r) => (
            <li key={r.id}>
              <Link href={`/reviews/${r.id}`} className="card grid gap-2 p-4 transition-colors hover:border-accent">
                <div className="flex flex-wrap items-baseline justify-between gap-x-3">
                  <h2 className="font-display text-[20px] font-semibold leading-tight tracking-tight">{r.event}</h2>
                  <span className="font-mono text-[12px] text-ink-3">{shortDay(r.date)} {r.date.slice(0, 4)}</span>
                </div>
                <div className="flex flex-wrap items-center gap-2 text-[13px]">
                  <span className="text-ink-2">Mood <b className="text-ink">{r.mood ?? "·"}</b> · Energy <b className="text-ink">{r.energy ?? "·"}</b></span>
                  {r.loop_tags.map((t) => (
                    <span key={t} className="kind-habit kind-badge rounded-md px-2 py-0.5 font-medium">{loopLabel(t)}</span>
                  ))}
                  {r.photos.length > 0 && <span className="text-ink-3">{r.photos.length} photo{r.photos.length === 1 ? "" : "s"}</span>}
                </div>
                {r.lesson && <p className="text-[15px] text-ink-2">“{r.lesson}”</p>}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </article>
  );
}
