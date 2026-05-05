/**
 * Global API fetch wrapper with automatic auth header injection.
 * All API calls should use apiFetch() instead of raw fetch().
 */

import { authHeaders } from "./auth-client";

/** Resolve API URL (empty base = same origin via nginx reverse proxy). */
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "";

/** Build full API URL. */
export function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}

/** Authenticated fetch - automatically injects JWT auth headers. */
export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  const auth = authHeaders();
  for (const [k, v] of Object.entries(auth)) {
    if (!headers.has(k)) headers.set(k, v);
  }
  return fetch(apiUrl(path), { ...init, headers });
}

/** Authenticated GET with JSON parsing. */
export async function apiGet<T = unknown>(path: string): Promise<T> {
  const res = await apiFetch(path);
  if (!res.ok) throw new Error(`API ${res.status}: ${path}`);
  return res.json();
}

/** Authenticated POST. */
export async function apiPost<T = unknown>(path: string, body: unknown): Promise<T> {
  const res = await apiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `API ${res.status}: ${path}`);
  }
  return res.json();
}

/** Authenticated DELETE. */
export async function apiDelete<T = unknown>(path: string): Promise<T> {
  const res = await apiFetch(path, { method: "DELETE" });
  if (!res.ok) throw new Error(`API ${res.status}: ${path}`);
  return res.json().catch(() => ({} as T));
}

/** Authenticated PATCH. */
export async function apiPatch<T = unknown>(path: string, body: unknown): Promise<T> {
  const res = await apiFetch(path, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`API ${res.status}: ${path}`);
  return res.json();
}
