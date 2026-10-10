import { cookies } from "next/headers";
import type { Today } from "./types";

const API_URL = process.env.API_URL ?? "http://localhost:8000";

export type Result<T> =
  | { status: "ok"; data: T }
  | { status: "unauthorized" }
  | { status: "down" };

/** Server-side fetch that forwards the visitor's session cookie to the API. */
export async function apiGet<T>(path: string): Promise<Result<T>> {
  try {
    const jar = await cookies();
    const res = await fetch(`${API_URL}${path}`, {
      cache: "no-store",
      headers: { cookie: jar.toString() },
    });
    if (res.status === 401) return { status: "unauthorized" };
    if (!res.ok) return { status: "down" };
    return { status: "ok", data: (await res.json()) as T };
  } catch {
    return { status: "down" };
  }
}

export const getToday = () => apiGet<Today>("/api/today");
