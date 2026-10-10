"use client";

import { useEffect, useState } from "react";

type Mode = "system" | "light" | "dark";
const ORDER: Mode[] = ["system", "light", "dark"];

function apply(mode: Mode) {
  const root = document.documentElement;
  if (mode === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", mode);
}

export function ThemeToggle() {
  const [mode, setMode] = useState<Mode>("system");

  useEffect(() => {
    try {
      const saved = localStorage.getItem("lifey-theme") as Mode | null;
      if (saved && ORDER.includes(saved)) setMode(saved);
    } catch {}
  }, []);

  function pick(m: Mode) {
    setMode(m);
    apply(m);
    try {
      localStorage.setItem("lifey-theme", m);
    } catch {}
  }

  return (
    <div role="group" aria-label="Theme" className="flex rounded-xl border border-line bg-raised p-1 text-xs font-medium">
      {ORDER.map((m) => (
        <button
          key={m}
          type="button"
          onClick={() => pick(m)}
          aria-pressed={mode === m}
          className={`flex-1 rounded-lg px-2 py-1.5 capitalize ${mode === m ? "bg-accent-soft text-accent" : "text-ink-3 hover:text-ink"}`}
        >
          {m}
        </button>
      ))}
    </div>
  );
}
