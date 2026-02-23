import type { ControlState, Health, Status } from '../types';

// Clean-lane hard lock: do not route clean runtime calls to legacy or remote bridge URLs.
const BASE = 'http://127.0.0.1:8797';

async function req<T>(path: string, init?: RequestInit, timeoutMs = 60000): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${BASE}${path}`, {
      headers: { 'Content-Type': 'application/json' },
      ...init,
      signal: controller.signal,
    });
    const data = (await res.json()) as T & { ok?: boolean; error?: string };
    if (!res.ok || (typeof data === 'object' && data && 'ok' in data && data.ok === false)) {
      throw new Error((data as { error?: string }).error ?? `${res.status}`);
    }
    return data;
  } catch (err) {
    if ((err as Error).name === 'AbortError') throw new Error(`request_timeout_${timeoutMs}ms:${path}`);
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

export type CleanMode = 'app_dev' | 'robot_dev' | 'ops_debug';

export type CleanAttachment = {
  id?: string;
  name: string;
  mime: string;
  kind: string;
  size: number;
  path: string;
  text_excerpt?: string;
};

export type CleanMessage = {
  ts: number;
  role: 'user' | 'assistant';
  text: string;
};

export type CleanThread = {
  id: string;
  title: string;
  created_at?: number;
  updated_at?: number;
  message_count?: number;
  preview?: string;
};

export type CleanToolCall = {
  name: string;
  arguments: Record<string, unknown>;
  result: {
    ok: boolean;
    data?: Record<string, unknown>;
    error?: string;
    execution_time_ms?: number;
  };
};

export type CleanOpResult = {
  ok: boolean;
  dt_ms?: number;
  error?: string;
  tool_call?: CleanToolCall;
};

export type CleanFirmwareStatus = {
  state: string;
  phase: string;
  running: boolean;
  started_at: number | null;
  finished_at: number | null;
  returncode: number | null;
  log_tail: string[];
  idempotent_reused?: boolean;
  operation?: {
    running: boolean;
    active?: {
      op_id: string;
      phase: string;
      idempotency_key?: string;
      started_at?: number;
    } | null;
    last_completed?: {
      op_id: string;
      phase: string;
      state: string;
      returncode: number;
      finished_at?: number;
    } | null;
  };
  defaults?: {
    sketch?: string;
    fqbn?: string;
    port?: string;
  };
};

export type CleanFirmwareBoards = {
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

export type CleanFirmwareTargets = {
  ok: boolean;
  version: number;
  families: Array<{
    id: string;
    label: string;
  }>;
  boards: Array<{
    id: string;
    family: string;
    label: string;
    fqbn_base: string;
    default_bootloader: string;
    bootloaders: Array<{
      id: string;
      label: string;
      fqbn_suffix: string;
    }>;
  }>;
};

export type CleanHardwareProfileRegistry = {
  ok: boolean;
  version: number;
  families: Array<{ id: string; label: string }>;
  boards: Array<{
    id: string;
    label: string;
    family: string;
    fqbn_base: string;
    default_bootloader: string;
    bootloaders: Array<{ id: string; label: string; fqbn_suffix: string }>;
    capabilities: {
      default_telemetry_hz: number;
      imu_protocols: string[];
      encoder_protocols: string[];
      actuator_classes: string[];
    };
    required_runtime_fields: string[];
  }>;
  sensors: Array<{
    id: string;
    label: string;
    class: string;
    supported_protocols: string[];
    required_signals: string[];
    typical_output_fields: string[];
  }>;
  actuators: Array<{
    id: string;
    label: string;
    class: string;
    required_channels: string[];
  }>;
  profile_schema: {
    required_profile_fields: string[];
    required_board_fields: string[];
    required_parts_fields: string[];
    required_pinmap_fields: string[];
    required_runtime_commands: string[];
    required_runtime_telemetry: string[];
  };
  templates: Array<{
    id: string;
    label: string;
    board_family: string;
    sensor_ids: string[];
    actuator_ids: string[];
  }>;
};

export type CleanRuntimeManifestValidation = {
  ok: boolean;
  manifest_path: string;
  source: string;
  errors: string[];
  warnings: string[];
  manifest: Record<string, unknown> | null;
  checked_at?: number;
};

export type CleanRuntimeManifestCompatibility = {
  ok: boolean;
  compatibility: {
    ok: boolean;
    errors: string[];
    warnings: string[];
    checks: Record<string, unknown>;
  };
  active_profile_id?: string | null;
  manifest_validation: CleanRuntimeManifestValidation;
};

export type CleanFirmwareUploadPrecheck = {
  ok: boolean;
  ready: boolean;
  error?: string;
  reasons: string[];
  hard_fail_reasons: string[];
  port: string;
  sketch?: string;
  detected_ports: string[];
  boards_ok: boolean;
  bridge_connected: boolean;
  target_runbook?: {
    target: {
      fqbn: string;
      board_id: string;
      board_family: string;
      board_label: string;
    };
    upload_sequence: string[];
    upload_sequence_steps?: Array<{
      id: string;
      label: string;
      action_key?: string;
    }>;
    recovery: Record<string, string[]>;
    recovery_steps?: Record<
      string,
      Array<{
        id: string;
        label: string;
        action_key?: string;
      }>
    >;
  };
  manifest_validation?: {
    ok: boolean;
    manifest_path?: string;
    errors?: string[];
    warnings?: string[];
  };
};

export type CleanKnownGoodRecovery = {
  ok: boolean;
  recovery: {
    ok: boolean;
    steps: Array<{
      id: string;
      ok: boolean;
      detail: string;
    }>;
    selected_port: string;
    detected_ports: string[];
    precheck: CleanFirmwareUploadPrecheck;
    status: Status;
    action_gates?: Record<string, { ok: boolean; reasons: string[] }>;
  };
  tool_call?: CleanToolCall;
};

export async function cleanStatus(mode: CleanMode): Promise<{
  clean_api?: {
    version?: number;
    min_ui_version?: number;
    capabilities?: string[];
  };
  agent: {
    mode: string;
    executor: string;
    provider: string;
    model: string;
    can_chat: boolean;
    degraded_reason: string;
    codex_login?: { logged_in?: boolean; detail?: string };
  };
  health: Health;
  control: ControlState;
  status: Status;
}> {
  const d = await req<{
    ok: true;
    clean_api?: {
      version?: number;
      min_ui_version?: number;
      capabilities?: string[];
    };
    agent: {
      mode: string;
      executor: string;
      provider: string;
      model: string;
      can_chat: boolean;
      degraded_reason: string;
      codex_login?: { logged_in?: boolean; detail?: string };
    };
    health: Health;
    control: ControlState;
    status: Status;
  }>(`/agent/clean/status?mode=${encodeURIComponent(mode)}`, undefined, 12000);
  return {
    clean_api: d.clean_api,
    agent: d.agent,
    health: d.health,
    control: d.control,
    status: d.status,
  };
}

export async function cleanThreads(mode: CleanMode): Promise<{ threads: CleanThread[] }> {
  const d = await req<{ ok: true; threads: CleanThread[] }>(`/agent/clean/threads?mode=${encodeURIComponent(mode)}`);
  return { threads: d.threads ?? [] };
}

export async function cleanNewThread(mode: CleanMode, title?: string): Promise<{
  thread: CleanThread;
  threads: CleanThread[];
  history: CleanMessage[];
}> {
  const d = await req<{ ok: true; thread: CleanThread; threads: CleanThread[]; history: CleanMessage[] }>(
    '/agent/clean/thread/new',
    { method: 'POST', body: JSON.stringify({ mode, title }) },
  );
  return { thread: d.thread, threads: d.threads ?? [], history: d.history ?? [] };
}

export async function cleanSelectThread(mode: CleanMode, threadId: string): Promise<{
  thread: CleanThread;
  threads: CleanThread[];
  history: CleanMessage[];
}> {
  const d = await req<{ ok: true; thread: CleanThread; threads: CleanThread[]; history: CleanMessage[] }>(
    '/agent/clean/thread/select',
    { method: 'POST', body: JSON.stringify({ mode, thread_id: threadId }) },
  );
  return { thread: d.thread, threads: d.threads ?? [], history: d.history ?? [] };
}

export async function cleanChat(
  mode: CleanMode,
  message: string,
  threadId?: string,
  attachments?: CleanAttachment[],
  autoTools = false,
): Promise<{
  reply: string;
  thread_id?: string;
  history: CleanMessage[];
  threads: CleanThread[];
  provider: string;
  executor: string;
  tool_calls: CleanToolCall[];
}> {
  const d = await req<{
    ok: true;
    reply: string;
    thread_id?: string;
    history: CleanMessage[];
    threads: CleanThread[];
    provider: string;
    executor: string;
    tool_calls?: CleanToolCall[];
  }>(
    '/agent/clean/chat',
    {
      method: 'POST',
      body: JSON.stringify({ mode, message, thread_id: threadId, attachments: attachments ?? [], auto_tools: autoTools }),
    },
    120000,
  );
  return {
    reply: d.reply,
    thread_id: d.thread_id,
    history: d.history ?? [],
    threads: d.threads ?? [],
    provider: d.provider,
    executor: d.executor,
    tool_calls: d.tool_calls ?? [],
  };
}

export async function cleanChatStream(
  mode: CleanMode,
  message: string,
  threadId: string | undefined,
  attachments: CleanAttachment[] | undefined,
  handlers: {
    onStart?: () => void;
    onProgress?: (line: string) => void;
    onDelta?: (text: string) => void;
    onDone?: (payload: {
      reply: string;
      thread_id?: string;
      history: CleanMessage[];
      threads: CleanThread[];
      provider: string;
      executor: string;
      tool_calls: CleanToolCall[];
    }) => void;
  },
  signal?: AbortSignal,
): Promise<{
  reply: string;
  thread_id?: string;
  history: CleanMessage[];
  threads: CleanThread[];
  provider: string;
  executor: string;
  tool_calls: CleanToolCall[];
}> {
  const res = await fetch(`${BASE}/agent/clean/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mode, message, thread_id: threadId, attachments: attachments ?? [] }),
    signal,
  });
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
  let donePayload: {
    reply: string;
    thread_id?: string;
    history: CleanMessage[];
    threads: CleanThread[];
    provider: string;
    executor: string;
    tool_calls: CleanToolCall[];
  } | null = null;

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
    if (evt === 'progress') {
      handlers.onProgress?.(String(obj.line ?? ''));
      return;
    }
    if (evt === 'delta') {
      handlers.onDelta?.(String(obj.text ?? ''));
      return;
    }
    if (evt === 'done') {
      donePayload = {
        reply: String(obj.reply ?? ''),
        thread_id: (obj.thread_id as string | undefined),
        history: (obj.history as CleanMessage[]) ?? [],
        threads: (obj.threads as CleanThread[]) ?? [],
        provider: String(obj.provider ?? 'codex_cli'),
        executor: String(obj.executor ?? 'codex_cli_exec'),
        tool_calls: (obj.tool_calls as CleanToolCall[]) ?? [],
      };
      handlers.onDone?.(donePayload);
      return;
    }
    if (evt === 'error') {
      throw new Error(String(obj.error ?? 'stream_failed'));
    }
  };

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let idx = buf.indexOf('\n\n');
    while (idx >= 0) {
      const frame = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      if (frame.trim()) handleFrame(frame);
      idx = buf.indexOf('\n\n');
    }
  }

  if (!donePayload) throw new Error('stream_no_done');
  return donePayload;
}

