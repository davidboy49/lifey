"use client";
import { useState } from "react";
import { Spark } from "./Spark";
import type { Metric } from "@/lib/types";

const RANGES = [7, 14, 28];

// The full trend view with a range toggle. Slicing keeps the baseline and band as computed over the
// whole history, so a short range is a closer look, not a different "usual".
export function TrendChart({ metric, color, endDate }: { metric: Metric; color: string; endDate: string }) {
  const options = RANGES.filter((r) => r < metric.series.length).concat(metric.series.length);
  const [days, setDays] = useState(metric.series.length);
  const shown = { ...metric, series: metric.series.slice(-days) };

  return (
    <div className="grid gap-3">
      <div role="group" aria-label={`${metric.label} range`} className="flex w-fit gap-1 rounded-xl border border-line bg-panel p-1">
        {options.map((r) => (
          <button
            key={r}
            type="button"
            aria-pressed={days === r}
            onClick={() => setDays(r)}
            className={`rounded-lg px-2.5 py-1 font-mono text-xs ${days === r ? "bg-accent-soft text-accent" : "text-ink-2 hover:text-ink"}`}
          >
            {r}d
          </button>
        ))}
      </div>
      <div className="max-w-[760px]">
        <Spark metric={shown} color={color} height={240} axis endDate={endDate} />
      </div>
    </div>
  );
}
