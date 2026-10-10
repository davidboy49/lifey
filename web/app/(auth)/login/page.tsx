"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export default function LoginPage() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ username: form.get("username"), password: form.get("password") }),
      });
      if (res.ok) {
        router.replace("/");
        router.refresh();
        return;
      }
      if (res.status === 429) {
        const wait = Math.ceil(Number(res.headers.get("retry-after") ?? 900) / 60);
        setError(`Too many attempts. Try again in about ${wait} minute${wait === 1 ? "" : "s"}.`);
      } else if (res.status === 401) {
        setError("That username and password don’t match.");
      } else {
        setError("Sign-in is unavailable right now. Try again shortly.");
      }
    } catch {
      setError("Couldn’t reach the server. Check your connection.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-dvh items-center justify-center px-4 py-10">
      <div className="w-full max-w-[400px]">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src="/brand/lifey-logo.webp"
          width={150}
          height={205}
          alt="Lifey"
          className="mx-auto mb-8 h-auto w-[150px] rounded-3xl border border-line"
        />
        <form onSubmit={submit} className="card rise flex flex-col gap-5 p-7" aria-describedby="login-error">
          <div>
            <h1 className="font-display text-2xl font-semibold">Sign in</h1>
            <p className="mt-1 text-sm text-ink-2">Your health and money stay private to you.</p>
          </div>

          <label className="flex flex-col gap-1.5 text-sm font-medium" htmlFor="username">
            Username
            <input
              id="username"
              name="username"
              autoComplete="username"
              autoCapitalize="none"
              spellCheck={false}
              required
              className="rounded-xl border border-line bg-panel px-3.5 py-2.5 text-[15px] font-normal text-ink outline-none focus:border-accent"
            />
          </label>

          <label className="flex flex-col gap-1.5 text-sm font-medium" htmlFor="password">
            Password
            <input
              id="password"
              name="password"
              type="password"
              autoComplete="current-password"
              required
              className="rounded-xl border border-line bg-panel px-3.5 py-2.5 text-[15px] font-normal text-ink outline-none focus:border-accent"
            />
          </label>

          <p id="login-error" role="alert" aria-live="polite" className={error ? "rounded-xl bg-alert-soft px-3.5 py-2.5 text-sm text-alert" : "sr-only"}>
            {error}
          </p>

          <button
            type="submit"
            disabled={busy}
            className="rounded-xl bg-accent px-5 py-3 font-medium text-ground transition-opacity hover:opacity-90 disabled:cursor-wait disabled:opacity-60"
          >
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </div>
    </main>
  );
}
