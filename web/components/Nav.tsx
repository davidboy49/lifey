"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ThemeToggle } from "./ThemeToggle";

// The four pages used most sit in the phone's bottom bar; the rest are under "More".
const MOBILE_PRIMARY = ["/", "/journal", "/sleep", "/habits"];

const ITEMS = [
  { href: "/", label: "Today", d: "M12 3v2m0 14v2M3 12h2m14 0h2M5.6 5.6l1.4 1.4m10 10 1.4 1.4m0-12.8L17 7M7 17l-1.4 1.4M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8Z" },
  { href: "/journal", label: "Journal", d: "M6 3h11a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6V3Zm0 0v18M10 8h5M10 12h5" },
  { href: "/sleep", label: "Sleep", d: "M21 12.8A8.5 8.5 0 1 1 11.2 3a6.5 6.5 0 0 0 9.8 9.8Z" },
  { href: "/habits", label: "Habits", d: "M4 6h16M4 12h16M4 18h16M8 3v6M16 9v6M10 15v6" },
  { href: "/review", label: "Review", d: "M9 11l3 3 8-8M20 12v7a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h9" },
  { href: "/trends", label: "Trends", d: "M3 17l5-6 4 3 8-9M3 21h18" },
  { href: "/data", label: "Data", d: "M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3Zm0 0v6c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6" },
  { href: "/money", label: "Money", d: "M4 7h14a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V7Zm0 0V6a2 2 0 0 1 2-2h10M16 14h.01" },
];

const MORE_ICON = "M5 12h.01M12 12h.01M19 12h.01";
const SIGN_OUT_ICON = "M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3M10 17l-5-5 5-5M5 12h11";

function Icon({ d }: { d: string }) {
  return (
    <svg viewBox="0 0 24 24" width={20} height={20} fill="none" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d={d} />
    </svg>
  );
}

export function Nav() {
  const path = usePathname();
  const router = useRouter();
  const [more, setMore] = useState(false);

  useEffect(() => setMore(false), [path]);

  async function signOut() {
    try {
      await fetch("/api/auth/logout", { method: "POST" });
    } finally {
      router.replace("/login");
      router.refresh();
    }
  }

  const active = (h: string) => (h === "/" ? path === "/" : path.startsWith(h));
  const primary = ITEMS.filter((i) => MOBILE_PRIMARY.includes(i.href));
  const secondary = ITEMS.filter((i) => !MOBILE_PRIMARY.includes(i.href));
  const moreActive = secondary.some((i) => active(i.href));

  return (
    <>
      <aside className="fixed inset-y-0 left-0 hidden w-[232px] flex-col border-r border-line bg-panel px-4 py-6 md:flex">
        <Link href="/" className="mb-8 flex items-center gap-3 px-2" aria-label="Lifey home">
          {/* Light tile: the mark's navy figure needs a light ground in dark mode. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/brand/lifey-mark.webp" width={40} height={40} alt="" className="size-10 rounded-xl border border-line" />
          <span className="font-display text-[26px] font-semibold tracking-tight">
            lifey<span className="text-accent">.</span>
          </span>
        </Link>
        <nav className="flex flex-1 flex-col gap-1" aria-label="Main">
          {ITEMS.map((it) => (
            <Link
              key={it.href}
              href={it.href}
              aria-current={active(it.href) ? "page" : undefined}
              className={`flex items-center gap-3 rounded-xl px-3 py-2.5 text-[15px] font-medium transition-colors ${
                active(it.href) ? "bg-accent-soft text-accent" : "text-ink-2 hover:bg-raised hover:text-ink"
              }`}
            >
              <Icon d={it.d} />
              {it.label}
            </Link>
          ))}
        </nav>
        <button
          type="button"
          onClick={signOut}
          className="mb-3 flex items-center gap-3 rounded-xl px-3 py-2.5 text-[15px] font-medium text-ink-2 hover:bg-raised hover:text-ink"
        >
          <Icon d={SIGN_OUT_ICON} />
          Sign out
        </button>
        <ThemeToggle />
      </aside>

      {more && (
        <div className="fixed inset-0 z-20 md:hidden" onClick={() => setMore(false)} aria-hidden>
          <div className="absolute inset-0 bg-ink/30" />
        </div>
      )}
      {more && (
        <div
          className="card fixed inset-x-3 z-30 grid gap-1 p-2 md:hidden"
          style={{ bottom: "calc(env(safe-area-inset-bottom, 0px) + 68px)" }}
          role="menu"
        >
          {secondary.map((it) => (
            <Link
              key={it.href}
              href={it.href}
              role="menuitem"
              className={`flex items-center gap-3 rounded-xl px-3 py-3 text-[15px] font-medium ${active(it.href) ? "bg-accent-soft text-accent" : "text-ink-2"}`}
            >
              <Icon d={it.d} />
              {it.label}
            </Link>
          ))}
          <button type="button" role="menuitem" onClick={signOut} className="flex items-center gap-3 rounded-xl px-3 py-3 text-left text-[15px] font-medium text-ink-2">
            <Icon d={SIGN_OUT_ICON} />
            Sign out
          </button>
          <div className="p-1"><ThemeToggle /></div>
        </div>
      )}

      <nav
        aria-label="Main"
        className="fixed inset-x-0 bottom-0 z-30 flex border-t border-line bg-panel/95 px-2 backdrop-blur md:hidden"
        style={{ paddingBottom: "env(safe-area-inset-bottom, 0px)" }}
      >
        {primary.map((it) => (
          <Link
            key={it.href}
            href={it.href}
            aria-current={active(it.href) ? "page" : undefined}
            className={`flex flex-1 flex-col items-center gap-1 py-2.5 text-[11px] font-medium ${active(it.href) ? "text-accent" : "text-ink-3"}`}
          >
            <Icon d={it.d} />
            {it.label}
          </Link>
        ))}
        <button
          type="button"
          onClick={() => setMore((m) => !m)}
          aria-expanded={more}
          className={`flex flex-1 flex-col items-center gap-1 py-2.5 text-[11px] font-medium ${moreActive || more ? "text-accent" : "text-ink-3"}`}
        >
          <Icon d={MORE_ICON} />
          More
        </button>
      </nav>
    </>
  );
}
