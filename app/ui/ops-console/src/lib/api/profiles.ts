/**
 * Profiles Domain API Client
 * Hardware profiles, compatibility, and overwatch.
 */

import { fetchJson, postJson } from './client';

export type RobotProfile = {
  id: string;
  label: string;
  chassis: string;
  created_at: number;
  validation?: RobotValidationReport;
};

export type RobotProfilesState = {
  active_profile_id: string | null;
  profiles: RobotProfile[];
};

export type RobotValidationReport = {
  ok: boolean;
  robot_id: string;
  validated_at: number;
  checks: Array<{ name: string; passed: boolean; message: string }>;
  summary: string;
};

export type CompatReport = {
  ok: boolean;
  serial_connected: boolean;
  firmware_detected: boolean;
  protocol_version?: string;
  mcu_family?: string;
  checks: Array<{ name: string; passed: boolean; message: string }>;
};

export type ConnectProbeReport = {
  ok: boolean;
  port: string | null;
  baud: number | null;
  firmware_version?: string;
  capabilities?: string[];
  error?: string;
};

export type OverwatchReport = {
  overall: string;
  checks: Array<{
    name: string;
    status: string;
    message: string;
    severity: string;
  }>;
  recommendations: string[];
  last_updated: number;
};

export async function profilesList(): Promise<RobotProfilesState> {
  return fetchJson<RobotProfilesState>('/profiles');
}

export async function profilesValidate(durationS = 12, sampleIntervalS = 0.25): Promise<RobotValidationReport> {
  return postJson<RobotValidationReport>('/profiles/validate', {
    duration_s: durationS,
    sample_interval_s: sampleIntervalS,
  });
}

export async function profilesSave(
  profile: Partial<RobotProfile> & { label: string; chassis: string }
): Promise<RobotProfilesState> {
  return postJson<RobotProfilesState>('/profiles/save', profile);
}

export async function profilesActivate(profileId: string, validation: RobotValidationReport): Promise<RobotProfilesState> {
  return postJson<RobotProfilesState>('/profiles/activate', { profile_id: profileId, validation });
}

export async function profilesDelete(profileId: string): Promise<RobotProfilesState> {
  return postJson<RobotProfilesState>('/profiles/delete', { profile_id: profileId });
}

export async function probeCompat(): Promise<CompatReport> {
  return fetchJson<CompatReport>('/probe/compat');
}

export async function probeConnect(): Promise<ConnectProbeReport> {
  return fetchJson<ConnectProbeReport>('/probe/connect');
}

export async function getOverwatchStatus(refresh = false): Promise<OverwatchReport> {
  const url = refresh ? '/overwatch/status?refresh=1' : '/overwatch/status';
  return fetchJson<OverwatchReport>(url);
}
