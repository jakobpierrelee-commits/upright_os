/**
 * Firmware Domain API Client
 * Firmware lifecycle: compile, upload, sketches, commissioning.
 */

import { fetchJson, postJson } from './client';

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

export type FirmwareSketchFolders = {
  ok: boolean;
  folders: string[];
  default_folder?: string;
};

export type FirmwarePickedSketchFolder = {
  ok: boolean;
  path: string;
  has_ino: boolean;
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
  generated_path: string;
  ino_path: string;
  profile_snapshot: Record<string, unknown>;
  warnings: string[];
};

export type FirmwareDocsPack = {
  ok: boolean;
  generated_at: string;
  pack_path?: string;
  contents?: {
    readme: string;
    wiring_guide: string;
    bom: string;
    troubleshooting: string;
    full_profile: Record<string, unknown>;
  };
  warnings?: string[];
  error?: string;
};

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

export async function firmwareStatus(): Promise<FirmwareStatus> {
  return fetchJson<FirmwareStatus>('/firmware/status');
}

export async function firmwareCheck(): Promise<FirmwareCheck> {
  return fetchJson<FirmwareCheck>('/firmware/check');
}

export async function firmwareCompile(sketch?: string, fqbn?: string): Promise<FirmwareStatus> {
  return postJson<FirmwareStatus>('/firmware/compile', { sketch, fqbn });
}

export async function firmwareUpload(sketch?: string, fqbn?: string, port?: string): Promise<FirmwareStatus> {
  return postJson<FirmwareStatus>('/firmware/upload', { sketch, fqbn, port });
}

export async function firmwareUploadGuarded(sketch?: string, fqbn?: string, port?: string): Promise<FirmwareStatus> {
  return postJson<FirmwareStatus>('/firmware/upload/guarded', { sketch, fqbn, port });
}

export async function firmwareInstallCli(): Promise<FirmwareStatus> {
  return postJson<FirmwareStatus>('/firmware/install-cli');
}

export async function firmwareReadSketch(path?: string): Promise<FirmwareSketch> {
  const url = path ? `/firmware/sketch?path=${encodeURIComponent(path)}` : '/firmware/sketch';
  return fetchJson<FirmwareSketch>(url);
}

export async function firmwareWriteSketch(content: string, path?: string): Promise<{ path: string; bytes: number }> {
  return postJson('/firmware/sketch', { content, path });
}

export async function firmwareBoards(): Promise<FirmwareBoards> {
  return fetchJson<FirmwareBoards>('/firmware/boards');
}

export async function firmwareSketchFolders(): Promise<FirmwareSketchFolders> {
  return fetchJson<FirmwareSketchFolders>('/firmware/sketch-folders');
}

export async function firmwarePickSketchFolder(): Promise<FirmwarePickedSketchFolder> {
  return postJson<FirmwarePickedSketchFolder>('/firmware/sketch-folders/pick');
}

export async function firmwareUnifiedSchema(): Promise<UnifiedFirmwareSchema> {
  return fetchJson<UnifiedFirmwareSchema>('/firmware/unified-schema');
}

export async function firmwareGenerateUnified(
  profile: Record<string, unknown>,
  sketchName?: string
): Promise<UnifiedFirmwareGenerated> {
  return postJson<UnifiedFirmwareGenerated>('/firmware/generate-unified', { profile, sketch_name: sketchName });
}

export async function firmwareGenerateDocsPack(
  profile: Record<string, unknown>,
  options?: { include_wiring?: boolean; include_bom?: boolean; include_troubleshooting?: boolean }
): Promise<FirmwareDocsPack> {
  return postJson<FirmwareDocsPack>('/firmware/generate-docs-pack', { profile, ...options });
}

export async function commissioningRun(autoPrompts = true): Promise<CommissioningStatus> {
  return postJson<CommissioningStatus>('/commissioning/run', { auto_prompts: autoPrompts });
}

export async function commissioningStatus(): Promise<CommissioningStatus> {
  return fetchJson<CommissioningStatus>('/commissioning/status');
}

export async function commissioningArtifacts(): Promise<CommissioningArtifacts> {
  return fetchJson<CommissioningArtifacts>('/commissioning/artifacts');
}
