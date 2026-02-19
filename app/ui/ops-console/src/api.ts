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

export type UnifiedFirmwareSchema = {
  version: string;
  required: {
    profile: string[];
    board: string[];
    hardware: string[];
    pins: string[];
  };
  optional_pins: string[];
  notes: string[];
};

export type UnifiedFirmwareGenerated = {
  schema_version: string;
  sketch_folder: string;
  main_file: string;
  archive: string;
  files: string[];
  profile: Record<string, unknown>;
};

export type FirmwareDocsPack = {
  schema_version: string;
  docs_folder: string;
  archive: string;
  files: string[];
  artifacts?: Record<string, string>;
  generation_id?: string;
  generated_at?: number;
  profile: Record<string, unknown>;
};

export type SerialDiag = {
  connected: boolean;
  port: string;
  baud: number;
  last_status: Record<string, string>;
  last_status_age_ms?: number | null;
  recent_line_count: number;
  queue_depth?: number;
  worker_alive?: boolean;
  serial_metrics?: {
    commands_ok: number;
    commands_err: number;
    timeouts: number;
    latency_p50_ms?: number | null;
    latency_p95_ms?: number | null;
    last_error?: string | null;
  };
};

export type HostCaptureStatus = {
  state: string;
  delay_ms: number;
  freq_hz?: number;
  target_lines: number;
  rows: number;
  started_at?: number | null;
  finished_at?: number | null;
  latest_run?: string | null;
  last_error?: string | null;
};

export type BurstStatus = {
  state: string;
  last_event?: string | null;
  events_recent: string[];
  csv_recent: number;
  host_capture: HostCaptureStatus;
};

export type TraceReplayResult = {
  trace: string;
  result: {
    ok: boolean;
    pass: boolean;
    error?: string;
    checks?: Array<{
      id: string;
      ok: boolean;
      value: number;
      threshold: number;
    }>;
    summary?: {
      sample_count: number;
      rmse_command: number;
      max_abs_command_error: number;
      rmse_pid: number;
      rmse_motion: number;
    };
  };
  replay?: Record<string, unknown>;
};

export type ParamSweepResult = {
  ok: boolean;
  baseline: {
    kp: number;
    ki: number;
    kd: number;
  };
  candidate_count: number;
  pass_count: number;
  best_candidate_summary?: string;
  ranked_top: Array<Record<string, unknown>>;
  rows: Array<Record<string, unknown>>;
};

export type SurrogateSimResult = {
  ok: boolean;
  model?: {
    log_count: number;
    sample_count: number;
    dt_s: number;
    confidence: number;
    distance_from_known: number;
    warning?: string | null;
    gain_ranges?: {
      kp: { min: number; max: number };
      ki: { min: number; max: number };
      kd: { min: number; max: number };
    };
  };
  simulation?: {
    params: {
      kp: number;
      ki: number;
      kd: number;
      setpoint: number;
      duration_s: number;
    };
    metrics: {
      rmse: number;
      overshoot: number;
      settle_s: number | null;
      max_out_pct: number;
      faceplant: boolean;
    };
    sample_count: number;
    samples: Array<{
      t_s: number;
      ang: number;
      gyro: number;
      out: number;
      set: number;
    }>;
  };
  error?: string;
};

export type AiHistoryItem = {
  ts: number;
  role: 'user' | 'assistant';
  text: string;
  meta?: {
    sent_at?: number;
    done_at?: number;
    request_ms?: number;
    first_byte_ms?: number | null;
    tool_calls?: Array<{
      tool: string;
      args: Record<string, unknown>;
      result: {
        ok: boolean;
        tool: string;
        data: Record<string, unknown>;
        error?: string;
        execution_time_ms: number;
      };
    }>;
    apply?: {
      ok: boolean;
      snapshot_id?: string;
      applied?: string[];
      status?: Status;
      error?: string;
      artifacts?: {
        unified_folder?: string;
        unified_archive?: string;
        unified_main_file?: string;
        sketch_path?: string;
        sketch_backup?: string;
        sketch_bytes?: number;
      };
    };
  };
};

