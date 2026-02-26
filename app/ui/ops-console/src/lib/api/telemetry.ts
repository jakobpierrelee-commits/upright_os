/**
 * Telemetry Domain API Client
 * Serial diagnostics, burst capture, traces.
 */

import { fetchJson, postJson } from './client';

export type SerialDiag = {
  connected: boolean;
  port: string | null;
  baud: number | null;
  bytes_rx: number;
  bytes_tx: number;
  errors: number;
  last_rx_ts: number | null;
};

export type BurstStatus = {
  state: string;
  armed: boolean;
  triggered: boolean;
  samples: number;
  delay_ms: number;
  lines: number;
  freq_hz: number;
  csv_path: string | null;
  label: string | null;
};

export async function serialDiag(): Promise<SerialDiag> {
  return fetchJson<SerialDiag>('/diag/serial');
}

export async function burstStatus(): Promise<BurstStatus> {
  return fetchJson<BurstStatus>('/burst/status');
}

export async function burstArm(delayMs = 3000, lines = 80, freqHz = 8): Promise<BurstStatus> {
  return postJson<BurstStatus>('/burst/arm', { delay_ms: delayMs, lines, freq_hz: freqHz });
}

export async function burstLabel(label: string): Promise<BurstStatus> {
  return postJson<BurstStatus>('/burst/label', { label });
}

export async function toolingListTraces(): Promise<string[]> {
  const data = await fetchJson<{ traces: string[] }>('/tooling/traces');
  return data.traces;
}

export async function toolingTraceReplay(payload: {
  trace_path: string;
  speed?: number;
  start_offset_s?: number;
  end_offset_s?: number;
}): Promise<{ ok: boolean; samples: number; duration_s: number }> {
  return postJson('/tooling/trace-replay', payload);
}

export async function toolingParamSweep(payload: {
  param: string;
  start: number;
  end: number;
  steps: number;
  duration_per_step_s?: number;
  metrics?: string[];
}): Promise<{
  ok: boolean;
  param: string;
  results: Array<{ value: number; metrics: Record<string, number> }>;
}> {
  return postJson('/tooling/param-sweep', payload);
}

export async function toolingSurrogateSim(payload: {
  kp: number;
  ki: number;
  kd: number;
  setpoint?: number;
  duration_s?: number;
}): Promise<{
  ok: boolean;
  predicted_metrics: Record<string, number>;
  confidence: number;
}> {
  return postJson('/tooling/surrogate/simulate', payload);
}
