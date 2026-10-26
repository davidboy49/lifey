"use client";
import { useId } from "react";
import { Bar, BarChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { HatchPattern, TICK, TipRow, TipShell, useReducedMotion } from "./chartKit";
import type { SleepNight } from "@/lib/sleep";
import { hm } from "@/lib/sleep";
import { shortDay } from "@/lib/journal";

// One bar per night, oldest to newest. A missing night is an empty dashed slot,
// a partly recorded night is hatched grey, and neither is ever drawn as zero.
interface Row extends SleepNight {
  /** What the bar is drawn from. A missing night borrows a 2 h slot for its dashed outline only. */
  plot: number;
}

const MISSING_SLOT_H = 2;

export function SleepBars({ nights, target, incompleteBelow }: { nights: SleepNight[]; target: number; incompleteBelow: number }) {
  const id = useId().replace(/:/g, "");
  const reduced = useReducedMotion();
  const max = Math.max(10, Math.ceil(Math.max(target + 1, ...nights.map((n) => n.hours ?? 0))));
  const recorded = nights.filter((n) => n.kind === "recorded");
  const mean = recorded.length ? recorded.reduce((a, n) => a + (n.hours ?? 0), 0) / recorded.length : null;
  const rows: Row[] = nights.map((n) => ({ ...n, plot: n.kind === "missing" ? MISSING_SLOT_H : (n.hours ?? 0) }));
  const first = nights[0].date;
  const lastDate = nights[nights.length - 1].date;

  const color = (n: SleepNight) =>
    n.hours === null ? "none" : n.hours >= target ? "var(--good)" : n.hours >= 6 ? "var(--watch)" : "var(--alert)";

  return (
    <div role="img" aria-label={`Hours slept per night, last ${nights.length} nights, against a ${target} hour target. Use the arrow keys to inspect a night.`}>
      <ResponsiveContainer width="100%" height={240} initialDimension={{ width: 760, height: 240 }}>
        <BarChart data={rows} margin={{ top: 14, right: 8, bottom: 0, left: 0 }} barCategoryGap="14%">
          <defs>
            <HatchPattern id={`${id}-hatch`} base="var(--panel)" />
          </defs>
          <CartesianGrid vertical={false} horizontalValues={[0, 4, 8].filter((t) => t <= max)} stroke="var(--line)" />
          <XAxis
            dataKey="date" ticks={[first, lastDate]} interval={0} axisLine={false} tickLine={false} tickMargin={10}
            tick={({ x, y, payload }) => (
              <text x={x} y={Number(y) + 8} textAnchor={payload.value === first ? "start" : "end"} {...TICK}>{shortDay(payload.value)}</text>
            )}
          />
          <YAxis
            width={34} domain={[0, max]} ticks={[0, 4, 8].filter((t) => t <= max)} axisLine={false} tickLine={false}
            tickFormatter={(t) => `${t}h`} tick={TICK}
          />
          <Tooltip
            isAnimationActive={false}
            allowEscapeViewBox={{ x: false, y: true }}
            wrapperStyle={{ outline: "none", zIndex: 20 }}
            cursor={{ fill: "var(--ink-3)", fillOpacity: 0.12 }}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const n = payload[0].payload as Row;
              return (
                <TipShell title={shortDay(n.date)}>
                  {n.kind === "missing" ? (
                    <p className="text-ink-2">No recording</p>
                  ) : (
                    <>
                      <p className="font-mono text-ink">{hm(n.hours)}</p>
                      {n.kind === "incomplete" && (
                        <p className="text-ink-2">Under {incompleteBelow} h, probably an incomplete recording</p>
                      )}
                      {n.hours !== null && (
                        <TipRow label="vs target" value={`${n.hours - target >= 0 ? "+" : "−"}${hm(Math.abs(n.hours - target)).replace(/^0 h /, "")}`} />
                      )}
                      {n.bed && n.wake && <TipRow label="Bed, wake" value={`${n.bed} – ${n.wake}`} />}
                      {n.score !== null && <TipRow label="Sleep score" value={n.score} />}
                      {n.hrv !== null && <TipRow label="HRV" value={`${Math.round(n.hrv)} ms`} />}
                    </>
                  )}
                </TipShell>
              );
            }}
          />
          <Bar
            dataKey="plot" isAnimationActive={!reduced} animationDuration={500} maxBarSize={26}
            shape={(p: { x?: number; y?: number; width?: number; height?: number; payload?: Row }) => {
              const { x = 0, y = 0, width = 0, height = 0, payload: n } = p;
              if (!n) return <g />;
              if (n.kind === "missing") {
                return <rect x={x} y={y} width={width} height={height} rx={3} fill="none" stroke="var(--ink-3)" strokeDasharray="2 3" opacity={0.7} />;
              }
              const h = Math.max(2, height);
              const incomplete = n.kind === "incomplete";
              return (
                <rect
                  x={x} y={y + height - h} width={width} height={h} rx={3}
                  fill={incomplete ? `url(#${id}-hatch)` : color(n)} stroke={incomplete ? "var(--ink-3)" : "none"}
                />
              );
            }}
          />
          <ReferenceLine
            y={target} stroke="var(--accent)" strokeWidth={1.5} strokeDasharray="5 4"
            label={{ value: `target ${target.toFixed(1)} h`, position: "insideTopRight", fill: "var(--accent)", fontSize: 12, fontFamily: "var(--font-mono)" }}
          />
          {mean !== null && <ReferenceLine y={mean} stroke="var(--ink-2)" strokeOpacity={0.65} />}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
