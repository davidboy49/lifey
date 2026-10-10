import type { Provenance as P, Status } from "@/lib/types";

const LABEL: Record<P, string> = {
  measured: "Measured",
  estimate: "Garmin estimate",
  score: "Garmin score",
  not_recorded: "Not recorded",
};

const HINT: Record<P, string> = {
  measured: "Read directly from the device.",
  estimate: "Derived by Garmin; an estimate, not a clinical measurement.",
  score: "A vendor score, not a physical quantity.",
  not_recorded: "The device supplied no reading. This is a gap, not a zero.",
};

export function Provenance({ kind }: { kind: P }) {
  return (
    <span
      title={HINT[kind]}
      className={`inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full border px-2 py-0.5 font-mono text-[10.5px] uppercase tracking-[0.07em] ${
        kind === "not_recorded" ? "hatch border-dashed border-ink-3/50 text-ink-3" : "border-line text-ink-2"
      }`}
    >
      <span
        aria-hidden
        className={`inline-block size-1.5 rounded-full ${
          kind === "measured" ? "bg-ink-2" : kind === "not_recorded" ? "bg-transparent ring-1 ring-ink-3" : "border border-ink-2"
        }`}
      />
      {LABEL[kind]}
    </span>
  );
}

export const TONE: Record<Status, { fg: string; bg: string; text: string }> = {
  good: { fg: "var(--good)", bg: "bg-good-soft", text: "text-good" },
  watch: { fg: "var(--watch)", bg: "bg-watch-soft", text: "text-watch" },
  alert: { fg: "var(--alert)", bg: "bg-alert-soft", text: "text-alert" },
  unknown: { fg: "var(--ink-3)", bg: "bg-panel", text: "text-ink-3" },
};
