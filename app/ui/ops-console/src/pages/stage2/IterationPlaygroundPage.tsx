import { useEffect, useMemo, useState } from 'react';
import {
  armConfirm,
  armPrepare,
  disarm,
  estopLatch,
  estopReset,
  toolingListTraces,
  toolingParamSweep,
  toolingTraceReplay,
  type ParamSweepResult,
  type SurrogateSimResult,
  type TraceReplayResult,
  toolingSurrogateSim,
} from '../../api';
import type { ImuSample } from '../../hooks/useHudTelemetry';
import { strings } from '../../strings';
import type { ControlState, Status } from '../../types';

type Props = {
  bridgeOnline: boolean;
  status: Status;
  control: ControlState;
  imuHistory: ImuSample[];
  refreshBridge: () => Promise<void>;
  setMsg: (text: string, source?: string) => void;
};

type ModelMode = 'live' | 'sim';

type SimSample = {
  t: number;
  ang: number;
  out: number;
  set: number;
};

type SimRun = {
  id: string;
  name: string;
  params: {
    kp: number;
    ki: number;
    kd: number;
    setpoint: number;
    durationS: number;
    disturbance: number;
  };
  metrics: {
    rmse: number;
    overshoot: number;
    settleS: number | null;
    maxOutPct: number;
  };
  samples: SimSample[];
};

function n(v: string | undefined, fallback = 0): number {
  const parsed = Number.parseFloat(v ?? '');
  return Number.isFinite(parsed) ? parsed : fallback;
}

function clamp(v: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, v));
}

