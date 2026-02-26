/**
 * Auth Domain API Client
 * Authentication, session management, API keys.
 */

import { fetchJson, postJson, setSessionToken } from './client';

export type AuthUser = {
  id: string;
  email: string;
  created_at: number;
};

export async function authRegister(email: string, password: string): Promise<{ session_token: string; user: AuthUser }> {
  const result = await postJson<{ session_token: string; user: AuthUser }>('/auth/register', { email, password });
  setSessionToken(result.session_token);
  return result;
}

export async function authLogin(email: string, password: string): Promise<{ session_token: string; user: AuthUser }> {
  const result = await postJson<{ session_token: string; user: AuthUser }>('/auth/login', { email, password });
  setSessionToken(result.session_token);
  return result;
}

export async function authLogout(): Promise<void> {
  await postJson('/auth/logout');
  setSessionToken(null);
}

export async function authMe(): Promise<AuthUser> {
  return fetchJson<AuthUser>('/auth/me');
}

export async function authSetOpenAiKey(apiKey: string, model = 'gpt-5-codex'): Promise<{ configured: boolean; model: string }> {
  return postJson('/auth/openai-key', { api_key: apiKey, model });
}

export async function authOpenAiStatus(): Promise<{
  configured: boolean;
  model: string | null;
  masked_key: string | null;
  valid: boolean | null;
  error: string | null;
}> {
  return fetchJson('/auth/openai-key/status');
}

export async function authDeleteOpenAiKey(): Promise<{ configured: boolean; model: string | null }> {
  return postJson('/auth/openai-key/delete');
}

export async function authRequestPasswordReset(
  email: string
): Promise<{ accepted: boolean; delivery: string; reset_token: string | null; expires_in_s: number }> {
  return postJson('/auth/password-reset/request', { email });
}

export async function authConfirmPasswordReset(email: string, token: string, newPassword: string): Promise<void> {
  await postJson('/auth/password-reset/confirm', { email, token, new_password: newPassword });
}
