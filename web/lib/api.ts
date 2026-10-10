import type { Today } from "./types";

const API_URL = process.env.API_URL ?? "http://localhost:8000";

export async function getToday(): Promise<Today | null> {
  try {
    const res = await fetch(`${API_URL}/api/today`, { cache: "no-store" });
    if (!res.ok) return null;
    return (await res.json()) as Today;
  } catch {
    return null;
  }
}
