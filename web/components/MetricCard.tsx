import type { Metric } from "@/lib/types";
import { Provenance, TONE } from "./Provenance";
import { Spark } from "./Spark";

function fmt(n: number) {
  return Math.abs(n) >= 1000 ? Math.round(n).toLocaleString("en-US") : String(n);
}

export function MetricCard({ m, delay = 0 }: { m: Metric; delay?: number }) {
  const tone = TONE[m.status];
  const missing = m.value === null;

  return (
    <article className="card rise flex flex-col gap-4 p-5" style={{ animationDelay: `${delay}ms` }}>
      <header className="flex items-start justify-between gap-3">
        <h3 className="text-[15px] font-medium text-ink-2">{m.label}</h3>
        <Provenance kind={m.provenance} />
      </header>

      {missing ? (
        <div className="hatch flex h-[84px] items-center rounded-xl border border-dashed border-ink-3/40 px-4 text-sm text-ink-2">
          No reading in the last {m.series.length} days.
        </div>
      ) : (
        <>
          <div className="flex items-end justify-between gap-3">
            <p className="font-display text-[40px] font-semibold leading-none tracking-tight">
              {fmt(m.value as number)}
              {m.unit && <span className="ml-1.5 font-sans text-sm font-normal text-ink-3">{m.unit}</span>}
            </p>
            {m.delta_pct !== null && (
              <span className={`rounded-full px-2.5 py-1 font-mono text-xs ${tone.bg} ${tone.text}`}>
                {m.delta_pct > 0 ? "+" : "−"}
                {Math.abs(m.delta_pct).toFixed(0)}% vs usual
              </span>
            )}
          </div>
          <Spark metric={m} color={tone.fg} />
        </>
      )}

      <footer className="mt-auto flex items-center justify-between border-t border-line pt-3 font-mono text-[11px] text-ink-3">
        <span>
          {m.baseline !== null ? `Usual ${fmt(m.baseline)}${m.unit ? " " + m.unit : ""}` : "No baseline yet"}
        </span>
        <span>{m.coverage} days</span>
      </footer>
    </article>
  );
}
