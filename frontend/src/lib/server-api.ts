import { cookies } from "next/headers";
import type { User } from "@/types/auth";

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function cookieHeader(): Promise<string> {
  const store = await cookies();
  return store.getAll().map((c) => `${c.name}=${c.value}`).join("; ");
}

export async function serverGet<T>(path: string): Promise<T | null> {
  const response = await fetch(`${BACKEND_URL}/api/v1${path}`, {
    headers: { cookie: await cookieHeader() },
    cache: "no-store",
  });

  if (!response.ok) {
    return null;
  }
  return (await response.json()) as T;
}

export async function getCurrentUserServer(): Promise<User | null> {
  return serverGet<User>("/auth/me");
}
