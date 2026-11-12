"use client";

import { useRef, useState } from "react";

const NOTE_MAX = 2000;            // same limit as the API; never trim silently
const MAX_FILE = 10 * 1024 * 1024;
const ACCEPT = "image/jpeg,image/png,image/webp";

function problemText(res: Response, body: { detail?: unknown }): string {
  if (typeof body.detail === "string") return body.detail;
  if (res.status === 413) return "That photo is bigger than the server accepts. Nothing was saved.";
  if (res.status === 401) return "Your session has ended. Sign in again, then retry. Nothing was saved.";
  return "Couldn’t save that. Nothing was saved. Try again in a moment.";
}

/** Write on today's page of the book: a note, optionally with one photo. Saved as an ordinary journal note. */
export function BookWriter({ today, empty, onSaved }: { today: string; empty: boolean; onSaved: () => void }) {
  const [note, setNote] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const picker = useRef<HTMLInputElement>(null);
  const text = note.trim();

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!text && !file) return setError("Write something first, or add a photo.");
    if (text.length > NOTE_MAX) return setError(`That is ${text.length} characters; the limit is ${NOTE_MAX}. Nothing was cut.`);
    if (file && file.size > MAX_FILE) return setError("That photo is over 10 MB.");
    setBusy(true);
    setError(null);
    try {
      let res: Response;
      if (file) {
        const form = new FormData();
        form.append("files", file);
        form.append("note", text);
        form.append("date", today);
        res = await fetch("/api/attachments", { method: "POST", body: form });
      } else {
        res = await fetch("/api/journal", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ kind: "note", note: text, date: today }),
        });
      }
      const body = await res.json().catch(() => ({}));
      if (!res.ok) return setError(problemText(res, body));
      setNote("");
      setFile(null);
      if (picker.current) picker.current.value = "";
      onSaved();
    } catch {
      setError("Couldn’t reach the server. Nothing was saved.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={save} className="book-keep mt-[28px]">
      <label className="sr-only" htmlFor="book-write">Write on today’s page</label>
      <textarea
        id="book-write"
        value={note}
        onChange={(e) => setNote(e.target.value)}
        rows={6}
        placeholder={empty ? "Dear diary…" : "Keep writing…"}
        className="block w-full resize-none border-0 bg-transparent p-0 font-[family-name:var(--font-book)] text-[17px] leading-[28px] text-[var(--paper-ink)] outline-none placeholder:italic placeholder:text-[var(--paper-ink-2)]"
      />
      <div className="mt-[14px] flex flex-wrap items-center gap-2 font-sans">
        <button type="submit" disabled={busy}
                className="rounded-full bg-[var(--paper-ink)] px-4 py-1.5 text-sm font-semibold text-[var(--paper)] disabled:opacity-50">
          {busy ? "Saving…" : "Save to page"}
        </button>
        <label className="cursor-pointer rounded-full border border-[var(--paper-edge)] px-3 py-1.5 text-sm text-[var(--paper-ink-2)] hover:text-[var(--paper-ink)]">
          {file ? `Photo: ${file.name}` : "Add photo"}
          <input ref={picker} type="file" accept={ACCEPT} className="sr-only"
                 onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </label>
        {text.length > NOTE_MAX * 0.9 && <span className="text-xs text-[var(--paper-ink-2)]">{text.length}/{NOTE_MAX}</span>}
      </div>
      {error && <p role="alert" className="mt-2 font-sans text-sm text-[var(--alert)]">{error}</p>}
    </form>
  );
}
