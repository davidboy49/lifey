import Link from "next/link";
import { redirect } from "next/navigation";
import { ApiDown } from "@/components/ApiDown";
import { DataTable } from "@/components/DataTable";
import { apiGet } from "@/lib/api";
import type { DataTableResponse, DatasetInfo } from "@/lib/habits";

export const dynamic = "force-dynamic";

const PAGE = 100;

export default async function DataPage({ searchParams }: { searchParams: Promise<{ set?: string; page?: string }> }) {
  const sp = await searchParams;
  const list = await apiGet<DatasetInfo[]>("/api/data");
  if (list.status === "unauthorized") redirect("/login");
  if (list.status !== "ok") return <ApiDown />;

  const key = list.data.some((d) => d.key === sp.set) ? (sp.set as string) : "daily_metrics";
  const page = Math.max(1, Number(sp.page) || 1);
  const res = await apiGet<DataTableResponse>(`/api/data/${key}?limit=${PAGE}&offset=${(page - 1) * PAGE}`);
  if (res.status === "unauthorized") redirect("/login");
  if (res.status !== "ok") return <ApiDown />;
  const t = res.data;
  const pages = Math.max(1, Math.ceil(t.total / PAGE));
  const from = t.total === 0 ? 0 : t.offset + 1;
  const to = Math.min(t.total, t.offset + t.rows.length);
  const href = (set: string, p = 1) => `/data?set=${set}${p > 1 ? `&page=${p}` : ""}`;

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow">Data</p>
          <h1 className="font-display text-[34px] font-semibold leading-tight tracking-tight sm:text-[44px]">{t.label}</h1>
        </div>
        <a
          href={`/api/data/${key}/export.csv`}
          className="rounded-xl border border-line bg-raised px-4 py-2.5 text-sm font-medium text-ink-2 hover:border-accent hover:text-accent"
        >
          Export all as CSV
        </a>
      </header>

      <nav aria-label="Dataset" className="flex flex-wrap gap-2">
        {list.data.map((d) => (
          <Link
            key={d.key}
            href={href(d.key)}
            aria-current={d.key === key ? "true" : undefined}
            className={`rounded-full border px-3.5 py-1.5 text-sm font-medium ${d.key === key ? "border-accent bg-accent-soft text-accent" : "border-line bg-raised text-ink-2 hover:text-ink"}`}
          >
            {d.label} <span className="font-mono text-xs text-ink-3">{d.rows.toLocaleString("en-US")}</span>
          </Link>
        ))}
      </nav>

      <DataTable key={key + page} columns={t.columns} rows={t.rows} />

      <footer className="flex flex-wrap items-center justify-between gap-3 text-sm text-ink-2">
        <p>
          Showing {from.toLocaleString("en-US")}–{to.toLocaleString("en-US")} of {t.total.toLocaleString("en-US")}, newest first.
          A dot means no value was recorded. That is a gap, not a zero.
        </p>
        {pages > 1 && (
          <nav aria-label="Pages" className="flex items-center gap-2">
            {page > 1 && <Link href={href(key, page - 1)} className="rounded-lg border border-line bg-raised px-3 py-1.5 hover:text-accent">Newer</Link>}
            <span className="font-mono text-xs text-ink-3">{page} / {pages}</span>
            {page < pages && <Link href={href(key, page + 1)} className="rounded-lg border border-line bg-raised px-3 py-1.5 hover:text-accent">Older</Link>}
          </nav>
        )}
      </footer>
    </div>
  );
}
