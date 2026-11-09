import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { ApiDown } from "@/components/ApiDown";
import { EventReviewDetail } from "@/components/EventReviewDetail";
import { apiGet } from "@/lib/api";
import type { EventReview } from "@/lib/eventReviews";

export const dynamic = "force-dynamic";

export default async function ReviewPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!/^\d+$/.test(id)) notFound();
  const res = await apiGet<EventReview>(`/api/event-reviews/${id}`);
  if (res.status === "unauthorized") redirect("/login");
  if (res.status !== "ok") {
    // apiGet folds a 404 into "down"; tell the two apart with the list.
    const list = await apiGet<{ reviews: EventReview[] }>("/api/event-reviews");
    if (list.status === "ok") notFound();
    return <ApiDown />;
  }
  return (
    <article className="mx-auto flex w-full max-w-[760px] flex-col gap-6">
      <Link href="/reviews" className="font-mono text-xs text-ink-3 hover:text-accent">← All reviews</Link>
      <EventReviewDetail key={res.data.updated_at} initial={res.data} />
    </article>
  );
}
