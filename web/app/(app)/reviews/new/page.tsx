import Link from "next/link";
import { EventReviewForm } from "@/components/EventReviewForm";

export const dynamic = "force-dynamic";

export default function NewReviewPage() {
  return (
    <article className="mx-auto flex w-full max-w-[760px] flex-col gap-8">
      <header className="grid gap-1">
        <Link href="/reviews" className="font-mono text-xs text-ink-3 hover:text-accent">← All reviews</Link>
        <h1 className="font-display text-[36px] font-semibold leading-[1.05] tracking-tight sm:text-[46px]">Look back</h1>
        <p className="text-ink-2">About two minutes. Only the event and date are needed.</p>
      </header>
      <EventReviewForm />
    </article>
  );
}
