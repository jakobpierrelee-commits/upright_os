import { useCallback, useEffect, useMemo, useReducer, useRef, useState, type ChangeEvent } from 'react';
import {
  armConfirm,
  armPrepare,
  calZero,
  disarm,
  estopLatch,
  estopReset,
  getHealth,
  getLines,
  getStatus,
  heartbeat,
  probeCompat,
  probeConnect,
  configRevert,
  saveCfg,
  setMotion,
  setPid,
  setSetpoint,
  postCommand,
  firmwareCheck,
  firmwareInstallCli,
  firmwareCompile,
  firmwareUpload,
  firmwareUploadGuarded,
  firmwareBoards,
  firmwareGenerateUnified,
  firmwareGenerateDocsPack,
  firmwareReadSketch,
  firmwareWriteSketch,
  serialDiag,
  burstArm,
  burstStatus,
  profilesList,
  profilesSave,
  profilesValidate,
  profilesActivate,
  profilesDelete,
  getOverwatchStatus,
  type SerialDiag,
  type BurstStatus,
  type CompatReport,
  type ConnectProbeReport,
  type FirmwareDocsPack,
  type OverwatchReport,
  type RobotProfile,
  type RobotValidationReport,
} from './api';
import type { ControlState, Health, Status } from './types';
import { useUiAlerts } from './hooks/useUiAlerts';
import { GlobalAlertRail } from './components/alerts/GlobalAlertRail';
import { useBridgePolling } from './hooks/useBridgePolling';
import { WorkbenchPanel } from './features/workbench/WorkbenchPanel';
import { initialWorkbenchState, workbenchReducer } from './features/workbench/workbenchReducer';
import { HudVisuals } from './pages/shared/HudVisuals';
import { CodexPanel } from './features/codex/CodexPanel';
import { useCodexWorkspace } from './hooks/useCodexWorkspace';
import { useHudTelemetry, type ImuSample } from './hooks/useHudTelemetry';
import { strings } from './strings';
import { ConnectPreflightPage } from './pages/stage1/ConnectPreflightPage';

const HISTORY_MAX = 180;

type MainTab = 'setup' | 'tune' | 'ide';

const BAL_BOUNDS = {
  kp: 1.0,
  ki: 0.05,
  kd: 0.2,
  kv: 0.05,
  kx: 0.002,
  setpoint: 0.5,
};

const LOCAL_COMMAND_REFERENCE = [
  '--- Command Reference (local fallback) ---',
  'GET',
  'HELP',
  'ARM',
  'DISARM',
  'CAL ZERO',
  'SAVECFG',
  'PID <kp> <ki> <kd>',
  'MOTION <kv> <kx>',
  'SETPOINT <deg>',
  'LIMITS <out_max> <tip_deg> <i_max>',
  'LOGCSV',
  'LOGT',
];

const OVERWATCH_ACCEPT_STORAGE_KEY = 'upright.overwatch.accepted.v1';

const KALMAN_STANDARD_SNIPPET = `// Standard IMU fusion contract (required by UpRight compatibility probe)
// Inputs:
//   measDeg  -> accel-derived tilt angle (degrees)
//   gyroDps  -> gyro rate on balance axis (deg/s)
// Output:
//   kfAngle  -> filtered tilt estimate (publish as STATUS ang=...)
// Also publish:
//   STATUS raw=<accelAngleDeg> gyro=<gyroRateDps>
float kalmanUpdate(float measDeg, float gyroDps, float dt) {
  float rate = gyroDps - kfBias;
  kfAngle += dt * rate;

  P00 += dt * (dt * P11 - P01 - P10 + cfg.qAngle);
  P01 -= dt * P11;
  P10 -= dt * P11;
  P11 += cfg.qBias * dt;

  float innovation = measDeg - kfAngle;
  float s = P00 + cfg.rMeasure;
  float k0 = P00 / s;
  float k1 = P10 / s;

  kfAngle += k0 * innovation;
  kfBias += k1 * innovation;

  float p00 = P00;
  float p01 = P01;
  P00 -= k0 * p00;
  P01 -= k0 * p01;
  P10 -= k1 * p00;
  P11 -= k1 * p01;
  return kfAngle;
}`;

function n(v: string | undefined, fallback = 0): number {
  const parsed = Number.parseFloat(v ?? '');
  return Number.isFinite(parsed) ? parsed : fallback;
}

function defaultUnifiedProfileDraft(fqbn: string, port: string): string {
  return JSON.stringify({
    label: 'UpRight Unified',
    board: {
      fqbn: fqbn || 'arduino:avr:nano',
      port: port || '/dev/cu.usbserial-2210',
      mcu_family: 'avr',
    },
    hardware: {
      imu_type: 'mpu6050',
      motor_driver: 'tb6612',
    },
    pins: {
      motor_l_pwm: 5,
      motor_l_dir: 4,
      motor_r_pwm: 6,
      motor_r_dir: 7,
      imu_sda: 18,
      imu_scl: 19,
      gate_enable: 8,
      led: 13,
      enc_l_a: -1,
      enc_l_b: -1,
      enc_r_a: -1,
      enc_r_b: -1,
    },
  }, null, 2);
}

function miniPolar(cx: number, cy: number, r: number, degFromTopCw: number) {
  const t = ((degFromTopCw - 90) * Math.PI) / 180;
  return { x: cx + (r * Math.cos(t)), y: cy + (r * Math.sin(t)) };
}

function miniSideArcPath(radius: number, value: number, pct: number): string {
  const cx = 20;
  const cy = 20;
  const mag = Math.max(0, Math.min(1, pct));
  if (mag <= 0.0001) return '';
  const sweep = 170 * mag;
  const start = miniPolar(cx, cy, radius, 0);
  const end = miniPolar(cx, cy, radius, value >= 0 ? sweep : -sweep);
  const sweepFlag = value >= 0 ? 1 : 0;
  return `M ${start.x.toFixed(2)} ${start.y.toFixed(2)} A ${radius} ${radius} 0 0 ${sweepFlag} ${end.x.toFixed(2)} ${end.y.toFixed(2)}`;
}

function miniSemiTrackPath(radius: number): string {
  const cx = 20;
  const cy = 20;
  const start = miniPolar(cx, cy, radius, -90);
  const end = miniPolar(cx, cy, radius, 90);
  return `M ${start.x.toFixed(2)} ${start.y.toFixed(2)} A ${radius} ${radius} 0 0 1 ${end.x.toFixed(2)} ${end.y.toFixed(2)}`;
}

function miniSemiFillPath(radius: number, value: number, pct: number): string {
  const cx = 20;
  const cy = 20;
  const mag = Math.max(0, Math.min(1, pct));
  if (mag <= 0.0001) return '';
  const sweep = 90 * mag;
  const start = miniPolar(cx, cy, radius, 0);
  const end = miniPolar(cx, cy, radius, value >= 0 ? sweep : -sweep);
  const sweepFlag = value >= 0 ? 1 : 0;
  return `M ${start.x.toFixed(2)} ${start.y.toFixed(2)} A ${radius} ${radius} 0 0 ${sweepFlag} ${end.x.toFixed(2)} ${end.y.toFixed(2)}`;
}