export type AiStatus = {
  configured: boolean;
  model: string;
  history_len: number;
  active_thread_id?: string;
  thread_count?: number;
};

export type AiThreadSummary = {
  id: string;
  title: string;
  created_at: number;
  updated_at: number;
  message_count: number;
  preview: string;
};

export type AiProfile = {
  profile_id: string;
  label: string;
  description: string;
  instructions: string;
  policy?: {
    allow_auto_apply?: boolean;
  };
  created_at: number;
  updated_at: number;
};

export type AiProfilesState = {
  active_profile_id: string | null;
  profiles: AiProfile[];
};

export type AuthUser = {
  id: number;
  email: string;
  openai_configured: boolean;
  openai_model: string | null;
};


export type ReadinessCheck = {
  check: string;
  status: 'pass' | 'warn' | 'fail';
  detail: string;
};

export type V2Readiness = {
  contract_version_detected: 'v1' | 'v2' | 'unknown';
  v1_ok: boolean;
  v2_ready: boolean;
  v2_missing_fields: string[];
  v2_factory_ready?: boolean;
  v2_factory_missing_fields?: string[];
  v2_present_fields: string[];
  readiness_checks: ReadinessCheck[];
  v2_recommended_action?: string | null;
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
  // v2 readiness (additive)
  contract_version_detected?: 'v1' | 'v2' | 'unknown';
  v1_ok?: boolean;
  v2_ready?: boolean;
  v2_missing_fields?: string[];
  v2_factory_ready?: boolean;
  v2_factory_missing_fields?: string[];
  v2_present_fields?: string[];
  readiness_checks?: ReadinessCheck[];
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
  // v2 readiness (additive)
  contract_version_detected?: 'v1' | 'v2' | 'unknown';
  v1_ok?: boolean;
  v2_ready?: boolean;
  v2_missing_fields?: string[];
  v2_factory_ready?: boolean;
  v2_factory_missing_fields?: string[];
  v2_present_fields?: string[];
  readiness_checks?: ReadinessCheck[];
  v2_recommended_action?: string | null;
};

export type RobotValidationCheck = {
  id: string;
  label: string;
  ok: boolean;
  detail: string;
};

export type RobotValidationReport = {
  ok: boolean;
  score_pct: number;
  checks: RobotValidationCheck[];
  generated_at: number;
  duration_s: number;
  sample_interval_s: number;
  connect: ConnectProbeReport;
  compat: CompatReport;
  serial: SerialDiag;
};

export type OverwatchCheck = {
  id: string;
  label: string;
  status: 'pass' | 'warn' | 'fail';
  detail: string;
  evidence?: string;
};

export type OverwatchReport = {
  ok: boolean;
  overall: 'pass' | 'warn' | 'fail';
  score_pct: number;
  generated_at: number;
  checks: OverwatchCheck[];
  counts: {
    pass: number;
    warn: number;
    fail: number;
    total: number;
  };
  actions: string[];
  contract_version_detected?: 'v1' | 'v2' | 'unknown';
  connect_confidence_pct?: number;
  docs?: {
    latest_folder?: string | null;
    exists?: boolean;
    fresh?: boolean;
    sketch_path?: string;
    check?: {
      ok: boolean;
      missing: string[];
      invalid: string[];
      required: string[];
    };
  };
};

export type RobotProfile = {
  profile_id: string;
  label: string;
  chassis: string;
  board: Record<string, unknown>;
  parts: Record<string, unknown>;
  pinmap: Record<string, unknown>;
  firmware: Record<string, unknown>;
  limits: Record<string, unknown>;
  calibration: Record<string, unknown>;
  probe: ConnectProbeReport;
  validation: Partial<RobotValidationReport> | Record<string, unknown>;
  created_at: number;
  updated_at: number;
};

