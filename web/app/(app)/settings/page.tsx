import { redirect } from "next/navigation";
import { ApiDown } from "@/components/ApiDown";
import { BackupCard } from "@/components/BackupCard";
import { ReminderSettings } from "@/components/ReminderSettings";
import type { BackupStatus } from "@/lib/backups";
import { apiGet } from "@/lib/api";

export const dynamic = "force-dynamic";

interface Settings {
  timezone: string;
  reminders: { key: string; label: string; enabled: boolean; time: string }[];
}

export default async function SettingsPage() {
  const res = await apiGet<Settings>("/api/settings/reminders");
  if (res.status === "unauthorized") redirect("/login");
  if (res.status !== "ok") return <ApiDown />;
  const backups = await apiGet<BackupStatus>("/api/backups");

  return (
    <div className="flex flex-col gap-6">
      <header>
        <p className="eyebrow">Settings</p>
        <h1 className="font-display text-[34px] font-semibold leading-tight tracking-tight sm:text-[44px]">Backups and reminders</h1>
        <p className="mt-2 max-w-[60ch] text-ink-2">
          Whether your data is safely copied off the server, and when the Telegram bot asks you things. Each reminder
          is a single message with no follow-up, and an unanswered question stays unknown, never “no”.
        </p>
      </header>
      {backups.status === "ok" && <BackupCard status={backups.data} />}
      <ReminderSettings initial={res.data.reminders} timezone={res.data.timezone} />
    </div>
  );
}
