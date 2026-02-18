import type { ControlState, Health, Status } from './types';

const BASE = (import.meta.env.VITE_BRIDGE_BASE as string | undefined) ?? 'http://127.0.0.1:8787';
let SESSION_TOKEN = '';

export function setSessionToken(token: string | null): void {
  SESSION_TOKEN = (token ?? '').trim();
}

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

export type FirmwareStatus = {
  state: string;
  phase: string;
  running: boolean;
  started_at: number | null;
  finished_at: number | null;
  returncode: number | null;
  last_cmd: string[];
  log_tail: string[];
  defaults: {
    sketch: string;
    fqbn: string;
    port: string;
  };
};

export type FirmwareCheck = {
  ok: boolean;
  version?: string;
  binary?: string;
  detected_ports?: unknown[];
  raw?: unknown;
  error?: string;
  hint?: string;
  install_suggestion?: string;
};

export type FirmwareSketch = {
  path: string;
  content: string;
};

export type FirmwareBoards = {
  ok: boolean;
  recommended_fqbn?: string;
  recommended_port?: string;
  ports: Array<{
    address: string | null;
    label: string | null;
    protocol: string | null;
    fqbn: string | null;
    board_name: string | null;
  }>;
  raw?: unknown;
  error?: string;
};

export type AiHistoryItem = {
  ts: number;
  role: 'user' | 'assistant';
  text: string;
};

export type AiStatus = {
  configured: boolean;
  model: string;
  history_len: number;
};

export type AuthUser = {
  id: number;
  email: string;
  openai_configured: boolean;
  openai_model: string | null;
};


export type CompatReport = {
  ok: boolean;
  profile: string;
  firmware_id: string | null;
  required_fields: string[];
  missing_fields: string[];
  supported_commands: string[];
  missing_commands: string[];
  warnings: string[];
  status?: Status;
};

export type ConnectProbeReport = {
  ok: boolean;
  connected: boolean;
  port: string;
  baud: number;
  port_meta: {
    device: string;
    description: string | null;
    manufacturer: string | null;
    product: string | null;
    serial_number: string | null;
    vid: number | null;
    pid: number | null;
    hwid: string | null;
  };
  mcu_guess: string;
  firmware_profile: string;
  confidence_pct: number;
  status_schema_ok: boolean;
  status_error: string | null;
  components: {
    imu: boolean;
    motor_driver: boolean;
    encoder_feedback: boolean;
    voltage_telemetry: boolean;
    wheel_model: boolean;
    persistent_calibration: boolean;
  };
  commands: string[];
  missing_commands: string[];
  warnings: string[];
  next_questions: string[];
  compat?: CompatReport;
};

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(SESSION_TOKEN ? { 'X-Session-Token': SESSION_TOKEN } : {}),
      ...(init?.headers ?? {}),
    },
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


export async function probeCompat(): Promise<CompatReport> {
  const d = await req<{ ok: true; compat: CompatReport }>('/probe/compat');
  return d.compat;
}

