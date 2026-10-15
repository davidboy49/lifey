import { redirect } from "next/navigation";
import { ApiDown } from "@/components/ApiDown";
import { Inbox } from "@/components/Inbox";
import { LearningFocus } from "@/components/LearningFocus";
import { StudyShelf } from "@/components/StudyShelf";
import { apiGet } from "@/lib/api";
import { CATEGORY_LABEL, RESULT_LABEL, monthName, type LearningResponse, type Proposal } from "@/lib/learning";

export const dynamic = "force-dynamic";

export default async function LearningPage() {
  const res = await apiGet<LearningResponse>("/api/learning");
  if (res.status === "unauthorized") redirect("/login");
  if (res.status !== "ok") return <ApiDown />;
  const d = res.data;
  const inbox = await apiGet<{ proposals: Proposal[] }>("/api/proposals");

  return (
    <article className="mx-auto flex w-full max-w-[760px] flex-col gap-10">
      <header className="grid gap-1">
        <p className="eyebrow">Learning</p>
        <h1 className="font-display text-[36px] font-semibold leading-[1.05] tracking-tight sm:text-[46px]">
          Always something to get better at
        </h1>
      </header>

      {inbox.status === "ok" && <Inbox items={inbox.data.proposals} />}

      <LearningFocus data={d} />

      <StudyShelf data={d} />

      {d.history.length > 0 && (
        <section className="grid gap-3" aria-labelledby="lh">
          <h2 id="lh" className="eyebrow">Earlier months</h2>
          {d.history.map((f) => (
            <div key={f.id} className="card grid gap-1 p-4">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <p className="font-display text-lg font-semibold">{f.topic}</p>
                <p className="font-mono text-[11px] text-ink-3">
                  {monthName(f.month)} · {CATEGORY_LABEL[f.category]}
                </p>
              </div>
              <p className="text-[15px] text-ink-2">{f.outcome}</p>
              {f.result && <p className="text-sm"><b>{RESULT_LABEL[f.result]}</b></p>}
            </div>
          ))}
        </section>
      )}
    </article>
  );
}