export async function cleanUploadFile(file: File): Promise<CleanAttachment> {
  const buf = await file.arrayBuffer();
  const bytes = new Uint8Array(buf);
  let binary = '';
  for (let i = 0; i < bytes.length; i += 1) binary += String.fromCharCode(bytes[i]);
  const b64 = btoa(binary);
  const d = await req<{ ok: true; attachment: CleanAttachment }>(
    '/agent/clean/file/upload',
    {
      method: 'POST',
      body: JSON.stringify({
        name: file.name,
        mime: file.type || 'application/octet-stream',
        content_base64: b64,
      }),
    },
    60000,
  );
  return d.attachment;
}

export async function cleanFirmwareCompile(
  sketch?: string,
  fqbn?: string,
  idempotencyKey?: string,
): Promise<CleanOpResult> {
  const d = await req<{
    ok: boolean;
    error?: string;
    tool_call?: CleanToolCall;
  }>(
    '/agent/clean/firmware/compile',
    { method: 'POST', body: JSON.stringify({ sketch, fqbn, idempotency_key: idempotencyKey }) },
    180000,
  );
  return {
    ok: Boolean(d.ok),
    error: d.error,
    dt_ms: d.tool_call?.result?.execution_time_ms,
    tool_call: d.tool_call,
  };
}

