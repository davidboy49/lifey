import { ApiDown } from "@/components/ApiDown";
import { Dial } from "@/components/Dial";
import { MetricCard } from "@/components/MetricCard";
import { getToday } from "@/lib/api";

export const dynamic = "force-dynamic";

const TONE: Record<string, string> = {
  Primed: "var(--good)",
  Steady: "var(--accent)",
  "Ease off": "var(--watch)",
  Recover: "var(--alert)",
};

function ago(iso: string | null) {
  if (!iso) return "never";
  const mins = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const h = Math.round(mins / 60);
  return h < 24 ? `${h} h ago` : `${Math.round(h / 24)} d ago`;
}

export default async function TodayPage() {
  const t = await getToday();
  if (!t) return <ApiDown />;

  const date = new Date(`${t.date}T12:00:00`);
  const weekday = date.toLocaleDateString("en-GB", { weekday: "long" });
  const rest = date.toLocaleDateString("en-GB", { day: "numeric", month: "long" });
  const r = t.readiness;
  const tone = TONE[r.label] ?? "var(--ink-3)";

  return (
    <div className="flex flex-col gap-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow">Today</p>
          <h1 className="font-display text-[34px] font-semibold leading-tight tracking-tight sm:text-[44px]">
            {weekday}, <span className="text-ink-3">{rest}</span>
          </h1>
        </div>
        <p className="flex items-center gap-2 rounded-full border border-line bg-raised px-3 py-1.5 font-mono text-xs text-ink-2">
          <span className="size-1.5 rounded-full bg-good" aria-hidden />
          Synced {ago(t.synced_at)}
        </p>
      </header>

      {t.source === "demo" && (
        <p className="hatch rounded-xl border border-dashed border-ink-3/40 px-4 py-2.5 text-sm text-ink-2">
          <strong className="font-semibold text-ink">Sample data.</strong> No Garmin account is linked yet, so everything
          below is generated for the preview.
        </p>
      )}

      <section className="grid gap-5 lg:grid-cols-[1.35fr_1fr]">
        <div className="card rise grid items-center gap-6 p-6 sm:grid-cols-[240px_1fr] sm:p-8">
          <div className="mx-auto w-full max-w-[240px]">
            <Dial score={r.score} label={r.label} tone={tone} />
          </div>
          <div className="flex flex-col gap-4">
            <div>
              <p className="eyebrow">Readiness</p>
              <h2 className="font-display text-[40px] font-semibold leading-none tracking-tight" style={{ color: tone }}>
                {r.label}
              </h2>
            </div>
            <p className="text-[17px] leading-snug">{r.action}</p>
            <p className="text-sm text-ink-3">
              {r.summary} <span className="font-mono text-xs uppercase">· {r.confidence} confidence</span>
            </p>
          </div>
        </div>

        <aside className="card rise p-6" style={{ animationDelay: "80ms" }}>
          <p className="eyebrow">Why this verdict</p>
          {t.reasons.length === 0 ? (
            <p className="mt-3 text-ink-2">Not enough verified data to explain a verdict yet.</p>
          ) : (
            <ol className="mt-3 flex flex-col divide-y divide-line">
              {t.reasons.map((x) => (
                <li key={x.evidence.join()} className="py-3 first:pt-0 last:pb-0">
                  <p className="leading-snug">{x.text}</p>
                  <p className="mt-1 font-mono text-[11px] uppercase tracking-wider text-ink-3">
                    Source · {x.evidence.join(", ")}
                  </p>
                </li>
              ))}
            </ol>
          )}
        </aside>
      </section>

      <section aria-labelledby="signals">
        <h2 id="signals" className="eyebrow mb-3">
          Signals · last {t.metrics[0]?.series.length ?? 28} days
        </h2>
        <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
          {t.metrics.map((m, i) => (
            <MetricCard key={m.key} m={m} delay={120 + i * 60} />
          ))}
        </div>
      </section>

      <p className="max-w-[62ch] text-sm text-ink-3">
        Scores and stages come from Garmin and are estimates for personal wellness tracking. They are not a medical
        measurement or a diagnosis.
      </p>
    </div>
  );
}
