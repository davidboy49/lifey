import Link from "next/link";
import { redirect } from "next/navigation";
import { ApiDown } from "@/components/ApiDown";
import { apiGet } from "@/lib/api";
import { longDay } from "@/lib/eventReviews";

export const dynamic = "force-dynamic";

type Lesson = { id: number; date: string; event: string; lesson: string };

export default async function LessonsPage() {
  const res = await apiGet<{ lessons: Lesson[] }>("/api/event-reviews/lessons");
  if (res.status === "unauthorized") redirect("/login");
  if (res.status !== "ok") return <ApiDown />;
  const lessons = res.data.lessons;

  return (
    <article className="mx-auto flex w-full max-w-[760px] flex-col gap-8">
      <header className="grid gap-1">
        <Link href="/reviews" className="font-mono text-xs text-ink-3 hover:text-accent">← All reviews</Link>
        <h1 className="font-display text-[36px] font-semibold leading-[1.05] tracking-tight sm:text-[46px]">Lessons</h1>
        <p className="text-ink-2">{lessons.length} line{lessons.length === 1 ? "" : "s"} to carry forward.</p>
      </header>
      {lessons.length === 0 ? (
        <p className="text-ink-2">No lessons yet. Add one at the end of your next review.</p>
      ) : (
        <ol className="grid gap-2">
          {lessons.map((l) => (
            <li key={l.id}>
              <Link href={`/reviews/${l.id}`} className="grid gap-0.5 rounded-xl border border-line bg-panel px-4 py-3 hover:border-accent">
                <span className="text-[16px]">{l.lesson}</span>
                <span className="font-mono text-[11.5px] text-ink-3">{longDay(l.date)} · {l.event}</span>
              </Link>
            </li>
          ))}
        </ol>
      )}
    </article>
  );
}
