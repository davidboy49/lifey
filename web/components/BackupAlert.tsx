import Link from "next/link";
import { apiGet } from "@/lib/api";
import type { BackupStatus } from "@/lib/backups";

// A thin banner on every page, shown only when the backup needs the owner.
export async function BackupAlert() {
  const res = await apiGet<BackupStatus>("/api/backups");
  if (res.status !== "ok" || !res.data.needs_attention || res.data.state === "never") return null;
  return (
    <div role="alert" className="mx-auto mb-5 flex max-w-[1040px] flex-wrap items-center justify-between gap-2 rounded-xl bg-alert-soft px-4 py-3 text-sm text-alert">
      <span><b>Backup needs attention.</b> {res.data.headline}</span>
      <Link href="/settings" className="font-medium underline underline-offset-2">Details</Link>
    </div>
  );
}
