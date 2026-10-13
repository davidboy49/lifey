import type { FeelingByRun as Data } from "@/lib/habits";

// Average waking feeling by days since the last slip. A group only gets a verdict
// once it has enough rated mornings; before that it shows the count and no average.
export function FeelingByRun({ data }: { data: Data }) {
  if (data.placed === 0) {
    return (
      <p className="rounded-xl bg-panel px-3.5 py-2.5 text-sm text-ink-2">
        Rate your mornings and log slips, and this fills in: how you wake up on the day of a slip, in the days after it,
        and deep into a run. It needs at least {data.needed} rated mornings in a group before it shows an average.
      </p>
    );
  }
  return (
    <div className="grid gap-3">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[420px] text-left text-sm">
          <caption className="sr-only">Average waking feeling by days since the last slip</caption>
          <thead>
            <tr className="text-ink-3">
              <th className="py-2 pr-3 font-medium">Days since a slip</th>
              <th className="py-2 pr-3 font-medium">Mornings</th>
              <th className="py-2 pr-3 font-medium">Average feeling</th>
              <th className="py-2 font-medium" aria-hidden />
            </tr>
          </thead>
          <tbody>
            {data.rows.map((r) => (
              <tr key={r.label} className="border-t border-line">
                <th scope="row" className="py-2.5 pr-3 font-medium">{r.label}</th>
                <td className="py-2.5 pr-3 text-ink-2">{r.n}</td>
                <td className="py-2.5 pr-3">
                  {r.n === 0 ? (
                    <span className="text-ink-3">no mornings yet</span>
                  ) : r.enough ? (
                    <b>{r.mean?.toFixed(1)} / 5</b>
                  ) : (
                    <span className="text-ink-3">{r.mean?.toFixed(1)} / 5 · too few to count (needs {data.needed})</span>
                  )}
                </td>
                <td className="w-[120px] py-2.5">
                  {r.enough && r.mean !== null && (
                    <span className="block h-2 rounded-full bg-raised" aria-hidden>
                      <span className="block h-2 rounded-full bg-accent" style={{ width: `${(r.mean / 5) * 100}%` }} />
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-ink-3">
        {data.placed} of {data.rated_days} rated mornings fall after a recorded slip. This is one person’s pattern, not
        proof of cause: mornings after poor sleep or a hard day also feel worse.
      </p>
    </div>
  );
}
