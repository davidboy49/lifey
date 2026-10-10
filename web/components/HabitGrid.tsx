import type { HabitCell, WellbeingRow, HabitRow } from "@/lib/habits";
import { shortDay } from "@/lib/journal";

type Cell = HabitCell | WellbeingRow["cells"][number];

function cellClass(c: Cell, scale: "habit" | "scale"): string {
  if (c.state === "unknown") return "cell cell-unknown";
  if (c.state === "none") return "cell";
  return `cell ${scale === "habit" ? `cell-h${c.level ?? 1}` : `cell-s${c.level ?? 1}`}`;
}

function tip(c: Cell, unit: string, tag: string): string {
  const day = shortDay(c.date);
  if (c.state === "unknown") return `${day} · nothing logged (unknown)`;
  if (c.state === "none") return `${day} · not logged`;
  if ("value" in c && c.value !== undefined) return `${day} · ${tag} ${c.value}/5`;
  return `${day} · ${"amount" in c ? c.amount : ""} ${unit}`.trim();
}

function Row({ label, cells, unit, tag, scale, total }: {
  label: string; cells: Cell[]; unit: string; tag: string; scale: "habit" | "scale"; total: React.ReactNode;
}) {
  return (
    <div className="grid grid-cols-[116px_minmax(0,1fr)_auto] items-center gap-3">
      <span className="truncate text-sm font-medium">{label}</span>
      <div className="grid gap-[3px]" style={{ gridTemplateColumns: `repeat(${cells.length}, minmax(0, 1fr))` }}>
        {cells.map((c) => (
          <i key={c.date} className={cellClass(c, scale)} title={tip(c, unit, tag)} />
        ))}
      </div>
      <span className="min-w-[88px] text-right font-mono text-xs text-ink-2">{total}</span>
    </div>
  );
}

function WeekLabels({ days }: { days: string[] }) {
  return (
    <div className="grid grid-cols-[116px_minmax(0,1fr)_auto] items-end gap-3">
      <span />
      <div className="grid gap-[3px]" style={{ gridTemplateColumns: `repeat(${days.length}, minmax(0, 1fr))` }}>
        {days.map((d) => {
          const monday = new Date(`${d}T00:00:00Z`).getUTCDay() === 1;
          return (
            <span key={d} className="overflow-visible whitespace-nowrap font-mono text-[10px] text-ink-3">
              {monday ? new Date(`${d}T00:00:00Z`).toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" }) : ""}
            </span>
          );
        })}
      </div>
      <span className="min-w-[88px]" />
    </div>
  );
}

export function Legend({ items }: { items: { cls: string; text: string }[] }) {
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1.5 text-[12.5px] text-ink-3">
      {items.map((i) => (
        <span key={i.text} className="inline-flex items-center gap-1.5">
          <i className={`${i.cls} inline-block size-[11px]`} />
          {i.text}
        </span>
      ))}
    </div>
  );
}

export function HabitGrid({ days, rows }: { days: string[]; rows: HabitRow[] }) {
  return (
    <div className="grid gap-3 overflow-x-auto" style={{ minWidth: 0 }}>
      <div className="grid min-w-[560px] gap-3">
        <WeekLabels days={days} />
        {rows.map((r) => (
          <Row
            key={r.tag}
            label={r.label}
            unit={r.unit}
            tag={r.tag}
            cells={r.cells}
            scale="habit"
            total={r.days ? <><b className="text-ink">{r.days}</b> {r.days === 1 ? "day" : "days"}</> : <span className="text-ink-3">none</span>}
          />
        ))}
      </div>
    </div>
  );
}

export function WellbeingGrid({ days, rows }: { days: string[]; rows: WellbeingRow[] }) {
  return (
    <div className="grid gap-3 overflow-x-auto" style={{ minWidth: 0 }}>
      <div className="grid min-w-[560px] gap-3">
        <WeekLabels days={days} />
        {rows.map((r) => (
          <Row
            key={r.tag}
            label={r.label}
            unit=""
            tag={r.tag}
            cells={r.cells}
            scale="scale"
            total={r.average !== null ? <>avg <b className="text-ink">{r.average.toFixed(1)}</b> · {r.count}</> : <span className="text-ink-3">no check-ins</span>}
          />
        ))}
      </div>
    </div>
  );
}
