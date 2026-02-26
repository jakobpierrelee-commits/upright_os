import type { ActionGates } from '../api';
import type { ControlState, Health, Status } from '../types';

export type CleanAction = {
  label: string;
  run: () => Promise<unknown>;
  className?: string;
  disabled?: boolean;
};

export type CleanGlobalStatusEvent = {
  level: 'ok' | 'warn' | 'fail';
  summary: string;
  source: string;
  ts: number;
};

export type CleanGlobalDock = {
  level: 'ok' | 'warn' | 'fail';
  summary: string;
  source: string;
  ts: number;
};

export type CleanAppState = {
  health: Health | null;
  apiContractOk: boolean;
  control: ControlState | null;
  actionGates: ActionGates | null;
  status: Status;
  busy: boolean;
  msg: string;
  actions: CleanAction[];
  globalDock: CleanGlobalDock;
  refresh: () => Promise<void>;
  runAction: (label: string, fn: () => Promise<unknown>) => Promise<void>;
  onGlobalStatus: (evt: CleanGlobalStatusEvent) => void;
};

export function statusValue(status: Status, key: string): string {
  if (key === 'gyro') return String(status.gyro ?? status.gyr ?? status.gx ?? '-');
  return String(status[key] ?? '-');
}

export function modeLabel(raw: unknown): string {
  const val = String(raw ?? '').trim().toLowerCase();
  if (!val || val === '-' || val === 'unknown') return 'Unknown';
  if (val === '0' || val === 'safe_idle' || val === 'idle') return 'Safe Idle';
  if (val === '1' || val === 'armed') return 'Armed';
  if (val === '2' || val === 'balancing' || val === 'run') return 'Balancing';
  if (val === '3' || val === 'estop') return 'E-Stop';
  return String(raw);
}