export type RobotProfilesState = {
  active_profile_id: string | null;
  profiles: RobotProfile[];
};

async function req<T>(path: string, init?: RequestInit, timeoutMs = 15000): Promise<T> {
  const maxAttempts = 3;
  let attempt = 0;
  while (true) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const res = await fetch(`${BASE}${path}`, {
        headers: {
          'Content-Type': 'application/json',
          ...(SESSION_TOKEN ? { 'X-Session-Token': SESSION_TOKEN } : {}),
          ...(init?.headers ?? {}),
        },
        ...init,
        signal: controller.signal,
      });
      const data = (await res.json()) as T & { ok?: boolean; error?: string };
      if (!res.ok || (typeof data === 'object' && data && 'ok' in data && data.ok === false)) {
        const msg = (data as { error?: string }).error ?? `${res.status}`;
        throw new Error(msg);
      }
      return data;
    } catch (err) {
      if ((err as Error).name === 'AbortError') {
        throw new Error(`request_timeout_${timeoutMs}ms:${path}`);
      }
      const emsg = String((err as Error)?.message ?? err ?? '');
      const isNetwork = emsg.includes('Failed to fetch') || emsg.includes('NetworkError') || emsg.includes('ERR_CONNECTION');
      attempt += 1;
      if (!isNetwork || attempt >= maxAttempts) {
        throw err;
      }
      await new Promise((resolve) => setTimeout(resolve, 150 * attempt));
    } finally {
      clearTimeout(timer);
    }
  }
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

export async function profilesList(): Promise<RobotProfilesState> {
  const d = await req<{ ok: true; profiles: RobotProfilesState }>('/profiles');
  return d.profiles;
}

export async function profilesValidate(durationS = 12, sampleIntervalS = 0.25): Promise<RobotValidationReport> {
  const d = await req<{ ok: true; validation: RobotValidationReport }>('/profiles/validate', {
    method: 'POST',
    body: JSON.stringify({ duration_s: durationS, sample_interval_s: sampleIntervalS }),
  }, Math.max(25000, (durationS + 5) * 1000));
  return d.validation;
}

export async function getOverwatchStatus(refresh = false): Promise<OverwatchReport> {
  const qs = refresh ? '?refresh=1' : '';
  const d = await req<{ ok: true; overwatch: OverwatchReport }>(`/overwatch/status${qs}`);
  return d.overwatch;
}

export async function profilesSave(profile: Partial<RobotProfile> & { label: string; chassis: string }): Promise<RobotProfilesState> {
  const d = await req<{ ok: true; profiles: RobotProfilesState }>('/profiles/save', {
    method: 'POST',
    body: JSON.stringify({ profile }),
  });
  return d.profiles;
}

export async function profilesActivate(profileId: string, validation: RobotValidationReport): Promise<RobotProfilesState> {
  const d = await req<{ ok: true; profiles: RobotProfilesState }>('/profiles/activate', {
    method: 'POST',
    body: JSON.stringify({ profile_id: profileId, validation }),
  });
  return d.profiles;
}

