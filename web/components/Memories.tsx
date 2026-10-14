import type { Memory } from "@/lib/journal";

function when(m: Memory): string {
  const [y, mo, d] = m.date.split("-").map(Number);
  const day = new Date(Date.UTC(y, mo - 1, d)).toLocaleDateString("en-GB", {
    weekday: "short", day: "numeric", month: "short", year: "numeric", timeZone: "UTC",
  });
  return m.time ? `${day} · ${m.time}` : day;
}

/** Notes and photos from this date in earlier months and years. Rendered only when there are any. */
export function Memories({ items }: { items: Memory[] }) {
  if (items.length === 0) return null;
  return (
    <section className="grid gap-3" aria-labelledby="otd">
      <h2 id="otd" className="eyebrow">On this day</h2>
      <div className="grid gap-3 md:grid-cols-2">
        {items.slice(0, 4).map((m) => (
          <figure key={`${m.months}-${m.log_id}`} className="card kind-note grid content-start gap-2 overflow-hidden p-3">
            {m.attachment && (
              <a href={`/api/attachments/${m.attachment.id}`} target="_blank" rel="noopener noreferrer"
                 className="block overflow-hidden rounded-xl border border-line bg-panel">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={`/api/attachments/${m.attachment.id}`} alt={m.attachment.filename} loading="lazy"
                     className="mx-auto block max-h-[320px] w-auto max-w-full object-contain" />
              </a>
            )}
            {m.note && <blockquote className="font-display text-[17px] leading-snug tracking-tight">{m.note}</blockquote>}
            <figcaption className="font-mono text-[11.5px] text-ink-3">
              {m.label} · {when(m)}
              {m.files > 1 ? ` · ${m.files} files` : ""}
            </figcaption>
          </figure>
        ))}
      </div>
    </section>
  );
}
