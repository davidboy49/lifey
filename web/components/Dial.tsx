// Readiness dial: a 270° arc, 0–100. With no score it renders hatched, empty.
const SIZE = 240;
const R = 96;
const C = SIZE / 2;
const START = 135;
const SWEEP = 270;

function polar(deg: number, r = R) {
  const a = (deg * Math.PI) / 180;
  return [C + r * Math.cos(a), C + r * Math.sin(a)] as const;
}

function arc(from: number, to: number, r = R) {
  const [x1, y1] = polar(from, r);
  const [x2, y2] = polar(to, r);
  const large = to - from > 180 ? 1 : 0;
  return `M ${x1.toFixed(2)} ${y1.toFixed(2)} A ${r} ${r} 0 ${large} 1 ${x2.toFixed(2)} ${y2.toFixed(2)}`;
}

export function Dial({ score, label, tone }: { score: number | null; label: string; tone: string }) {
  const len = (SWEEP / 360) * 2 * Math.PI * R;
  const end = START + (SWEEP * (score ?? 0)) / 100;
  const ticks = Array.from({ length: 11 }, (_, i) => START + (SWEEP * i) / 10);

  return (
    <svg
      viewBox={`0 0 ${SIZE} ${SIZE}`}
      className="w-full max-w-[240px]"
      role="img"
      aria-label={score === null ? "Readiness unavailable" : `Readiness ${score} out of 100, ${label}`}
    >
      {ticks.map((d, i) => {
        const [x1, y1] = polar(d, R + 14);
        const [x2, y2] = polar(d, R + (i % 5 === 0 ? 24 : 19));
        return <line key={d} x1={x1} y1={y1} x2={x2} y2={y2} stroke="var(--line)" strokeWidth={1.5} strokeLinecap="round" />;
      })}
      <path d={arc(START, START + SWEEP)} fill="none" stroke="var(--line)" strokeWidth={14} strokeLinecap="round" />
      {score !== null && score > 0 && (
        <path
          d={arc(START, end)}
          fill="none"
          stroke={tone}
          strokeWidth={14}
          strokeLinecap="round"
          className="dial-arc"
          strokeDasharray={len}
          style={{ ["--len" as string]: len }}
        />
      )}
      <text x={C} y={C + 6} textAnchor="middle" fontSize={score === null ? 40 : 76} fill="var(--ink)"
        style={{ fontFamily: "var(--font-display)", fontWeight: 600, letterSpacing: "-0.03em" }}>
        {score === null ? "–" : score}
      </text>
      <text x={C} y={C + 36} textAnchor="middle" fontSize={11} fill="var(--ink-3)"
        style={{ fontFamily: "var(--font-mono)", letterSpacing: "0.1em" }}>
        {score === null ? "NO VERDICT" : "OUT OF 100"}
      </text>
    </svg>
  );
}