export default function App() {
  const codexRailRef = useRef<HTMLElement | null>(null);
  const statusbarRef = useRef<HTMLElement | null>(null);
  const profileImportRef = useRef<HTMLInputElement | null>(null);
  const lastAssistantApplyRef = useRef<string>('');
  const lastOverwatchOverallRef = useRef<string>('unknown');
  const missingTelemetryPromptedRef = useRef(false);
  const [activeTab, setActiveTab] = useState<MainTab>('setup');
  const [health, setHealth] = useState<Health | null>(null);
  const [bridgeOnline, setBridgeOnline] = useState(false);
  const [status, setStatus] = useState<Status>({});
  const [control, setControl] = useState<ControlState>({ arm_prepared: false, estop_latched: false });
  const [lines, setLines] = useState<string[]>([]);
  const [statusMsg, setStatusMsg] = useState('');
  const [unifiedSketchName, setUnifiedSketchName] = useState('upright_unified_v1');
  const [unifiedProfileJson, setUnifiedProfileJson] = useState(defaultUnifiedProfileDraft('arduino:avr:nano', '/dev/cu.usbserial-2210'));

  const [pid, setPidDraft] = useState({ kp: 31, ki: 0.05, kd: 1.05 });
  const [motion, setMotionDraft] = useState({ kv: 0, kx: 0 });
  const [setpoint, setSetpointDraft] = useState(0);
  const [compat, setCompat] = useState<CompatReport | null>(null);
  const [connectProbe, setConnectProbe] = useState<ConnectProbeReport | null>(null);
  const [validation, setValidation] = useState<RobotValidationReport | null>(null);
  const [overwatch, setOverwatch] = useState<OverwatchReport | null>(null);
  const [profileLabel, setProfileLabel] = useState('New Robot');
  const [chassisClass, setChassisClass] = useState('2wd_inverted_pendulum');
  const [robotProfilesState, setRobotProfilesState] = useState<{ active_profile_id: string | null; profiles: RobotProfile[] }>({
    active_profile_id: null,
    profiles: [],
  });
  const [imuHistory, setImuHistory] = useState<ImuSample[]>([]);
  const [serialHealth, setSerialHealth] = useState<SerialDiag | null>(null);
  const [burstInfo, setBurstInfo] = useState<BurstStatus | null>(null);
  const [burstDelayMs, setBurstDelayMs] = useState(3000);
  const [burstLines, setBurstLines] = useState(80);
  const [burstFreqHz, setBurstFreqHz] = useState(8);
  const [armAdvisory, setArmAdvisory] = useState<string | null>(null);
  const [revertBusy, setRevertBusy] = useState(false);

  const [preflightOpen, setPreflightOpen] = useState(false);
  const [overwatchOpen, setOverwatchOpen] = useState(false);
  const [overwatchDiagNote, setOverwatchDiagNote] = useState('');
  const [acceptedOverwatchChecks, setAcceptedOverwatchChecks] = useState<Record<string, number>>({});
  const compactUi = true;
  const [preflightChecks, setPreflightChecks] = useState({
    ide_closed: false,
    bot_safe: false,
    correct_port: false,
    power_expected: false,
  });

  const [workbenchState, workbenchDispatch] = useReducer(workbenchReducer, initialWorkbenchState);
  const { fw, fwCheck, fwCfg, workbenchTab, boardScan, sketchPath, sketchContent, serialWrite } = workbenchState;
  const sketchRevision = useMemo(() => {
    const s = sketchContent ?? '';
    let h = 2166136261;
    for (let i = 0; i < s.length; i += 1) {
      h ^= s.charCodeAt(i);
      h = Math.imul(h, 16777619);
    }
    return `${sketchPath ?? ''}:${s.length}:${h >>> 0}`;
  }, [sketchContent, sketchPath]);

  const setFw = useCallback((next: typeof fw) => workbenchDispatch({ type: 'set_fw', payload: next }), []);
  const setFwCheck = useCallback((next: typeof fwCheck) => workbenchDispatch({ type: 'set_fw_check', payload: next }), []);
  const setWorkbenchTab = useCallback((next: typeof workbenchTab) => workbenchDispatch({ type: 'set_workbench_tab', payload: next }), []);
  const setBoardScan = useCallback((next: typeof boardScan) => workbenchDispatch({ type: 'set_board_scan', payload: next }), []);
  const setSketchPath = useCallback((next: string) => workbenchDispatch({ type: 'set_sketch_path', payload: next }), []);
  const setSketchContent = useCallback((next: string) => workbenchDispatch({ type: 'set_sketch_content', payload: next }), []);
  const setSerialWrite = useCallback((next: string) => workbenchDispatch({ type: 'set_serial_write', payload: next }), []);
  const setFwCfg = useCallback((next: typeof fwCfg | ((prev: typeof fwCfg) => typeof fwCfg)) => {
    const resolved = typeof next === 'function' ? next(fwCfg) : next;
    workbenchDispatch({ type: 'set_fw_cfg', payload: resolved });
  }, [fwCfg]);

  const {
    active: alertsActive,
    history: alertsHistory,
    allActive: alertsAllActive,
    filter: alertsFilter,
    setFilter: setAlertsFilter,
    pushAlert,
    unlockSource: unlockAlertSource,
    dismiss: dismissAlert,
    clearNonError: clearNonErrorAlerts,
    clearAll: clearAllAlerts,
    clearHistory: clearAlertHistory,
  } = useUiAlerts();

  const setMsg = useCallback((text: string, source = 'general') => {
    setStatusMsg(text);
    pushAlert(text, undefined, source);
  }, [pushAlert]);

  const codex = useCodexWorkspace(setMsg);

  useEffect(() => {
    void codex.actions.bootstrap();
  }, [codex.actions.bootstrap]);

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(OVERWATCH_ACCEPT_STORAGE_KEY);
      if (!raw) return;
      const parsed = JSON.parse(raw) as unknown;
      if (!parsed || typeof parsed !== 'object') return;
      const next: Record<string, number> = {};
      Object.entries(parsed as Record<string, unknown>).forEach(([k, v]) => {
        if (typeof k === 'string' && typeof v === 'number' && Number.isFinite(v)) {
          next[k] = v;
        }
      });
      setAcceptedOverwatchChecks(next);
    } catch {
      // Ignore invalid persisted values.
    }
  }, []);

  useEffect(() => {
    try {
      window.localStorage.setItem(OVERWATCH_ACCEPT_STORAGE_KEY, JSON.stringify(acceptedOverwatchChecks));
    } catch {
      // Ignore storage write failures.
    }
  }, [acceptedOverwatchChecks]);

  const mode = status.mode ?? 'UNKNOWN';
  const balancing = mode === 'BALANCING';
  const compatKnown = compat !== null;
  const compatOk = compat?.ok === true;
  const modeUpper = mode.toUpperCase();
  const modeTone =
    modeUpper === 'BALANCING' || modeUpper === 'ARMED'
      ? 'good'
      : modeUpper === 'SAFE_IDLE' || modeUpper === 'IDLE' || modeUpper === 'READY' || modeUpper === 'PREARM'
        ? 'warn'
        : modeUpper === 'FAULT' || modeUpper === 'ESTOP' || modeUpper === 'ERROR'
          ? 'bad'
          : 'unknown';
  const angleParsed = Number.parseFloat(status.ang ?? '');
  const angleAbs = Number.isFinite(angleParsed) ? Math.abs(angleParsed) : null;
  const angleTone = angleAbs == null ? 'unknown' : angleAbs <= 6.0 ? 'good' : angleAbs <= 12.0 ? 'warn' : 'bad';
  const estopTone = control.estop_latched ? 'bad' : 'good';
  const compatTone = !compatKnown ? 'unknown' : compatOk ? 'good' : 'bad';
  const burstHost = burstInfo?.host_capture ?? null;
  const burstRows = burstHost?.rows ?? 0;
  const burstTarget = burstHost?.target_lines ?? 0;
  const burstProgressPct = burstTarget > 0 ? Math.max(0, Math.min(100, (burstRows / burstTarget) * 100)) : 0;
  const burstStateLower = String(burstInfo?.state ?? 'idle').toLowerCase();
  const burstTone =
    burstStateLower.includes('captur') || burstStateLower.includes('done')
      ? 'good'
      : burstStateLower.includes('arm') || burstStateLower.includes('queue')
        ? 'warn'
        : burstStateLower.includes('fail') || burstStateLower.includes('error')
          ? 'bad'
          : 'unknown';
  const overwatchEffective = useMemo(() => {
    const checks = overwatch?.checks ?? [];
    let pass = 0;
    let warn = 0;
    let fail = 0;
    let accepted = 0;
    for (const c of checks) {
      if (c.status === 'pass') {
        pass += 1;
        continue;
      }
      if (acceptedOverwatchChecks[c.id]) {
        accepted += 1;
        continue;
      }
      if (c.status === 'warn') warn += 1;
      else if (c.status === 'fail') fail += 1;
    }
    const total = checks.length;
    const overall = fail > 0 ? 'fail' : warn > 0 ? 'warn' : 'pass';
    const score_pct = total > 0 ? Math.round(((pass + accepted + 0.5 * warn) / total) * 100) : 100;
    return { pass, warn, fail, accepted, total, overall, score_pct };
  }, [acceptedOverwatchChecks, overwatch?.checks]);
  const overwatchTone = overwatchEffective.overall === 'fail' ? 'bad' : overwatchEffective.overall === 'warn' ? 'warn' : 'good';
  const overwatchLabel = overwatchEffective.overall === 'fail' ? 'ISSUE' : overwatchEffective.overall === 'warn' ? 'WATCH' : 'OK';
  const activeRobotProfile = useMemo(
    () => robotProfilesState.profiles.find((p) => p.profile_id === robotProfilesState.active_profile_id) ?? null,
    [robotProfilesState.active_profile_id, robotProfilesState.profiles],
  );

  const runCompatProbe = useCallback(async (): Promise<CompatReport | null> => {
    unlockAlertSource('bridge.poll');
    try {
      const r = await probeCompat();
      setCompat(r);
      setMsg(r.ok ? 'Compatibility probe passed' : 'Compatibility probe failed');
      return r;
    } catch (e) {
      setMsg(`compat probe error: ${(e as Error).message}`);
      return null;
    }
  }, [setMsg, unlockAlertSource]);

  const loadAssistantPrompt = useCallback((prompt: string) => {
    codex.actions.setAiInput(prompt);
    setMsg('Prompt loaded into Codex input. Press Send when ready.', 'setup.prompt');
  }, [codex.actions, setMsg]);

  const refreshProfiles = useCallback(async () => {
    try {
      const out = await profilesList();
      setRobotProfilesState(out);
    } catch (e) {
      setMsg(`profiles list error: ${(e as Error).message}`);
    }
  }, [setMsg]);

  const runConnectWizard = useCallback(async (): Promise<ConnectProbeReport | null> => {
    unlockAlertSource('bridge.poll');
    try {
      const probe = await probeConnect();
      setConnectProbe(probe);
      if (probe.compat) setCompat(probe.compat);
      setMsg(probe.ok ? 'Connect auto-detect passed' : 'Connect auto-detect incomplete');
      return probe;
    } catch (e) {
      setMsg(`connect probe error: ${(e as Error).message}`);
      return null;
    }
  }, [setMsg, unlockAlertSource]);

  const runProfileValidation = useCallback(async () => {
    unlockAlertSource('bridge.poll');
    try {
      setMsg('Running validation checks...');
      const out = await profilesValidate(12, 0.25);
      setValidation(out);
      setConnectProbe(out.connect);
      if (out.compat) setCompat(out.compat);
      setSerialHealth(out.serial);
      setMsg(out.ok ? `Validation passed (${out.score_pct}%)` : `Validation failed (${out.score_pct}%)`);
    } catch (e) {
      setMsg(`validation error: ${(e as Error).message}`);
    }
  }, [setMsg, unlockAlertSource]);

  const refreshOverwatch = useCallback(async (opts?: { force?: boolean; announce?: boolean }): Promise<OverwatchReport | null> => {
    const force = Boolean(opts?.force);
    const announce = Boolean(opts?.announce);
    try {
      const out = await getOverwatchStatus(force);
      setOverwatch(out);
      const next = (() => {
        let hasFail = false;
        let hasWarn = false;
        for (const c of out.checks ?? []) {
          if (c.status === 'pass') continue;
          if (acceptedOverwatchChecks[c.id]) continue;
          if (c.status === 'fail') hasFail = true;
          else if (c.status === 'warn') hasWarn = true;
        }
        if (hasFail) return 'fail';
        if (hasWarn) return 'warn';
        return 'pass';
      })();
      if (announce) {
        setMsg(`Overwatch ${String(next).toUpperCase()} (${out.score_pct}%)`);
      } else {
        const prev = lastOverwatchOverallRef.current;
        if (prev !== next && (next === 'warn' || next === 'fail')) {
          setMsg(`Overwatch changed to ${next.toUpperCase()} (${out.score_pct}%)`, 'overwatch');
        }
      }
      lastOverwatchOverallRef.current = String(next);
      return out;
    } catch (e) {
      if (announce) {
        setMsg(`overwatch error: ${(e as Error).message}`);
      }
      return null;
    }
  }, [acceptedOverwatchChecks, setMsg]);

  const runOverwatchCheck = useCallback(async (): Promise<OverwatchReport | null> => {
    unlockAlertSource('bridge.poll');
    const out = await refreshOverwatch({ force: true, announce: true });
    const stamp = new Date().toLocaleTimeString();
    setOverwatchDiagNote(
      out
        ? `Diagnostics ran at ${stamp}: ${String(lastOverwatchOverallRef.current).toUpperCase()} (${out.score_pct}%)`
        : `Diagnostics ran at ${stamp}: ERROR`,
    );
    return out;
  }, [refreshOverwatch, unlockAlertSource]);

  const acceptOverwatchCheck = useCallback((checkId: string) => {
    setAcceptedOverwatchChecks((prev) => ({ ...prev, [checkId]: Date.now() }));
  }, []);

  const restoreOverwatchCheck = useCallback((checkId: string) => {
    setAcceptedOverwatchChecks((prev) => {
      const next = { ...prev };
      delete next[checkId];
      return next;
    });
  }, []);

  useEffect(() => {
    if (!bridgeOnline) return;
    let cancelled = false;
    const tick = async () => {
      if (cancelled) return;
      await refreshOverwatch({ force: false, announce: false });
    };
    void tick();
    const id = window.setInterval(() => {
      void tick();
    }, 2500);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [bridgeOnline, refreshOverwatch]);

  const saveRobotProfile = useCallback(async () => {
    if (!profileLabel.trim()) {
      setMsg('Profile label is required');
      return;
    }
    try {
      const out = await profilesSave({
        profile_id: activeRobotProfile?.profile_id,
        label: profileLabel.trim(),
        chassis: chassisClass,
        board: {
          fqbn: fwCfg.fqbn,
          port: fwCfg.port,
          detected: boardScan?.ports ?? [],
        },
        firmware: {
          sketch: sketchPath,
          profile: connectProbe?.firmware_profile ?? compat?.profile ?? 'unknown',
        },
        probe: connectProbe ?? ({} as ConnectProbeReport),
        validation: validation ?? {},
      });
      setRobotProfilesState(out);
      setMsg('Robot profile saved');
    } catch (e) {
      setMsg(`profile save error: ${(e as Error).message}`);
    }
  }, [activeRobotProfile?.profile_id, boardScan?.ports, chassisClass, compat?.profile, connectProbe, fwCfg.fqbn, fwCfg.port, profileLabel, setMsg, sketchPath, validation]);

  const loadSavedRobotProfile = useCallback(() => {
    if (!activeRobotProfile) {
      setMsg('No active profile to load');
      return;
    }
    setProfileLabel(activeRobotProfile.label);
    setChassisClass(activeRobotProfile.chassis);
    if (activeRobotProfile.probe) setConnectProbe(activeRobotProfile.probe);
    setMsg(`Loaded profile: ${activeRobotProfile.label}`);
  }, [activeRobotProfile, setMsg]);

  const loadProfileById = useCallback((profileId: string) => {
    const target = robotProfilesState.profiles.find((p) => p.profile_id === profileId);
    if (!target) {
      setMsg('Selected profile not found');
      return;
    }
    setProfileLabel(target.label);
    setChassisClass(target.chassis);
    if (target.probe) setConnectProbe(target.probe);
    setMsg(`Loaded profile: ${target.label}`);
  }, [robotProfilesState.profiles, setMsg]);

  const exportRobotProfile = useCallback(async () => {
    const target = activeRobotProfile;
    if (!target) {
      setMsg('No active profile to export');
      return;
    }
    const blob = new Blob([JSON.stringify(target, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${target.label.replace(/\s+/g, '_').toLowerCase()}_profile.json`;
    a.click();
    URL.revokeObjectURL(url);
    setMsg('Profile export started');
  }, [activeRobotProfile, setMsg]);

  const exportProfileById = useCallback(async (profileId: string) => {
    const target = robotProfilesState.profiles.find((p) => p.profile_id === profileId);
    if (!target) {
      setMsg('Selected profile not found for export');
      return;
    }
    const blob = new Blob([JSON.stringify(target, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${target.label.replace(/\s+/g, '_').toLowerCase()}_profile.json`;
    a.click();
    URL.revokeObjectURL(url);
    setMsg(`Profile export started: ${target.label}`);
  }, [robotProfilesState.profiles, setMsg]);

  const importRobotProfile = useCallback(() => {
    profileImportRef.current?.click();
  }, []);

  const onProfileImportFile = useCallback(async (ev: ChangeEvent<HTMLInputElement>) => {
    const file = ev.target.files?.[0];
    ev.target.value = '';
    if (!file) return;
    try {
      const text = await file.text();
      const parsed = JSON.parse(text) as Partial<RobotProfile>;
      const out = await profilesSave({
        ...parsed,
        label: String(parsed.label ?? profileLabel).trim(),
        chassis: String(parsed.chassis ?? chassisClass).trim() || 'custom',
      });
      setRobotProfilesState(out);
      setMsg('Profile imported');
    } catch (e) {
      setMsg(`profile import error: ${(e as Error).message}`);
    }
  }, [chassisClass, profileLabel, setMsg]);

  const deleteSavedRobotProfile = useCallback(async () => {
    const target = activeRobotProfile;
    if (!target) {
      setMsg('No active profile to delete');
      return;
    }
    try {
      const out = await profilesDelete(target.profile_id);
      setRobotProfilesState(out);
      setMsg(`Deleted profile: ${target.label}`);
    } catch (e) {
      setMsg(`profile delete error: ${(e as Error).message}`);
    }
  }, [activeRobotProfile, setMsg]);

  const deleteProfileById = useCallback(async (profileId: string) => {
    const target = robotProfilesState.profiles.find((p) => p.profile_id === profileId);
    if (!target) {
      setMsg('Selected profile not found for delete');
      return;
    }
    try {
      const out = await profilesDelete(profileId);
      setRobotProfilesState(out);
      setMsg(`Deleted profile: ${target.label}`);
    } catch (e) {
      setMsg(`profile delete error: ${(e as Error).message}`);
    }
  }, [robotProfilesState.profiles, setMsg]);

  const activateProfileIfValid = useCallback(async () => {
    if (!activeRobotProfile) {
      setMsg('Save profile before activation');
      return;
    }
    if (!validation?.ok) {
      setMsg('Run validation and pass all checks before activation');
      return;
    }
    try {
      const out = await profilesActivate(activeRobotProfile.profile_id, validation);
      setRobotProfilesState(out);
      setMsg(`Activated profile: ${activeRobotProfile.label}`);
    } catch (e) {
      setMsg(`profile activate error: ${(e as Error).message}`);
    }
  }, [activeRobotProfile, setMsg, validation]);

  const activateProfileByIdIfValid = useCallback(async (profileId: string) => {
    const target = robotProfilesState.profiles.find((p) => p.profile_id === profileId);
    if (!target) {
      setMsg('Selected profile not found for activation');
      return;
    }
    if (!validation?.ok) {
      setMsg('Run validation and pass all checks before activation');
      return;
    }
    try {
      const out = await profilesActivate(profileId, validation);
      setRobotProfilesState(out);
      setMsg(`Activated profile: ${target.label}`);
    } catch (e) {
      setMsg(`profile activate error: ${(e as Error).message}`);
    }
  }, [robotProfilesState.profiles, setMsg, validation]);

  const generateFirmwareDocsPack = useCallback(async (): Promise<FirmwareDocsPack | null> => {
    const pinmap = (activeRobotProfile?.pinmap ?? {}) as Record<string, unknown>;
    const profile: Record<string, unknown> = {
      label: profileLabel.trim() || activeRobotProfile?.label || 'UpRight Robot',
      board: {
        fqbn: String((activeRobotProfile?.board as Record<string, unknown> | undefined)?.fqbn ?? fwCfg.fqbn ?? 'arduino:avr:nano'),
        port: String((activeRobotProfile?.board as Record<string, unknown> | undefined)?.port ?? fwCfg.port ?? ''),
        mcu_family: String((activeRobotProfile?.board as Record<string, unknown> | undefined)?.mcu_family ?? connectProbe?.mcu_guess ?? 'unknown'),
      },
      hardware: {
        imu_type: String((activeRobotProfile?.parts as Record<string, unknown> | undefined)?.imu_type ?? 'unknown_imu'),
        motor_driver: String((activeRobotProfile?.parts as Record<string, unknown> | undefined)?.motor_driver ?? 'unknown_driver'),
      },
      pins: {
        motor_l_pwm: Number(pinmap.motor_l_pwm ?? 5),
        motor_l_dir: Number(pinmap.motor_l_dir ?? 4),
        motor_r_pwm: Number(pinmap.motor_r_pwm ?? 6),
        motor_r_dir: Number(pinmap.motor_r_dir ?? 7),
        imu_sda: Number(pinmap.imu_sda ?? 18),
        imu_scl: Number(pinmap.imu_scl ?? 19),
        gate_enable: Number(pinmap.gate_enable ?? 8),
        led: Number(pinmap.led ?? 13),
        enc_l_a: Number(pinmap.enc_l_a ?? -1),
        enc_l_b: Number(pinmap.enc_l_b ?? -1),
        enc_r_a: Number(pinmap.enc_r_a ?? -1),
        enc_r_b: Number(pinmap.enc_r_b ?? -1),
      },
    };
    try {
      const out = await firmwareGenerateDocsPack(
        profile,
        `${profileLabel.trim() || 'upright'}_firmware`,
        sketchContent,
        sketchPath || undefined,
        true,
      );
      setMsg(`Firmware docs pack generated: ${out.docs_folder} (zip: ${out.archive})`);
      return out;
    } catch (e) {
      setMsg(`docs pack generation error: ${(e as Error).message}`);
      return null;
    }
  }, [activeRobotProfile?.board, activeRobotProfile?.label, activeRobotProfile?.parts, activeRobotProfile?.pinmap, connectProbe?.mcu_guess, fwCfg.fqbn, fwCfg.port, profileLabel, setMsg, sketchContent, sketchPath]);

  const initDraftsFromStatus = useCallback((s: Status) => {
    setPidDraft({ kp: n(s.kp, 31), ki: n(s.ki, 0.05), kd: n(s.kd, 1.05) });
    setMotionDraft({ kv: n(s.kv, 0), kx: n(s.kx, 0) });
    setSetpointDraft(n(s.set, 0));
  }, []);

  useBridgePolling({
    setHealth,
    setBridgeOnline,
    setStatus,
    setControl,
    setImuHistory,
    initDraftsFromStatus,
    runCompatProbe: () => void runCompatProbe(),
    setMsg,
    historyMax: HISTORY_MAX,
    n,
  });

  const refreshBoards = useCallback(async () => {
    try {
      const b = await firmwareBoards();
      setBoardScan(b);
      if (b.recommended_fqbn || b.recommended_port) {
        setFwCfg((prev) => ({
          ...prev,
          fqbn: b.recommended_fqbn || prev.fqbn,
          port: b.recommended_port || prev.port,
        }));
      }
      setMsg(b.ok ? `Found ${b.ports.length} serial port(s)` : `Board scan failed: ${b.error ?? 'unknown error'}`);
    } catch (e) {
      setMsg(`board scan error: ${(e as Error).message}`);
    }
  }, [setBoardScan, setFwCfg, setMsg]);

  const loadSketch = useCallback(async () => {
    try {
      const sk = await firmwareReadSketch(sketchPath || undefined);
      setSketchPath(sk.path);
      setSketchContent(sk.content);
      setMsg(`Sketch loaded: ${sk.path}`);
    } catch (e) {
      setMsg(`sketch load error: ${(e as Error).message}`);
    }
  }, [setMsg, setSketchContent, setSketchPath, sketchPath]);

  const refreshSerialDiag = useCallback(async () => {
    try {
      const d = await serialDiag();
      setSerialHealth(d);
    } catch {
      setSerialHealth(null);
    }
  }, []);

  const refreshBurstInfo = useCallback(async () => {
    try {
      const b = await burstStatus();
      setBurstInfo(b);
    } catch {
      setBurstInfo(null);
    }
  }, []);

  useEffect(() => {
    if (!sketchContent) void loadSketch();
    if (!boardScan) void refreshBoards();
    void refreshSerialDiag();
    void refreshBurstInfo();
    void refreshProfiles();
  }, [boardScan, loadSketch, refreshBoards, refreshBurstInfo, refreshSerialDiag, sketchContent]);

  useEffect(() => {
    const id = window.setInterval(() => {
      void refreshBurstInfo();
    }, 800);
    return () => window.clearInterval(id);
  }, [refreshBurstInfo]);

  const syncFromBot = useCallback(() => {
    setPidDraft({ kp: n(status.kp, 31), ki: n(status.ki, 0.05), kd: n(status.kd, 1.05) });
    setMotionDraft({ kv: n(status.kv, 0), kx: n(status.kx, 0) });
    setSetpointDraft(n(status.set, 0));
    setMsg('Drafts synced from bot status');
  }, [setMsg, status.kd, status.ki, status.kp, status.kv, status.kx, status.set]);

  const runFirmwareCheck = useCallback(async () => {
    try {
      const r = await firmwareCheck();
      setFwCheck(r);
      setMsg(r.ok ? 'Arduino CLI detected' : `Arduino CLI check failed: ${r.error ?? 'unknown error'}`);
    } catch (e) {
      setMsg(`firmware check error: ${(e as Error).message}`);
    }
  }, [setFwCheck, setMsg]);

  const runFirmwareInstall = useCallback(async () => {
    try {
      const st = await firmwareInstallCli();
      setFw(st);
      setMsg('Arduino CLI install started');
    } catch (e) {
      setMsg(`install error: ${(e as Error).message}`);
    }
  }, [setFw, setMsg]);

  const runFirmwareCompile = useCallback(async () => {
    try {
      const st = await firmwareCompile(fwCfg.sketch, fwCfg.fqbn);
      setFw(st);
      setMsg('Firmware compile started');
    } catch (e) {
      setMsg(`compile error: ${(e as Error).message}`);
    }
  }, [fwCfg.fqbn, fwCfg.sketch, setFw, setMsg]);

  const runFirmwareUpload = useCallback(async () => {
    try {
      const st = await firmwareUpload(fwCfg.sketch, fwCfg.fqbn, fwCfg.port);
      setFw(st);
      setMsg('Firmware upload started');
    } catch (e) {
      setMsg(`upload error: ${(e as Error).message}`);
    }
  }, [fwCfg.fqbn, fwCfg.port, fwCfg.sketch, setFw, setMsg]);

  const runFirmwareUploadGuarded = useCallback(async () => {
    setPreflightOpen(true);
  }, []);

  const executeGuardedFlash = useCallback(async () => {
    try {
      setPreflightOpen(false);
      const st = await firmwareUploadGuarded(fwCfg.sketch, fwCfg.fqbn, fwCfg.port);
      setFw(st);
      setMsg('Guarded flash started');
    } catch (e) {
      setMsg(`guarded flash error: ${(e as Error).message}`);
    }
  }, [fwCfg.fqbn, fwCfg.port, fwCfg.sketch, setFw, setMsg]);

  const runGenerateUnified = useCallback(async () => {
    try {
      let profile: Record<string, unknown>;
      try {
        profile = JSON.parse(unifiedProfileJson) as Record<string, unknown>;
      } catch (e) {
        setMsg(`unified profile JSON parse error: ${(e as Error).message}`);
        return;
      }
      const out = await firmwareGenerateUnified(profile, unifiedSketchName);
      const loaded = await firmwareReadSketch(out.main_file);
      setSketchPath(loaded.path);
      setSketchContent(loaded.content);
      setFwCfg((prev) => ({ ...prev, sketch: out.sketch_folder }));
      setMsg(`Unified scaffold generated: ${out.sketch_folder} (zip: ${out.archive})`);
    } catch (e) {
      setMsg(`unified generate error: ${(e as Error).message}`);
    }
  }, [setFwCfg, setMsg, setSketchContent, setSketchPath, unifiedProfileJson, unifiedSketchName]);

  const applyPastedSketch = useCallback((text: string) => {
    const next = text.trim();
    if (!next) {
      setMsg('Paste sketch is empty');
      return;
    }
    setSketchContent(next);
    setMsg('Pasted sketch loaded into IDE buffer');
  }, [setMsg, setSketchContent]);

  const saveSketch = useCallback(async () => {
    try {
      const out = await firmwareWriteSketch(sketchContent, sketchPath || undefined);
      setSketchPath(out.path);
      setMsg(`Sketch saved (${out.bytes} bytes)`);
    } catch (e) {
      setMsg(`sketch save error: ${(e as Error).message}`);
    }
  }, [setMsg, setSketchPath, sketchContent, sketchPath]);

  const sendSerialLine = useCallback(async () => {
    const cmd = serialWrite.trim();
    if (!cmd) return;
    try {
      const verb = cmd.split(/\s+/, 1)[0]?.toUpperCase() ?? '';
      const timeoutS = verb === 'GET' || verb === 'HELP' || verb.startsWith('LOG') ? 6.0 : 2.5;
      await postCommand(cmd, undefined, timeoutS);
      setSerialWrite('');
      setMsg(`Sent: ${cmd}`);
      const ls = await getLines(200);
      setLines(ls);
      await refreshSerialDiag();
    } catch (e) {
      setMsg(`serial send error: ${(e as Error).message}`);
    }
  }, [refreshSerialDiag, serialWrite, setMsg, setSerialWrite]);

  const sendSerialCommand = useCallback(async (cmdRaw: string) => {
    const cmd = cmdRaw.trim();
    if (!cmd) return;
    try {
      const verb = cmd.split(/\s+/, 1)[0]?.toUpperCase() ?? '';
      const timeoutS = verb === 'HELP' ? 12.0 : (verb === 'GET' || verb.startsWith('LOG') ? 6.0 : 2.5);
      const before = await getLines(300);
      await postCommand(cmd, undefined, timeoutS);
      setMsg(`Sent: ${cmd}`);
      let latest = before;
      for (let i = 0; i < 3; i += 1) {
        if (i > 0) {
          await new Promise((resolve) => setTimeout(resolve, 120));
        }
        latest = await getLines(300);
        setLines(latest);
      }
      await refreshSerialDiag();
      if (verb === 'HELP' && latest.length <= before.length) {
        const stamped = `${new Date().toLocaleTimeString()} ${LOCAL_COMMAND_REFERENCE[0]}`;
        setLines((prev) => [...prev, stamped, ...LOCAL_COMMAND_REFERENCE.slice(1)]);
        setMsg('HELP returned no serial output; showing local command reference');
      }
    } catch (e) {
      setMsg(`serial send error: ${(e as Error).message}`);
    }
  }, [refreshSerialDiag, setMsg]);

  const refreshLogs = useCallback(async () => {
    const ls = await getLines(200);
    setLines(ls);
  }, []);

  const applyPid = useCallback(async () => {
    const current = { kp: n(status.kp), ki: n(status.ki), kd: n(status.kd) };
    if (balancing) {
      if (
        Math.abs(pid.kp - current.kp) > BAL_BOUNDS.kp ||
        Math.abs(pid.ki - current.ki) > BAL_BOUNDS.ki ||
        Math.abs(pid.kd - current.kd) > BAL_BOUNDS.kd
      ) {
        setMsg('PID change too large while BALANCING; DISARM for larger edits.');
        return;
      }
    }
    const r = await setPid(pid.kp, pid.ki, pid.kd);
    setStatus(r.status);
    if (r.control) setControl(r.control);
    setMsg('PID applied');
  }, [balancing, pid.kd, pid.ki, pid.kp, setMsg, status.kd, status.ki, status.kp]);

  const applyMotion = useCallback(async () => {
    const current = { kv: n(status.kv), kx: n(status.kx) };
    if (balancing) {
      if (Math.abs(motion.kv - current.kv) > BAL_BOUNDS.kv || Math.abs(motion.kx - current.kx) > BAL_BOUNDS.kx) {
        setMsg('MOTION change too large while BALANCING; DISARM for larger edits.');
        return;
      }
    }
    const r = await setMotion(motion.kv, motion.kx);
    setStatus(r.status);
    if (r.control) setControl(r.control);
    setMsg('MOTION applied');
  }, [balancing, motion.kv, motion.kx, setMsg, status.kv, status.kx]);

  const applySetpoint = useCallback(async () => {
    const current = n(status.set);
    if (balancing && Math.abs(setpoint - current) > BAL_BOUNDS.setpoint) {
      setMsg('SETPOINT change too large while BALANCING; DISARM for larger edits.');
      return;
    }
    const r = await setSetpoint(setpoint);
    setStatus(r.status);
    if (r.control) setControl(r.control);
    setMsg('SETPOINT applied');
  }, [balancing, setMsg, setpoint, status.set]);

  const revertLatestConfig = useCallback(async () => {
    if (revertBusy) return;
    setRevertBusy(true);
    try {
      const r = await configRevert();
      setStatus(r.revert.status);
      if (r.control) setControl(r.control);
      const parts = r.revert.reverted.length ? r.revert.reverted.join(', ') : 'none';
      setMsg(`Reverted config snapshot ${r.revert.snapshot_id ?? '(unknown)'} [${parts}]`);
    } catch (e) {
      setMsg(`config revert error: ${(e as Error).message}`);
    } finally {
      setRevertBusy(false);
    }
  }, [revertBusy, setMsg]);

  const refreshBridge = useCallback(async () => {
    unlockAlertSource('bridge.poll');
    try {
      const [h, s, hb] = await Promise.all([getHealth(), getStatus(), heartbeat()]);
      setBridgeOnline(true);
      setHealth(h.health);
      if (h.control) setControl(h.control);
      setControl(hb);
      setStatus(s.status);
      if (s.control) setControl(s.control);
      await refreshBurstInfo();
      setMsg('Refreshed');
    } catch (e) {
      setBridgeOnline(false);
      setMsg(`refresh error: ${(e as Error).message}`);
    }
  }, [refreshBurstInfo, setMsg, unlockAlertSource]);

  const armBurstCapture = useCallback(async () => {
    try {
      const out = await burstArm(burstDelayMs, burstLines, burstFreqHz);
      setBurstInfo(out);
      setMsg(`Burst armed: delay=${burstDelayMs}ms lines=${burstLines} freq=${burstFreqHz.toFixed(1)}Hz`);
      const ls = await getLines(240);
      setLines(ls);
    } catch (e) {
      setMsg(`burst arm error: ${(e as Error).message}`);
    }
  }, [burstDelayMs, burstLines, burstFreqHz, setMsg]);

  const insertKalmanTemplate = useCallback(() => {
    if (sketchContent.includes('float kalmanUpdate(')) {
      setMsg('Kalman function already exists in this sketch.');
      return;
    }
    setSketchContent(`${sketchContent.trimEnd()}\n\n${KALMAN_STANDARD_SNIPPET}\n`);
    setMsg('Inserted Kalman standard snippet (accel+gyro fusion + telemetry contract).');
  }, [setMsg, setSketchContent, sketchContent]);

  const hudMetrics = useHudTelemetry(status, imuHistory, strings.hud, health?.last_status_age_ms ?? null);

  useEffect(() => {
    const connected = Boolean(health?.connected) || bridgeOnline;
    const missingTelemetry = connected && !hudMetrics.requiredInputState.ok;
    if (missingTelemetry && !missingTelemetryPromptedRef.current) {
      missingTelemetryPromptedRef.current = true;
      setMsg('Device connected but telemetry data is missing. Run Compatibility Probe.', 'telemetry.contract');
      return;
    }
    if (!missingTelemetry) {
      missingTelemetryPromptedRef.current = false;
    }
  }, [bridgeOnline, health?.connected, hudMetrics.requiredInputState.ok, setMsg]);

  const codexProps = useMemo(() => ({
    bridgeReady: bridgeOnline,
    authUser: codex.state.authUser,
    ai: codex.state.ai,
    authAlert: codex.state.authAlert,
    authMode: codex.state.authMode,
    setAuthMode: codex.actions.setAuthMode,
    setAuthAlert: codex.actions.setAuthAlert,
    authEmail: codex.state.authEmail,
    setAuthEmail: codex.actions.setAuthEmail,
    authPassword: codex.state.authPassword,
    setAuthPassword: codex.actions.setAuthPassword,
    authBusy: codex.state.authBusy,
    submitAuth: codex.actions.submitAuth,
    openAiKeyInput: codex.state.openAiKeyInput,
    setOpenAiKeyInput: codex.actions.setOpenAiKeyInput,
    openAiModelInput: codex.state.openAiModelInput,
    setOpenAiModelInput: codex.actions.setOpenAiModelInput,
    saveUserOpenAiKey: codex.actions.saveUserOpenAiKey,
    clearUserOpenAiKey: codex.actions.clearUserOpenAiKey,
    runLogout: codex.actions.runLogout,
    aiHistory: codex.state.aiHistory,
    aiThreads: codex.state.aiThreads,
    aiActiveThreadId: codex.state.aiActiveThreadId,
    aiProfiles: codex.state.aiProfiles,
    aiActiveProfileId: codex.state.aiActiveProfileId,
    aiProfileLabelInput: codex.state.aiProfileLabelInput,
    setAiProfileLabelInput: codex.actions.setAiProfileLabelInput,
    aiProfileDescriptionInput: codex.state.aiProfileDescriptionInput,
    setAiProfileDescriptionInput: codex.actions.setAiProfileDescriptionInput,
    aiProfileInstructionsInput: codex.state.aiProfileInstructionsInput,
    setAiProfileInstructionsInput: codex.actions.setAiProfileInstructionsInput,
    aiProfileAllowAutoApplyInput: codex.state.aiProfileAllowAutoApplyInput,
    setAiProfileAllowAutoApplyInput: codex.actions.setAiProfileAllowAutoApplyInput,
    refreshAiProfiles: codex.actions.refreshAiProfiles,
    saveAiProfile: codex.actions.saveAiProfile,
    activateAiProfile: codex.actions.activateAiProfile,
    aiInput: codex.state.aiInput,
    setAiInput: codex.actions.setAiInput,
    aiBusy: codex.state.aiBusy,
    sendAi: codex.actions.sendAi,
    requestPasswordReset: codex.actions.requestPasswordReset,
    confirmPasswordReset: codex.actions.confirmPasswordReset,
    refreshThreads: codex.actions.refreshThreads,
    startNewChat: codex.actions.startNewChat,
    selectChatThread: codex.actions.selectChatThread,
  }), [bridgeOnline, codex.actions, codex.state.ai, codex.state.aiActiveProfileId, codex.state.aiActiveThreadId, codex.state.aiBusy, codex.state.aiHistory, codex.state.aiInput, codex.state.aiProfileAllowAutoApplyInput, codex.state.aiProfileDescriptionInput, codex.state.aiProfileInstructionsInput, codex.state.aiProfileLabelInput, codex.state.aiProfiles, codex.state.aiThreads, codex.state.authAlert, codex.state.authBusy, codex.state.authEmail, codex.state.authMode, codex.state.authPassword, codex.state.authUser, codex.state.openAiKeyInput, codex.state.openAiModelInput]);

  useEffect(() => {
    const updateLayoutVars = () => {
      const root = document.documentElement;
      const railTop = codexRailRef.current?.getBoundingClientRect().top ?? 120;
      const statusHeight = statusbarRef.current?.getBoundingClientRect().height ?? 44;
      root.style.setProperty('--ops-codex-top-offset', `${Math.max(0, Math.ceil(railTop))}px`);
      root.style.setProperty('--statusbar-clearance', `${Math.max(56, Math.ceil(statusHeight + 20))}px`);
    };

    updateLayoutVars();
    window.addEventListener('resize', updateLayoutVars);
    return () => window.removeEventListener('resize', updateLayoutVars);
  }, [activeTab]);

  useEffect(() => {
    const lastAssistant = [...codex.state.aiHistory].reverse().find((m) => m.role === 'assistant');
    const apply = lastAssistant?.meta?.apply;
    if (!apply || !apply.ok) return;
    const key = `${apply.snapshot_id ?? ''}:${lastAssistant?.ts ?? 0}`;
    if (key === lastAssistantApplyRef.current) return;
    lastAssistantApplyRef.current = key;
    if (apply.status) {
      setStatus(apply.status);
      initDraftsFromStatus(apply.status);
    }
    const artifacts = apply.artifacts ?? {};
    const sketchCandidate = artifacts.unified_main_file ?? artifacts.sketch_path;
    if (typeof sketchCandidate === 'string' && sketchCandidate) {
      void (async () => {
        try {
          const loaded = await firmwareReadSketch(sketchCandidate);
          setSketchPath(loaded.path);
          setSketchContent(loaded.content);
          const folder = loaded.path.replace(/\/[^/]+$/, '');
          setFwCfg((prev) => ({ ...prev, sketch: folder }));
        } catch {
          // Non-blocking: assistant message still carries path if read fails.
        }
      })();
    }
    const sections = Array.isArray(apply.applied) && apply.applied.length ? apply.applied.join(', ') : 'none';
    setMsg(`Assistant applied: ${sections}.`, 'codex.apply');
  }, [codex.state.aiHistory, initDraftsFromStatus, setFwCfg, setMsg, setSketchContent, setSketchPath]);

  return (
    <div className={`app-shell app-rebuild ${compactUi ? 'compact-ui' : ''}`}>
      <header className="topbar rebuild-topbar">
        <div>
          <h1>{strings.app.title} <span className="ui-build-chip">{strings.app.buildLabel}</span></h1>
        </div>
        <div className="topbar-actions">
          <button className={`badge overwatch-chip ${overwatchTone}`} onClick={() => setOverwatchOpen(true)}>
            OVERWATCH {overwatchLabel}
          </button>
          <div className={`badge ${health?.connected ? 'connected' : 'disconnected'}`}>
            {health?.connected ? strings.app.connected : strings.app.disconnected}
          </div>
        </div>
      </header>

      <main className="ops-layout" aria-label="Operations workspace">
        <aside className="ops-codex-rail" ref={codexRailRef}>
          <CodexPanel {...codexProps} />
        </aside>

        <section className="ops-main" aria-label="Main workspace">
          <div className="ops-tabs" role="tablist" aria-label="Primary app tabs">
            <button className={`btn-sm ${activeTab === 'setup' ? 'active' : ''}`} onClick={() => setActiveTab('setup')}>1_SETUP</button>
            <button className={`btn-sm ${activeTab === 'ide' ? 'active' : ''}`} onClick={() => setActiveTab('ide')}>2_IDE</button>
            <button className={`btn-sm ${activeTab === 'tune' ? 'active' : ''}`} onClick={() => setActiveTab('tune')}>3_TUNE</button>
          </div>

          {activeTab === 'setup' && (
            <div className="setup-view-grid">
              <section className="panel tool-panel" aria-label="Setup workflow">
                <ConnectPreflightPage
                  healthPort={health?.port}
                  mode={mode}
                  angle={status.ang}
                  estopLatched={control.estop_latched}
                  compatKnown={compatKnown}
                  compatOk={compatOk}
                  compat={compat}
                  connectProbe={connectProbe}
                  profileLabel={profileLabel}
                  setProfileLabel={setProfileLabel}
                  chassisClass={chassisClass}
                  setChassisClass={setChassisClass}
                  profiles={robotProfilesState.profiles}
                  robotProfile={activeRobotProfile ? { profile_id: activeRobotProfile.profile_id, label: activeRobotProfile.label, chassis: activeRobotProfile.chassis, updated_at: activeRobotProfile.updated_at, probe: activeRobotProfile.probe } : null}
                  runCompatProbe={runCompatProbe}
                  runConnectWizard={runConnectWizard}
                  runProfileValidation={runProfileValidation}
                  runOverwatchCheck={runOverwatchCheck}
                  activateProfileIfValid={activateProfileIfValid}
                  activateProfileByIdIfValid={activateProfileByIdIfValid}
                  loadProfileById={loadProfileById}
                  validation={validation}
                  overwatch={overwatch}
                  activeProfileId={robotProfilesState.active_profile_id}
                  generateFirmwareDocsPack={generateFirmwareDocsPack}
                  runGenerateUnified={runGenerateUnified}
                  onPasteSketch={applyPastedSketch}
                  sketchPrepared={Boolean(sketchContent.trim().length > 0)}
                  sketchRevision={sketchRevision}
                  loadAssistantPrompt={loadAssistantPrompt}
                  goToIde={() => setActiveTab('ide')}
                  goToTune={() => setActiveTab('tune')}
                  saveRobotProfile={() => { void saveRobotProfile(); }}
                  loadSavedRobotProfile={loadSavedRobotProfile}
                  exportRobotProfile={() => exportRobotProfile()}
                  exportProfileById={(profileId) => exportProfileById(profileId)}
                  importRobotProfile={importRobotProfile}
                  deleteSavedRobotProfile={() => { void deleteSavedRobotProfile(); }}
                  deleteProfileById={(profileId) => { void deleteProfileById(profileId); }}
                  refreshBridge={refreshBridge}
                />
              </section>
            </div>
          )}

          {activeTab === 'tune' && (
            <div className="tune-view-grid">
              <section className="panel tool-panel" aria-label="Calibration and tuning">
                <div className="tool-panel-head tune-head">
                  <div>
                    <h3>{strings.tune.title}</h3>
                    <span className="workflow-label">{strings.tune.subtitle}</span>
                  </div>
                </div>
                <div className="tool-panel-body">
                  <section className="firmware-pane">
                    <div className="telemetry-grid" aria-label="Calibration status">
                      <p className="telemetry-row">
                        <span className="telemetry-label">{strings.tune.mode}:</span>
                        <span className={`indicator-value telemetry-field ${modeTone} is-live`}>{mode}</span>
                      </p>
                      <p className="telemetry-row">
                        <span className="telemetry-label">{strings.tune.angle}:</span>
                        <span className={`indicator-value telemetry-field ${angleTone} is-live`}>{status.ang ?? 'n/a'}</span>
                      </p>
                      <p className="telemetry-row">
                        <span className="telemetry-label">{strings.tune.estop}:</span>
                        <span className={`indicator-value telemetry-field ${estopTone}`}>{control.estop_latched ? strings.status.latched : strings.status.clear}</span>
                      </p>
                      <p className="telemetry-row">
                        <span className="telemetry-label">{strings.tune.compat}:</span>
                        <span className={`indicator-value telemetry-field ${compatTone}`}>{compatKnown ? (compatOk ? strings.status.pass : strings.status.fail) : strings.status.untested}</span>
                      </p>
                    </div>

                    <div className="row">
                      <button className="btn-secondary btn-sm btn-intent-discover" onClick={() => void refreshBridge()}>{strings.tune.refresh}</button>
                      <button className="btn-secondary btn-sm btn-intent-discover btn-cal-zero" onClick={() => void runCompatProbe()}>{strings.tune.compatProbe}</button>
                      <button className="btn-secondary btn-sm" onClick={syncFromBot}>{strings.tune.syncFromBot}</button>
                    </div>

                    <div className={`burst-rig tone-${burstTone}`}>
                      <div className="burst-rig-head">
                        <span className="burst-rig-title">Burst Capture Rig</span>
                        <span className={`hud-pill ${burstTone}`}>{burstInfo?.state ?? 'idle'}</span>
                      </div>
                      <div className="row burst-controls-row">
                        <label>Burst Delay ms<input type="number" min={0} step={100} value={burstDelayMs} onChange={(e) => setBurstDelayMs(Math.max(0, Number(e.target.value) || 0))} /></label>
                        <label>Burst Lines<input type="number" min={1} step={10} value={burstLines} onChange={(e) => setBurstLines(Math.max(1, Number(e.target.value) || 1))} /></label>
                        <label>Burst Freq Hz<input type="number" min={1} max={100} step={0.5} value={burstFreqHz} onChange={(e) => setBurstFreqHz(Math.max(1, Math.min(100, Number(e.target.value) || 1)))} /></label>
                        <button className="btn-secondary btn-sm btn-intent-discover" disabled={control.estop_latched} onClick={() => void armBurstCapture()}>Queue Burst CSV</button>
                        <button className="btn-secondary btn-sm btn-intent-discover" onClick={() => void refreshBurstInfo()}>Burst Status</button>
                      </div>
                      <div className="burst-progress" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(burstProgressPct)}>
                        <span style={{ width: `${burstProgressPct}%` }} />
                      </div>
                      <p className="burst-rig-status">
                        {burstInfo
                          ? `host=${burstInfo.host_capture.state} (${burstRows}/${burstTarget}) @ ${(burstInfo.host_capture.freq_hz ?? burstFreqHz).toFixed(1)}Hz`
                          : 'host=n/a'}
                      </p>
                      {burstInfo?.last_event && (
                        <p className="burst-event-chip">{burstInfo.last_event}</p>
                      )}
                    </div>

                    <div className="action-rig arm-rig">
                      <div className="action-rig-head">
                        <span className="action-rig-title">Arm</span>
                      </div>
                      <div className="row action-rig-row">
                        <button className="btn-secondary btn-intent-safety btn-prepare-arm" disabled={control.estop_latched || !compatOk} onClick={async () => {
                          const c = await armPrepare();
                          setControl(c);
                          setArmAdvisory(null);
                          setMsg('Arm prepared. Press Confirm Arm to execute.');
                        }}>{strings.tune.prepareArm}</button>
                        <button className="btn-primary btn-lg btn-intent-safety" disabled={!control.arm_prepared || control.estop_latched} onClick={async () => {
                          try {
                            const r = await armConfirm();
                            setStatus(r.status);
                            setControl(r.control);
                            const modeAfter = String(r.status.mode ?? '');
                            const angAbs = Math.abs(n(r.status.ang, 0));
                            if (modeAfter === 'FAULT' || (modeAfter === 'SAFE_IDLE' && angAbs > 6.0)) {
                              setArmAdvisory('Arm was blocked by failsafe. Robot may not be zeroed/upright. Run Cal Zero and try again.');
                              setMsg('Arm blocked by failsafe');
                            } else {
                              setArmAdvisory(null);
                              setMsg('Arm confirmed');
                            }
                          } catch (e) {
                            setArmAdvisory('Arm command failed. If filtered angle is out of arming limits, re-zero with Cal Zero.');
                            setMsg(`arm confirm error: ${(e as Error).message}`);
                          }
                        }}>{strings.tune.confirmArm}</button>
                        <button className="btn-secondary btn-intent-safety btn-prepare-arm" onClick={async () => {
                          const r = await disarm();
                          setStatus(r.status);
                          if (r.control) setControl(r.control);
                          setMsg('Disarmed');
                        }}>{strings.tune.disarm}</button>
                      </div>
                      {armAdvisory && (
                        <div className="compat-box action-rig-advisory">
                          <p><strong>Arm Advisory:</strong> {armAdvisory}</p>
                        </div>
                      )}
                    </div>

                    <div className="action-rig estop-rig">
                      <div className="action-rig-head">
                        <span className="action-rig-title">Emergency Stop</span>
                      </div>
                      <div className="row action-rig-row">
                        <button
                          className={
                            control.estop_latched
                              ? 'btn-secondary btn-intent-safety btn-prepare-arm btn-estop-toggle'
                              : 'btn-danger btn-intent-safety btn-prepare-arm btn-estop-latch btn-estop-toggle'
                          }
                          onClick={async () => {
                            if (control.estop_latched) {
                              const r = await estopReset();
                              setStatus(r.status);
                              setControl(r.control);
                              setMsg('E-Stop reset');
                              return;
                            }
                            const r = await estopLatch();
                            setStatus(r.status);
                            setControl(r.control);
                            setMsg('E-Stop latched');
                          }}
                        >
                          {control.estop_latched ? strings.tune.estopReset : strings.tune.estopLatch}
                        </button>
                      </div>
                    </div>

                    <div className="action-rig config-rig">
                      <div className="action-rig-head">
                        <span className="action-rig-title">Configure</span>
                      </div>
                      <div className="row action-rig-row">
                        <button className="btn-secondary btn-intent-build" onClick={async () => {
                          await saveCfg();
                          setMsg('Config saved');
                        }}>{strings.tune.saveCfg}</button>
                        <button className="btn-secondary btn-intent-build" disabled={revertBusy} onClick={() => void revertLatestConfig()}>
                          {revertBusy ? 'Reverting...' : 'Revert Last Config'}
                        </button>
                        <button
                          className="btn-secondary btn-sm btn-intent-safety btn-cal-zero tune-cal-btn config-cal-zero-btn"
                          disabled={control.estop_latched}
                          onClick={async () => {
                            const r = await calZero();
                            setStatus(r.status);
                            if (r.control) setControl(r.control);
                            setMsg('CAL ZERO complete');
                          }}
                        >
                          {strings.tune.calZero}
                        </button>
                      </div>
                    </div>

                    <div className="tune-param-rigs">
                      <div className="action-rig tune-param-rig">
                        <div className="action-rig-head">
                          <span className="action-rig-title">PID</span>
                        </div>
                        <div className="grid3 tune-vars-grid">
                          <label className="tune-var-label">Kp<input className="tune-var-input" type="number" step="0.1" value={pid.kp} onChange={(e) => setPidDraft((p) => ({ ...p, kp: Number(e.target.value) }))} /></label>
                          <label className="tune-var-label">Ki<input className="tune-var-input" type="number" step="0.01" value={pid.ki} onChange={(e) => setPidDraft((p) => ({ ...p, ki: Number(e.target.value) }))} /></label>
                          <label className="tune-var-label">Kd<input className="tune-var-input" type="number" step="0.01" value={pid.kd} onChange={(e) => setPidDraft((p) => ({ ...p, kd: Number(e.target.value) }))} /></label>
                        </div>
                        <button className="btn-primary btn-lg btn-intent-apply tune-param-apply" disabled={control.estop_latched || !compatOk} onClick={() => void applyPid()}>{strings.tune.applyPid}</button>
                      </div>

                      <div className="action-rig tune-param-rig">
                        <div className="action-rig-head">
                          <span className="action-rig-title">Motion</span>
                        </div>
                        <div className="grid2 tune-vars-grid">
                          <label className="tune-var-label">Kv<input className="tune-var-input" type="number" step="0.001" value={motion.kv} onChange={(e) => setMotionDraft((m) => ({ ...m, kv: Number(e.target.value) }))} /></label>
                          <label className="tune-var-label">Kx<input className="tune-var-input" type="number" step="0.0001" value={motion.kx} onChange={(e) => setMotionDraft((m) => ({ ...m, kx: Number(e.target.value) }))} /></label>
                        </div>
                        <button className="btn-primary btn-lg btn-intent-apply tune-param-apply" disabled={control.estop_latched || !compatOk} onClick={() => void applyMotion()}>{strings.tune.applyMotion}</button>
                      </div>

                      <div className="action-rig tune-param-rig">
                        <div className="action-rig-head">
                          <span className="action-rig-title">Setpoint</span>
                        </div>
                        <div className="grid1 tune-vars-grid tune-vars-grid-single">
                          <label className="tune-var-label">{strings.tune.setpoint}<input className="tune-var-input" type="number" step="0.01" value={setpoint} onChange={(e) => setSetpointDraft(Number(e.target.value))} /></label>
                        </div>
                        <button className="btn-primary btn-lg btn-intent-apply tune-param-apply" disabled={control.estop_latched || !compatOk} onClick={() => void applySetpoint()}>{strings.tune.applySetpoint}</button>
                      </div>
                    </div>

                    {compat && (
                      <div className="compat-box">
                        <p><strong>Firmware ID:</strong> {compat.firmware_id ?? 'n/a'}</p>
                        <p><strong>Missing fields:</strong> {compat.missing_fields.length ? compat.missing_fields.join(', ') : 'none'}</p>
                        <p><strong>Warnings:</strong> {compat.warnings.length ? compat.warnings.join(' | ') : 'none'}</p>
                      </div>
                    )}
                  </section>
                </div>
              </section>

              <aside className="tune-hud-rail" aria-label="Live feed HUD rail">
                <section className="panel input-hud-panel" aria-label="Live input HUDs">
                  <div className="tool-panel-head">
                    <h3>{strings.hud.title}</h3>
                    <span className="workflow-label">{strings.hud.subtitle}</span>
                  </div>
                  <div className="input-hud-grid">
                    {hudMetrics.cards.map((card) => (
                      <article key={card.id} className="input-hud-card">
                        <span className="input-hud-label">{card.label}</span>
                        {(card.id === 'filteredAngle' || card.id === 'rawAngle') && (
                          <svg className="input-semi-dial" viewBox="0 0 40 28" role="img" aria-label={`${card.label} semicircle dial`}>
                            <path d={miniSemiTrackPath(14.5)} className="input-semi-dial-track" />
                            <line x1="20" y1="3.5" x2="20" y2="8.6" className="input-semi-dial-axis" />
                            <path
                              d={miniSemiFillPath(
                                14.5,
                                card.id === 'filteredAngle' ? hudMetrics.hud.angle : hudMetrics.hud.rawAngle,
                                Math.max(0, Math.min(1, Math.abs(card.id === 'filteredAngle' ? hudMetrics.hud.angle : hudMetrics.hud.rawAngle) / 90)),
                              )}
                              className={`input-semi-dial-fill ${card.id === 'filteredAngle' ? 'filtered' : 'raw'}`}
                            />
                          </svg>
                        )}
                        {card.id === 'gyroRate' && (
                          <div className="hud-bidir-slider" role="img" aria-label="Gyro rate bidirectional slider">
                            <span className="hud-bidir-center" />
                            {hudMetrics.gyroRate != null && (
                              <span
                                className={`hud-bidir-fill ${hudMetrics.gyroRate >= 0 ? 'pos' : 'neg'}`}
                                style={{ width: `${Math.max(0, Math.min(100, (Math.abs(hudMetrics.gyroRate) / 260) * 100))}%` }}
                              />
                            )}
                          </div>
                        )}
                        <strong className={`input-hud-value ${(card.id === 'filteredAngle' || card.id === 'rawAngle') ? 'angle-semi-value' : ''}`}>
                          {card.value}
                          {card.unit ? <small>{card.unit}</small> : null}
                        </strong>
                        {card.id === 'loopFeed' && (
                          <span className="loop-feed-stats">
                            status: {hudMetrics.loopFeedQuality} | avg 5m: {hudMetrics.loopFeedAvg5mHz != null ? hudMetrics.loopFeedAvg5mHz.toFixed(1) : 'n/a'} Hz | min 5m: {hudMetrics.loopFeedMin5mHz != null ? hudMetrics.loopFeedMin5mHz.toFixed(1) : 'n/a'} Hz
                          </span>
                        )}
                        {card.id === 'output' && (
                          <div className="output-session-stats">
                            <span className="output-session-stat">
                              <small>mean</small>
                              <strong>{hudMetrics.outputSessionMeanPct != null ? `${hudMetrics.outputSessionMeanPct.toFixed(0)}%` : 'n/a'}</strong>
                            </span>
                            <span className="output-session-stat">
                              <small>max</small>
                              <strong>{hudMetrics.outputSessionMaxPct != null ? `${hudMetrics.outputSessionMaxPct.toFixed(0)}%` : 'n/a'}</strong>
                            </span>
                          </div>
                        )}
                        {card.id === 'contract' && (
                          <span className="loop-feed-stats">
                            source decay: {hudMetrics.telemetryDecayMs != null ? `${hudMetrics.telemetryDecayMs.toFixed(0)} ms` : 'n/a'} | effective decay: {hudMetrics.perceivedDecayMs != null ? `${hudMetrics.perceivedDecayMs.toFixed(0)} ms` : 'n/a'}
                          </span>
                        )}
                        {card.id === 'output' && hudMetrics.outputAlertLevel === 'caution' && (
                          <span className="output-caution-text">CAUTION</span>
                        )}
                        <span className={`hud-pill ${card.tone}`}>
                          {card.id === 'output' && hudMetrics.outputAlertLevel === 'caution' ? 'caution' : card.tone}
                        </span>
                      </article>
                    ))}
                  </div>
                </section>

                <HudVisuals
                  show={true}
                  hud={{ angle: hudMetrics.hud.angle, rawAngle: hudMetrics.hud.rawAngle, output: hudMetrics.hud.output, voltageRaw: hudMetrics.hud.voltageRaw }}
                  angleDelta={hudMetrics.angleDelta}
                  outputDelta={hudMetrics.outputDelta}
                  angleDialPct={hudMetrics.angleDialPct}
                  rawAngleDialPct={hudMetrics.rawAngleDialPct}
                  outputDialPct={hudMetrics.outputDialPct}
                  voltageDialPct={hudMetrics.voltageDialPct}
                  chartPointsRaw={hudMetrics.chartPointsRaw}
                  chartPointsKf={hudMetrics.chartPointsKf}
                  chartPointsRef={hudMetrics.chartPointsRef}
                  imuHistory={imuHistory}
                  chartBounds={hudMetrics.chartBounds}
                />
              </aside>
            </div>
          )}

          {activeTab === 'ide' && (
            <div className="ide-view-grid">
              <WorkbenchPanel
                workbenchTab={workbenchTab}
                setWorkbenchTab={setWorkbenchTab}
                sketchPath={sketchPath}
                setSketchPath={setSketchPath}
                sketchContent={sketchContent}
                setSketchContent={setSketchContent}
                loadSketch={loadSketch}
                saveSketch={saveSketch}
                runFirmwareCheck={runFirmwareCheck}
                runFirmwareInstall={runFirmwareInstall}
                refreshBoards={refreshBoards}
                fw={fw}
                fwCheck={fwCheck}
                fwCfg={fwCfg}
                setFwCfg={setFwCfg}
                boardScan={boardScan}
                runFirmwareCompile={runFirmwareCompile}
                runFirmwareUpload={runFirmwareUpload}
                runFirmwareUploadGuarded={runFirmwareUploadGuarded}
                unifiedSketchName={unifiedSketchName}
                setUnifiedSketchName={setUnifiedSketchName}
                unifiedProfileJson={unifiedProfileJson}
                setUnifiedProfileJson={setUnifiedProfileJson}
                runGenerateUnified={runGenerateUnified}
                serialWrite={serialWrite}
                setSerialWrite={setSerialWrite}
                sendSerialLine={sendSerialLine}
                sendSerialCommand={sendSerialCommand}
                refreshLogs={refreshLogs}
                serialDiag={serialHealth}
                refreshSerialDiag={refreshSerialDiag}
                lines={lines}
                insertKalmanTemplate={insertKalmanTemplate}
                ideMode={true}
              />

              <section className="panel input-hud-panel input-hud-panel-compact" aria-label="Compact input HUDs">
                <div className="tool-panel-head">
                  <h3>{strings.hud.title}</h3>
                  <span className="workflow-label">{strings.ide.subtitle}</span>
                </div>
                <div className="input-hud-grid input-hud-grid-compact">
                  {hudMetrics.cards.map((card) => (
                    <article key={`${card.id}-compact`} className="input-hud-card">
                      <span className="input-hud-label">{card.label}</span>
                      {card.id === 'gyroRate' && (
                        <div className="hud-bidir-slider" role="img" aria-label="Gyro rate bidirectional slider">
                          <span className="hud-bidir-center" />
                          {hudMetrics.gyroRate != null && (
                            <span
                              className={`hud-bidir-fill ${hudMetrics.gyroRate >= 0 ? 'pos' : 'neg'}`}
                              style={{ width: `${Math.max(0, Math.min(100, (Math.abs(hudMetrics.gyroRate) / 260) * 100))}%` }}
                            />
                          )}
                        </div>
                      )}
                      <strong className="input-hud-value">
                        {card.value}
                        {card.unit ? <small>{card.unit}</small> : null}
                      </strong>
                      {card.id === 'loopFeed' && (
                        <span className="loop-feed-stats">
                          status: {hudMetrics.loopFeedQuality} | avg 5m: {hudMetrics.loopFeedAvg5mHz != null ? hudMetrics.loopFeedAvg5mHz.toFixed(1) : 'n/a'} Hz | min 5m: {hudMetrics.loopFeedMin5mHz != null ? hudMetrics.loopFeedMin5mHz.toFixed(1) : 'n/a'} Hz
                        </span>
                      )}
                      {card.id === 'output' && (
                        <div className="output-session-stats">
                          <span className="output-session-stat">
                            <small>mean</small>
                            <strong>{hudMetrics.outputSessionMeanPct != null ? `${hudMetrics.outputSessionMeanPct.toFixed(0)}%` : 'n/a'}</strong>
                          </span>
                          <span className="output-session-stat">
                            <small>max</small>
                            <strong>{hudMetrics.outputSessionMaxPct != null ? `${hudMetrics.outputSessionMaxPct.toFixed(0)}%` : 'n/a'}</strong>
                          </span>
                        </div>
                      )}
                      {card.id === 'contract' && (
                        <span className="loop-feed-stats">
                          source decay: {hudMetrics.telemetryDecayMs != null ? `${hudMetrics.telemetryDecayMs.toFixed(0)} ms` : 'n/a'} | effective decay: {hudMetrics.perceivedDecayMs != null ? `${hudMetrics.perceivedDecayMs.toFixed(0)} ms` : 'n/a'}
                        </span>
                      )}
                      {card.id === 'output' && hudMetrics.outputAlertLevel === 'caution' && (
                        <span className="output-caution-text">CAUTION</span>
                      )}
                    </article>
                  ))}
                </div>
              </section>
            </div>
          )}
        </section>
      </main>

      {preflightOpen && (
        <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="Guarded flash preflight checklist">
          <div className="preflight-modal">
            <h3>{strings.modal.title}</h3>
            <p className="wizard-subtitle">{strings.modal.subtitle}</p>
            <label className="check-item"><input type="checkbox" checked={preflightChecks.ide_closed} onChange={(e) => setPreflightChecks((p) => ({ ...p, ide_closed: e.target.checked }))} />{strings.modal.ideClosed}</label>
            <label className="check-item"><input type="checkbox" checked={preflightChecks.bot_safe} onChange={(e) => setPreflightChecks((p) => ({ ...p, bot_safe: e.target.checked }))} />{strings.modal.botSafe}</label>
            <label className="check-item"><input type="checkbox" checked={preflightChecks.correct_port} onChange={(e) => setPreflightChecks((p) => ({ ...p, correct_port: e.target.checked }))} />{strings.modal.portCorrectPrefix} ({fwCfg.port || 'not set'})</label>
            <label className="check-item"><input type="checkbox" checked={preflightChecks.power_expected} onChange={(e) => setPreflightChecks((p) => ({ ...p, power_expected: e.target.checked }))} />{strings.modal.powerExpected}</label>
            <div className="row">
              <button className="btn-secondary" onClick={() => setPreflightOpen(false)}>{strings.modal.cancel}</button>
              <button className="btn-primary btn-lg" disabled={!Object.values(preflightChecks).every(Boolean) || fw.running} onClick={() => void executeGuardedFlash()}>{strings.modal.start}</button>
            </div>
          </div>
        </div>
      )}

      {overwatchOpen && (
        <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="Overwatch integrity diagnostics" onClick={() => setOverwatchOpen(false)}>
          <div className="preflight-modal overwatch-modal" onClick={(e) => e.stopPropagation()}>
            <div className="firmware-docs-head">
              <h3>Overwatch Diagnostics</h3>
              <button className="firmware-docs-close" aria-label="Close Overwatch diagnostics" onClick={() => setOverwatchOpen(false)}>
                ×
              </button>
            </div>
            <p className="wizard-subtitle">
              Persistent integrity monitor across sketch, docs, contracts, telemetry, and deployment readiness.
            </p>
            <div className="overwatch-summary-row">
              <span className={`hud-pill ${overwatchTone}`}>{overwatch ? String(overwatchEffective.overall).toUpperCase() : 'PENDING'}</span>
              <span>Score: {overwatch ? `${overwatchEffective.score_pct}%` : 'n/a'}</span>
              <span>Checks: {overwatch ? `${overwatchEffective.pass}/${overwatchEffective.warn}/${overwatchEffective.fail}` : 'n/a'}</span>
              <span>Accepted: {overwatch ? overwatchEffective.accepted : 0}</span>
              <span>Updated: {overwatch ? new Date(overwatch.generated_at * 1000).toLocaleTimeString() : 'n/a'}</span>
            </div>
            <div className="overwatch-checks-list">
              {(overwatch?.checks ?? []).map((c) => (
                <article key={c.id} className={`overwatch-check-item ${c.status}`}>
                  <div className="overwatch-check-head">
                    <strong>{c.label}</strong>
                    <span className={`hud-pill ${acceptedOverwatchChecks[c.id] ? 'unknown' : (c.status === 'pass' ? 'good' : c.status === 'warn' ? 'warn' : 'bad')}`}>
                      {acceptedOverwatchChecks[c.id] ? 'ACCEPTED' : c.status.toUpperCase()}
                    </span>
                  </div>
                  <p>{c.detail}</p>
                  {c.evidence ? <p className="overwatch-evidence"><code>{c.evidence}</code></p> : null}
                  {c.status !== 'pass' && (
                    <div className="overwatch-check-actions">
                      {acceptedOverwatchChecks[c.id] ? (
                        <button className="btn-secondary btn-sm" onClick={() => restoreOverwatchCheck(c.id)}>
                          Bring Back Into Consideration
                        </button>
                      ) : (
                        <button className="btn-secondary btn-sm" onClick={() => acceptOverwatchCheck(c.id)}>
                          Accept Deficiency
                        </button>
                      )}
                    </div>
                  )}
                </article>
              ))}
              {!overwatch && <p className="wizard-subtitle">No report yet. Run diagnostics.</p>}
            </div>
            <div className="row">
              <button className="btn-secondary btn-sm btn-intent-discover" onClick={() => void runOverwatchCheck()}>
                Run Diagnostics
              </button>
              <button className="btn-secondary btn-sm" onClick={() => setOverwatchOpen(false)}>
                Close
              </button>
            </div>
            {overwatchDiagNote && <p className="setup-rig-test-note">{overwatchDiagNote}</p>}
          </div>
        </div>
      )}

      <input
        ref={profileImportRef}
        type="file"
        accept="application/json"
        className="profile-import-input"
        onChange={(e) => { void onProfileImportFile(e); }}
      />

      <footer className="statusbar" ref={statusbarRef}>
        <div className="statusbar-meta">
          <span>{statusMsg}</span>
          <span>State: {mode}</span>
          <span>Angle: {status.ang ?? 'n/a'}</span>
          <span>E-Stop: {control.estop_latched ? strings.status.latched : strings.status.clear}</span>
        </div>
        <GlobalAlertRail
          active={alertsActive}
          activeTotal={alertsAllActive.length}
          history={alertsHistory}
          filter={alertsFilter}
          onDismiss={dismissAlert}
          onClearNonError={clearNonErrorAlerts}
          onClearAll={clearAllAlerts}
          onClearHistory={clearAlertHistory}
          onSetFilter={setAlertsFilter}
        />
      </footer>
    </div>
  );
}
