"use client";

import { useRef, useState } from "react";

export function CopySummary({ text }: { text: string }) {
  const [state, setState] = useState<"idle" | "copied" | "manual">("idle");
  const area = useRef<HTMLTextAreaElement>(null);

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setState("copied");
      setTimeout(() => setState("idle"), 2500);
    } catch {
      // Some browsers refuse clipboard access: show the text selected so it can be copied by hand.
      setState("manual");
      setTimeout(() => area.current?.select(), 50);
    }
  }

  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={copy}
          className="rounded-xl bg-accent px-5 py-2.5 font-medium text-ground hover:opacity-90"
        >
          Copy a summary for your doctor
        </button>
        <span role="status" aria-live="polite" className="text-sm text-good">
          {state === "copied" ? "Copied." : ""}
        </span>
      </div>
      <details open={state === "manual"} className="rounded-xl border border-line bg-panel p-3 text-sm">
        <summary className="cursor-pointer font-medium text-ink-2">Preview the summary</summary>
        <textarea
          ref={area}
          readOnly
          value={text}
          rows={Math.min(14, text.split("\n").length + 1)}
          className="mt-2 w-full resize-y rounded-lg border border-line bg-raised p-3 font-mono text-[12.5px] text-ink"
          aria-label="Sleep summary to share"
        />
      </details>
    </div>
  );
}
