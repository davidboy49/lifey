"use client";

import { useEffect, useState } from "react";
import { activityType, distance, duration, type DayData } from "@/lib/eventReviews";

function Stat({ label, value, unit }: { label: string; value: string | number | null; unit?: string }) {
  const missing = value === null || value === "·";
  return (
    <div className="grid gap-0.5 rounded-xl border border-line bg-raised px-3 py-2.5">
      <span className="text-[12px] text-ink-3">{label}</span>
      <span className={`font-display text-[20px] font-semibold leading-tight ${missing ? "text-ink-3" : ""}`}>
        {missing ? "·" : value}
        {!missing && unit && <span className="ml-1 font-sans text-[12px] font-normal text-ink-3">{unit}</span>}
      </span>
    </div>
  );
}

/** That day's Garmin numbers, read only. Fetched again whenever the date changes. */
export function DayDataPanel({ date }: { date: string }) {
  const [data, setData] = useState<DayData | null>(null);
  const [state, setState] = useState<"loading" | "ok" | "error">("loading");

  useEffect(() => {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return;
    let live = true;
    setState("loading");
    fetch(`/api/event-reviews/day/${date}`)
      .then(async (r) => {
        if (!r.ok) throw new Error();
        const body = (await r.json()) as DayData;
        if (live) { setData(body); setState("ok"); }
      })
      .catch(() => live && setState("error"));
    return () => { live = false; };
  }, [date]);

  if (state === "loading") return <p className="text-sm text-ink-3">Loading the day’s data…</p>;
  if (state === "error" || !data) return <p className="text-sm text-ink-3">Couldn’t load the day’s data. You can still fill in the review.</p>;
  if (!data.has_data) return <p className="text-sm text-ink-3">No watch data for this day. Carry on with the review.</p>;

  const m = data.metrics;
  const bb = m.body_battery_high !== null
    ? `${m.body_battery_high}${m.body_battery_low !== null ? `–${m.body_battery_low}` : ""}` : null;
  return (
    <div className="grid gap-3">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        <Stat label="Sleep score" value={m.sleep_score} />
        <Stat label="Sleep" value={m.sleep_seconds === null ? null : duration(m.sleep_seconds)} />
        <Stat label="HRV" value={m.hrv_ms} unit="ms" />
        <Stat label="Resting HR" value={m.resting_hr} unit="bpm" />
        <Stat label="Readiness" value={m.training_readiness} />
        <Stat label="Body battery" value={bb} unit={bb && m.body_battery_low !== null ? "high–low" : "high"} />
      </div>
      {data.activities.length > 0 ? (
        <ul className="grid gap-2">
          {data.activities.map((a) => (
            <li key={a.id} className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 rounded-xl border border-line bg-raised px-3 py-2.5 text-[14px]">
              <b className="font-semibold">{a.name || activityType(a.type)}</b>
              <span className="text-ink-2">{activityType(a.type)}</span>
              {distance(a.distance_meters) && <span>{distance(a.distance_meters)}</span>}
              <span>{duration(a.duration_seconds)}</span>
              {a.avg_hr !== null && <span>{Math.round(a.avg_hr)} bpm avg</span>}
              {a.start && <span className="font-mono text-[12px] text-ink-3">{a.start}</span>}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-ink-3">No activities recorded.</p>
      )}
      <p className="font-mono text-[11px] text-ink-3">From Garmin. A dot means not recorded.</p>
    </div>
  );
}
