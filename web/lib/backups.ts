export interface BackupStatus {
  state: "ok" | "running" | "failed" | "stale" | "never";
  needs_attention: boolean;
  headline: string;
  hint: string | null;
  last_ok_at: string | null;
  last_ok_bytes: number | null;
  last_ok_files: number | null;
  destination: string | null;
  recent: { started_at: string; ok: boolean | null; bytes: number | null }[];
}
