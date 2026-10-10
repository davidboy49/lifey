import { redirect } from "next/navigation";
import { ApiDown } from "@/components/ApiDown";
import { Provenance, TONE } from "@/components/Provenance";
import { Spark } from "@/components/Spark";
import { getToday } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function TrendsPage() {
  const res = await getToday();
  if (res.status === "unauthorized") redirect("/login");
  if (res.status !== "ok") return <ApiDown />;
  const t = res.data;
  const metrics = t.metrics.filter((m) => m.value !== null);

  return (
    <div className="flex flex-col gap-8">
      <header>
        <p className="eyebrow">Trends</p>
        <h1 className="font-display text-[34px] font-semibold leading-tight tracking-tight sm:text-[44px]">
          Four weeks against your usual
        </h1>
        <p className="mt-2 max-w-[60ch] text-ink-2">
          The shaded band is your normal range for each signal. Short ticks along the bottom mark days with no
          reading; the line breaks there instead of guessing.
        </p>
      </header>

      <div className="flex flex-col gap-5">
        {metrics.map((m) => (
          <section key={m.key} className="card rise p-5 sm:p-6">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <h2 className="font-display text-xl font-semibold">{m.label}</h2>
              <div className="flex items-center gap-3">
                <span className="font-mono text-xs text-ink-3">{m.coverage} days recorded</span>
                <Provenance kind={m.provenance} />
              </div>
            </div>
            <div className="max-w-[760px]"><Spark metric={m} color={TONE[m.status].fg} width={520} height={210} axis /></div>
          </section>
        ))}
      </div>
    </div>
  );
}
