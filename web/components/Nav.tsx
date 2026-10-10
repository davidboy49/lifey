"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ThemeToggle } from "./ThemeToggle";

const ITEMS = [
  { href: "/", label: "Today", d: "M12 3v2m0 14v2M3 12h2m14 0h2M5.6 5.6l1.4 1.4m10 10 1.4 1.4m0-12.8L17 7M7 17l-1.4 1.4M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8Z" },
  { href: "/journal", label: "Journal", d: "M6 3h11a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6V3Zm0 0v18M10 8h5M10 12h5" },
  { href: "/trends", label: "Trends", d: "M3 17l5-6 4 3 8-9M3 21h18" },
  { href: "/money", label: "Money", d: "M4 7h14a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V7Zm0 0V6a2 2 0 0 1 2-2h10M16 14h.01" },
];

function Icon({ d }: { d: string }) {
  return (
    <svg viewBox="0 0 24 24" width={20} height={20} fill="none" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d={d} />
    </svg>
  );
}

const SIGN_OUT_ICON = "M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3M10 17l-5-5 5-5M5 12h11";

export function Nav() {
  const path = usePathname();
  const router = useRouter();

  async function signOut() {
    try {
      await fetch("/api/auth/logout", { method: "POST" });
    } finally {
      router.replace("/login");
      router.refresh();
    }
  }

  const active = (h: string) => (h === "/" ? path === "/" : path.startsWith(h));

  return (
    <>
      <aside className="fixed inset-y-0 left-0 hidden w-[232px] flex-col border-r border-line bg-panel px-4 py-6 md:flex">
        <Link href="/" className="mb-8 px-3 font-display text-[26px] font-semibold tracking-tight">
          lifey<span className="text-accent">.</span>
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

      <nav
        aria-label="Main"
        className="fixed inset-x-0 bottom-0 z-20 flex border-t border-line bg-panel/95 px-2 backdrop-blur md:hidden"
        style={{ paddingBottom: "env(safe-area-inset-bottom, 0px)" }}
      >
        {ITEMS.map((it) => (
          <Link
            key={it.href}
            href={it.href}
            aria-current={active(it.href) ? "page" : undefined}
            className={`flex flex-1 flex-col items-center gap-1 py-2.5 text-[11px] font-medium ${
              active(it.href) ? "text-accent" : "text-ink-3"
            }`}
          >
            <Icon d={it.d} />
            {it.label}
          </Link>
        ))}
        <button type="button" onClick={signOut} className="flex flex-1 flex-col items-center gap-1 py-2.5 text-[11px] font-medium text-ink-3">
          <Icon d={SIGN_OUT_ICON} />
          Sign out
        </button>
      </nav>
    </>
  );
}
