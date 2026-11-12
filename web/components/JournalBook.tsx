"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { BookWriter } from "@/components/BookWriter";
import type { Attachment, JournalEntry } from "@/lib/journal";

export interface BookChapter {
  month: string;
  title: string;
  days: number;
  notes: number;
  photos: number;
}

export interface BookDay {
  date: string;
  notes: JournalEntry[];
  feeling: string[];
  isToday: boolean;
}

const PAD_X = 36;       // page margin, left and right of each page
const PAD_TOP = 56;     // matches --book-pad-top so ruled lines sit under the text
const PAD_BOTTOM = 48;
const SPREAD_MIN = 760; // a two-page spread from this width (iPad landscape and up)
const SWIPE_PX = 48;

function longDay(iso: string) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString("en-GB", {
    weekday: "long", day: "numeric", month: "long", timeZone: "UTC",
  });
}

function Photo({ a, tilt }: { a: Attachment; tilt: number }) {
  const ratio = a.width && a.height ? `${a.width} / ${a.height}` : "4 / 3";
  return (
    <a href={`/api/attachments/${a.id}`} target="_blank" rel="noopener noreferrer"
       className="book-keep my-3 block w-fit max-w-full bg-white p-2 pb-6 shadow-[0_6px_18px_-8px_rgb(0_0_0/0.45)]"
       style={{ transform: `rotate(${tilt}deg)` }}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={`/api/attachments/${a.id}/thumb`} alt={a.filename} width={a.width ?? undefined} height={a.height ?? undefined}
           className="block max-h-[230px] w-auto max-w-full object-cover" style={{ aspectRatio: ratio }} />
    </a>
  );
}

