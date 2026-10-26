"use client";
// Small pieces shared by the Recharts charts: tooltip shell, axis text style, and a reduced-motion flag.
import { useEffect, useState, type ReactNode } from "react";

export const TICK = { fill: "var(--ink-3)", fontSize: 12, fontFamily: "var(--font-mono)" } as const;

export function useReducedMotion() {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const q = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(q.matches);
    const on = () => setReduced(q.matches);
    q.addEventListener("change", on);
    return () => q.removeEventListener("change", on);
  }, []);
  return reduced;
}

export function TipShell({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="pointer-events-none w-max max-w-[200px] rounded-xl border border-line bg-raised px-3 py-2 text-xs shadow-lg">
      <p className="font-medium text-ink">{title}</p>
      {children}
    </div>
  );
}

export function TipRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <p className="flex items-baseline justify-between gap-3 text-ink-2">
      <span className="whitespace-nowrap">{label}</span>
      <span className="whitespace-nowrap font-mono text-ink">{value}</span>
    </p>
  );
}

// Diagonal hatching for "no reading" and "partly recorded": never a flat zero.
export function HatchPattern({ id, base = "var(--raised)", opacity = 0.5 }: { id: string; base?: string; opacity?: number }) {
  return (
    <pattern id={id} width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
      <rect width="6" height="6" fill={base} />
      <line x1="0" y1="0" x2="0" y2="6" stroke="var(--ink-3)" strokeWidth="1.4" opacity={opacity} />
    </pattern>
  );
}
