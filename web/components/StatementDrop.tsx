"use client";

import { useEffect, useRef, useState } from "react";

type State =
  | { kind: "idle" }
  | { kind: "busy"; name: string }
  | { kind: "done"; summary: Record<string, unknown> }
  | { kind: "error"; message: string };

export function StatementDrop() {
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [state, setState] = useState<State>({ kind: "idle" });
  const [over, setOver] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    fetch("/api/money/status")
      .then((r) => r.json())
      .then((j) => setEnabled(Boolean(j.enabled)))
      .catch(() => setEnabled(false));
  }, []);

  async function send(file: File) {
    if (!file.name.toLowerCase().endsWith(".xlsx")) {
      setState({ kind: "error", message: "Choose an ABA statement exported as .xlsx." });
      return;
    }
    setState({ kind: "busy", name: file.name });
    const body = new FormData();
    body.append("file", file);
    try {
      const res = await fetch("/api/money/import", { method: "POST", body });
      const json = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(json.detail ?? `Import failed (${res.status})`);
      setState({ kind: "done", summary: json });
    } catch (e) {
      setState({ kind: "error", message: e instanceof Error ? e.message : "Import failed." });
    }
  }

  const disabled = enabled === false;

  return (
    <div className="flex flex-col gap-4">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled) setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setOver(false);
          const f = e.dataTransfer.files[0];
          if (f && !disabled) void send(f);
        }}
        className={`card flex flex-col items-center gap-3 border-dashed px-6 py-12 text-center transition-colors ${
          over ? "border-accent bg-accent-soft" : ""
        } ${disabled ? "hatch opacity-80" : ""}`}
      >
        <p className="font-display text-2xl font-semibold">
          {state.kind === "busy" ? `Importing ${state.name}…` : "Drop a statement here"}
        </p>
        <p className="max-w-[44ch] text-ink-2">
          {disabled
            ? "Statement import is turned off on this server. Set ENABLE_BANK_IMPORT=1 and mount the importer to enable it."
            : "ABA statement exported as .xlsx. Transactions are sent to Sure; nothing here touches your health data."}
        </p>
        <input
          ref={input}
          id="statement"
          type="file"
          accept=".xlsx"
          hidden
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) void send(f);
            e.target.value = "";
          }}
        />
        <button
          type="button"
          disabled={disabled || state.kind === "busy"}
          onClick={() => input.current?.click()}
          className="mt-2 rounded-xl bg-accent px-5 py-2.5 font-medium text-ground transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
        >
          Choose file
        </button>
      </div>

      <div aria-live="polite">
        {state.kind === "error" && (
          <p className="rounded-xl bg-alert-soft px-4 py-3 text-alert">{state.message}</p>
        )}
        {state.kind === "done" && (
          <dl className="card grid grid-cols-2 gap-x-6 gap-y-3 p-5 sm:grid-cols-3">
            {Object.entries(state.summary).map(([k, v]) => (
              <div key={k}>
                <dt className="eyebrow">{k.replace(/_/g, " ")}</dt>
                <dd className="font-display text-2xl font-semibold">{typeof v === "object" ? JSON.stringify(v) : String(v)}</dd>
              </div>
            ))}
          </dl>
        )}
      </div>
    </div>
  );
}