export function JournalBook({ chapter, days, today, yesterday, startAt, prevHref, nextHref }: {
  chapter: BookChapter;
  days: BookDay[];
  today: string;
  yesterday: string;
  startAt: string | null;   // a date to open at, "end" for the last page, or null for the chapter title
  prevHref: string | null;
  nextHref: string | null;
}) {
  const router = useRouter();
  const viewport = useRef<HTMLDivElement>(null);
  const flow = useRef<HTMLDivElement>(null);
  const end = useRef<HTMLSpanElement>(null);
  const [spread, setSpread] = useState(false);
  const [page, setPage] = useState(0);        // index of the left-most visible page
  const [count, setCount] = useState(1);
  const [ready, setReady] = useState(false);
  const [sweep, setSweep] = useState<{ dir: 1 | -1; n: number } | null>(null);
  const [shift, setShift] = useState({ x: 0, animate: false });
  const opened = useRef(false);
  const turned = useRef(false);   // until the reader turns a page, a re-layout re-opens at startAt
  const pageRef = useRef(0);
  pageRef.current = page;

  const per = spread ? 2 : 1;

  /** Page index an element starts on, from where the column layout put it. */
  const pageOf = useCallback((el: Element) => {
    const v = viewport.current!;
    const stride = v.clientWidth / (v.clientWidth >= SPREAD_MIN ? 2 : 1);
    // Both rects carry the same translateX, so the difference is the element's place in the column flow.
    const left = el.getBoundingClientRect().left - flow.current!.getBoundingClientRect().left;
    return Math.max(0, Math.floor((left + 1) / stride));
  }, []);

  const measure = useCallback(() => {
    const v = viewport.current;
    if (!v || !end.current) return;
    const isSpread = v.clientWidth >= SPREAD_MIN;
    setSpread(isSpread);
    const total = pageOf(end.current) + 1;
    setCount(total);
    return { isSpread, total };
  }, [pageOf]);

  const go = useCallback((target: number, animate = true) => {
    const v = viewport.current;
    if (!v) return;
    const isSpread = v.clientWidth >= SPREAD_MIN;
    const step = isSpread ? 2 : 1;
    const total = end.current ? pageOf(end.current) + 1 : 1;
    let p = Math.max(0, Math.min(target, total - 1));
    p -= p % step; // a spread always starts on an even page
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (animate && p !== pageRef.current) setSweep({ dir: p > pageRef.current ? 1 : -1, n: Date.now() });
    // A transform, not scrollLeft: scrolling is clamped at the content edge and would cut the last page short.
    setShift({ x: -(p / step) * v.clientWidth, animate: animate && !reduce });
    setPage(p);
  }, [pageOf]);

  // Lay out, then open at the asked-for day (or the end); re-measure when the size or fonts change.
  const openTarget = useCallback(() => {
    if (startAt === "end") return Number.MAX_SAFE_INTEGER;
    const el = startAt ? flow.current?.querySelector(`[data-day="${startAt}"]`) : null;
    return el ? pageOf(el) : 0;
  }, [startAt, pageOf]);

  useLayoutEffect(() => {
    if (opened.current || !measure()) return;
    opened.current = true;
    go(openTarget(), false);
    setReady(true);
  }, [measure, go, openTarget]);

  useEffect(() => {
    const v = viewport.current;
    if (!v) return;
    const again = () => {
      // Fonts and photos settle after the first layout; rotation changes the page size.
      // Before the first turn, re-open where asked; after it, keep the same page in view.
      measure();
      go(turned.current ? pageRef.current : openTarget(), false);
    };
    const ro = new ResizeObserver(again);
    ro.observe(v);
    // The flow box never changes size when pages are added, so also re-measure when a photo loads.
    const f = flow.current;
    f?.addEventListener("load", again, true);
    document.fonts?.ready.then(again);
    return () => {
      ro.disconnect();
      f?.removeEventListener("load", again, true);
    };
  }, [measure, go, openTarget]);

  const atStart = page === 0;
  const atEnd = page + per >= count;
  const back = useCallback(() => {
    turned.current = true;
    if (atStart) { if (prevHref) router.push(prevHref); } else go(page - per);
  }, [atStart, prevHref, router, go, page, per]);
  const forward = useCallback(() => {
    turned.current = true;
    if (atEnd) { if (nextHref) router.push(nextHref); } else go(page + per);
  }, [atEnd, nextHref, router, go, page, per]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const t = e.target as HTMLElement;
      if (t.closest("textarea, input, select, [contenteditable]")) return;
      if (e.key === "ArrowLeft") back();
      if (e.key === "ArrowRight") forward();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [back, forward]);

  // Swipe to turn on touch screens; a gesture that starts in the writing area is left alone.
  const touch = useRef<{ x: number; y: number } | null>(null);
  function onPointerDown(e: React.PointerEvent) {
    if (e.pointerType === "mouse" || (e.target as HTMLElement).closest("textarea, input, button, a, label")) return;
    touch.current = { x: e.clientX, y: e.clientY };
  }
  function onPointerUp(e: React.PointerEvent) {
    const t = touch.current;
    touch.current = null;
    if (!t) return;
    const dx = e.clientX - t.x;
    const dy = e.clientY - t.y;
    if (Math.abs(dx) < SWIPE_PX || Math.abs(dx) < Math.abs(dy) * 1.5) return;
    if (dx < 0) forward();
    else back();
  }

  const saved = useCallback(() => {
    router.refresh();
    // The new note lands at the end of today's page; follow it there once the layout settles.
    turned.current = true;
    setTimeout(() => {
      measure();
      go(Number.MAX_SAFE_INTEGER, false);
    }, 400);
  }, [router, measure, go]);

  const pageNo = (offset: number) => page + offset + 1;
  const navBtn = "grid size-11 place-items-center rounded-full border border-line bg-raised text-lg text-ink-2 hover:text-ink disabled:opacity-30";

  return (
    <section aria-label={`Journal book, ${chapter.title}`} className="flex flex-col gap-3">
      <div
        className="book-paper relative overflow-hidden rounded-[10px] border border-[var(--paper-edge)] shadow-[0_1px_0_var(--paper-edge),0_3px_0_-1px_var(--paper-edge),0_5px_0_-2px_var(--paper-edge),0_24px_48px_-24px_rgb(0_0_0/0.5)]"
        style={{ ["--book-pad-top" as string]: `${PAD_TOP}px` }}
      >
        <div
          ref={viewport}
          onPointerDown={onPointerDown}
          onPointerUp={onPointerUp}
          onPointerCancel={() => (touch.current = null)}
          className={`relative h-[calc(100dvh-15rem)] min-h-[440px] overflow-hidden [touch-action:pan-y] md:h-[calc(100dvh-12rem)] ${ready ? "" : "opacity-0"}`}
        >
          <div
            ref={flow}
            className="book-flow h-full font-[family-name:var(--font-book)] text-[17px]"
            style={{
              transform: `translateX(${shift.x}px)`,
              transition: shift.animate ? "transform 460ms cubic-bezier(.3,.7,.2,1)" : "none",
              columnCount: spread ? 2 : 1,
              columnGap: PAD_X * 2,
              padding: `${PAD_TOP}px ${PAD_X}px ${PAD_BOTTOM}px`,
            }}
          >
            <div className="book-chapter book-keep flex flex-col items-center pt-16 text-center">
              <p className="text-xs uppercase tracking-[0.3em] text-[var(--paper-ink-2)]">Chapter</p>
              <h2 className="mt-3 text-[40px] italic leading-[56px]">{chapter.title}</h2>
              <p className="mt-6 text-[var(--paper-ink-2)]">
                {chapter.days} {chapter.days === 1 ? "day" : "days"} · {chapter.notes} {chapter.notes === 1 ? "note" : "notes"}
                {chapter.photos > 0 ? ` · ${chapter.photos} ${chapter.photos === 1 ? "photo" : "photos"}` : ""}
              </p>
              <p className="mt-10 text-sm italic text-[var(--paper-ink-2)]">Days with nothing written are left out.</p>
            </div>

            {days.map((d) => {
              let tilt = 0;
              return (
                <article key={d.date} data-day={d.date} className="book-day">
                  <header className="book-keep">
                    <h3 className="text-[26px] italic leading-[56px]">
                      {d.isToday ? "Today" : d.date === yesterday ? "Yesterday" : longDay(d.date)}
                    </h3>
                    <p className="text-sm leading-[28px] text-[var(--paper-ink-2)]">
                      {d.isToday || d.date === yesterday ? longDay(d.date) : ""}
                      {d.feeling.length > 0 ? `${d.isToday || d.date === yesterday ? " · " : ""}${d.feeling.join(" · ")}` : ""}
                    </p>
                  </header>
                  {d.notes.map((n) => (
                    <div key={n.ids.join("-")} className="mt-[28px]">
                      <p className="text-xs leading-[28px] tracking-wide text-[var(--paper-ink-2)]">
                        {n.time}{n.recalled ? " · written later" : ""}
                      </p>
                      {n.note && <p className="whitespace-pre-line [overflow-wrap:anywhere]">{n.note}</p>}
                      {(n.attachments ?? []).filter((a) => a.has_thumb).map((a) => {
                        tilt = tilt >= 0 ? -1.6 : 1.4;
                        return <Photo key={a.id} a={a} tilt={tilt} />;
                      })}
                      {(n.attachments ?? []).filter((a) => !a.has_thumb).map((a) => (
                        <a key={a.id} href={`/api/attachments/${a.id}`} download={a.filename}
                           className="block text-sm text-[var(--paper-ink-2)] underline [overflow-wrap:anywhere]">{a.filename}</a>
                      ))}
                    </div>
                  ))}
                  {d.isToday && <BookWriter today={today} onSaved={saved} empty={d.notes.length === 0} />}
                </article>
              );
            })}
            <span ref={end} aria-hidden className="block h-px" />
          </div>
        </div>

        {/* Spine and page-turn shading sit over the paper and never catch a tap. */}
        {spread && (
          <div aria-hidden className="pointer-events-none absolute inset-y-0 left-1/2 w-16 -translate-x-1/2 bg-[linear-gradient(to_right,transparent,rgb(0_0_0/0.10)_45%,rgb(0_0_0/0.16)_50%,rgb(0_0_0/0.10)_55%,transparent)]" />
        )}
        {sweep && (
          <div key={sweep.n} aria-hidden onAnimationEnd={() => setSweep(null)}
               className="book-sweep pointer-events-none absolute inset-y-0 w-1/3 bg-[linear-gradient(to_right,transparent,rgb(0_0_0/0.18),transparent)]"
               style={{ left: sweep.dir > 0 ? "66%" : "0%", ["--sweep-from" as string]: "0%", ["--sweep-to" as string]: sweep.dir > 0 ? "-180%" : "180%" }} />
        )}
        <div aria-hidden className="pointer-events-none absolute inset-x-0 bottom-3 flex text-xs text-[var(--paper-ink-2)]">
          <span className={`${spread ? "w-1/2" : "w-full"} text-center`}>{pageNo(0)}</span>
          {spread && pageNo(1) <= count && <span className="w-1/2 text-center">{pageNo(1)}</span>}
        </div>
      </div>

      <nav aria-label="Pages" className="book-chrome flex items-center justify-between gap-3">
        <button type="button" onClick={back} disabled={atStart && !prevHref} className={navBtn}
                aria-label={atStart ? "Previous chapter" : "Previous page"}>‹</button>
        <p className="text-sm text-ink-2">
          {atStart && prevHref ? "Turn back for last month · " : ""}
          Page {pageNo(0)}{spread && pageNo(1) <= count ? `–${pageNo(1)}` : ""} of {count}
          {atEnd && nextHref ? " · Turn on for next month" : ""}
        </p>
        <div className="flex items-center gap-2">
          {!days.some((d) => d.isToday) && (
            <Link href={`/journal/book?date=${today}`} className="rounded-xl border border-line bg-raised px-3 py-2 text-sm font-medium text-ink-2 hover:text-ink">
              Today
            </Link>
          )}
          <button type="button" onClick={forward} disabled={atEnd && !nextHref} className={navBtn}
                  aria-label={atEnd ? "Next chapter" : "Next page"}>›</button>
        </div>
      </nav>
    </section>
  );
}
