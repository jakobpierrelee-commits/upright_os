/**
 * Shared API client utilities.
 * Base URL, session token, and common fetch helpers.
 */

export const BASE = (import.meta.env.VITE_BRIDGE_BASE as string | undefined) ?? 'http://127.0.0.1:8797';

let SESSION_TOKEN = '';

export function setSessionToken(token: string | null): void {
  SESSION_TOKEN = (token ?? '').trim();
}

export function getSessionToken(): string {
  return SESSION_TOKEN;
}

export function authHeaders(): Record<string, string> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  if (SESSION_TOKEN) {
    headers['Authorization'] = `Bearer ${SESSION_TOKEN}`;
  }
  return headers;
}

export async function fetchJson<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: {
      ...authHeaders(),
      ...options?.headers,
    },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json();
}

export async function postJson<T>(path: string, body?: unknown): Promise<T> {
  return fetchJson<T>(path, {
    method: 'POST',
    body: body ? JSON.stringify(body) : undefined,
  });
}