export async function profilesDelete(profileId: string): Promise<RobotProfilesState> {
  const d = await req<{ ok: true; profiles: RobotProfilesState }>('/profiles/delete', {
    method: 'POST',
    body: JSON.stringify({ profile_id: profileId }),
  });
  return d.profiles;
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

export async function firmwareUnifiedSchema(): Promise<UnifiedFirmwareSchema> {
  const d = await req<{ ok: true; schema: UnifiedFirmwareSchema }>('/firmware/unified-schema');
  return d.schema;
}

export async function firmwareGenerateUnified(profile: Record<string, unknown>, sketchName?: string): Promise<UnifiedFirmwareGenerated> {
  const d = await req<{ ok: true; unified: UnifiedFirmwareGenerated }>('/firmware/generate-unified', {
    method: 'POST',
    body: JSON.stringify({ profile, sketch_name: sketchName }),
  });
  return d.unified;
}

export async function firmwareGenerateDocsPack(
  profile: Record<string, unknown>,
  sketchName?: string,
  sketchContent?: string,
  sketchPath?: string,
  forceRegenerate = true,
): Promise<FirmwareDocsPack> {
  const d = await req<{ ok: true; docs_pack: FirmwareDocsPack }>('/firmware/generate-docs-pack', {
    method: 'POST',
    body: JSON.stringify({
      profile,
      sketch_name: sketchName,
      sketch_content: sketchContent,
      sketch_path: sketchPath,
      force_regenerate: !!forceRegenerate,
    }),
  });
  return d.docs_pack;
}

export async function serialDiag(): Promise<SerialDiag> {
  const d = await req<{ ok: true; serial: SerialDiag }>('/diag/serial');
  return d.serial;
}

export async function burstStatus(): Promise<BurstStatus> {
  const d = await req<{ ok: true; burst: BurstStatus }>('/burst/status');
  return d.burst;
}

export async function burstArm(delayMs = 3000, lines = 80, freqHz = 8): Promise<BurstStatus> {
  const d = await req<{ ok: true; burst: BurstStatus }>('/burst/arm', {
    method: 'POST',
    body: JSON.stringify({ delay_ms: delayMs, lines, freq_hz: freqHz }),
  });
  return d.burst;
}

export async function toolingListTraces(): Promise<string[]> {
  const d = await req<{ ok: true; traces: string[] }>('/tooling/traces');
  return d.traces ?? [];
}

export async function toolingTraceReplay(payload: {
  trace_path: string;
  i_limit?: number;
  out_limit?: number;
  cmd_vel?: number;
  cmd_rmse_max?: number;
  cmd_abs_max?: number;
}): Promise<TraceReplayResult> {
  const d = await req<{ ok: true; replay: TraceReplayResult }>('/tooling/trace-replay', {
    method: 'POST',
    body: JSON.stringify(payload),
  }, 120000);
  return d.replay;
}

export async function toolingParamSweep(payload: {
  kp_spec: string;
  ki_spec: string;
  kd_spec: string;
  settle_s?: number;
  observe_s?: number;
  sample_rate_hz?: number;
  max_angle_variance?: number;
  max_output_saturation_pct?: number;
  require_no_oscillation?: boolean;
  max_candidates?: number;
  rollback_on_fail?: boolean;
  restore_baseline_at_end?: boolean;
  dry_run?: boolean;
}): Promise<ParamSweepResult> {
  const d = await req<{ ok: true; sweep: ParamSweepResult }>('/tooling/param-sweep', {
    method: 'POST',
    body: JSON.stringify(payload),
  }, 240000);
  return d.sweep;
}

export async function toolingSurrogateSim(payload: {
  trace_paths: string[];
  kp: number;
  ki: number;
  kd: number;
  setpoint?: number;
  duration_s?: number;
}): Promise<SurrogateSimResult> {
  const d = await req<{ ok: boolean; surrogate: SurrogateSimResult }>('/tooling/surrogate/simulate', {
    method: 'POST',
    body: JSON.stringify(payload),
  }, 120000);
  return d.surrogate;
}

export async function aiStatus(): Promise<{ ai: AiStatus; history: AiHistoryItem[]; threads: AiThreadSummary[] }> {
  const d = await req<{ ok: true; ai: AiStatus; history: AiHistoryItem[]; threads?: AiThreadSummary[] }>('/ai/status');
  return { ai: d.ai, history: d.history, threads: d.threads ?? [] };
}

export async function aiChat(message: string, threadId?: string): Promise<{ reply: string; ai: AiStatus; history: AiHistoryItem[]; threads: AiThreadSummary[]; thread_id?: string; apply?: { ok: boolean; snapshot_id?: string; applied?: string[]; status?: Status; error?: string; artifacts?: { unified_folder?: string; unified_archive?: string; unified_main_file?: string; sketch_path?: string; sketch_backup?: string; sketch_bytes?: number } } }> {
  const d = await req<{ ok: true; reply: string; ai: AiStatus; history: AiHistoryItem[]; threads?: AiThreadSummary[]; thread_id?: string; apply?: { ok: boolean; snapshot_id?: string; applied?: string[]; status?: Status; error?: string; artifacts?: { unified_folder?: string; unified_archive?: string; unified_main_file?: string; sketch_path?: string; sketch_backup?: string; sketch_bytes?: number } } }>('/ai/chat', {
    method: 'POST',
    body: JSON.stringify({ message, thread_id: threadId }),
  }, 45000);
  return { reply: d.reply, ai: d.ai, history: d.history, threads: d.threads ?? [], thread_id: d.thread_id, apply: d.apply };
}

export type ToolCallResult = {
  tool: string;
  args: Record<string, unknown>;
  result: {
    ok: boolean;
    tool: string;
    data: Record<string, unknown>;
    error?: string;
    execution_time_ms: number;
  };
};

export type AiChatToolsResponse = {
  reply: string;
  ai: AiStatus;
  history: AiHistoryItem[];
  threads: AiThreadSummary[];
  thread_id?: string;
  tool_calls: ToolCallResult[];
  iterations: number;
};

export async function aiChatWithTools(
  message: string,
  options?: {
    threadId?: string;
    enableTools?: boolean;
    sketchPath?: string;
    robotId?: string;
    board?: string;
    port?: string;
  },
): Promise<AiChatToolsResponse> {
  const d = await req<{
    ok: true;
    reply: string;
    ai: AiStatus;
    history: AiHistoryItem[];
    threads?: AiThreadSummary[];
    thread_id?: string;
    tool_calls?: ToolCallResult[];
    iterations?: number;
  }>('/ai/chat/tools', {
    method: 'POST',
    body: JSON.stringify({
      message,
      thread_id: options?.threadId,
      enable_tools: options?.enableTools ?? true,
      sketch_path: options?.sketchPath,
      robot_id: options?.robotId,
      board: options?.board,
      port: options?.port,
    }),
  }, 90000);
  return {
    reply: d.reply,
    ai: d.ai,
    history: d.history,
    threads: d.threads ?? [],
    thread_id: d.thread_id,
    tool_calls: d.tool_calls ?? [],
    iterations: d.iterations ?? 1,
  };
}

export type UploadConfirmResult = {
  ok: boolean;
  action: 'approved' | 'rejected' | 'expired' | 'invalid';
  upload_result?: {
    ok: boolean;
    sketch?: string;
    board?: string;
    port?: string;
    output?: string;
    error?: string;
  };
  error?: string;
};

export async function aiConfirmUpload(
  token: string,
  action: 'approve' | 'reject',
): Promise<UploadConfirmResult> {
  const d = await req<{
    ok: boolean;
    action: 'approved' | 'rejected' | 'expired' | 'invalid';
    upload_result?: {
      ok: boolean;
      sketch?: string;
      board?: string;
      port?: string;
      output?: string;
      error?: string;
    };
    error?: string;
  }>('/ai/upload/confirm', {
    method: 'POST',
    body: JSON.stringify({ token, action }),
  }, 60000);
  return d;
}

export async function aiChatStream(
  message: string,
  threadId: string | undefined,
  handlers: {
    onStart?: () => void;
    onDelta?: (text: string) => void;
    onDone?: (payload: { reply: string; ai: AiStatus; history: AiHistoryItem[]; threads: AiThreadSummary[]; thread_id?: string; apply?: { ok: boolean; snapshot_id?: string; applied?: string[]; status?: Status; error?: string; artifacts?: { unified_folder?: string; unified_archive?: string; unified_main_file?: string; sketch_path?: string; sketch_backup?: string; sketch_bytes?: number } } }) => void;
  },
): Promise<{ reply: string; ai: AiStatus; history: AiHistoryItem[]; threads: AiThreadSummary[]; thread_id?: string; apply?: { ok: boolean; snapshot_id?: string; applied?: string[]; status?: Status; error?: string; artifacts?: { unified_folder?: string; unified_archive?: string; unified_main_file?: string; sketch_path?: string; sketch_backup?: string; sketch_bytes?: number } } }> {
  let res: Response | null = null;
  let lastErr: unknown = null;
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    try {
      res = await fetch(`${BASE}/ai/chat/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(SESSION_TOKEN ? { 'X-Session-Token': SESSION_TOKEN } : {}),
        },
        body: JSON.stringify({ message, thread_id: threadId }),
      });
      break;
    } catch (e) {
      lastErr = e;
      const emsg = String((e as Error)?.message ?? e ?? '');
      const isNetwork = emsg.includes('Failed to fetch') || emsg.includes('NetworkError') || emsg.includes('ERR_CONNECTION');
      if (!isNetwork || attempt >= 3) throw e;
      await new Promise((resolve) => setTimeout(resolve, 150 * attempt));
    }
  }
  if (!res && lastErr) throw lastErr;
  if (!res) throw new Error('stream_unavailable');

  if (!res.ok || !res.body) {
    let body = '';
    try {
      body = await res.text();
    } catch {
      body = '';
    }
    throw new Error(body || `${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = '';
  let donePayload: { reply: string; ai: AiStatus; history: AiHistoryItem[]; threads: AiThreadSummary[]; thread_id?: string; apply?: { ok: boolean; snapshot_id?: string; applied?: string[]; status?: Status; error?: string; artifacts?: { unified_folder?: string; unified_archive?: string; unified_main_file?: string; sketch_path?: string; sketch_backup?: string; sketch_bytes?: number } } } | null = null;

  const handleFrame = (frame: string): void => {
    const lines = frame.split('\n');
    let evt = 'message';
    const dataLines: string[] = [];
    for (const ln of lines) {
      if (ln.startsWith('event:')) evt = ln.slice(6).trim();
      else if (ln.startsWith('data:')) dataLines.push(ln.slice(5).trim());
    }
    if (dataLines.length === 0) return;
    const dataTxt = dataLines.join('\n');
    const obj = JSON.parse(dataTxt) as Record<string, unknown>;
    if (evt === 'start') {
      handlers.onStart?.();
      return;
    }
    if (evt === 'delta') {
      handlers.onDelta?.(String(obj.text ?? ''));
      return;
    }
    if (evt === 'done') {
      donePayload = {
        reply: String(obj.reply ?? ''),
        ai: obj.ai as AiStatus,
        history: (obj.history as AiHistoryItem[]) ?? [],
        threads: (obj.threads as AiThreadSummary[]) ?? [],
        thread_id: (obj.thread_id as string | undefined),
        apply: obj.apply as { ok: boolean; snapshot_id?: string; applied?: string[]; status?: Status; error?: string; artifacts?: { unified_folder?: string; unified_archive?: string; unified_main_file?: string; sketch_path?: string; sketch_backup?: string; sketch_bytes?: number } } | undefined,
      };
      handlers.onDone?.(donePayload);
      return;
    }
    if (evt === 'error') {
      throw new Error(String(obj.error ?? 'stream_error'));
    }
  };

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    while (true) {
      const idx = buf.indexOf('\n\n');
      if (idx < 0) break;
      const frame = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      if (frame.trim()) handleFrame(frame);
    }
  }
  if (buf.trim()) handleFrame(buf);
  if (!donePayload) throw new Error('stream_incomplete');
  return donePayload;
}

export async function aiThreads(): Promise<{ ai: AiStatus; threads: AiThreadSummary[] }> {
  const d = await req<{ ok: true; ai: AiStatus; threads: AiThreadSummary[] }>('/ai/threads');
  return { ai: d.ai, threads: d.threads };
}

export async function aiProfiles(): Promise<AiProfilesState> {
  const d = await req<{ ok: true; profiles: AiProfilesState }>('/ai/profiles');
  return d.profiles;
}

export async function aiProfileSave(profile: Partial<AiProfile> & { label: string; instructions: string }): Promise<AiProfilesState> {
  const d = await req<{ ok: true; profiles: AiProfilesState }>('/ai/profile/save', {
    method: 'POST',
    body: JSON.stringify({ profile }),
  });
  return d.profiles;
}

export async function aiProfileActivate(profileId: string): Promise<AiProfilesState> {
  const d = await req<{ ok: true; profiles: AiProfilesState }>('/ai/profile/activate', {
    method: 'POST',
    body: JSON.stringify({ profile_id: profileId }),
  });
  return d.profiles;
}

export async function aiNewThread(title?: string): Promise<{ ai: AiStatus; history: AiHistoryItem[]; threads: AiThreadSummary[]; thread: { id: string; title: string } }> {
  const d = await req<{ ok: true; ai: AiStatus; history: AiHistoryItem[]; threads: AiThreadSummary[]; thread: { id: string; title: string } }>('/ai/thread/new', {
    method: 'POST',
    body: JSON.stringify({ title }),
  });
  return { ai: d.ai, history: d.history, threads: d.threads, thread: d.thread };
}

export async function aiSelectThread(threadId: string): Promise<{ ai: AiStatus; history: AiHistoryItem[]; threads: AiThreadSummary[]; thread: { id: string; title: string } }> {
  const d = await req<{ ok: true; ai: AiStatus; history: AiHistoryItem[]; threads: AiThreadSummary[]; thread: { id: string; title: string } }>('/ai/thread/select', {
    method: 'POST',
    body: JSON.stringify({ thread_id: threadId }),
  });
  return { ai: d.ai, history: d.history, threads: d.threads, thread: d.thread };
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

export async function authRequestPasswordReset(email: string): Promise<{ accepted: boolean; delivery: string; reset_token: string | null; expires_in_s: number }> {
  const d = await req<{ ok: true; reset: { accepted: boolean; delivery: string; reset_token: string | null; expires_in_s: number } }>(
    '/auth/password-reset/request',
    {
      method: 'POST',
      body: JSON.stringify({ email }),
    },
  );
  return d.reset;
}

export async function authConfirmPasswordReset(email: string, token: string, newPassword: string): Promise<void> {
  await req('/auth/password-reset/confirm', {
    method: 'POST',
    body: JSON.stringify({ email, token, new_password: newPassword }),
  });
}

export async function postCommand(cmd: string, expect?: string, timeoutS?: number): Promise<void> {
  await req('/command', {
    method: 'POST',
    body: JSON.stringify({ cmd, expect, timeout: timeoutS }),
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

export type ConfigRevertResult = {
  ok: boolean;
  snapshot_id?: string;
  reverted: string[];
  status: Status;
};

export async function configRevert(snapshotId?: string): Promise<{ revert: ConfigRevertResult; control?: ControlState }> {
  const d = await req<{ ok: true; revert: ConfigRevertResult; control?: ControlState }>('/config/revert', {
    method: 'POST',
    body: JSON.stringify(snapshotId ? { snapshot_id: snapshotId } : {}),
  });
  return { revert: d.revert, control: d.control };
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

export type RagStats = {
  doc_chunk_count: number;
  embedded_docs_count: number;
  embedding_model: string;
  chunk_size: number;
  has_openai_key: boolean;
};

export async function aiRagStats(): Promise<RagStats> {
  const d = await req<{ ok: true; stats: RagStats; ts: number }>('/ai/rag/stats');
  return d.stats;
}
