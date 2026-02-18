import { useEffect, useMemo, useRef, useState } from 'react';
import Editor from '@monaco-editor/react';
import {
  authDeleteOpenAiKey,
  authLogin,
  authLogout,
  authMe,
  authOpenAiStatus,
  authRegister,
  authSetOpenAiKey,
  armConfirm,
  armPrepare,
  calZero,
  disarm,
  estopLatch,
  estopReset,
  heartbeat,
  getHealth,
  getLines,
  getStatus,
  commissioningArtifacts,
  commissioningRun,
  commissioningStatus,
  firmwareCheck,
  firmwareBoards,
  firmwareCompile,
  firmwareInstallCli,
  firmwareReadSketch,
  aiChat,
  aiStatus,
  firmwareStatus,
  firmwareUpload,
  firmwareUploadGuarded,
  firmwareWriteSketch,
  saveCfg,
  setMotion,
  setPid,
  setSetpoint,
  postCommand,
  probeCompat,
  probeConnect,
  setSessionToken,
} from './api';
import type {
  AiHistoryItem,
  AiStatus,
  AuthUser,
  CompatReport,
  ConnectProbeReport,
  FirmwareBoards,
  FirmwareCheck,
  FirmwareStatus,
} from './api';
import type { ControlState, Health, Status } from './types';

type Tab = 'connect' | 'control' | 'tuning' | 'commissioning' | 'logs';
type WorkbenchTab = 'sketch' | 'board' | 'serial' | 'codex';

type Checkpoint = {
  id: string;
  ts: number;
  rating: 'poor' | 'ok' | 'good' | 'great';
  mode: string;
  angle: number;
  wpos: number;
  pid: { kp: number; ki: number; kd: number };
  motion: { kv: number; kx: number };
  setpoint: number;
};

type RobotProfile = {
  label: string;
  chassis: string;
  updated_at: number;
  probe: ConnectProbeReport;
};

const CHECKPOINT_KEY = 'upright_ops_checkpoints_v1';
const ROBOT_PROFILE_KEY = 'upright_ops_robot_profile_v1';
const AUTH_SESSION_KEY = 'upright_ops_session_token_v1';
const CHECKPOINT_MAX = 6;

const BAL_BOUNDS = {
  kp: 1.0,
  ki: 0.05,
  kd: 0.2,
  kv: 0.05,
  kx: 0.002,
  setpoint: 0.5,
};

const HISTORY_MAX = 180;
const UI_BUILD = 'HUD-V5-LAYOUT';
const TAB_FLOW: Array<{ id: Tab; step: string; label: string }> = [
  { id: 'connect', step: '01', label: 'Connect' },
  { id: 'control', step: '02', label: 'Control' },
  { id: 'tuning', step: '03', label: 'Tuning' },
  { id: 'commissioning', step: '04', label: 'Commission' },
  { id: 'logs', step: '05', label: 'Logs' },
];

type ImuSample = {
  t: number;
  kf: number;
  raw: number;
  gyro: number;
  out: number;
};

type UiAlert = {
  id: string;
  tone: 'error' | 'warn' | 'ok' | 'info';
  text: string;
  ts: number;
};

function n(v: string | undefined, fallback = 0): number {
  const parsed = Number.parseFloat(v ?? '');
  return Number.isFinite(parsed) ? parsed : fallback;
}

function clamp(v: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, v));
}

