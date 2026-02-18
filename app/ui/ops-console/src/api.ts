import type { ControlState, Health, Status } from './types';

const BASE = (import.meta.env.VITE_BRIDGE_BASE as string | undefined) ?? 'http://127.0.0.1:8787';

export type CommissioningStatus = {
  state: string;
  running: boolean;
  started_at: number | null;
  finished_at: number | null;
  returncode: number | null;
  last_cmd: string[];
  log_tail: string[];
};

export type CommissioningArtifacts = {
  out_dir: string;
  latest_metrics: string | null;
  latest_run: string | null;
  metrics: string[];
  runs: string[];
};

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    ...init,
  });
  const data = (await res.json()) as T & { ok?: boolean; error?: string };
  if (!res.ok || (typeof data === 'object' && data && 'ok' in data && data.ok === false)) {
    const msg = (data as { error?: string }).error ?? `${res.status}`;
    throw new Error(msg);
  }
  return data;
}

export async function getHealth(): Promise<{ health: Health; control?: ControlState; telemetry_ws?: string; telemetry_enabled?: boolean }> {
  const d = await req<{ ok: true; health: Health; control?: ControlState; telemetry_ws?: string; telemetry_enabled?: boolean }>('/health');
  return { health: d.health, control: d.control, telemetry_ws: d.telemetry_ws, telemetry_enabled: d.telemetry_enabled };
}

export async function getStatus(): Promise<{ status: Status; control?: ControlState }> {
  const d = await req<{ ok: true; status: Status; control?: ControlState }>('/status');
  return { status: d.status, control: d.control };
}

export async function getLines(n = 120): Promise<string[]> {
  const d = await req<{ ok: true; lines: string[] }>(`/lines?n=${n}`);
  return d.lines;
}

export async function heartbeat(): Promise<ControlState> {
  const d = await req<{ ok: true; control: ControlState }>('/session/heartbeat', { method: 'POST', body: '{}' });
  return d.control;
}

export async function commissioningRun(autoPrompts = true): Promise<CommissioningStatus> {
  const d = await req<{ ok: true; commissioning: CommissioningStatus }>('/commissioning/run', {
    method: 'POST',
    body: JSON.stringify({ auto_prompts: autoPrompts }),
  });
  return d.commissioning;
}

export async function commissioningStatus(): Promise<CommissioningStatus> {
  const d = await req<{ ok: true; commissioning: CommissioningStatus }>('/commissioning/status');
  return d.commissioning;
}

export async function commissioningArtifacts(): Promise<CommissioningArtifacts> {
  const d = await req<{ ok: true; artifacts: CommissioningArtifacts }>('/commissioning/artifacts');
  return d.artifacts;
}

export async function postCommand(cmd: string, expect?: string): Promise<void> {
  await req('/command', {
    method: 'POST',
    body: JSON.stringify({ cmd, expect }),
  });
}

export async function armPrepare(): Promise<ControlState> {
  const d = await req<{ ok: true; control: ControlState }>('/arm/prepare', { method: 'POST', body: '{}' });
  return d.control;
}

export async function armConfirm(): Promise<{ status: Status; control: ControlState }> {
  const d = await req<{ ok: true; status: Status; control: ControlState }>('/arm/confirm', {
    method: 'POST',
    body: '{}',
  });
  return { status: d.status, control: d.control };
}

export async function arm(): Promise<{ status: Status; control?: ControlState }> {
  const d = await req<{ ok: true; status: Status; control?: ControlState }>('/arm', { method: 'POST', body: '{}' });
  return { status: d.status, control: d.control };
}

export async function disarm(): Promise<{ status: Status; control?: ControlState }> {
  const d = await req<{ ok: true; status: Status; control?: ControlState }>('/disarm', { method: 'POST', body: '{}' });
  return { status: d.status, control: d.control };
}

export async function estopLatch(): Promise<{ status: Status; control: ControlState }> {
  const d = await req<{ ok: true; status: Status; control: ControlState }>('/estop/latch', {
    method: 'POST',
    body: '{}',
  });
  return { status: d.status, control: d.control };
}

export async function estopReset(): Promise<{ status: Status; control: ControlState }> {
  const d = await req<{ ok: true; status: Status; control: ControlState }>('/estop/reset', {
    method: 'POST',
    body: '{}',
  });
  return { status: d.status, control: d.control };
}

export async function calZero(): Promise<{ status: Status; control?: ControlState }> {
  const d = await req<{ ok: true; status: Status; control?: ControlState }>('/cal_zero', { method: 'POST', body: '{}' });
  return { status: d.status, control: d.control };
}

export async function saveCfg(): Promise<void> {
  await req('/savecfg', { method: 'POST', body: '{}' });
}

export async function setPid(kp: number, ki: number, kd: number): Promise<{ status: Status; control?: ControlState }> {
  const d = await req<{ ok: true; status: Status; control?: ControlState }>('/pid', {
    method: 'POST',
    body: JSON.stringify({ kp, ki, kd }),
  });
  return { status: d.status, control: d.control };
}

export async function setMotion(kv: number, kx: number): Promise<{ status: Status; control?: ControlState }> {
  const d = await req<{ ok: true; status: Status; control?: ControlState }>('/motion', {
    method: 'POST',
    body: JSON.stringify({ kv, kx }),
  });
  return { status: d.status, control: d.control };
}

export async function setSetpoint(deg: number): Promise<{ status: Status; control?: ControlState }> {
  const d = await req<{ ok: true; status: Status; control?: ControlState }>('/setpoint', {
    method: 'POST',
    body: JSON.stringify({ deg }),
  });
  return { status: d.status, control: d.control };
}
