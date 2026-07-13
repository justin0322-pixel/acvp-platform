import { wrap } from "./envelope";
import type {
  Algorithm, Envelope, LoginResult, ModuleResource, OeResource, Paged, SessionObject,
  SessionInfo, VectorSetResponse, VectorResults, SessionResults, RequestObject, Prompt,
} from "./types";

/**
 * BASE is the ACVP root; ORIGIN is the server root. URLs the server hands back
 * (e.g. vectorSetUrls) already include the "/acvp/v1" prefix, so we resolve
 * those against ORIGIN and our own short paths against BASE.
 */
const BASE = (import.meta.env.VITE_API_BASE as string) ?? "http://localhost:8000/acvp/v1";
const ORIGIN = BASE.replace(/\/acvp\/v1\/?$/, "");

export const backendLabel = ORIGIN;

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

function resolve(pathOrUrl: string): string {
  return pathOrUrl.startsWith("/acvp/") ? ORIGIN + pathOrUrl : BASE + pathOrUrl;
}

async function call<T>(pathOrUrl: string, init: RequestInit = {}, token?: string): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string>),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(resolve(pathOrUrl), { ...init, headers });
  const text = await res.text();
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`;
    try { msg = JSON.parse(text)?.error ?? msg; } catch { /* keep default */ }
    throw new ApiError(res.status, msg);
  }
  if (!text) return undefined as T; // 200 no-content (results submission)
  const body = JSON.parse(text) as Envelope<T>;
  return body[1];
}

/* ---- auth ---- */
export function login(password: string, accessToken?: string): Promise<LoginResult> {
  const payload: Record<string, unknown> = { password };
  if (accessToken) payload.accessToken = accessToken; // renewal
  return call<LoginResult>("/login", { method: "POST", body: JSON.stringify(wrap(payload)) });
}

export const listAlgorithms = (loginToken: string) =>
  call<{ algorithms: Algorithm[] }>("/algorithms", {}, loginToken);

/* ---- metadata: what a certificate binds to (spec 12.11 / 12.12) ---- */
export const listModules = (loginToken: string) =>
  call<Paged<ModuleResource>>("/modules", {}, loginToken);

export const listOes = (loginToken: string) =>
  call<Paged<OeResource>>("/oes", {}, loginToken);

/* ---- test session (created with the LOGIN token) ---- */
export function createSession(
  loginToken: string, algorithms: Record<string, unknown>[], isSample: boolean,
): Promise<SessionObject> {
  return call<SessionObject>(
    "/testSessions",
    { method: "POST", body: JSON.stringify(wrap({ isSample, algorithms })) },
    loginToken,
  );
}

/* ---- everything below is SESSION-scoped: use the session's own token ---- */
export const getSession = (id: number, sessionToken: string) =>
  call<SessionInfo>(`/acvp/v1/testSessions/${id}`, {}, sessionToken);

export const listVectorSets = (id: number, sessionToken: string) =>
  call<{ vectorSetUrls: string[] }>(`/acvp/v1/testSessions/${id}/vectorSets`, {}, sessionToken);

export const getVectorSet = (url: string, sessionToken: string) =>
  call<VectorSetResponse>(url, {}, sessionToken);

export const getExpected = (vsUrl: string, sessionToken: string) =>
  call<Prompt>(`${vsUrl}/expected`, {}, sessionToken);

export const submitResults = (vsUrl: string, payload: unknown, sessionToken: string) =>
  call<void>(`${vsUrl}/results`, { method: "POST", body: JSON.stringify(wrap(payload)) }, sessionToken);

export const resubmitResults = (vsUrl: string, payload: unknown, sessionToken: string) =>
  call<void>(`${vsUrl}/results`, { method: "PUT", body: JSON.stringify(wrap(payload)) }, sessionToken);

export const getResults = (vsUrl: string, sessionToken: string) =>
  call<VectorResults>(`${vsUrl}/results`, {}, sessionToken);

export const getSessionResults = (id: number, sessionToken: string) =>
  call<SessionResults>(`/acvp/v1/testSessions/${id}/results`, {}, sessionToken);

export const certify = (
  id: number, body: { moduleUrl: string; oeUrl: string }, sessionToken: string,
) => call<RequestObject>(`/acvp/v1/testSessions/${id}`, { method: "PUT", body: JSON.stringify(wrap(body)) }, sessionToken);

/* ---- requests are user-level: poll with the LOGIN token ---- */
export const getRequest = (url: string, loginToken: string) =>
  call<RequestObject>(url, {}, loginToken);

export const idFromUrl = (url: string) => Number(url.split("/").pop());

export function getJwtExpiry(token: string): number | null {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;
    const payload = JSON.parse(atob(parts[1]));
    return typeof payload.exp === "number" ? payload.exp : null;
  } catch {
    return null;
  }
}
