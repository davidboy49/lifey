import type { SleepNight } from "@/lib/sleep";
import { shortDay } from "@/lib/journal";

// One bar per night, oldest to newest. A missing night is an empty dashed slot,
// a partly recorded night is hatched grey, and neither is ever drawn as zero.
export function SleepBars({ nights, target, incompleteBelow }: { nights: SleepNight[]; target: number; incompleteBelow: number }) {
  const W = 760;
  const H = 220;
  const padL = 34;
  const padR = 8;
  const padT = 14;
  const padB = 26;
  const iw = W - padL - padR;
  const ih = H - padT - padB;
  const max = Math.max(10, Math.ceil(Math.max(target + 1, ...nights.map((n) => n.hours ?? 0))));
  const slot = iw / nights.length;
  const bar = Math.max(3, slot - 3);
  const y = (h: number) => padT + ih - (h / max) * ih;
  const recorded = nights.filter((n) => n.kind === "recorded");
  const mean = recorded.length ? recorded.reduce((a, n) => a + (n.hours ?? 0), 0) / recorded.length : null;

  const color = (n: SleepNight) =>
    n.hours === null ? "none" : n.hours >= target ? "var(--good)" : n.hours >= 6 ? "var(--watch)" : "var(--alert)";

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="block w-full" role="img" aria-label={`Hours slept per night, last ${nights.length} nights, against a ${target} hour target`}>
      <defs>
        <pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <rect width="6" height="6" fill="var(--panel)" />
          <line x1="0" y1="0" x2="0" y2="6" stroke="var(--ink-3)" strokeWidth="1.4" opacity="0.6" />
        </pattern>
      </defs>
      {[0, 4, 8].filter((t) => t <= max).map((t) => (
        <g key={t}>
          <line x1={padL} x2={W - padR} y1={y(t)} y2={y(t)} stroke="var(--line)" />
          <text x={padL - 6} y={y(t) + 4} textAnchor="end" fontSize={12} fill="var(--ink-3)" style={{ fontFamily: "var(--font-mono)" }}>{t}h</text>
        </g>
      ))}
      {nights.map((n, i) => {
        const x = padL + i * slot + (slot - bar) / 2;
        if (n.kind === "missing") {
          return <rect key={n.date} x={x} y={y(2)} width={bar} height={y(0) - y(2)} rx={2} fill="none" stroke="var(--ink-3)" strokeDasharray="2 3" opacity="0.7"><title>{`${shortDay(n.date)}: no recording`}</title></rect>;
        }
        const h = n.hours ?? 0;
        return (
          <rect key={n.date} x={x} y={y(h)} width={bar} height={Math.max(2, y(0) - y(h))} rx={2}
                fill={n.kind === "incomplete" ? "url(#hatch)" : color(n)} stroke={n.kind === "incomplete" ? "var(--ink-3)" : "none"}>
            <title>{`${shortDay(n.date)}: ${h.toFixed(1)} h${n.kind === "incomplete" ? ` (under ${incompleteBelow} h, probably an incomplete recording)` : ""}`}</title>
          </rect>
        );
      })}
      <line x1={padL} x2={W - padR} y1={y(target)} y2={y(target)} stroke="var(--accent)" strokeWidth={1.5} strokeDasharray="5 4" />
      <text x={W - padR} y={y(target) - 5} textAnchor="end" fontSize={12} fill="var(--accent)" style={{ fontFamily: "var(--font-mono)" }}>target {target.toFixed(1)} h</text>
      {mean !== null && (
        <line x1={padL} x2={W - padR} y1={y(mean)} y2={y(mean)} stroke="var(--ink-2)" strokeWidth={1} opacity={0.65} />
      )}
      <text x={padL} y={H - 6} fontSize={12} fill="var(--ink-3)" style={{ fontFamily: "var(--font-mono)" }}>{shortDay(nights[0].date)}</text>
      <text x={W - padR} y={H - 6} textAnchor="end" fontSize={12} fill="var(--ink-3)" style={{ fontFamily: "var(--font-mono)" }}>{shortDay(nights[nights.length - 1].date)}</text>
    </svg>
  );
}
