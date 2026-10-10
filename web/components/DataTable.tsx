"use client";

import { useMemo, useState } from "react";
import type { DataColumn } from "@/lib/habits";

type Row = Record<string, string | number | boolean | null>;

function cell(col: DataColumn, v: string | number | boolean | null) {
  if (v === null || v === "") return <span className="text-ink-3" title="No value recorded">·</span>;
  if (col.kind === "chip") {
    const text = typeof v === "boolean" ? (v ? "yes" : "no") : String(v);
    const bad = ["partial", "failed", "partial"].includes(text);
    const good = ["complete", "success", "yes"].includes(text);
    return (
      <span className={`rounded-full border px-2 py-0.5 font-mono text-[10.5px] uppercase tracking-wider ${
        bad ? "border-transparent bg-watch-soft text-watch" : good ? "border-line text-ink-2" : "border-line text-ink-3"}`}>
        {text}
      </span>
    );
  }
  if (typeof v === "number") return v.toLocaleString("en-US");
  return String(v);
}

export function DataTable({ columns, rows }: { columns: DataColumn[]; rows: Row[] }) {
  const [hidden, setHidden] = useState<Set<string>>(new Set(columns.filter((c) => c.hidden).map((c) => c.key)));
  const [open, setOpen] = useState(false);
  const visible = useMemo(() => columns.filter((c) => !hidden.has(c.key)), [columns, hidden]);

  function toggle(key: string) {
    setHidden((h) => {
      const next = new Set(h);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
  }

  return (
    <div className="grid gap-3">
      <div className="relative flex justify-end">
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
          className="rounded-xl border border-line bg-raised px-3.5 py-2 text-sm font-medium text-ink-2 hover:text-ink"
        >
          Columns ({visible.length}/{columns.length})
        </button>
        {open && (
          <div className="card absolute right-0 top-11 z-10 grid max-h-72 w-60 gap-0.5 overflow-auto p-2">
            {columns.map((c) => (
              <label key={c.key} className="flex cursor-pointer items-center gap-2 rounded-lg px-2 py-1.5 text-sm hover:bg-panel">
                <input type="checkbox" checked={!hidden.has(c.key)} onChange={() => toggle(c.key)} />
                {c.label}
              </label>
            ))}
          </div>
        )}
      </div>

      <div className="max-h-[68vh] overflow-auto rounded-2xl border border-line bg-raised">
        <table className="w-full min-w-[640px] border-separate border-spacing-0 text-sm">
          <thead>
            <tr>
              {visible.map((c, i) => (
                <th
                  key={c.key}
                  scope="col"
                  className={`sticky top-0 z-[1] whitespace-nowrap border-b border-line bg-panel px-3.5 py-2.5 font-mono text-[11px] font-medium uppercase tracking-wider text-ink-3 ${
                    c.kind === "number" ? "text-right" : "text-left"} ${i === 0 ? "left-0 z-[2]" : ""}`}
                >
                  {c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr><td colSpan={visible.length} className="px-4 py-8 text-center text-ink-2">No rows yet.</td></tr>
            )}
            {rows.map((row, ri) => (
              <tr key={ri} className="hover:bg-panel">
                {visible.map((c, i) => (
                  <td
                    key={c.key}
                    className={`whitespace-nowrap border-b border-line px-3.5 py-2.5 ${c.kind === "number" ? "text-right tabular-nums" : "text-left"} ${
                      c.key === "note" || c.key === "message" || c.key === "details" ? "max-w-[360px] truncate" : ""} ${
                      i === 0 ? "sticky left-0 bg-raised font-medium" : ""}`}
                    title={typeof row[c.key] === "string" && String(row[c.key]).length > 40 ? String(row[c.key]) : undefined}
                  >
                    {cell(c, row[c.key] ?? null)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
