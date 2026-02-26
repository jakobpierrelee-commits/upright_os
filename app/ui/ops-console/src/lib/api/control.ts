/**
 * Control Domain API Client
 * Robot control: arm, disarm, estop, tuning parameters.
 */

import type { ControlState, Status } from '../../types';
import { fetchJson, postJson } from './client';

export async function heartbeat(): Promise<ControlState> {
  return fetchJson<ControlState>('/heartbeat');
}

export async function postCommand(cmd: string, expect?: string, timeoutS?: number): Promise<void> {
  await postJson('/command', { cmd, expect, timeout_s: timeoutS });
}

export async function armPrepare(): Promise<ControlState> {
  return postJson<ControlState>('/arm/prepare');
}

export type PrecheckResult = {
  safe: boolean;
  advisory: string | null;
  checks: Array<{ name: string; passed: boolean; message: string }>;
};

export async function armPrecheck(payload: {
  idle_check?: boolean;
  tilt_check?: boolean;
  tilt_limit_deg?: number;
  serial_check?: boolean;
}): Promise<PrecheckResult> {
  return postJson<PrecheckResult>('/arm/precheck', payload);
}

export async function armConfirm(): Promise<{ status: Status; control: ControlState }> {
  return postJson('/arm/confirm');
}

export async function arm(): Promise<{ status: Status; control?: ControlState }> {
  return postJson('/arm');
}

export async function disarm(): Promise<{ status: Status; control?: ControlState }> {
  return postJson('/disarm');
}

export async function estopLatch(): Promise<{ status: Status; control: ControlState }> {
  return postJson('/estop/latch');
}

export async function estopReset(): Promise<{ status: Status; control: ControlState }> {
  return postJson('/estop/reset');
}

export async function calZero(): Promise<{ status: Status; control?: ControlState }> {
  return postJson('/cal_zero');
}

export async function imuCalibrate(): Promise<{ status: Status; control?: ControlState }> {
  return postJson('/imu/calibrate');
}

export async function imuLoad(): Promise<{ status: Status; control?: ControlState }> {
  return postJson('/imu/load');
}

export async function imuSave(): Promise<{ status: Status; control?: ControlState }> {
  return postJson('/imu/save');
}

export async function imuInfo(): Promise<{ status: Status; control?: ControlState }> {
  return fetchJson('/imu/info');
}

export async function saveCfg(): Promise<void> {
  await postJson('/savecfg');
}

export async function loadCfg(): Promise<{ status: Status; control?: ControlState }> {
  return postJson('/loadcfg');
}

export async function defaultCfg(): Promise<{ status: Status; control?: ControlState }> {
  return postJson('/defaultcfg');
}

export type ConfigRevertResult = {
  ok: boolean;
  reverted_to: string | null;
  error?: string;
};

export async function configRevert(snapshotId?: string): Promise<{ revert: ConfigRevertResult; control?: ControlState }> {
  return postJson('/config/revert', { snapshot_id: snapshotId });
}

export async function setPid(
  kp: number,
  ki: number,
  kd: number,
  preflightId?: string
): Promise<{ status: Status; control?: ControlState; preflight_id?: string | null }> {
  return postJson('/pid', { kp, ki, kd, preflight_id: preflightId });
}

export async function setMotion(
  kv: number,
  kx: number,
  preflightId?: string
): Promise<{ status: Status; control?: ControlState; preflight_id?: string | null }> {
  return postJson('/motion', { kv, kx, preflight_id: preflightId });
}

export async function setSetpoint(
  deg: number,
  preflightId?: string
): Promise<{ status: Status; control?: ControlState; preflight_id?: string | null }> {
  return postJson('/setpoint', { deg, preflight_id: preflightId });
}

export async function setLimits(
  outMax: number,
  tipDeg: number,
  iMax: number,
  preflightId?: string
): Promise<{ status: Status; control?: ControlState; preflight_id?: string | null }> {
  return postJson('/limits', { out_max: outMax, tip_deg: tipDeg, i_max: iMax, preflight_id: preflightId });
}