export async function cleanFirmwareStatus(): Promise<CleanFirmwareStatus> {
  const d = await req<{ ok: true; firmware: CleanFirmwareStatus }>('/firmware/status', undefined, 12000);
  return d.firmware;
}

export async function cleanFirmwareUpload(
  sketch?: string,
  fqbn?: string,
  port?: string,
  idempotencyKey?: string,
): Promise<CleanOpResult> {
  const d = await req<{
    ok: boolean;
    error?: string;
    tool_call?: CleanToolCall;
  }>(
    '/agent/clean/firmware/upload',
    { method: 'POST', body: JSON.stringify({ sketch, fqbn, port, idempotency_key: idempotencyKey }) },
    240000,
  );
  return {
    ok: Boolean(d.ok),
    error: d.error,
    dt_ms: d.tool_call?.result?.execution_time_ms,
    tool_call: d.tool_call,
  };
}

export async function cleanFirmwareUploadPrecheck(port?: string, fqbn?: string): Promise<CleanFirmwareUploadPrecheck> {
  const d = await req<CleanFirmwareUploadPrecheck>(
    '/agent/clean/firmware/upload/precheck',
    { method: 'POST', body: JSON.stringify({ port, fqbn }) },
    15000,
  );
  return d;
}

export async function cleanKnownGoodRecovery(
  port?: string,
  fqbn?: string,
  sketch?: string,
): Promise<CleanKnownGoodRecovery> {
  const d = await req<CleanKnownGoodRecovery>(
    '/agent/clean/recovery/known-good',
    { method: 'POST', body: JSON.stringify({ port, fqbn, sketch }) },
    30000,
  );
  return d;
}