function seriesPoints(samples: ImuSample[], pick: (s: ImuSample) => number, minY: number, maxY: number): string {
  if (samples.length <= 1) return '';
  const w = 820;
  const h = 160;
  const span = Math.max(0.0001, maxY - minY);
  return samples
    .map((sample, i) => {
      const x = (i / (samples.length - 1)) * w;
      const yNorm = (pick(sample) - minY) / span;
      const y = h - yNorm * h;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(' ');
}

function loadCheckpoints(): Checkpoint[] {
  try {
    const raw = localStorage.getItem(CHECKPOINT_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as Checkpoint[];
    if (!Array.isArray(parsed)) return [];
    return parsed.slice(0, CHECKPOINT_MAX);
  } catch {
    return [];
  }
}

function loadRobotProfile(): RobotProfile | null {
  try {
    const raw = localStorage.getItem(ROBOT_PROFILE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as RobotProfile;
    if (!parsed || typeof parsed !== 'object' || !parsed.probe) return null;
    return parsed;
  } catch {
    return null;
  }
}

function parseRobotProfile(text: string): RobotProfile | null {
  try {
    const parsed = JSON.parse(text) as RobotProfile;
    if (!parsed || typeof parsed !== 'object' || !parsed.probe) return null;
    if (typeof parsed.label !== 'string' || typeof parsed.chassis !== 'string') return null;
    return parsed;
  } catch {
    return null;
  }
}

export default function App() {
  const [tab, setTab] = useState<Tab>('connect');
  const [health, setHealth] = useState<Health | null>(null);
  const [status, setStatus] = useState<Status>({});
  const [control, setControl] = useState<ControlState>({ arm_prepared: false, estop_latched: false });
  const [lines, setLines] = useState<string[]>([]);
  const [msg, setMsgState] = useState<string>('');
  const [uiAlerts, setUiAlerts] = useState<UiAlert[]>([]);


  const [pid, setPidDraft] = useState({ kp: 31, ki: 0.05, kd: 1.05 });
  const [motion, setMotionDraft] = useState({ kv: 0, kx: 0 });
  const [setpoint, setSetpointDraft] = useState(0);
  const [checkpoints, setCheckpoints] = useState<Checkpoint[]>(() => loadCheckpoints());
  const [connectProbe, setConnectProbe] = useState<ConnectProbeReport | null>(null);
  const [robotProfile, setRobotProfile] = useState<RobotProfile | null>(() => loadRobotProfile());
  const [profileLabel, setProfileLabel] = useState('My Robot');
  const [chassisClass, setChassisClass] = useState('2wd_inverted_pendulum');

  const [comm, setComm] = useState<{ state: string; running: boolean; returncode: number | null; log_tail: string[] }>({
    state: 'idle',
    running: false,
    returncode: null,
    log_tail: [],
  });
  const [commArtifacts, setCommArtifacts] = useState<{ latest_metrics: string | null; latest_run: string | null }>({
    latest_metrics: null,
    latest_run: null,
  });
  const [fw, setFw] = useState<FirmwareStatus>({
    state: 'idle',
    phase: 'none',
    running: false,
    started_at: null,
    finished_at: null,
    returncode: null,
    last_cmd: [],
    log_tail: [],
    defaults: { sketch: '', fqbn: 'arduino:avr:nano', port: '' },
  });
  const [fwCheck, setFwCheck] = useState<FirmwareCheck | null>(null);
  const [fwCfg, setFwCfg] = useState<{ sketch: string; fqbn: string; port: string }>({
    sketch: '',
    fqbn: 'arduino:avr:nano',
    port: '',
  });
  const [workbenchOpen, setWorkbenchOpen] = useState(true);
  const [workbenchTab, setWorkbenchTab] = useState<WorkbenchTab>('board');
  const [boardScan, setBoardScan] = useState<FirmwareBoards | null>(null);
  const [sketchPath, setSketchPath] = useState('');
  const [sketchContent, setSketchContent] = useState('');
  const [serialWrite, setSerialWrite] = useState('');
  const [ai, setAi] = useState<AiStatus>({ configured: false, model: 'unknown', history_len: 0 });
  const [aiHistory, setAiHistory] = useState<AiHistoryItem[]>([]);
  const [aiInput, setAiInput] = useState('');
  const [aiBusy, setAiBusy] = useState(false);
  const [authMode, setAuthMode] = useState<'login' | 'register'>('login');
  const [authBusy, setAuthBusy] = useState(false);
  const [authEmail, setAuthEmail] = useState('');
  const [authPassword, setAuthPassword] = useState('');
  const [authAlert, setAuthAlert] = useState<{ tone: 'error' | 'ok'; text: string } | null>(null);
  const [authUser, setAuthUser] = useState<AuthUser | null>(null);
  const [openAiKeyInput, setOpenAiKeyInput] = useState('');
  const [openAiModelInput, setOpenAiModelInput] = useState('gpt-5-mini');
  const [preflightOpen, setPreflightOpen] = useState(false);
  const [preflightChecks, setPreflightChecks] = useState({
    ide_closed: false,
    bot_safe: false,
    correct_port: false,
    power_expected: false,
  });
  const [imuHistory, setImuHistory] = useState<ImuSample[]>([]);
  const [compat, setCompat] = useState<CompatReport | null>(null);

  const draftsInitializedRef = useRef(false);
  const compatRequestedRef = useRef(false);
  const lastMsgRef = useRef<{ text: string; at: number }>({ text: '', at: 0 });

  const setMsg = (text: string) => {
    const now = Date.now();
    if (text === lastMsgRef.current.text && now - lastMsgRef.current.at < 1500) return;
    lastMsgRef.current = { text, at: now };
    setMsgState(text);
  };

  const mode = status.mode ?? 'UNKNOWN';
  const balancing = mode === 'BALANCING';
  const compatOk = compat?.ok === true;
  const compatKnown = compat !== null;

  useEffect(() => {
    if (!msg) return;
    const lower = msg.toLowerCase();
    const tone: UiAlert['tone'] =
      /(error|failed|cannot|invalid|missing|blocked|denied|unknown|latched)/.test(lower) ? 'error' :
      /(warn|risk|watch)/.test(lower) ? 'warn' :
      /(ok|pass|saved|loaded|applied|prepared|confirmed|complete|detected|found|synced|removed|deleted|imported|copied|refreshed|started|logged)/.test(lower) ? 'ok' :
      'info';

    const next: UiAlert = {
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      tone,
      text: msg,
      ts: Date.now(),
    };
    setUiAlerts((prev) => [next, ...prev].slice(0, 8));
  }, [msg]);

  const dismissAlert = (id: string) => {
    setUiAlerts((prev) => prev.filter((a) => a.id !== id));
  };

  const persistCheckpoints = (next: Checkpoint[]) => {
    const clipped = next.slice(0, CHECKPOINT_MAX);
    setCheckpoints(clipped);
    localStorage.setItem(CHECKPOINT_KEY, JSON.stringify(clipped));
  };

  const syncFromBot = () => {
    setPidDraft({ kp: n(status.kp, 31), ki: n(status.ki, 0.05), kd: n(status.kd, 1.05) });
    setMotionDraft({ kv: n(status.kv, 0), kx: n(status.kx, 0) });
    setSetpointDraft(n(status.set, 0));
    setMsg('Drafts synced from bot status');
  };

  const makeCheckpoint = (rating: Checkpoint['rating']) => {
    const cp: Checkpoint = {
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      ts: Date.now(),
      rating,
      mode,
      angle: n(status.ang, 0),
      wpos: n(status.wpos, 0),
      pid: { ...pid },
      motion: { ...motion },
      setpoint,
    };
    persistCheckpoints([cp, ...checkpoints]);
    setMsg(`Checkpoint saved (${rating})`);
  };

  const restoreDraftFromCheckpoint = (cp: Checkpoint) => {
    setPidDraft({ ...cp.pid });
    setMotionDraft({ ...cp.motion });
    setSetpointDraft(cp.setpoint);
    setMsg('Checkpoint loaded to drafts');
  };

  const applyCheckpointToBot = async (cp: Checkpoint, save = false) => {
    if (control.estop_latched) {
      setMsg('Cannot apply checkpoint while E-Stop is latched');
      return;
    }
    const r1 = await setPid(cp.pid.kp, cp.pid.ki, cp.pid.kd);
    if (r1.control) setControl(r1.control);
    const r2 = await setMotion(cp.motion.kv, cp.motion.kx);
    if (r2.control) setControl(r2.control);
    const r3 = await setSetpoint(cp.setpoint);
    setStatus(r3.status);
    if (r3.control) setControl(r3.control);
    if (save) await saveCfg();
    restoreDraftFromCheckpoint(cp);
    setMsg(save ? 'Checkpoint applied and saved to bot' : 'Checkpoint applied to bot');
  };

  const deleteCheckpoint = (id: string) => {
    persistCheckpoints(checkpoints.filter((c) => c.id !== id));
    setMsg('Checkpoint deleted');
  };

  const runCompatProbe = async () => {
    try {
      const r = await probeCompat();
      setCompat(r);
      setMsg(r.ok ? 'Compatibility probe passed' : 'Compatibility probe failed');
    } catch (e) {
      setMsg(`compat probe error: ${(e as Error).message}`);
    }
  };

  const runConnectWizard = async () => {
    try {
      const r = await probeConnect();
      setConnectProbe(r);
      if (r.compat) setCompat(r.compat);
      setMsg(
        r.ok
          ? `Connect probe passed (${r.confidence_pct}% confidence)`
          : `Connect probe incomplete (${r.confidence_pct}% confidence)`
      );
    } catch (e) {
      setMsg(`connect probe error: ${(e as Error).message}`);
    }
  };

  const saveRobotProfile = () => {
    if (!connectProbe) {
      setMsg('Run connect probe first');
      return;
    }
    const next: RobotProfile = {
      label: profileLabel.trim() || 'My Robot',
      chassis: chassisClass,
      updated_at: Date.now(),
      probe: connectProbe,
    };
    localStorage.setItem(ROBOT_PROFILE_KEY, JSON.stringify(next));
    setRobotProfile(next);
    setProfileLabel(next.label);
    setChassisClass(next.chassis);
    setMsg('Robot profile saved locally');
  };

  const loadSavedRobotProfile = () => {
    const loaded = loadRobotProfile();
    if (!loaded) {
      setMsg('No saved local profile found');
      return;
    }
    setRobotProfile(loaded);
    setConnectProbe(loaded.probe);
    setProfileLabel(loaded.label);
    setChassisClass(loaded.chassis);
    if (loaded.probe.compat) setCompat(loaded.probe.compat);
    setMsg(`Loaded local profile: ${loaded.label}`);
  };

  const deleteSavedRobotProfile = () => {
    localStorage.removeItem(ROBOT_PROFILE_KEY);
    setRobotProfile(null);
    setMsg('Deleted local profile');
  };

  const exportRobotProfile = async () => {
    const active = robotProfile ?? (connectProbe
      ? {
          label: profileLabel.trim() || 'My Robot',
          chassis: chassisClass,
          updated_at: Date.now(),
          probe: connectProbe,
        }
      : null);

    if (!active) {
      setMsg('Nothing to export yet');
      return;
    }

    const payload = JSON.stringify(active, null, 2);
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(payload);
        setMsg('Profile JSON copied to clipboard');
      } else {
        setMsg('Clipboard unavailable; use Import/Export prompt instead');
      }
    } catch {
      setMsg('Clipboard write failed; use Import/Export prompt instead');
    }
  };

  const importRobotProfile = () => {
    const raw = window.prompt('Paste Robot Profile JSON');
    if (!raw) return;
    const parsed = parseRobotProfile(raw);
    if (!parsed) {
      setMsg('Invalid profile JSON');
      return;
    }
    localStorage.setItem(ROBOT_PROFILE_KEY, JSON.stringify(parsed));
    setRobotProfile(parsed);
    setConnectProbe(parsed.probe);
    setProfileLabel(parsed.label);
    setChassisClass(parsed.chassis);
    if (parsed.probe.compat) setCompat(parsed.probe.compat);
    setMsg(`Imported profile: ${parsed.label}`);
  };

  const runFirmwareCheck = async () => {
    try {
      const r = await firmwareCheck();
      setFwCheck(r);
      setMsg(r.ok ? 'Arduino CLI detected' : `Arduino CLI check failed: ${r.error ?? 'unknown error'}`);
    } catch (e) {
      setMsg(`firmware check error: ${(e as Error).message}`);
    }
  };

  const runFirmwareInstall = async () => {
    try {
      const st = await firmwareInstallCli();
      setFw(st);
      setMsg('Arduino CLI install started');
    } catch (e) {
      setMsg(`install error: ${(e as Error).message}`);
    }
  };

  const runFirmwareCompile = async () => {
    try {
      const st = await firmwareCompile(fwCfg.sketch || undefined, fwCfg.fqbn || undefined);
      setFw(st);
      setMsg('Firmware compile started');
    } catch (e) {
      setMsg(`compile error: ${(e as Error).message}`);
    }
  };

  const runFirmwareUpload = async () => {
    try {
      const st = await firmwareUpload(
        fwCfg.sketch || undefined,
        fwCfg.fqbn || undefined,
        fwCfg.port || undefined,
      );
      setFw(st);
      setMsg('Firmware upload started');
    } catch (e) {
      setMsg(`upload error: ${(e as Error).message}`);
    }
  };

  const runFirmwareUploadGuarded = async () => {
    setPreflightOpen(true);
  };

  const executeGuardedFlash = async () => {
    try {
      const st = await firmwareUploadGuarded(
        fwCfg.sketch || undefined,
        fwCfg.fqbn || undefined,
        fwCfg.port || undefined,
      );
      setFw(st);
      setPreflightOpen(false);
      setPreflightChecks({
        ide_closed: false,
        bot_safe: false,
        correct_port: false,
        power_expected: false,
      });
      setMsg('Guarded flash started');
    } catch (e) {
      setMsg(`guarded flash error: ${(e as Error).message}`);
    }
  };

  const refreshBoards = async () => {
    try {
      const b = await firmwareBoards();
      setBoardScan(b);
      if (b.ok && b.ports.length > 0) {
        const first = b.ports[0];
        setFwCfg((prev) => ({
          sketch: prev.sketch,
          fqbn: b.recommended_fqbn || prev.fqbn || first.fqbn || 'arduino:avr:nano',
          port: b.recommended_port || prev.port || first.address || '',
        }));
      }
      setMsg(b.ok ? `Found ${b.ports.length} serial port(s)` : `Board scan failed: ${b.error ?? 'unknown error'}`);
    } catch (e) {
      setMsg(`board scan error: ${(e as Error).message}`);
    }
  };

  const loadSketch = async () => {
    try {
      const sk = await firmwareReadSketch(sketchPath || undefined);
      setSketchPath(sk.path);
      setSketchContent(sk.content);
      setMsg(`Sketch loaded: ${sk.path}`);
    } catch (e) {
      setMsg(`sketch load error: ${(e as Error).message}`);
    }
  };

  const saveSketch = async () => {
    try {
      const out = await firmwareWriteSketch(sketchContent, sketchPath || undefined);
      setSketchPath(out.path);
      setMsg(`Sketch saved (${out.bytes} bytes)`);
    } catch (e) {
      setMsg(`sketch save error: ${(e as Error).message}`);
    }
  };

  const sendSerialLine = async () => {
    const cmd = serialWrite.trim();
    if (!cmd) return;
    try {
      await postCommand(cmd);
      setSerialWrite('');
      setMsg(`Sent: ${cmd}`);
      await refreshLogs();
    } catch (e) {
      setMsg(`serial send error: ${(e as Error).message}`);
    }
  };

  const sendAi = async () => {
    const message = aiInput.trim();
    if (!message || aiBusy) return;
    setAiBusy(true);
    try {
      const out = await aiChat(message);
      setAi(out.ai);
      setAiHistory(out.history);
      setAiInput('');
    } catch (e) {
      const raw = (e as Error).message;
      const mapped = raw.includes('openai_tls_cert_verify_failed')
        ? 'OpenAI TLS certificate verification failed on this machine. Install/update system Python certificates (certifi).'
        : raw;
      setAuthAlert({ tone: 'error', text: mapped });
      setMsg(`codex chat error: ${mapped}`);
    } finally {
      setAiBusy(false);
    }
  };

  const applySession = (token: string | null) => {
    setSessionToken(token);
    if (token) localStorage.setItem(AUTH_SESSION_KEY, token);
    else localStorage.removeItem(AUTH_SESSION_KEY);
  };

  const submitAuth = async () => {
    const email = authEmail.trim();
    const password = authPassword;
    if (!email || !password) {
      setAuthAlert({ tone: 'error', text: 'Email and password are required.' });
      setMsg('Email and password required');
      return;
    }
    setAuthAlert(null);
    setAuthBusy(true);
    try {
      const out = authMode === 'register' ? await authRegister(email, password) : await authLogin(email, password);
      applySession(out.session_token);
      setAuthUser(out.user);
      setAuthAlert({ tone: 'ok', text: `${authMode === 'register' ? 'Account created' : 'Login successful'}.` });
      setMsg(`${authMode === 'register' ? 'Registered' : 'Logged in'} as ${out.user.email}`);
    } catch (e) {
      const raw = (e as Error).message;
      const mapped =
        raw.includes('invalid_credentials') ? 'Wrong email or password.' :
        raw.includes('weak_password') ? 'Password must be at least 8 characters.' :
        raw.includes('email_exists') ? 'That email is already registered.' :
        raw.includes('invalid_email') ? 'Please enter a valid email address.' :
        raw.includes('unauthenticated') ? 'You are not authenticated.' :
        raw;
      setAuthAlert({ tone: 'error', text: mapped });
      setMsg(`auth error: ${mapped}`);
    } finally {
      setAuthBusy(false);
    }
  };

  const runLogout = async () => {
    try {
      await authLogout();
    } catch {
      // best-effort
    }
    applySession(null);
    setAuthUser(null);
    setAuthAlert({ tone: 'ok', text: 'Logged out.' });
    setAi({ configured: false, model: 'unknown', history_len: 0 });
    setAiHistory([]);
    setMsg('Logged out');
  };

  const saveUserOpenAiKey = async () => {
    const k = openAiKeyInput.trim();
    if (!k) {
      setMsg('API key required');
      return;
    }
    try {
      const out = await authSetOpenAiKey(k, openAiModelInput || 'gpt-5-mini');
      setAuthUser((u) => (u ? { ...u, openai_configured: out.configured, openai_model: out.model } : u));
      setOpenAiKeyInput('');
      setAuthAlert({ tone: 'ok', text: `OpenAI key synced. Model: ${out.model}` });
      try {
        const st = await aiStatus();
        setAi(st.ai);
        setAiHistory(st.history);
      } catch {
        // best effort refresh
      }
      setMsg('OpenAI key saved for this user');
    } catch (e) {
      const raw = (e as Error).message;
      const mapped =
        raw.includes('invalid_openai_key') ? 'OpenAI key is invalid.' :
        raw.includes('unauthenticated') ? 'Please login first.' :
        raw.includes('missing') ? 'OpenAI key is required.' :
        raw;
      setAuthAlert({ tone: 'error', text: mapped });
      setMsg(`save key error: ${mapped}`);
    }
  };

  const clearUserOpenAiKey = async () => {
    try {
      const out = await authDeleteOpenAiKey();
      setAuthUser((u) => (u ? { ...u, openai_configured: out.configured, openai_model: out.model } : u));
      setAuthAlert({ tone: 'ok', text: 'OpenAI key removed for this account.' });
      setAi({ configured: false, model: 'unknown', history_len: 0 });
      setAiHistory([]);
      setMsg('OpenAI key removed for this user');
    } catch (e) {
      const raw = (e as Error).message;
      const mapped = raw.includes('unauthenticated') ? 'Please login first.' : raw;
      setAuthAlert({ tone: 'error', text: mapped });
      setMsg(`delete key error: ${mapped}`);
    }
  };

  useEffect(() => {
    let mounted = true;

    const tick = async () => {
      try {
        const [h, s, hb] = await Promise.all([getHealth(), getStatus(), heartbeat()]);
        if (!mounted) return;
        setHealth(h.health);
        if (h.control) setControl(h.control);
        setControl(hb);
        setStatus(s.status);
        setImuHistory((prev) => {
          const next = [...prev, {
            t: Date.now(),
            kf: n(s.status.ang, 0),
            raw: n(s.status.raw, 0),
            gyro: n(s.status.gyro ?? s.status.gyr ?? s.status.gx, 0),
            out: n(s.status.out, 0),
          }];
          if (next.length > HISTORY_MAX) next.splice(0, next.length - HISTORY_MAX);
          return next;
        });
        if (s.control) setControl(s.control);
        if (!draftsInitializedRef.current) {
          setPidDraft({ kp: n(s.status.kp, 31), ki: n(s.status.ki, 0.05), kd: n(s.status.kd, 1.05) });
          setMotionDraft({ kv: n(s.status.kv, 0), kx: n(s.status.kx, 0) });
          setSetpointDraft(n(s.status.set, 0));
          draftsInitializedRef.current = true;
        }
        if (!compatRequestedRef.current) {
          compatRequestedRef.current = true;
          void runCompatProbe();
        }
      } catch (e) {
        if (!mounted) return;
        setMsg(`bridge error: ${(e as Error).message}`);
      }
    };

    void tick();
    const id = setInterval(() => {
      void tick();
    }, 250);

    return () => {
      mounted = false;
      clearInterval(id);
    };
  }, []);

  useEffect(() => {
    if (!workbenchOpen) return;
    if (!sketchContent) {
      void loadSketch();
    }
    if (!boardScan) {
      void refreshBoards();
    }
    // Intentionally one-way bootstrap when workbench is first opened.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workbenchOpen]);

  useEffect(() => {
    const tok = localStorage.getItem(AUTH_SESSION_KEY);
    if (!tok) return;
    applySession(tok);
    void (async () => {
      try {
        const me = await authMe();
        setAuthUser(me);
        const oa = await authOpenAiStatus();
        setAuthUser((u) => (u ? { ...u, openai_configured: oa.configured, openai_model: oa.model } : u));
        if (oa.model) setOpenAiModelInput(oa.model);
      } catch {
        applySession(null);
        setAuthUser(null);
      }
    })();
    // bootstrap once
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!authUser) {
      setAi({ configured: false, model: 'unknown', history_len: 0 });
      setAiHistory([]);
      return;
    }
    let mounted = true;
    const tickAi = async () => {
      try {
        const st = await aiStatus();
        if (!mounted) return;
        setAi(st.ai);
        setAiHistory(st.history);
      } catch {
        // AI may be unconfigured.
      }
    };
    void tickAi();
    const id = setInterval(() => void tickAi(), 3000);
    return () => {
      mounted = false;
      clearInterval(id);
    };
  }, [authUser]);

  useEffect(() => {
    let mounted = true;
    const tickComm = async () => {
      try {
        const [st, art, fst] = await Promise.all([commissioningStatus(), commissioningArtifacts(), firmwareStatus()]);
        if (!mounted) return;
        setComm({ state: st.state, running: st.running, returncode: st.returncode, log_tail: st.log_tail ?? [] });
        setCommArtifacts({ latest_metrics: art.latest_metrics, latest_run: art.latest_run });
        setFw(fst);
        setFwCfg((prev) => ({
          sketch: prev.sketch || fst.defaults.sketch || '',
          fqbn: prev.fqbn || fst.defaults.fqbn || 'arduino:avr:nano',
          port: prev.port || fst.defaults.port || '',
        }));
      } catch {
        // ignore commissioning polling errors in base control loop
      }
    };
    void tickComm();
    const id = setInterval(() => void tickComm(), 1000);
    return () => {
      mounted = false;
      clearInterval(id);
    };
  }, []);

  const healthBadge = useMemo(() => {
    if (!health) return 'unknown';
    return health.connected ? 'connected' : 'disconnected';
  }, [health]);

  const hud = useMemo(() => {
    const angle = n(status.ang, 0);
    const output = n(status.out, 0);
    const voltageRaw = n(status.volRaw, 0);
    const heartbeatAge = control.heartbeat_age_s ?? null;
    const heartbeatState =
      heartbeatAge == null ? 'unknown' : heartbeatAge <= 1.0 ? 'good' : heartbeatAge <= 2.0 ? 'warn' : 'bad';

    return {
      mode,
      angle,
      output,
      voltageRaw,
      setpoint: n(status.set, 0),
      kp: n(status.kp, 0),
      ki: n(status.ki, 0),
      kd: n(status.kd, 0),
      wspd: n(status.wspd, 0),
      wpos: n(status.wpos, 0),
      estop: control.estop_latched,
      armPrepared: control.arm_prepared,
      heartbeatAge,
      heartbeatState,
      connected: healthBadge === 'connected',
    };
  }, [control.arm_prepared, control.estop_latched, control.heartbeat_age_s, healthBadge, mode, status]);


  const chartBounds = useMemo(() => {
    if (imuHistory.length === 0) return { min: -10, max: 10 };
    const maxAbs = Math.max(
      5,
      ...imuHistory.map((sample) => Math.abs(sample.kf)),
      ...imuHistory.map((sample) => Math.abs(sample.raw)),
    );
    return { min: -maxAbs, max: maxAbs };
  }, [imuHistory]);

  const chartPointsKf = useMemo(() => seriesPoints(imuHistory, (sample) => sample.kf, chartBounds.min, chartBounds.max), [imuHistory, chartBounds.max, chartBounds.min]);
  const chartPointsRaw = useMemo(() => seriesPoints(imuHistory, (sample) => sample.raw, chartBounds.min, chartBounds.max), [imuHistory, chartBounds.max, chartBounds.min]);

  const angleDelta = useMemo(() => {
    if (imuHistory.length < 2) return 0;
    const a = imuHistory[imuHistory.length - 1].kf;
    const b = imuHistory[imuHistory.length - 2].kf;
    return a - b;
  }, [imuHistory]);

  const outputDelta = useMemo(() => {
    if (imuHistory.length < 2) return 0;
    const a = imuHistory[imuHistory.length - 1].out;
    const b = imuHistory[imuHistory.length - 2].out;
    return a - b;
  }, [imuHistory]);

  const angleDialPct = clamp(Math.abs(hud.angle) / 20, 0, 1);
  const outputDialPct = clamp(Math.abs(hud.output) / 120, 0, 1);
  const voltageDialPct = clamp((hud.voltageRaw - 120) / 120, 0, 1);

  const applyPid = async () => {
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
  };

  const applyMotion = async () => {
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
  };

  const applySetpoint = async () => {
    const current = n(status.set);
    if (balancing && Math.abs(setpoint - current) > BAL_BOUNDS.setpoint) {
      setMsg('SETPOINT change too large while BALANCING; DISARM for larger edits.');
      return;
    }
    const r = await setSetpoint(setpoint);
    setStatus(r.status);
    if (r.control) setControl(r.control);
    setMsg('SETPOINT applied');
  };

  const refreshLogs = async () => {
    const ls = await getLines(200);
    setLines(ls);
  };

  return (
    <div className={`app-shell ${workbenchOpen ? 'with-workbench' : ''}`}>
      <header className="topbar">
        <h1>UpRight.os Ops Console <span className="ui-build-chip">{UI_BUILD}</span></h1>
        <div className={`badge ${healthBadge}`}>{healthBadge}</div>
      </header>

      <div className="workspace-layout">
        <main className={`panel editor-panel ${tab === 'connect' ? 'panel-compact' : ''}`}>
          <div className="panel-workflow">
            <span className="workflow-label">Tuning Module Workflow</span>
            <nav className="tabs workflow-tabs" aria-label="Module workflow">
              {TAB_FLOW.map(({ id, step, label }, idx) => (
                <button
                  key={id}
                  className={`step-tab ${tab === id ? 'active' : ''} ${idx < TAB_FLOW.length - 1 ? 'has-connector' : ''}`}
                  onClick={() => setTab(id)}
                  aria-current={tab === id ? 'step' : undefined}
                >
                  <span className="step-num">{step}</span>
                  <span className="step-text">{label}</span>
                </button>
              ))}
            </nav>
          </div>
          <section className="system-alerts" aria-live="polite" aria-label="System alerts">
            <div className="system-alerts-head">
              <span>System Alerts</span>
              <button type="button" onClick={() => setUiAlerts([])} disabled={uiAlerts.length === 0}>
                Clear
              </button>
            </div>
            {uiAlerts.length === 0 && <p className="system-alerts-empty">No events yet.</p>}
            {uiAlerts.length > 0 && (
              <div className="system-alerts-list">
                {uiAlerts.map((a) => (
                  <div key={a.id} className={`system-alert ${a.tone}`}>
                    <span className="system-alert-time">{new Date(a.ts).toLocaleTimeString()}</span>
                    <span className="system-alert-text">{a.text}</span>
                    <button type="button" onClick={() => dismissAlert(a.id)} aria-label="Dismiss alert">
                      x
                    </button>
                  </div>
                ))}
              </div>
            )}
          </section>
          <div className="module-body">
        {tab === 'connect' && (
          <section>
            <h2>Connect</h2>
            <p className="indicator-line"><span className="indicator-label">Bridge Port:</span> <span className="indicator-value">{health?.port ?? 'n/a'}</span></p>
            <p className="indicator-line"><span className="indicator-label">Mode:</span> <span className="indicator-value">{mode}</span></p>
            <p className="indicator-line"><span className="indicator-label">Angle:</span> <span className="indicator-value">{status.ang ?? 'n/a'}</span></p>
            <p className="indicator-line"><span className="indicator-label">E-Stop Latched:</span> <span className="indicator-value">{control.estop_latched ? 'YES' : 'NO'}</span></p>
            <p className="indicator-line"><span className="indicator-label">Compatibility:</span> <span className="indicator-value">{compatKnown ? (compatOk ? 'PASS' : 'FAIL') : 'UNTESTED'}</span></p>
            <div className="row">
              <button onClick={() => void runCompatProbe()}>Run Compat Probe</button>
            </div>
            {compat && (
              <div className="compat-box">
                <p><strong>Profile:</strong> {compat.profile}</p>
                <p><strong>Firmware ID:</strong> {compat.firmware_id ?? 'n/a'}</p>
                <p><strong>Missing fields:</strong> {compat.missing_fields.length ? compat.missing_fields.join(', ') : 'none'}</p>
                <p><strong>Missing commands:</strong> {compat.missing_commands.length ? compat.missing_commands.join(', ') : 'none'}</p>
                <p><strong>Warnings:</strong> {compat.warnings.length ? compat.warnings.join(' | ') : 'none'}</p>
              </div>
            )}

            <div className="wizard-box">
              <h3>Connect Wizard</h3>
              <p className="wizard-subtitle">Run auto-detect to fingerprint processor/profile/components, then save this bot profile.</p>
              <div className="row">
                <button onClick={() => void runConnectWizard()}>Run Auto-Detect</button>
              </div>

              <div className="wizard-profile-inputs">
                <label>
                  Robot Label
                  <input type="text" value={profileLabel} onChange={(e) => setProfileLabel(e.target.value)} />
                </label>
                <label>
                  Chassis Class
                  <select value={chassisClass} onChange={(e) => setChassisClass(e.target.value)}>
                    <option value="2wd_inverted_pendulum">2WD Inverted Pendulum</option>
                    <option value="2wd_diff_drive">2WD Differential Drive</option>
                    <option value="custom">Custom</option>
                  </select>
                </label>
                <button onClick={saveRobotProfile}>Save Local Profile</button>
              </div>

              <div className="wizard-actions">
                <button onClick={loadSavedRobotProfile}>Load Saved Profile</button>
                <button onClick={() => void exportRobotProfile()}>Export Profile JSON</button>
                <button onClick={importRobotProfile}>Import Profile JSON</button>
                <button onClick={deleteSavedRobotProfile}>Delete Profile</button>
              </div>

              {robotProfile && (
                <p className="wizard-profile-summary">
                  Saved Profile: <strong>{robotProfile.label}</strong> · {robotProfile.chassis} · confidence {robotProfile.probe.confidence_pct}%
                </p>
              )}

              {connectProbe && (
                <div className="wizard-results">
                  <p><strong>Confidence:</strong> {connectProbe.confidence_pct}%</p>
                  <p><strong>MCU Guess:</strong> {connectProbe.mcu_guess}</p>
                  <p><strong>Firmware Profile:</strong> {connectProbe.firmware_profile}</p>
                  <p><strong>USB Device:</strong> {connectProbe.port_meta.description ?? connectProbe.port}</p>
                  <p>
                    <strong>Components:</strong>{' '}
                    IMU={connectProbe.components.imu ? 'Y' : 'N'} ·
                    Motor={connectProbe.components.motor_driver ? 'Y' : 'N'} ·
                    Enc={connectProbe.components.encoder_feedback ? 'Y' : 'N'} ·
                    Volt={connectProbe.components.voltage_telemetry ? 'Y' : 'N'}
                  </p>
                  <p><strong>Missing Commands:</strong> {connectProbe.missing_commands.length ? connectProbe.missing_commands.join(', ') : 'none'}</p>
                  {connectProbe.warnings.length > 0 && (
                    <p><strong>Warnings:</strong> {connectProbe.warnings.join(' | ')}</p>
                  )}
                  <p><strong>Prompt User For:</strong> {connectProbe.next_questions.join(' | ')}</p>
                </div>
              )}
            </div>

            <button
              onClick={async () => {
                const [h, s, hb] = await Promise.all([getHealth(), getStatus(), heartbeat()]);
                setHealth(h.health);
                if (h.control) setControl(h.control);
                setControl(hb);
                setStatus(s.status);
                if (s.control) setControl(s.control);
                setMsg('Refreshed');
              }}
            >
              Refresh
            </button>
          </section>
        )}

        {tab === 'control' && (
          <section>
            <h2>Control</h2>
            <div className="row">
              <button
                disabled={control.estop_latched || !compatOk}
                onClick={async () => {
                  const c = await armPrepare();
                  setControl(c);
                  setMsg('Arm prepared. Press Confirm Arm to execute.');
                }}
              >
                Prepare Arm
              </button>
              <button
                disabled={!control.arm_prepared || control.estop_latched}
                onClick={async () => {
                  const r = await armConfirm();
                  setStatus(r.status);
                  setControl(r.control);
                  setMsg('Arm confirmed');
                }}
              >
                Confirm Arm
              </button>
              <button
                onClick={async () => {
                  const r = await disarm();
                  setStatus(r.status);
                  if (r.control) setControl(r.control);
                  setMsg('Disarmed');
                }}
              >
                Disarm
              </button>
            </div>
            <div className="row">
              <button
                disabled={control.estop_latched}
                onClick={async () => {
                  const r = await calZero();
                  setStatus(r.status);
                  if (r.control) setControl(r.control);
                  setMsg('CAL ZERO complete');
                }}
              >
                Cal Zero
              </button>
              <button
                onClick={async () => {
                  await saveCfg();
                  setMsg('Config saved');
                }}
              >
                Save Config
              </button>
              <button
                onClick={async () => {
                  const r = await estopLatch();
                  setStatus(r.status);
                  setControl(r.control);
                  setMsg('E-Stop latched');
                }}
              >
                E-Stop Latch
              </button>
              <button
                disabled={!control.estop_latched}
                onClick={async () => {
                  const r = await estopReset();
                  setStatus(r.status);
                  setControl(r.control);
                  setMsg('E-Stop reset');
                }}
              >
                E-Stop Reset
              </button>
            </div>
          </section>
        )}

        {tab === 'tuning' && (
          <section>
            <h2>Tuning</h2>
            <div className="row">
              <button onClick={syncFromBot}>Sync From Bot</button>
            </div>

            <div className="grid3">
              <label>
                Kp
                <input type="number" step="0.1" value={pid.kp} onChange={(e) => setPidDraft((p) => ({ ...p, kp: Number(e.target.value) }))} />
              </label>
              <label>
                Ki
                <input type="number" step="0.01" value={pid.ki} onChange={(e) => setPidDraft((p) => ({ ...p, ki: Number(e.target.value) }))} />
              </label>
              <label>
                Kd
                <input type="number" step="0.01" value={pid.kd} onChange={(e) => setPidDraft((p) => ({ ...p, kd: Number(e.target.value) }))} />
              </label>
            </div>
            <button disabled={control.estop_latched || !compatOk} onClick={applyPid}>Apply PID</button>

            <div className="grid2">
              <label>
                Kv
                <input type="number" step="0.001" value={motion.kv} onChange={(e) => setMotionDraft((m) => ({ ...m, kv: Number(e.target.value) }))} />
              </label>
              <label>
                Kx
                <input type="number" step="0.0001" value={motion.kx} onChange={(e) => setMotionDraft((m) => ({ ...m, kx: Number(e.target.value) }))} />
              </label>
            </div>
            <button disabled={control.estop_latched || !compatOk} onClick={applyMotion}>Apply Motion</button>

            <div className="grid1">
              <label>
                Setpoint Deg
                <input type="number" step="0.01" value={setpoint} onChange={(e) => setSetpointDraft(Number(e.target.value))} />
              </label>
            </div>
            <button disabled={control.estop_latched || !compatOk} onClick={applySetpoint}>Apply Setpoint</button>

            <hr />
            <h3>Performance Checkpoints</h3>
            <p>One click rating saves current tuning as a checkpoint (keeps last {CHECKPOINT_MAX}).</p>
            <div className="row">
              <button onClick={() => makeCheckpoint('poor')}>Rate Poor</button>
              <button onClick={() => makeCheckpoint('ok')}>Rate OK</button>
              <button onClick={() => makeCheckpoint('good')}>Rate Good</button>
              <button onClick={() => makeCheckpoint('great')}>Rate Great</button>
            </div>

            <div className="checkpoint-list">
              {checkpoints.length === 0 && <p>No checkpoints yet.</p>}
              {checkpoints.map((cp) => (
                <div className="checkpoint-card" key={cp.id}>
                  <div>
                    <strong>{cp.rating.toUpperCase()}</strong> · {new Date(cp.ts).toLocaleString()}
                  </div>
                  <div>
                    mode={cp.mode} angle={cp.angle.toFixed(3)} wpos={cp.wpos.toFixed(1)}
                  </div>
                  <div>
                    PID {cp.pid.kp.toFixed(3)} / {cp.pid.ki.toFixed(3)} / {cp.pid.kd.toFixed(3)} · MOTION {cp.motion.kv.toFixed(4)} / {cp.motion.kx.toFixed(5)} · SP {cp.setpoint.toFixed(3)}
                  </div>
                  <div className="row">
                    <button onClick={() => restoreDraftFromCheckpoint(cp)}>Load Draft</button>
                    <button onClick={() => void applyCheckpointToBot(cp, false)}>Apply To Bot</button>
                    <button onClick={() => void applyCheckpointToBot(cp, true)}>Apply + SaveCfg</button>
                    <button onClick={() => deleteCheckpoint(cp.id)}>Delete</button>
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        {tab === 'commissioning' && (
          <section>
            <h2>Commissioning</h2>
            <div className="row">
              <button
                disabled={comm.running || control.estop_latched}
                onClick={async () => {
                  const st = await commissioningRun(true);
                  setComm({ state: st.state, running: st.running, returncode: st.returncode, log_tail: st.log_tail ?? [] });
                  setMsg('Commissioning started');
                }}
              >
                Run Full (Auto)
              </button>
              <button
                onClick={async () => {
                  const [st, art] = await Promise.all([commissioningStatus(), commissioningArtifacts()]);
                  setComm({ state: st.state, running: st.running, returncode: st.returncode, log_tail: st.log_tail ?? [] });
                  setCommArtifacts({ latest_metrics: art.latest_metrics, latest_run: art.latest_run });
                  setMsg('Commissioning status refreshed');
                }}
              >
                Refresh Status
              </button>
            </div>
            <p>State: <strong>{comm.state}</strong> running={comm.running ? 'yes' : 'no'} return={String(comm.returncode)}</p>
            <p>Latest metrics: {commArtifacts.latest_metrics ?? 'n/a'}</p>
            <p>Latest run: {commArtifacts.latest_run ?? 'n/a'}</p>
            <pre className="logbox">{comm.log_tail.join('\n')}</pre>
          </section>
        )}

        {tab === 'logs' && (
          <section>
            <h2>Logs</h2>
            <button onClick={refreshLogs}>Refresh Lines</button>
            <pre className="logbox">{lines.join('\n')}</pre>
          </section>
        )}
          </div>
      </main>

        <aside className="hud-rail hud-rail-left">
          <section className="hud-grid" aria-label="Live telemetry dashboard left">
            <article className="hud-card">
              <span className="hud-label">Mode</span>
              <span className="hud-value">{hud.mode}</span>
              <span className={`hud-pill ${hud.connected ? 'good' : 'bad'}`}>{hud.connected ? 'link up' : 'link down'}</span>
            </article>

            <article className="hud-card">
              <span className="hud-label">Angle</span>
              <span className="hud-value">{hud.angle.toFixed(3)} deg</span>
              <span className={`hud-pill ${Math.abs(hud.angle) <= 2 ? 'good' : Math.abs(hud.angle) <= 5 ? 'warn' : 'bad'}`}>
                {Math.abs(hud.angle) <= 2 ? 'stable' : Math.abs(hud.angle) <= 5 ? 'watch' : 'risk'}
              </span>
            </article>

            <article className="hud-card">
              <span className="hud-label">Output</span>
              <span className="hud-value">{hud.output.toFixed(2)}</span>
              <span className={`hud-pill ${Math.abs(hud.output) <= 30 ? 'good' : Math.abs(hud.output) <= 70 ? 'warn' : 'bad'}`}>
                motor effort
              </span>
            </article>

            <article className="hud-card">
              <span className="hud-label">Voltage Raw</span>
              <span className="hud-value">{hud.voltageRaw.toFixed(0)}</span>
              <span className={`hud-pill ${hud.voltageRaw >= 170 ? 'good' : hud.voltageRaw >= 140 ? 'warn' : 'bad'}`}>
                power rail
              </span>
            </article>

            <article className="hud-card">
              <span className="hud-label">Compat</span>
              <span className="hud-value">{compatKnown ? (compatOk ? 'PASS' : 'FAIL') : 'UNTESTED'}</span>
              <span className={`hud-pill ${!compatKnown ? 'unknown' : compatOk ? 'good' : 'bad'}`}>{compat?.profile ?? 'run probe'}</span>
            </article>
          </section>
        </aside>

        <aside className="hud-rail hud-rail-right">
          <section className="hud-grid" aria-label="Live telemetry dashboard right">
            <article className="hud-card">
              <span className="hud-label">PID</span>
              <span className="hud-value hud-mono">
                {hud.kp.toFixed(2)} / {hud.ki.toFixed(3)} / {hud.kd.toFixed(2)}
              </span>
              <span className="hud-pill good">k p / i / d</span>
            </article>

            <article className="hud-card">
              <span className="hud-label">Setpoint</span>
              <span className="hud-value">{hud.setpoint.toFixed(3)} deg</span>
              <span className="hud-pill good">target tilt</span>
            </article>

            <article className="hud-card">
              <span className="hud-label">Wheel</span>
              <span className="hud-value hud-mono">
                v {hud.wspd.toFixed(2)} / x {hud.wpos.toFixed(1)}
              </span>
              <span className="hud-pill good">speed / position</span>
            </article>

            <article className="hud-card">
              <span className="hud-label">Safety</span>
              <span className="hud-value">{hud.estop ? 'E-STOP LATCHED' : hud.armPrepared ? 'ARM PREPARED' : 'CLEAR'}</span>
              <span className={`hud-pill ${hud.estop ? 'bad' : hud.armPrepared ? 'warn' : 'good'}`}>{hud.estop ? 'blocked' : hud.armPrepared ? 'pending arm' : 'ready'}</span>
            </article>

            <article className="hud-card">
              <span className="hud-label">Heartbeat</span>
              <span className="hud-value">{hud.heartbeatAge == null ? 'n/a' : `${hud.heartbeatAge.toFixed(2)} s`}</span>
              <span className={`hud-pill ${hud.heartbeatState}`}>{hud.heartbeatState}</span>
            </article>
          </section>
        </aside>
      </div>

      <aside className={`firmware-drawer ${workbenchOpen ? 'open' : 'collapsed'}`} aria-label="Firmware workbench">
        <button className="firmware-drawer-toggle" onClick={() => setWorkbenchOpen((v) => !v)}>
          {workbenchOpen ? 'Hide Workbench' : 'Firmware'}
        </button>
        {workbenchOpen && (
          <div className="firmware-drawer-body">
            <div className="firmware-drawer-head">
              <h3>Firmware Workbench</h3>
              <span className="workflow-label">arduino-cli pipeline</span>
            </div>
            <nav className="tabs firmware-tabs" aria-label="Firmware workbench tabs">
              <button className={workbenchTab === 'sketch' ? 'active' : ''} onClick={() => setWorkbenchTab('sketch')}>Sketch</button>
              <button className={workbenchTab === 'board' ? 'active' : ''} onClick={() => setWorkbenchTab('board')}>Board / Build</button>
              <button className={workbenchTab === 'serial' ? 'active' : ''} onClick={() => setWorkbenchTab('serial')}>Serial</button>
              <button className={workbenchTab === 'codex' ? 'active' : ''} onClick={() => setWorkbenchTab('codex')}>Codex</button>
            </nav>

            {workbenchTab === 'sketch' && (
              <section className="firmware-pane">
                <label>
                  Sketch File
                  <input type="text" value={sketchPath} onChange={(e) => setSketchPath(e.target.value)} />
                </label>
                <div className="row">
                  <button onClick={() => void loadSketch()}>Load Sketch</button>
                  <button onClick={() => void saveSketch()}>Save Sketch</button>
                </div>
                <div className="sketch-editor">
                  <Editor
                    height="420px"
                    defaultLanguage="cpp"
                    value={sketchContent}
                    onChange={(v) => setSketchContent(v ?? '')}
                    options={{
                      minimap: { enabled: false },
                      fontSize: 13,
                      wordWrap: 'on',
                      smoothScrolling: true,
                      scrollBeyondLastLine: false,
                      automaticLayout: true,
                    }}
                    theme="vs-dark"
                  />
                </div>
              </section>
            )}

            {workbenchTab === 'board' && (
              <section className="firmware-pane">
                <div className="row">
                  <button onClick={() => void runFirmwareCheck()}>Check CLI</button>
                  <button disabled={fw.running} onClick={() => void runFirmwareInstall()}>Install CLI</button>
                  <button onClick={() => void refreshBoards()}>Scan Boards</button>
                </div>
                <label>
                  Board (FQBN)
                  <select value={fwCfg.fqbn} onChange={(e) => setFwCfg((p) => ({ ...p, fqbn: e.target.value }))}>
                    <option value={fwCfg.fqbn}>{fwCfg.fqbn || 'arduino:avr:nano'}</option>
                    {boardScan?.ports
                      .filter((p) => Boolean(p.fqbn) && p.fqbn !== fwCfg.fqbn)
                      .map((p) => (
                        <option key={`${p.address}-${p.fqbn}`} value={p.fqbn ?? ''}>
                          {p.board_name ?? 'Detected'} · {p.fqbn}
                        </option>
                      ))}
                  </select>
                </label>
                <label>
                  Port
                  <select value={fwCfg.port} onChange={(e) => setFwCfg((p) => ({ ...p, port: e.target.value }))}>
                    <option value={fwCfg.port}>{fwCfg.port || '/dev/cu.usbserial-...'}</option>
                    {boardScan?.ports
                      .filter((p) => Boolean(p.address) && p.address !== fwCfg.port)
                      .map((p) => (
                        <option key={p.address ?? 'unknown'} value={p.address ?? ''}>
                          {p.address} {p.board_name ? `(${p.board_name})` : ''}
                        </option>
                      ))}
                  </select>
                </label>
                <label>
                  Sketch Folder
                  <input type="text" value={fwCfg.sketch} onChange={(e) => setFwCfg((p) => ({ ...p, sketch: e.target.value }))} />
                </label>
                <div className="row">
                  <button disabled={fw.running} onClick={() => void runFirmwareCompile()}>Compile</button>
                  <button disabled={fw.running} onClick={() => void runFirmwareUpload()}>Upload</button>
                  <button disabled={fw.running} onClick={() => void runFirmwareUploadGuarded()}>
                    Guarded Flash
                  </button>
                </div>
                {boardScan?.recommended_fqbn && (
                  <p className="wizard-profile-summary">
                    Recommended: <strong>{boardScan.recommended_fqbn}</strong> on {boardScan.recommended_port ?? 'n/a'}
                  </p>
                )}
                <p className="wizard-profile-summary">
                  State: <strong>{fw.state}</strong> · phase={fw.phase} · running={fw.running ? 'yes' : 'no'} · return={String(fw.returncode)}
                </p>
                {fwCheck && (
                  <p className="wizard-profile-summary">
                    CLI: <strong>{fwCheck.ok ? 'PASS' : 'FAIL'}</strong>{fwCheck.version ? ` · ${fwCheck.version}` : ''}{fwCheck.error ? ` · ${fwCheck.error}` : ''}
                  </p>
                )}
                <pre className="logbox firmware-log">{fw.log_tail.join('\n')}</pre>
              </section>
            )}

            {workbenchTab === 'serial' && (
              <section className="firmware-pane">
                <p className="wizard-subtitle">Send raw serial commands and tail lines from the firmware.</p>
                <div className="row serial-send-row">
                  <input
                    type="text"
                    value={serialWrite}
                    onChange={(e) => setSerialWrite(e.target.value)}
                    placeholder="e.g. GET or PID 31 0.05 1.05"
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') void sendSerialLine();
                    }}
                  />
                  <button onClick={() => void sendSerialLine()}>Send</button>
                  <button onClick={() => void refreshLogs()}>Refresh Tail</button>
                </div>
                <pre className="logbox firmware-log">{lines.join('\n')}</pre>
              </section>
            )}

            {workbenchTab === 'codex' && (
              <section className="firmware-pane">
                <div className="codex-status-row">
                  <span className={`hud-pill ${authUser ? 'good' : 'bad'}`}>
                    {authUser ? 'account logged in' : 'account not logged in'}
                  </span>
                  <span className={`hud-pill ${ai.configured ? 'good' : 'warn'}`}>
                    {ai.configured ? 'openai key synced' : 'openai key missing'}
                  </span>
                  <span className="hud-pill unknown">model {authUser?.openai_model ?? ai.model ?? 'n/a'}</span>
                </div>
                {authAlert && <p className={`auth-alert ${authAlert.tone}`}>{authAlert.text}</p>}
                {!authUser && (
                  <>
                    <p className="wizard-subtitle">Sign in to use your own OpenAI key with Codex.</p>
                    <p className="wizard-subtitle">This is a local UpRight.os account (not your ChatGPT/Google login).</p>
                    <div className="row">
                      <button
                        onClick={() => {
                          setAuthMode('login');
                          setAuthAlert(null);
                        }}
                        className={authMode === 'login' ? 'active' : ''}
                      >
                        Login
                      </button>
                      <button
                        onClick={() => {
                          setAuthMode('register');
                          setAuthAlert(null);
                        }}
                        className={authMode === 'register' ? 'active' : ''}
                      >
                        Register
                      </button>
                    </div>
                    <label>
                      Email
                      <input type="email" value={authEmail} onChange={(e) => setAuthEmail(e.target.value)} />
                    </label>
                    <label>
                      Password
                      <input type="password" value={authPassword} onChange={(e) => setAuthPassword(e.target.value)} />
                    </label>
                    <button disabled={authBusy} onClick={() => void submitAuth()}>
                      {authBusy ? 'Working...' : authMode === 'login' ? 'Login' : 'Create Account'}
                    </button>
                  </>
                )}

                {authUser && (
                  <>
                    <p className="wizard-subtitle">
                      Signed in as <strong>{authUser.email}</strong>.{' '}
                      {authUser.openai_configured ? `Model: ${authUser.openai_model ?? ai.model}` : 'No OpenAI key saved yet.'}
                    </p>
                    <div className="grid2">
                      <label>
                        OpenAI API Key
                        <input
                          type="password"
                          value={openAiKeyInput}
                          onChange={(e) => setOpenAiKeyInput(e.target.value)}
                          placeholder="sk-..."
                        />
                      </label>
                      <label>
                        Model
                        <input value={openAiModelInput} onChange={(e) => setOpenAiModelInput(e.target.value)} />
                      </label>
                    </div>
                    <div className="row">
                      <button onClick={() => void saveUserOpenAiKey()}>Save OpenAI Key</button>
                      <button onClick={() => void clearUserOpenAiKey()}>Delete OpenAI Key</button>
                      <button onClick={() => void runLogout()}>Logout</button>
                    </div>
                    <div className="codex-chat-log">
                      {aiHistory.length === 0 && <p className="wizard-subtitle">No chat history yet.</p>}
                      {aiHistory.map((m, idx) => (
                        <div key={`${m.ts}-${idx}`} className={`codex-msg ${m.role}`}>
                          <span className="codex-role">{m.role}</span>
                          <pre>{m.text}</pre>
                        </div>
                      ))}
                    </div>
                    <div className="row serial-send-row">
                      <input
                        type="text"
                        value={aiInput}
                        onChange={(e) => setAiInput(e.target.value)}
                        placeholder="Ask Codex about tuning, logs, safety, or next steps..."
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') void sendAi();
                        }}
                      />
                      <button disabled={!ai.configured || aiBusy} onClick={() => void sendAi()}>
                        {aiBusy ? 'Thinking...' : 'Send'}
                      </button>
                    </div>
                    {!ai.configured && <p className="wizard-subtitle">Save an OpenAI key above to enable Codex chat.</p>}
                  </>
                )}
              </section>
            )}
          </div>
        )}
      </aside>

      {preflightOpen && (
        <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="Guarded flash preflight checklist">
          <div className="preflight-modal">
            <h3>Guarded Flash Preflight</h3>
            <p className="wizard-subtitle">Complete all checks before flashing.</p>
            <label className="check-item">
              <input
                type="checkbox"
                checked={preflightChecks.ide_closed}
                onChange={(e) => setPreflightChecks((p) => ({ ...p, ide_closed: e.target.checked }))}
              />
              Arduino IDE / Serial Monitor is closed
            </label>
            <label className="check-item">
              <input
                type="checkbox"
                checked={preflightChecks.bot_safe}
                onChange={(e) => setPreflightChecks((p) => ({ ...p, bot_safe: e.target.checked }))}
              />
              Robot is in safe posture (wheels clear / supported)
            </label>
            <label className="check-item">
              <input
                type="checkbox"
                checked={preflightChecks.correct_port}
                onChange={(e) => setPreflightChecks((p) => ({ ...p, correct_port: e.target.checked }))}
              />
              Selected port is correct ({fwCfg.port || 'not set'})
            </label>
            <label className="check-item">
              <input
                type="checkbox"
                checked={preflightChecks.power_expected}
                onChange={(e) => setPreflightChecks((p) => ({ ...p, power_expected: e.target.checked }))}
              />
              Power configuration matches your upload plan (USB-only vs external battery)
            </label>
            <div className="row">
              <button onClick={() => setPreflightOpen(false)}>Cancel</button>
              <button
                disabled={!Object.values(preflightChecks).every(Boolean) || fw.running}
                onClick={() => void executeGuardedFlash()}
              >
                Start Guarded Flash
              </button>
            </div>
          </div>
        </div>
      )}

      <section className="hud-visuals" aria-label="Persistent telemetry visuals">
        <article className="dial-panel">
          <h3>Reactor Dials</h3>
          <div className="dial-row">
            <div className="dial-card">
              <svg className="dial" viewBox="0 0 120 120" role="img" aria-label="Angle dial">
                <circle cx="60" cy="60" r="46" className="dial-track" />
                <circle cx="60" cy="60" r="46" className="dial-fill dial-angle" strokeDasharray={`${(2 * Math.PI * 46 * angleDialPct).toFixed(1)} ${(2 * Math.PI * 46).toFixed(1)}`} />
              </svg>
              <span className="dial-label">ANGLE</span>
              <span className="dial-value">{hud.angle.toFixed(2)}°</span>
              <span className={`trend ${Math.abs(angleDelta) < 0.05 ? 'flat' : angleDelta > 0 ? 'up' : 'down'}`}>
                Δ {angleDelta.toFixed(3)}
              </span>
            </div>

            <div className="dial-card">
              <svg className="dial" viewBox="0 0 120 120" role="img" aria-label="Output dial">
                <circle cx="60" cy="60" r="46" className="dial-track" />
                <circle cx="60" cy="60" r="46" className="dial-fill dial-output" strokeDasharray={`${(2 * Math.PI * 46 * outputDialPct).toFixed(1)} ${(2 * Math.PI * 46).toFixed(1)}`} />
              </svg>
              <span className="dial-label">OUTPUT</span>
              <span className="dial-value">{hud.output.toFixed(1)}</span>
              <span className={`trend ${Math.abs(outputDelta) < 0.2 ? 'flat' : outputDelta > 0 ? 'up' : 'down'}`}>
                Δ {outputDelta.toFixed(2)}
              </span>
            </div>

            <div className="dial-card">
              <svg className="dial" viewBox="0 0 120 120" role="img" aria-label="Voltage dial">
                <circle cx="60" cy="60" r="46" className="dial-track" />
                <circle cx="60" cy="60" r="46" className="dial-fill dial-voltage" strokeDasharray={`${(2 * Math.PI * 46 * voltageDialPct).toFixed(1)} ${(2 * Math.PI * 46).toFixed(1)}`} />
              </svg>
              <span className="dial-label">VOLT RAW</span>
              <span className="dial-value">{hud.voltageRaw.toFixed(0)}</span>
              <span className="trend flat">rail health</span>
            </div>
          </div>
        </article>

        <article className="imu-chart-panel">
          <h3>IMU Overlay (Raw vs Kalman)</h3>
          <div className="chart-legend">
            <span className="legend-item"><i className="legend-dot raw" /> raw angle</span>
            <span className="legend-item"><i className="legend-dot kf" /> kalman angle</span>
          </div>
          <svg className="imu-chart" viewBox="0 0 820 160" role="img" aria-label="IMU and Kalman overlay chart">
            <line x1="0" y1="80" x2="820" y2="80" className="chart-axis" />
            {chartPointsRaw && <polyline className="chart-line raw" points={chartPointsRaw} />}
            {chartPointsKf && <polyline className="chart-line kf" points={chartPointsKf} />}
          </svg>
          <div className="chart-meta">
            <span>samples: {imuHistory.length}</span>
            <span>range: {chartBounds.min.toFixed(1)}° to {chartBounds.max.toFixed(1)}°</span>
          </div>
        </article>
      </section>



      <footer className="statusbar">
        <span>{msg}</span>
        <span>State: {mode}</span>
        <span>Angle: {status.ang ?? 'n/a'}</span>
        <span>E-Stop: {control.estop_latched ? 'LATCHED' : 'CLEAR'}</span>
      </footer>
    </div>
  );
}
