"use client";
// One chart for both the card sparkline and the full trend view. A day with no reading breaks the
// line and is shaded as a hatched gap; nothing is interpolated.
import { useId } from "react";
import { Area, AreaChart, ReferenceArea, ReferenceDot, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { HatchPattern, TICK, TipRow, TipShell, useReducedMotion } from "./chartKit";
import { addDays, shortDay } from "@/lib/journal";
import type { Metric } from "@/lib/types";

interface Props {
  metric: Metric;
  color: string;
  height?: number;
  axis?: boolean;
  /** Date of the last point in the series, so the chart can name each day. */
  endDate?: string;
}

interface Row {
  i: number;
  v: number | null;
}

const nice = (n: number) => (Math.abs(n) >= 1000 ? Math.round(n).toLocaleString() : String(Math.round(n * 10) / 10));

export function Spark({ metric, color, height = 64, axis = false, endDate }: Props) {
  const id = useId().replace(/:/g, "");
  const reduced = useReducedMotion();
  const { series, baseline, baseline_sd } = metric;
  const n = series.length;
  const last = n - 1;

  const vals = series.filter((v): v is number => v !== null);
  if (vals.length === 0) {
    return <div className="hatch rounded-lg" style={{ height }} aria-label="No readings" />;
  }

  const band = baseline !== null && baseline_sd ? baseline_sd : null;
  const lo0 = Math.min(...vals, band !== null ? baseline! - band : Infinity);
  const hi0 = Math.max(...vals, band !== null ? baseline! + band : -Infinity);
  const pad = (hi0 - lo0 || 1) * 0.08;
  const lo = lo0 - pad;
  const hi = hi0 + pad;

  const rows: Row[] = series.map((v, i) => ({ i, v }));
  const gaps = rows.filter((r) => r.v === null).map((r) => r.i);
  const lastVal = series[last];
  const unit = metric.unit ? ` ${metric.unit}` : "";

  const dayName = (i: number) =>
    endDate ? shortDay(addDays(endDate, -(last - i))) : i === last ? "Today" : `${last - i}d ago`;
  const axisDay = (i: number) => {
    if (!endDate) return i === last ? "today" : `${last - i}d ago`;
    return new Date(`${addDays(endDate, -(last - i))}T00:00:00Z`).toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
  };

  return (
    <div role="img" aria-label={`${metric.label}, last ${n} days. Use the arrow keys to inspect a day.`}>
      <ResponsiveContainer width="100%" height={height} initialDimension={{ width: 240, height }}>
        <AreaChart data={rows} margin={axis ? { top: 10, right: 14, bottom: 0, left: 0 } : { top: 6, right: 8, bottom: 6, left: 8 }}>
          <defs>
            <linearGradient id={`${id}-fill`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.28} />
              <stop offset="100%" stopColor={color} stopOpacity={0} />
            </linearGradient>
            <HatchPattern id={`${id}-gap`} base="transparent" opacity={0.7} />
          </defs>
          <XAxis
            dataKey="i" type="number" domain={[0, last]} hide={!axis} ticks={[0, last]} interval={0}
            axisLine={false} tickLine={false} tickMargin={6}
            tick={({ x, y, payload }) => (
              <text x={x} y={Number(y) + 8} textAnchor={payload.value === 0 ? "start" : "end"} {...TICK}>{axisDay(payload.value)}</text>
            )}
          />
          <YAxis
            hide={!axis} width={axis ? 40 : 0} domain={[lo, hi]} ticks={[lo0, (hi0 + lo0) / 2, hi0]}
            axisLine={false} tickLine={false} tickFormatter={nice} tick={TICK} tickMargin={6}
          />
          {band !== null && (
            <ReferenceArea y1={baseline! - band} y2={baseline! + band} fill="var(--ink-3)" fillOpacity={0.12} stroke="none" />
          )}
          {baseline !== null && (
            <ReferenceLine y={baseline} stroke="var(--ink-3)" strokeDasharray="3 4" />
          )}
          {gaps.map((i) => (
            <ReferenceArea key={i} x1={Math.max(0, i - 0.5)} x2={Math.min(last, i + 0.5)} fill={`url(#${id}-gap)`} stroke="none" />
          ))}
          <Tooltip
            filterNull={false}
            isAnimationActive={false}
            allowEscapeViewBox={{ x: false, y: true }}
            wrapperStyle={{ outline: "none", zIndex: 20 }}
            cursor={{ stroke: "var(--ink-2)", strokeOpacity: 0.5, strokeDasharray: "3 3" }}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const row = payload[0].payload as Row;
              return (
                <TipShell title={dayName(row.i)}>
                  {row.v === null ? (
                    <p className="text-ink-2">No reading</p>
                  ) : (
                    <>
                      <p className="font-mono text-ink">{nice(row.v)}{unit}</p>
                      {baseline !== null && (
                        <TipRow label="vs usual" value={`${row.v - baseline >= 0 ? "+" : "−"}${nice(Math.abs(row.v - baseline))}`} />
                      )}
                    </>
                  )}
                </TipShell>
              );
            }}
          />
          <Area
            type="monotone" dataKey="v" stroke={color} strokeWidth={2} fill={`url(#${id}-fill)`} baseValue={lo}
            connectNulls={false} dot={false}
            activeDot={{ r: 5, fill: "var(--raised)", stroke: color, strokeWidth: 2.5 }}
            isAnimationActive={!reduced} animationDuration={600}
          />
          {lastVal !== null && (
            <>
              <ReferenceDot x={last} y={lastVal} r={7} fill={color} fillOpacity={0.18} stroke="none" />
              <ReferenceDot x={last} y={lastVal} r={3.5} fill={color} stroke="none" />
            </>
          )}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