export async function cleanFirmwareBoards(): Promise<CleanFirmwareBoards> {
  const d = await req<{ ok: true; boards: CleanFirmwareBoards }>('/firmware/boards', undefined, 20000);
  return d.boards;
}

export async function cleanFirmwareTargets(): Promise<CleanFirmwareTargets> {
  const d = await req<{ ok: true; targets: CleanFirmwareTargets }>('/firmware/targets', undefined, 20000);
  return d.targets;
}

export async function cleanHardwareProfileRegistry(): Promise<CleanHardwareProfileRegistry> {
  const d = await req<{ ok: true; registry: CleanHardwareProfileRegistry }>('/profiles/hardware', undefined, 20000);
  return d.registry;
}

export async function cleanRuntimeManifestValidation(sketch?: string): Promise<{
  ok: boolean;
  validation: CleanRuntimeManifestValidation;
}> {
  const q = sketch ? `?sketch=${encodeURIComponent(sketch)}` : '';
  const d = await req<{ ok: boolean; validation: CleanRuntimeManifestValidation }>(
    `/firmware/runtime-manifest${q}`,
    undefined,
    20000,
  );
  return d;
}

export async function cleanRuntimeManifestCompatibility(sketch?: string): Promise<CleanRuntimeManifestCompatibility> {
  const q = sketch ? `?sketch=${encodeURIComponent(sketch)}` : '';
  return await req<CleanRuntimeManifestCompatibility>(`/firmware/runtime-manifest/compat${q}`, undefined, 20000);
}

