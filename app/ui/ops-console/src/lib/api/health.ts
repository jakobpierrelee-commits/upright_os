/**
 * Health Domain API Client
 * Health checks, status, and connection monitoring.
 */

import type { Health, Status } from '../../types';
import { fetchJson } from './client';

export async function getHealth(): Promise<Health> {
  return fetchJson<Health>('/health');
}

export async function getStatus(): Promise<Status> {
  return fetchJson<Status>('/status');
}

export async function getLines(): Promise<string[]> {
  const data = await fetchJson<{ lines: string[] }>('/lines');
  return data.lines;
}
