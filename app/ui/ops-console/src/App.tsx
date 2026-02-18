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
} from './api';
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

function n(v: string | undefined, fallback = 0): number {
  const parsed = Number.parseFloat(v ?? '');
  return Number.isFinite(parsed) ? parsed : fallback;
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

  const draftsInitializedRef = useRef(false);

  const mode = status.mode ?? 'UNKNOWN';
  const balancing = mode === 'BALANCING';

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
        if (s.control) setControl(s.control);
        if (!draftsInitializedRef.current) {
          setPidDraft({ kp: n(s.status.kp, 31), ki: n(s.status.ki, 0.05), kd: n(s.status.kd, 1.05) });
          setMotionDraft({ kv: n(s.status.kv, 0), kx: n(s.status.kx, 0) });
          setSetpointDraft(n(s.status.set, 0));
          draftsInitializedRef.current = true;
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
        <h1>UpRight.os Ops Console</h1>
        <div className={`badge ${healthBadge}`}>{healthBadge}</div>
      </header>

      <nav className="tabs">
        {(['connect', 'control', 'tuning', 'commissioning', 'logs'] as Tab[]).map((t) => (
          <button key={t} className={tab === t ? 'active' : ''} onClick={() => setTab(t)}>
            {t}
          </button>
        ))}
      </nav>

      <main className="panel">
        {tab === 'connect' && (
          <section>
            <h2>Connect</h2>
            <p>Bridge Port: {health?.port ?? 'n/a'}</p>
            <p>Mode: {mode}</p>
            <p>Angle: {status.ang ?? 'n/a'}</p>
            <p>E-Stop Latched: {control.estop_latched ? 'YES' : 'NO'}</p>
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
                disabled={control.estop_latched}
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
            <button disabled={control.estop_latched} onClick={applyPid}>Apply PID</button>

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
            <button disabled={control.estop_latched} onClick={applyMotion}>Apply Motion</button>

            <div className="grid1">
              <label>
                Setpoint Deg
                <input type="number" step="0.01" value={setpoint} onChange={(e) => setSetpointDraft(Number(e.target.value))} />
              </label>
            </div>
            <button disabled={control.estop_latched} onClick={applySetpoint}>Apply Setpoint</button>

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

      <footer className="statusbar">
        <span>{msg}</span>
        <span>State: {mode}</span>
        <span>Angle: {status.ang ?? 'n/a'}</span>
        <span>E-Stop: {control.estop_latched ? 'LATCHED' : 'CLEAR'}</span>
      </footer>
    </div>
  );
}
