// One chart for both the card sparkline and the full trend view. Gaps in the
// series break the line and are marked on the baseline; nothing is interpolated.
import type { Metric } from "@/lib/types";

interface Props {
  metric: Metric;
  color: string;
  width?: number;
  height?: number;
  axis?: boolean;
}

export function Spark({ metric, color, width = 240, height = 64, axis = false }: Props) {
  const { series, baseline, baseline_sd } = metric;
  const padL = axis ? 40 : 4;
  const padR = 8;
  const padT = 8;
  const padB = axis ? 24 : 8;
  const iw = width - padL - padR;
  const ih = height - padT - padB;

  const vals = series.filter((v): v is number => v !== null);
  if (vals.length === 0) {
    return <div className="hatch rounded-lg" style={{ aspectRatio: `${width} / ${height}` }} aria-label="No readings" />;
  }
  const lo0 = Math.min(...vals, baseline !== null && baseline_sd ? baseline - baseline_sd : Infinity);
  const hi0 = Math.max(...vals, baseline !== null && baseline_sd ? baseline + baseline_sd : -Infinity);
  const span = hi0 - lo0 || 1;
  const lo = lo0 - span * 0.08;
  const hi = hi0 + span * 0.08;
  const x = (i: number) => padL + (iw * i) / (series.length - 1);
  const y = (v: number) => padT + ih - ((v - lo) / (hi - lo)) * ih;

  const segs: string[] = [];
  let cur = "";
  series.forEach((v, i) => {
    if (v === null) {
      if (cur) segs.push(cur);
      cur = "";
    } else {
      cur += `${cur ? "L" : "M"}${x(i).toFixed(1)} ${y(v).toFixed(1)} `;
    }
  });
  if (cur) segs.push(cur);

  const lastIdx = series.length - 1;
  const last = series[lastIdx];
  const nice = (n: number) => (Math.abs(n) >= 1000 ? Math.round(n).toLocaleString() : String(Math.round(n * 10) / 10));

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="block w-full" role="img"
      aria-label={`${metric.label}, last ${series.length} days`}>
      {baseline !== null && baseline_sd ? (
        <>
          <rect x={padL} width={iw} y={y(baseline + baseline_sd)} height={y(baseline - baseline_sd) - y(baseline + baseline_sd)}
            fill="var(--ink-3)" opacity={0.12} rx={3} />
          <line x1={padL} x2={padL + iw} y1={y(baseline)} y2={y(baseline)} stroke="var(--ink-3)" strokeWidth={1} strokeDasharray="3 4" />
        </>
      ) : null}
      {axis && (
        <>
          {[hi0, (hi0 + lo0) / 2, lo0].map((t) => (
            <g key={t}>
              <line x1={padL} x2={padL + iw} y1={y(t)} y2={y(t)} stroke="var(--line)" strokeWidth={1} />
              <text x={padL - 8} y={y(t) + 4} textAnchor="end" fontSize={13} fill="var(--ink-3)" style={{ fontFamily: "var(--font-mono)" }}>
                {nice(t)}
              </text>
            </g>
          ))}
          <text x={padL} y={height - 4} fontSize={13} fill="var(--ink-3)" style={{ fontFamily: "var(--font-mono)" }}>
            {series.length - 1}d ago
          </text>
          <text x={padL + iw} y={height - 4} textAnchor="end" fontSize={13} fill="var(--ink-3)" style={{ fontFamily: "var(--font-mono)" }}>
            today
          </text>
        </>
      )}
      {segs.map((d, i) => (
        <path key={i} d={d} fill="none" stroke={color} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
      ))}
      {series.map((v, i) =>
        v === null ? (
          <line key={i} x1={x(i)} x2={x(i)} y1={padT + ih - 6} y2={padT + ih} stroke="var(--ink-3)" strokeWidth={1.5} strokeLinecap="round" />
        ) : null,
      )}
      {last !== null && (
        <>
          <circle cx={x(lastIdx)} cy={y(last)} r={7} fill={color} opacity={0.18} />
          <circle cx={x(lastIdx)} cy={y(last)} r={3.5} fill={color} />
        </>
      )}
    </svg>
  );
}