export async function cleanPreflight(
  mode: CleanMode,
  withCompile = false,
): Promise<{
  ok: boolean;
  failures: number;
  max_ms: number;
  max_ms_tools: number;
  results: Array<{
    id: string;
    ok: boolean;
    dt_ms: number;
    limit_ms: number;
    expect_tools: boolean;
    error: string;
    tool_calls: CleanToolCall[];
  }>;
}> {
  const d = await req<{
    ok: boolean;
    failures: number;
    max_ms: number;
    max_ms_tools: number;
    results: Array<{
      id: string;
      ok: boolean;
      dt_ms: number;
      limit_ms: number;
      expect_tools: boolean;
      error: string;
      tool_calls: CleanToolCall[];
    }>;
  }>(
    '/agent/clean/preflight',
    { method: 'POST', body: JSON.stringify({ mode, with_compile: withCompile }) },
    300000,
  );
  return d;
}

export async function cleanPreflightStream(
  mode: CleanMode,
  withCompile: boolean,
  handlers: {
    onStart?: () => void;
    onCheckStart?: (payload: { index: number; total: number; id: string; expect_tools: boolean; prompt: string }) => void;
    onCheckDone?: (payload: {
      index: number;
      total: number;
      result: {
        id: string;
        ok: boolean;
        dt_ms: number;
        limit_ms: number;
        expect_tools: boolean;
        error: string;
        tool_calls: CleanToolCall[];
        reply?: string;
      };
    }) => void;
  },
): Promise<{
  ok: boolean;
  failures: number;
  max_ms: number;
  max_ms_tools: number;
  results: Array<{
    id: string;
    ok: boolean;
    dt_ms: number;
    limit_ms: number;
    expect_tools: boolean;
    error: string;
    tool_calls: CleanToolCall[];
    reply?: string;
  }>;
}> {
  const res = await fetch(`${BASE}/agent/clean/preflight/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mode, with_compile: withCompile }),
  });
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
  let donePayload: {
    ok: boolean;
    failures: number;
    max_ms: number;
    max_ms_tools: number;
    results: Array<{
      id: string;
      ok: boolean;
      dt_ms: number;
      limit_ms: number;
      expect_tools: boolean;
      error: string;
      tool_calls: CleanToolCall[];
      reply?: string;
    }>;
  } | null = null;

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
    if (evt === 'check_start') {
      handlers.onCheckStart?.({
        index: Number(obj.index ?? 0),
        total: Number(obj.total ?? 0),
        id: String(obj.id ?? ''),
        expect_tools: Boolean(obj.expect_tools),
        prompt: String(obj.prompt ?? ''),
      });
      return;
    }
    if (evt === 'check_done') {
      const src = (obj.result as Record<string, unknown>) ?? {};
      handlers.onCheckDone?.({
        index: Number(obj.index ?? 0),
        total: Number(obj.total ?? 0),
        result: {
          id: String(src.id ?? ''),
          ok: Boolean(src.ok),
          dt_ms: Number(src.dt_ms ?? 0),
          limit_ms: Number(src.limit_ms ?? 0),
          expect_tools: Boolean(src.expect_tools),
          error: String(src.error ?? ''),
          tool_calls: (src.tool_calls as CleanToolCall[]) ?? [],
          reply: String(src.reply ?? ''),
        },
      });
      return;
    }
    if (evt === 'done') {
      donePayload = {
        ok: Boolean(obj.ok),
        failures: Number(obj.failures ?? 0),
        max_ms: Number(obj.max_ms ?? 0),
        max_ms_tools: Number(obj.max_ms_tools ?? 0),
        results: (obj.results as Array<{
          id: string;
          ok: boolean;
          dt_ms: number;
          limit_ms: number;
          expect_tools: boolean;
          error: string;
          tool_calls: CleanToolCall[];
          reply?: string;
        }>) ?? [],
      };
      return;
    }
    if (evt === 'error') {
      throw new Error(String(obj.error ?? 'stream_failed'));
    }
  };

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let idx = buf.indexOf('\n\n');
    while (idx >= 0) {
      const frame = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      if (frame.trim()) handleFrame(frame);
      if (donePayload) {
        try {
          await reader.cancel();
        } catch {
          // ignore cancellation errors
        }
        return donePayload;
      }
      idx = buf.indexOf('\n\n');
    }
  }

  if (!donePayload) throw new Error('preflight_stream_no_done');
  return donePayload;
}