function sparkline(values: number[], minY: number, maxY: number): string {
  if (values.length <= 1) return '';
  const w = 640;
  const h = 140;
  const span = Math.max(0.0001, maxY - minY);
  return values
    .map((value, i) => {
      const x = (i / (values.length - 1)) * w;
      const yNorm = (value - minY) / span;
      const y = h - yNorm * h;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(' ');
}

function runSim(opts: {
  name: string;
  kp: number;
  ki: number;
  kd: number;
  setpoint: number;
  durationS: number;
  disturbance: number;
}): SimRun {
  const dt = 0.02;
  const steps = Math.max(25, Math.floor(opts.durationS / dt));
  let theta = (Math.random() - 0.5) * 0.6;
  let omega = 0;
  let iTerm = 0;
  let prevErr = 0;
  const actuatorDelayTicks = 2;
  const cmdQueue: number[] = Array.from({ length: actuatorDelayTicks }, () => 0);

  const samples: SimSample[] = [];
  for (let i = 0; i < steps; i += 1) {
    const t = i * dt;
    const external = (Math.exp(-t * 0.9) * opts.disturbance) + ((Math.random() - 0.5) * 0.05);
    const err = opts.setpoint - theta;
    iTerm = clamp(iTerm + (err * dt), -16, 16);
    const dTerm = (err - prevErr) / dt;
    prevErr = err;

    let out = (opts.kp * err) + (opts.ki * iTerm) + (opts.kd * dTerm);
    if (Math.abs(out) < 4.0) out = 0; // motor deadband
    out = clamp(out, -180, 180);
    cmdQueue.push(out);
    const delayedOut = cmdQueue.shift() ?? 0;

    // Unstable around upright: gravity term amplifies deviation.
    // Control term counters instability when gains are adequate.
    const thetaRad = (theta * Math.PI) / 180;
    const gravity = 46 * Math.sin(thetaRad);
    const accel = gravity - (delayedOut * 0.34) - (omega * 0.95) + external;
    omega += accel * dt;
    theta += omega * dt;
    theta = clamp(theta, -86, 86);

    samples.push({ t, ang: theta, out: delayedOut, set: opts.setpoint });
    if (Math.abs(theta) >= 72) {
      // Faceplant / unrecoverable region; stop run early.
      break;
    }
  }

  const errs = samples.map((s) => s.ang - opts.setpoint);
  const rmse = Math.sqrt(errs.reduce((sum, e) => sum + (e * e), 0) / Math.max(1, errs.length));
  const overshoot = Math.max(0, ...samples.map((s) => Math.abs(s.ang - opts.setpoint)));
  const maxOutPct = Math.max(0, ...samples.map((s) => Math.abs(s.out) / 180)) * 100;
  let settleS: number | null = null;
  const band = 1.1;
  for (let i = 0; i < samples.length; i += 1) {
    const tail = samples.slice(i);
    if (tail.every((s) => Math.abs(s.ang - opts.setpoint) <= band)) {
      settleS = samples[i].t;
      break;
    }
  }

  return {
    id: `${Date.now()}-${Math.round(Math.random() * 10_000)}`,
    name: opts.name,
    params: {
      kp: opts.kp,
      ki: opts.ki,
      kd: opts.kd,
      setpoint: opts.setpoint,
      durationS: opts.durationS,
      disturbance: opts.disturbance,
    },
    metrics: { rmse, overshoot, settleS, maxOutPct },
    samples,
  };
}

export function IterationPlaygroundPage(props: Props) {
  const { bridgeOnline, status, control, imuHistory, refreshBridge, setMsg } = props;
  const [traceList, setTraceList] = useState<string[]>([]);
  const [tracePath, setTracePath] = useState('app/bridge/tests/fixtures/trace_replay_nominal.csv');
  const [traceBusy, setTraceBusy] = useState(false);
  const [traceResult, setTraceResult] = useState<TraceReplayResult | null>(null);

  const [kpSpec, setKpSpec] = useState('31,32');
  const [kiSpec, setKiSpec] = useState('0.05,0.06');
  const [kdSpec, setKdSpec] = useState('1.0,1.2');
  const [settleS, setSettleS] = useState(1);
  const [observeS, setObserveS] = useState(2);
  const [sweepBusy, setSweepBusy] = useState(false);
  const [sweepResult, setSweepResult] = useState<ParamSweepResult | null>(null);

  const [mode, setMode] = useState<ModelMode>('live');
  const [liveBusy, setLiveBusy] = useState(false);

  const [simKp, setSimKp] = useState(31);
  const [simKi, setSimKi] = useState(0.05);
  const [simKd, setSimKd] = useState(1.05);
  const [simSetpoint, setSimSetpoint] = useState(0);
  const [simDurationS, setSimDurationS] = useState(2.5);
  const [simDisturbance, setSimDisturbance] = useState(4.0);
  const [simRuns, setSimRuns] = useState<SimRun[]>([]);
  const [simTrainingPaths, setSimTrainingPaths] = useState<string[]>([]);
  const [surrogateBusy, setSurrogateBusy] = useState(false);
  const [surrogateReport, setSurrogateReport] = useState<SurrogateSimResult | null>(null);
  const [simActiveRunId, setSimActiveRunId] = useState<string | null>(null);
  const [simPlaybackIndex, setSimPlaybackIndex] = useState(0);
  const [simPlaying, setSimPlaying] = useState(false);

  useEffect(() => {
    if (!bridgeOnline) return;
    void (async () => {
      try {
        const traces = await toolingListTraces();
        setTraceList(traces);
        if (traces.length > 0 && !traces.includes(tracePath)) {
          setTracePath(traces[0]);
        }
        if (traces.length > 0 && simTrainingPaths.length === 0) {
          setSimTrainingPaths(traces.slice(0, Math.min(5, traces.length)));
        }
      } catch (e) {
        setMsg(`trace list error: ${(e as Error).message}`, 'playground');
      }
    })();
  }, [bridgeOnline, setMsg, simTrainingPaths.length, tracePath]);

  const topSweep = useMemo(() => (sweepResult?.ranked_top?.[0] ?? null), [sweepResult]);
  const pid = useMemo(() => ({
    kp: n(status.kp, 0),
    ki: n(status.ki, 0),
    kd: n(status.kd, 0),
  }), [status.kd, status.ki, status.kp]);
  const outputLimit = useMemo(() => {
    const parsed = Number.parseFloat(String(status.outMax ?? status.out_max ?? '180'));
    return Number.isFinite(parsed) && parsed > 0 ? parsed : 180;
  }, [status.outMax, status.out_max]);

  const liveView = useMemo(() => ({
    angle: n(status.ang, 0),
    raw: n(status.raw, 0),
    set: n(status.set, 0),
    out: n(status.out, 0),
    mode: String(status.mode ?? 'UNKNOWN').toUpperCase(),
  }), [status.ang, status.mode, status.out, status.raw, status.set]);

  const lastSim = simRuns[simRuns.length - 1] ?? null;
  const activeSim = useMemo(
    () => simRuns.find((r) => r.id === simActiveRunId) ?? lastSim,
    [lastSim, simActiveRunId, simRuns],
  );
  const simSample = useMemo(
    () => (activeSim?.samples[Math.min(simPlaybackIndex, Math.max(0, (activeSim?.samples.length ?? 1) - 1))] ?? null),
    [activeSim, simPlaybackIndex],
  );
  const angle = mode === 'sim' ? (simSample?.ang ?? 0) : liveView.angle;
  const rawAngle = mode === 'sim' ? angle : liveView.raw;
  const setpoint = mode === 'sim' ? simSetpoint : liveView.set;
  const output = mode === 'sim' ? (simSample?.out ?? 0) : liveView.out;
  const modeLabel = mode === 'sim' ? 'SIMULATED' : liveView.mode;
  const outputPct = clamp((Math.abs(output) / outputLimit) * 100, 0, 100);

  const series = useMemo(() => {
    if (mode === 'sim' && activeSim) {
      const kf = activeSim.samples.map((s) => s.ang);
      const raw = activeSim.samples.map((s) => s.ang * 1.03);
      const set = activeSim.samples.map((s) => s.set);
      const out = activeSim.samples.map((s) => s.out);
      const maxAbs = Math.max(8, ...kf.map((v) => Math.abs(v)), ...set.map((v) => Math.abs(v)));
      const outAbs = Math.max(outputLimit, ...out.map((v) => Math.abs(v)));
      return { kf, raw, set, out, angleMin: -maxAbs, angleMax: maxAbs, outMin: -outAbs, outMax: outAbs };
    }

    const recent = imuHistory.slice(-64);
    if (recent.length > 1) {
      const kf = recent.map((s) => s.kf);
      const raw = recent.map((s) => s.raw);
      const out = recent.map((s) => s.out);
      const set = recent.map(() => liveView.set);
      const maxAbs = Math.max(8, ...kf.map((v) => Math.abs(v)), ...raw.map((v) => Math.abs(v)), ...set.map((v) => Math.abs(v)));
      const outAbs = Math.max(outputLimit, ...out.map((v) => Math.abs(v)));
      return { kf, raw, set, out, angleMin: -maxAbs, angleMax: maxAbs, outMin: -outAbs, outMax: outAbs };
    }

    return {
      kf: [liveView.angle, liveView.angle],
      raw: [liveView.raw, liveView.raw],
      set: [liveView.set, liveView.set],
      out: [liveView.out, liveView.out],
      angleMin: -10,
      angleMax: 10,
      outMin: -outputLimit,
      outMax: outputLimit,
    };
  }, [activeSim, imuHistory, liveView.angle, liveView.out, liveView.raw, liveView.set, mode, outputLimit]);

  useEffect(() => {
    if (mode !== 'sim' || !simPlaying || !activeSim || activeSim.samples.length <= 1) return;
    const id = window.setInterval(() => {
      setSimPlaybackIndex((prev) => {
        const next = prev + 1;
        if (next >= activeSim.samples.length) {
          window.clearInterval(id);
          setSimPlaying(false);
          return activeSim.samples.length - 1;
        }
        return next;
      });
    }, 40);
    return () => window.clearInterval(id);
  }, [activeSim, mode, simPlaying]);

  const angleSpark = useMemo(
    () => ({
      kf: sparkline(series.kf, series.angleMin, series.angleMax),
      raw: sparkline(series.raw, series.angleMin, series.angleMax),
      set: sparkline(series.set, series.angleMin, series.angleMax),
    }),
    [series],
  );
  const outSpark = useMemo(() => sparkline(series.out, series.outMin, series.outMax), [series]);

  const runTraceReplay = async () => {
    setTraceBusy(true);
    try {
      const out = await toolingTraceReplay({
        trace_path: tracePath,
        cmd_rmse_max: 6,
        cmd_abs_max: 20,
      });
      setTraceResult(out);
      setMsg(`Trace replay ${out.result?.pass ? 'PASS' : 'FAIL'}`, 'playground.trace');
    } catch (e) {
      setMsg(`Trace replay error: ${(e as Error).message}`, 'playground.trace');
    } finally {
      setTraceBusy(false);
    }
  };

  const runParamSweep = async () => {
    setSweepBusy(true);
    try {
      const out = await toolingParamSweep({
        kp_spec: kpSpec,
        ki_spec: kiSpec,
        kd_spec: kdSpec,
        settle_s: settleS,
        observe_s: observeS,
        rollback_on_fail: true,
        restore_baseline_at_end: true,
        max_candidates: 60,
      });
      setSweepResult(out);
      setMsg(`Sweep done: pass ${out.pass_count}/${out.candidate_count}`, 'playground.sweep');
    } catch (e) {
      setMsg(`Sweep error: ${(e as Error).message}`, 'playground.sweep');
    } finally {
      setSweepBusy(false);
    }
  };

  const doLiveAction = async (kind: 'prepare' | 'confirm' | 'disarm' | 'estop') => {
    if (!bridgeOnline) return;
    setLiveBusy(true);
    try {
      if (kind === 'prepare') {
        await armPrepare();
        setMsg('Playground: arm prepared', 'playground.live');
      } else if (kind === 'confirm') {
        await armConfirm();
        setMsg('Playground: arm confirmed', 'playground.live');
      } else if (kind === 'disarm') {
        await disarm();
        setMsg('Playground: disarmed', 'playground.live');
      } else {
        if (control.estop_latched) {
          await estopReset();
          setMsg('Playground: E-Stop reset', 'playground.live');
        } else {
          await estopLatch();
          setMsg('Playground: E-Stop latched', 'playground.live');
        }
      }
      await refreshBridge();
    } catch (e) {
      setMsg(`Playground live action error: ${(e as Error).message}`, 'playground.live');
    } finally {
      setLiveBusy(false);
    }
  };

  const runSimTest = (name: string) => {
    const next = runSim({
      name,
      kp: simKp,
      ki: simKi,
      kd: simKd,
      setpoint: simSetpoint,
      durationS: simDurationS,
      disturbance: simDisturbance,
    });
    setSimRuns((prev) => [...prev.slice(-1), next]);
    setSimActiveRunId(next.id);
    setSimPlaybackIndex(0);
    setSimPlaying(true);
    setMsg(`Sim ${name}: rmse=${next.metrics.rmse.toFixed(2)} overshoot=${next.metrics.overshoot.toFixed(2)}`, 'playground.sim');
  };

  const runSimPair = () => {
    const runA = runSim({
      name: 'A',
      kp: simKp,
      ki: simKi,
      kd: simKd,
      setpoint: simSetpoint,
      durationS: simDurationS,
      disturbance: Math.abs(simDisturbance),
    });
    const runB = runSim({
      name: 'B',
      kp: simKp,
      ki: simKi,
      kd: simKd,
      setpoint: simSetpoint,
      durationS: simDurationS,
      disturbance: -Math.abs(simDisturbance),
    });
    setSimRuns([runA, runB]);
    setSimActiveRunId(runB.id);
    setSimPlaybackIndex(0);
    setSimPlaying(true);
    setMsg('Sim A/B complete: back-to-back pair captured', 'playground.sim');
  };

  const runSurrogateSim = async () => {
    if (!simTrainingPaths.length) {
      setMsg('Select at least one training trace log first.', 'playground.sim');
      return;
    }
    setSurrogateBusy(true);
    try {
      const out = await toolingSurrogateSim({
        trace_paths: simTrainingPaths,
        kp: simKp,
        ki: simKi,
        kd: simKd,
        setpoint: simSetpoint,
        duration_s: simDurationS,
      });
      setSurrogateReport(out);
      if (out.ok && out.simulation) {
        const run: SimRun = {
          id: `surrogate-${Date.now()}`,
          name: 'Surrogate',
          params: {
            kp: simKp,
            ki: simKi,
            kd: simKd,
            setpoint: simSetpoint,
            durationS: simDurationS,
            disturbance: simDisturbance,
          },
          metrics: {
            rmse: out.simulation.metrics.rmse,
            overshoot: out.simulation.metrics.overshoot,
            settleS: out.simulation.metrics.settle_s,
            maxOutPct: out.simulation.metrics.max_out_pct,
          },
          samples: out.simulation.samples.map((s) => ({ t: s.t_s, ang: s.ang, out: s.out, set: s.set })),
        };
        setSimRuns((prev) => [...prev.slice(-1), run]);
        setSimActiveRunId(run.id);
        setSimPlaybackIndex(0);
        setSimPlaying(true);
        setMsg(`Surrogate sim done (confidence ${(100 * (out.model?.confidence ?? 0)).toFixed(0)}%)`, 'playground.sim');
      } else {
        setMsg(`Surrogate sim failed: ${out.error ?? 'unknown_error'}`, 'playground.sim');
      }
    } catch (e) {
      setMsg(`Surrogate sim error: ${(e as Error).message}`, 'playground.sim');
    } finally {
      setSurrogateBusy(false);
    }
  };

  const simCompare = useMemo(() => {
    if (simRuns.length < 2) return null;
    const a = simRuns[simRuns.length - 2];
    const b = simRuns[simRuns.length - 1];
    return {
      a,
      b,
      rmseDelta: b.metrics.rmse - a.metrics.rmse,
      overshootDelta: b.metrics.overshoot - a.metrics.overshoot,
      settleDelta: (b.metrics.settleS ?? simDurationS) - (a.metrics.settleS ?? simDurationS),
      outDelta: b.metrics.maxOutPct - a.metrics.maxOutPct,
    };
  }, [simDurationS, simRuns]);

  return (
    <div className="playground-grid">
      <section className="panel tool-panel">
        <div className="tool-panel-head">
          <div>
            <h3>{strings.playground.title}</h3>
            <span className="workflow-label">{strings.playground.subtitle}</span>
          </div>
        </div>
        <div className="tool-panel-body playground-body">
          <div className="playground-mode-toggle" role="tablist" aria-label="Playground model mode">
            <button className={`btn-sm ${mode === 'live' ? 'active' : ''}`} onClick={() => setMode('live')}>LIVE BALANCE MODEL</button>
            <button className={`btn-sm ${mode === 'sim' ? 'active' : ''}`} onClick={() => setMode('sim')}>SIM BOT SESSION</button>
          </div>

          <div className="playground-visual-grid">
            <div className="playground-robot-card">
              <div className="playground-card-head">
                <span className="action-rig-title">Live Balance Model</span>
                <span className={`badge ${Math.abs(angle) <= 6 ? 'ok' : Math.abs(angle) <= 12 ? 'warn' : 'bad'}`}>
                  {modeLabel}
                </span>
              </div>
              <div className="playground-robot-stage">
                <div className="playground-stage-grid" />
                <div className="playground-ground" />
                <div className="playground-setpoint-mark" style={{ left: `${50 + clamp(setpoint * 2.2, -24, 24)}%` }} />
                <div className="playground-motion-axis">
                  <span className={`playground-motion-chip ${output > 1 ? 'fwd' : output < -1 ? 'rev' : 'hold'}`}>
                    {output > 1 ? 'FWD ->' : output < -1 ? '<- REV' : 'HOLD'}
                  </span>
                </div>
                <div
                  className="playground-bot-wrap"
                  style={{ transform: `translateX(calc(-50% + ${clamp((output / outputLimit) * 18, -18, 18)}px)) rotate(${clamp(angle, -28, 28)}deg)` }}
                >
                  <div className="playground-bot-wheel" />
                  <div className="playground-bot-body" />
                  <div className="playground-bot-sensor" />
                </div>
              </div>
              <div className="playground-stat-row">
                <div className="playground-stat-tile">
                  <span className="k">Angle</span>
                  <strong>{angle.toFixed(2)} deg</strong>
                </div>
                <div className="playground-stat-tile">
                  <span className="k">Setpoint</span>
                  <strong>{setpoint.toFixed(2)} deg</strong>
                </div>
                <div className="playground-stat-tile">
                  <span className="k">Output</span>
                  <strong>{output.toFixed(1)} ({outputPct.toFixed(0)}%)</strong>
                </div>
              </div>
            </div>

            <div className="playground-gauge-card">
              <div className="playground-card-head">
                <span className="action-rig-title">Control Vector</span>
              </div>
              <div className="playground-gauge-list">
                <div className="playground-gauge-item">
                  <label>Output load</label>
                  <div className="playground-gauge-track">
                    <div className="playground-gauge-fill output" style={{ width: `${outputPct}%` }} />
                  </div>
                </div>
                <div className="playground-gauge-item">
                  <label>Kp {(mode === 'sim' ? simKp : pid.kp).toFixed(2)}</label>
                  <div className="playground-gauge-track">
                    <div className="playground-gauge-fill kp" style={{ width: `${clamp((((mode === 'sim' ? simKp : pid.kp) / 40) * 100), 0, 100)}%` }} />
                  </div>
                </div>
                <div className="playground-gauge-item">
                  <label>Ki {(mode === 'sim' ? simKi : pid.ki).toFixed(3)}</label>
                  <div className="playground-gauge-track">
                    <div className="playground-gauge-fill ki" style={{ width: `${clamp((((mode === 'sim' ? simKi : pid.ki) / 0.5) * 100), 0, 100)}%` }} />
                  </div>
                </div>
                <div className="playground-gauge-item">
                  <label>Kd {(mode === 'sim' ? simKd : pid.kd).toFixed(3)}</label>
                  <div className="playground-gauge-track">
                    <div className="playground-gauge-fill kd" style={{ width: `${clamp((((mode === 'sim' ? simKd : pid.kd) / 5) * 100), 0, 100)}%` }} />
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="playground-scope-grid">
            <div className="playground-scope-card">
              <div className="playground-card-head">
                <span className="action-rig-title">Angle Relationship</span>
              </div>
              <svg className="playground-scope" viewBox="0 0 640 140" role="img" aria-label="Angle relationship chart">
                <polyline className="scope-line set" points={angleSpark.set} />
                <polyline className="scope-line raw" points={angleSpark.raw} />
                <polyline className="scope-line kf" points={angleSpark.kf} />
              </svg>
            </div>
            <div className="playground-scope-card">
              <div className="playground-card-head">
                <span className="action-rig-title">Control Output Trend</span>
              </div>
              <svg className="playground-scope" viewBox="0 0 640 140" role="img" aria-label="Output trend chart">
                <polyline className="scope-line out" points={outSpark} />
              </svg>
            </div>
          </div>

          {mode === 'live' && (
            <div className="action-rig">
              <div className="action-rig-head">
                <span className="action-rig-title">Live Control Mirror (Playground)</span>
              </div>
              <div className="row action-rig-row playground-live-controls">
                <button className="btn-secondary btn-intent-safety" disabled={!bridgeOnline || control.estop_latched || liveBusy} onClick={() => void doLiveAction('prepare')}>Prepare Arm</button>
                <button className="btn-primary btn-intent-safety" disabled={!bridgeOnline || !control.arm_prepared || control.estop_latched || liveBusy} onClick={() => void doLiveAction('confirm')}>Confirm Arm</button>
                <button className="btn-secondary btn-intent-safety" disabled={!bridgeOnline || liveBusy} onClick={() => void doLiveAction('disarm')}>Disarm</button>
                <button className={control.estop_latched ? 'btn-secondary btn-intent-safety' : 'btn-danger btn-intent-safety'} disabled={!bridgeOnline || liveBusy} onClick={() => void doLiveAction('estop')}>
                  {control.estop_latched ? 'Reset E-Stop' : 'Latch E-Stop'}
                </button>
              </div>
            </div>
          )}

          {mode === 'sim' && (
            <div className="action-rig">
              <div className="action-rig-head">
                <span className="action-rig-title">Sim Session Controls (Detached from hardware)</span>
              </div>
              <div className="playground-trace-picker">
                <p className="playground-sim-help">Training logs (2-5 recommended):</p>
                <div className="playground-trace-list">
                  {traceList.slice(0, 12).map((p) => {
                    const checked = simTrainingPaths.includes(p);
                    return (
                      <label key={p} className="playground-trace-item">
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={(e) => {
                            setSimTrainingPaths((prev) => {
                              if (e.target.checked) {
                                if (prev.includes(p)) return prev;
                                return [...prev, p].slice(0, 5);
                              }
                              return prev.filter((x) => x !== p);
                            });
                          }}
                        />
                        <span>{p}</span>
                      </label>
                    );
                  })}
                </div>
              </div>
              <div className="row playground-sweep-row">
                <label className="playground-label">Kp<input type="number" step="0.1" value={simKp} onChange={(e) => setSimKp(Number(e.target.value) || 0)} /></label>
                <label className="playground-label">Ki<input type="number" step="0.01" value={simKi} onChange={(e) => setSimKi(Number(e.target.value) || 0)} /></label>
                <label className="playground-label">Kd<input type="number" step="0.01" value={simKd} onChange={(e) => setSimKd(Number(e.target.value) || 0)} /></label>
                <label className="playground-label">Setpoint deg<input type="number" step="0.1" value={simSetpoint} onChange={(e) => setSimSetpoint(Number(e.target.value) || 0)} /></label>
                <label className="playground-label">Duration s<input type="number" min={1} step="0.5" value={simDurationS} onChange={(e) => setSimDurationS(Math.max(1, Number(e.target.value) || 1))} /></label>
                <label className="playground-label">Disturbance<input type="number" step="0.5" value={simDisturbance} onChange={(e) => setSimDisturbance(Number(e.target.value) || 0)} /></label>
              </div>
              <div className="row action-rig-row">
                <button className="btn-secondary btn-sm" onClick={() => runSimTest('A')}>Run Sim Test</button>
                <button className="btn-primary btn-sm" onClick={runSimPair}>Run 2x Back-to-Back</button>
                <button className="btn-secondary btn-sm" onClick={() => void runSurrogateSim()} disabled={surrogateBusy || simTrainingPaths.length === 0}>
                  {surrogateBusy ? 'Calibrating...' : 'Run Log-Calibrated Sim'}
                </button>
              </div>
              {surrogateReport?.model && (
                <div className="compat-box">
                  <p><strong>Surrogate Confidence:</strong> {(surrogateReport.model.confidence * 100).toFixed(0)}%</p>
                  <p><strong>Distance From Known Gains:</strong> {surrogateReport.model.distance_from_known.toFixed(2)}</p>
                  <p><strong>Training Rows:</strong> {surrogateReport.model.sample_count} from {surrogateReport.model.log_count} logs</p>
                  {surrogateReport.model.warning && (
                    <p><strong>Warning:</strong> {surrogateReport.model.warning}</p>
                  )}
                </div>
              )}
              {simCompare && (
                <div className="compat-box playground-compare-box">
                  <p><strong>Latest Compare:</strong> {simCompare.a.name} {'->'} {simCompare.b.name}</p>
                  <p><strong>RMSE Δ:</strong> {simCompare.rmseDelta >= 0 ? '+' : ''}{simCompare.rmseDelta.toFixed(3)}</p>
                  <p><strong>Overshoot Δ:</strong> {simCompare.overshootDelta >= 0 ? '+' : ''}{simCompare.overshootDelta.toFixed(3)}</p>
                  <p><strong>Settle Δ (s):</strong> {simCompare.settleDelta >= 0 ? '+' : ''}{simCompare.settleDelta.toFixed(3)}</p>
                  <p><strong>Output Load Δ:</strong> {simCompare.outDelta >= 0 ? '+' : ''}{simCompare.outDelta.toFixed(1)}%</p>
                </div>
              )}
            </div>
          )}

          <div className="action-rig">
            <div className="action-rig-head">
              <span className="action-rig-title">{strings.playground.traceTitle}</span>
            </div>
            <div className="row">
              <label className="playground-label">
                Trace CSV
                <select value={tracePath} onChange={(e) => setTracePath(e.target.value)}>
                  {traceList.map((p) => (
                    <option key={p} value={p}>{p}</option>
                  ))}
                  {!traceList.length && (
                    <option value={tracePath}>{tracePath}</option>
                  )}
                </select>
              </label>
              <button className="btn-secondary btn-sm" onClick={runTraceReplay} disabled={!bridgeOnline || traceBusy}>
                {traceBusy ? 'Running...' : strings.playground.runTrace}
              </button>
            </div>
            {traceResult && (
              <div className="compat-box">
                <p><strong>Result:</strong> {traceResult.result?.pass ? 'PASS' : 'FAIL'}</p>
                <p><strong>RMSE command:</strong> {traceResult.result?.summary?.rmse_command?.toFixed?.(4) ?? 'n/a'}</p>
                <p><strong>Max abs error:</strong> {traceResult.result?.summary?.max_abs_command_error?.toFixed?.(4) ?? 'n/a'}</p>
              </div>
            )}
          </div>

          <div className="action-rig">
            <div className="action-rig-head">
              <span className="action-rig-title">{strings.playground.sweepTitle}</span>
            </div>
            <div className="row playground-sweep-row">
              <label className="playground-label">Kp Spec<input value={kpSpec} onChange={(e) => setKpSpec(e.target.value)} /></label>
              <label className="playground-label">Ki Spec<input value={kiSpec} onChange={(e) => setKiSpec(e.target.value)} /></label>
              <label className="playground-label">Kd Spec<input value={kdSpec} onChange={(e) => setKdSpec(e.target.value)} /></label>
              <label className="playground-label">Settle s<input type="number" step="0.5" min={0} value={settleS} onChange={(e) => setSettleS(Number(e.target.value) || 0)} /></label>
              <label className="playground-label">Observe s<input type="number" step="0.5" min={0.5} value={observeS} onChange={(e) => setObserveS(Number(e.target.value) || 0.5)} /></label>
              <button className="btn-primary btn-sm" onClick={runParamSweep} disabled={!bridgeOnline || sweepBusy}>
                {sweepBusy ? 'Sweeping...' : strings.playground.runSweep}
              </button>
            </div>
            {sweepResult && (
              <div className="compat-box">
                <p><strong>Summary:</strong> {sweepResult.best_candidate_summary ?? 'n/a'}</p>
                <p><strong>Pass Count:</strong> {sweepResult.pass_count}/{sweepResult.candidate_count}</p>
                {topSweep && (
                  <p>
                    <strong>Top Candidate:</strong> kp={String((topSweep as Record<string, unknown>).kp)} ki={String((topSweep as Record<string, unknown>).ki)} kd={String((topSweep as Record<string, unknown>).kd)}
                  </p>
                )}
              </div>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
