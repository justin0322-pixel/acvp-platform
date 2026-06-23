import type { Algorithm, Envelope, LoginResult } from "./types";
import { wrap } from "./envelope";

const BASE = (import.meta.env.VITE_API_BASE as string) ?? "http://localhost:8000/acvp/v1";

async function call<T>(path: string, init: RequestInit = {}, token?: string): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string>),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${BASE}${path}`, { ...init, headers });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);

  const body = (await res.json()) as Envelope<T>;
  return body[1]; // strip the acvVersion envelope
}

export function login(password: string): Promise<LoginResult> {
  return call<LoginResult>("/login", {
    method: "POST",
    body: JSON.stringify(wrap({ password })),
  });
}

export function listAlgorithms(token: string): Promise<{ algorithms: Algorithm[] }> {
  return call<{ algorithms: Algorithm[] }>("/algorithms", {}, token);
}