export async function probeConnect(): Promise<ConnectProbeReport> {
  const d = await req<{ ok: true; probe: ConnectProbeReport }>('/probe/connect');
  return d.probe;
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

export async function firmwareStatus(): Promise<FirmwareStatus> {
  const d = await req<{ ok: true; firmware: FirmwareStatus }>('/firmware/status');
  return d.firmware;
}

export async function firmwareCheck(): Promise<FirmwareCheck> {
  const d = await req<{ ok: true; firmware_check: FirmwareCheck }>('/firmware/check', {
    method: 'POST',
    body: '{}',
  });
  return d.firmware_check;
}

export async function firmwareCompile(sketch?: string, fqbn?: string): Promise<FirmwareStatus> {
  const d = await req<{ ok: true; firmware: FirmwareStatus }>('/firmware/compile', {
    method: 'POST',
    body: JSON.stringify({ sketch, fqbn }),
  });
  return d.firmware;
}

export async function firmwareUpload(sketch?: string, fqbn?: string, port?: string): Promise<FirmwareStatus> {
  const d = await req<{ ok: true; firmware: FirmwareStatus }>('/firmware/upload', {
    method: 'POST',
    body: JSON.stringify({ sketch, fqbn, port }),
  });
  return d.firmware;
}

export async function firmwareUploadGuarded(sketch?: string, fqbn?: string, port?: string): Promise<FirmwareStatus> {
  const d = await req<{ ok: true; firmware: FirmwareStatus }>('/firmware/upload-guarded', {
    method: 'POST',
    body: JSON.stringify({ sketch, fqbn, port }),
  });
  return d.firmware;
}

export async function firmwareInstallCli(): Promise<FirmwareStatus> {
  const d = await req<{ ok: true; firmware: FirmwareStatus }>('/firmware/install-cli', {
    method: 'POST',
    body: '{}',
  });
  return d.firmware;
}

export async function firmwareReadSketch(path?: string): Promise<FirmwareSketch> {
  const qs = path ? `?path=${encodeURIComponent(path)}` : '';
  const d = await req<{ ok: true; sketch: FirmwareSketch }>(`/firmware/sketch${qs}`);
  return d.sketch;
}

export async function firmwareWriteSketch(content: string, path?: string): Promise<{ path: string; bytes: number }> {
  const d = await req<{ ok: true; sketch: { path: string; bytes: number } }>('/firmware/sketch', {
    method: 'POST',
    body: JSON.stringify({ content, path }),
  });
  return d.sketch;
}

export async function firmwareBoards(): Promise<FirmwareBoards> {
  const d = await req<{ ok: true; boards: FirmwareBoards }>('/firmware/boards');
  return d.boards;
}

export async function aiStatus(): Promise<{ ai: AiStatus; history: AiHistoryItem[] }> {
  const d = await req<{ ok: true; ai: AiStatus; history: AiHistoryItem[] }>('/ai/status');
  return { ai: d.ai, history: d.history };
}

export async function aiChat(message: string): Promise<{ reply: string; ai: AiStatus; history: AiHistoryItem[] }> {
  const d = await req<{ ok: true; reply: string; ai: AiStatus; history: AiHistoryItem[] }>('/ai/chat', {
    method: 'POST',
    body: JSON.stringify({ message }),
  });
  return { reply: d.reply, ai: d.ai, history: d.history };
}

export async function authRegister(email: string, password: string): Promise<{ session_token: string; user: AuthUser }> {
  const d = await req<{ ok: true; session_token: string; user: AuthUser }>('/auth/register', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  });
  return { session_token: d.session_token, user: d.user };
}

export async function authLogin(email: string, password: string): Promise<{ session_token: string; user: AuthUser }> {
  const d = await req<{ ok: true; session_token: string; user: AuthUser }>('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  });
  return { session_token: d.session_token, user: d.user };
}

export async function authLogout(): Promise<void> {
  await req('/auth/logout', { method: 'POST', body: '{}' });
}

export async function authMe(): Promise<AuthUser> {
  const d = await req<{ ok: true; user: AuthUser }>('/auth/me');
  return d.user;
}

export async function authSetOpenAiKey(apiKey: string, model = 'gpt-5-mini'): Promise<{ configured: boolean; model: string }> {
  const d = await req<{ ok: true; openai: { configured: boolean; model: string } }>('/auth/openai-key', {
    method: 'POST',
    body: JSON.stringify({ api_key: apiKey, model }),
  });
  return d.openai;
}

export async function authOpenAiStatus(): Promise<{ configured: boolean; model: string | null }> {
  const d = await req<{ ok: true; openai: { configured: boolean; model: string | null } }>('/auth/openai-key/status');
  return d.openai;
}

export async function authDeleteOpenAiKey(): Promise<{ configured: boolean; model: string | null }> {
  const d = await req<{ ok: true; openai: { configured: boolean; model: string | null } }>('/auth/openai-key/delete', {
    method: 'POST',
    body: '{}',
  });
  return d.openai;
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
