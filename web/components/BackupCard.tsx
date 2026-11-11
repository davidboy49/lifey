import type { BackupStatus } from "@/lib/backups";

function when(iso: string | null): string {
  if (!iso) return "never";
  return new Date(iso).toLocaleString("en-GB", {
    day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: "Asia/Phnom_Penh",
  });
}

function size(bytes: number | null): string {
  if (bytes === null) return "·";
  return bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

export function BackupCard({ status }: { status: BackupStatus }) {
  const bad = status.needs_attention;
  return (
    <section className={`card grid gap-4 p-5 sm:p-6 ${bad ? "border-alert" : ""}`} aria-labelledby="backup-h">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 id="backup-h" className="font-display text-xl font-semibold">Backups</h2>
          <p className={`mt-1 text-[15px] font-medium ${bad ? "text-alert" : "text-good"}`} role={bad ? "alert" : undefined}>
            {status.headline}
          </p>
          {status.hint && <p className="mt-1 max-w-[62ch] text-sm text-ink-2">{status.hint}</p>}
        </div>
        <span className={`rounded-full px-3 py-1 text-xs font-semibold ${bad ? "bg-alert-soft text-alert" : "bg-good-soft text-good"}`}>
          {bad ? "Needs attention" : status.state === "running" ? "Running" : "All good"}
        </span>
      </div>
      <dl className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-4">
        <div><dt className="eyebrow">Last success</dt><dd className="text-[15px] font-medium">{when(status.last_ok_at)}</dd></div>
        <div><dt className="eyebrow">Size</dt><dd className="text-[15px] font-medium">{size(status.last_ok_bytes)}</dd></div>
        <div><dt className="eyebrow">Files</dt><dd className="text-[15px] font-medium">{status.last_ok_files ?? "·"}</dd></div>
        <div><dt className="eyebrow">Destination</dt><dd className="truncate text-[15px] font-medium">{status.destination ?? "·"}</dd></div>
      </dl>
      {status.recent.length > 0 && (
        <div className="flex items-center gap-1.5" aria-label="Last runs, newest on the right">
          {[...status.recent].reverse().map((r, i) => (
            <span
              key={i}
              title={`${when(r.started_at)} · ${r.ok === null ? "running" : r.ok ? "ok" : "failed"}`}
              className={`h-2.5 w-6 rounded-full ${r.ok === null ? "bg-watch" : r.ok ? "bg-good" : "bg-alert"}`}
            />
          ))}
        </div>
      )}
      <p className="text-xs text-ink-3">
        Copied to Google Drive without encryption, so anyone who can open that folder can read it. Backed up every Sunday.
      </p>
    </section>
  );
}
