import { useEffect, useMemo, useRef, useState } from 'react';
import {
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
  saveCfg,
  setMotion,
  setPid,
  setSetpoint,
  probeCompat,
} from './api';
import type { CompatReport } from './api';
import type { ControlState, Health, Status } from './types';

type Tab = 'connect' | 'control' | 'tuning' | 'commissioning' | 'logs';

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

const CHECKPOINT_KEY = 'upright_ops_checkpoints_v1';
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
const UI_BUILD = 'HUD-V4-LIVE';

type ImuSample = {
  t: number;
  kf: number;
  raw: number;
  gyro: number;
  out: number;
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
  const h = 210;
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

export default function App() {
  const [tab, setTab] = useState<Tab>('connect');
  const [health, setHealth] = useState<Health | null>(null);
  const [status, setStatus] = useState<Status>({});
  const [control, setControl] = useState<ControlState>({ arm_prepared: false, estop_latched: false });
  const [lines, setLines] = useState<string[]>([]);
  const [msg, setMsg] = useState<string>('');

  const [pid, setPidDraft] = useState({ kp: 31, ki: 0.05, kd: 1.05 });
  const [motion, setMotionDraft] = useState({ kv: 0, kx: 0 });
  const [setpoint, setSetpointDraft] = useState(0);
  const [checkpoints, setCheckpoints] = useState<Checkpoint[]>(() => loadCheckpoints());

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
  const [imuHistory, setImuHistory] = useState<ImuSample[]>([]);
  const [compat, setCompat] = useState<CompatReport | null>(null);

  const draftsInitializedRef = useRef(false);
  const compatRequestedRef = useRef(false);

  const mode = status.mode ?? 'UNKNOWN';
  const balancing = mode === 'BALANCING';
  const compatOk = compat?.ok === true;
  const compatKnown = compat !== null;

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
    let mounted = true;
    const tickComm = async () => {
      try {
        const [st, art] = await Promise.all([commissioningStatus(), commissioningArtifacts()]);
        if (!mounted) return;
        setComm({ state: st.state, running: st.running, returncode: st.returncode, log_tail: st.log_tail ?? [] });
        setCommArtifacts({ latest_metrics: art.latest_metrics, latest_run: art.latest_run });
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
    <div className="app-shell">
      <header className="topbar">
        <h1>UpRight.os Ops Console <span className="ui-build-chip">{UI_BUILD}</span></h1>
        <div className={`badge ${healthBadge}`}>{healthBadge}</div>
      </header>

      <nav className="tabs">
        {(['connect', 'control', 'tuning', 'commissioning', 'logs'] as Tab[]).map((t) => (
          <button key={t} className={tab === t ? 'active' : ''} onClick={() => setTab(t)}>
            {t}
          </button>
        ))}
      </nav>

      <div className="workspace-layout">
        <main className={`panel editor-panel ${tab === 'connect' ? 'panel-compact' : ''}`}>
        {tab === 'connect' && (
          <section>
            <h2>Connect</h2>
            <p>Bridge Port: {health?.port ?? 'n/a'}</p>
            <p>Mode: {mode}</p>
            <p>Angle: {status.ang ?? 'n/a'}</p>
            <p>E-Stop Latched: {control.estop_latched ? 'YES' : 'NO'}</p>
            <p>Compatibility: {compatKnown ? (compatOk ? 'PASS' : 'FAIL') : 'UNTESTED'}</p>
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
          <svg className="imu-chart" viewBox="0 0 820 210" role="img" aria-label="IMU and Kalman overlay chart">
            <line x1="0" y1="105" x2="820" y2="105" className="chart-axis" />
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
