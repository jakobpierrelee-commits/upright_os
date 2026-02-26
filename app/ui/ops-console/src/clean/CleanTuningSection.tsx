import { useEffect, useMemo, useState } from 'react';
import {
  cleanBurstArm,
  cleanBurstLabel,
  cleanBurstStatus,
  cleanRecoverRearm,
  cleanSetpointSave,
  cleanFailureDetailFromError,
  type CleanBurstStatus,
  type CleanMode,
  type CleanRunIntent,
} from './cleanApi';

type CleanTuningSectionProps = {
  mode: CleanMode;
  onRefreshStatus: () => void;
};

function toneFromState(state: string): 'good' | 'warn' | 'bad' {
  const v = String(state ?? '').toLowerCase();
  if (v.includes('fail') || v.includes('error')) return 'bad';
  if (v.includes('capture') || v.includes('arm') || v.includes('queue')) return 'warn';
  return 'good';
}

export function CleanTuningSection({
  mode,
  onRefreshStatus,
}: CleanTuningSectionProps): JSX.Element {
  const [burstInfo, setBurstInfo] = useState<CleanBurstStatus | null>(null);
  const [delayMs, setDelayMs] = useState(30000);
  const [lines, setLines] = useState(220);
  const [freqHz, setFreqHz] = useState(25);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState('Ready');
  const [runIntent, setRunIntent] = useState<CleanRunIntent>('unassisted_tuning');
  const [changedParam, setChangedParam] = useState('setpoint');
  const [operatorOutcome, setOperatorOutcome] = useState('unknown');
  const [operatorAssisted, setOperatorAssisted] = useState(false);
  const [operatorNotes, setOperatorNotes] = useState('');
  const [setpointDeg, setSetpointDeg] = useState(0);
  const [chkBattery, setChkBattery] = useState(false);
  const [chkSlack, setChkSlack] = useState(false);
  const [chkRunway, setChkRunway] = useState(false);
  const [chkUpright, setChkUpright] = useState(false);

  const checklistReady = chkBattery && chkSlack && chkRunway && chkUpright;

  const refreshBurst = async (): Promise<void> => {
    const next = await cleanBurstStatus();
    setBurstInfo(next);
  };

  const armBurst = async (): Promise<void> => {
    if (!checklistReady) {
      setMsg('Pre-release checklist incomplete; arm blocked.');
      return;
    }
    if (!changedParam.trim() || changedParam === 'none') {
      setMsg('Single-variable lock: select exactly one changed parameter.');
      return;
    }
    setBusy(true);
    try {
      const next = await cleanBurstArm(
        delayMs,
        lines,
        freqHz,
        true,
        80,
        3.0,
        0.35,
        0.06,
        140,
        runIntent,
        [changedParam],
        operatorOutcome,
        operatorAssisted,
        operatorNotes,
      );
      setBurstInfo(next);
      setMsg(
        `Burst armed: delay=${delayMs}ms lines=${lines} freq=${freqHz.toFixed(
          1,
        )}Hz trigger=angle3.0/out0.35/runaway0.06`,
      );
    } catch (err) {
      setMsg(cleanFailureDetailFromError('generic', err));
    } finally {
      setBusy(false);
    }
  };

  const applyRunLabel = async (): Promise<void> => {
    setBusy(true);
    try {
      const next = await cleanBurstLabel(
        operatorOutcome,
        operatorAssisted,
        operatorNotes,
        runIntent,
        [changedParam],
      );
      setBurstInfo(next);
      setMsg(`Run label saved: outcome=${operatorOutcome} assisted=${operatorAssisted ? 'yes' : 'no'}`);
    } catch (err) {
      setMsg(cleanFailureDetailFromError('generic', err));
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    void refreshBurst().catch(() => {});
  }, []);

  const liveHostState = String(burstInfo?.host_capture?.state ?? '').toLowerCase();

  useEffect(() => {
    if (!liveHostState || !['armed', 'capturing'].includes(liveHostState)) return;
    const timer = window.setInterval(() => {
      void refreshBurst().catch(() => {});
    }, 800);
    return () => window.clearInterval(timer);
  }, [liveHostState]);

  const progress = useMemo(() => {
    const rows = Number(burstInfo?.host_capture?.rows ?? 0);
    const target = Number(burstInfo?.host_capture?.target_lines ?? 0);
    return target > 0 ? Math.max(0, Math.min(100, (rows / target) * 100)) : 0;
  }, [burstInfo]);

  const tone = toneFromState(String(burstInfo?.state ?? 'idle'));
  const recentEvents = burstInfo?.events_recent ?? [];

  const recoverRearm = async (): Promise<void> => {
    setBusy(true);
    try {
      const res = await cleanRecoverRearm();
      if (res.ok) {
        setMsg('Recover + Re-arm: OK');
      } else {
        const bad = res.steps.filter((s) => !s.ok).map((s) => `${s.cmd}:${s.detail}`).join(' | ');
        setMsg(`Recover + Re-arm failed: ${bad || 'unknown'}`);
      }
      await refreshBurst();
      onRefreshStatus();
    } catch (err) {
      setMsg(cleanFailureDetailFromError('generic', err));
    } finally {
      setBusy(false);
    }
  };

  const applySetpointSave = async (): Promise<void> => {
    setBusy(true);
    try {
      const saved = await cleanSetpointSave(setpointDeg);
      setMsg(`Setpoint saved: set=${saved.set} set_eff=${saved.set_eff}`);
      onRefreshStatus();
    } catch (err) {
      setMsg(cleanFailureDetailFromError('generic', err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="clean-card clean-gradient clean-tuning-panel">
      <div className="clean-card-head">
        <h2>Tuning + Burst Capture</h2>
        <div className="clean-tuning-head-actions">
          <button className="clean-link" onClick={onRefreshStatus} disabled={busy}>Refresh Status</button>
          <button className="clean-link" onClick={() => void refreshBurst()} disabled={busy}>Refresh Burst</button>
        </div>
      </div>

      <div className="clean-subtle">
        Temporary test rig for burst capture and quick runtime markers in <strong>{mode}</strong>.
      </div>

      <div className={`burst-rig tone-${tone}`}>
        <div className="burst-rig-head">
          <span className="burst-rig-title">Burst Capture Rig</span>
          <span className={`hud-pill ${tone}`}>{burstInfo?.state ?? 'idle'}</span>
        </div>
        <div className="row burst-controls-row clean-tuning-controls">
          <label>
            Setpoint (deg)
            <input
              type="number"
              min={-30}
              max={30}
              step={0.01}
              value={setpointDeg}
              onChange={(e) => setSetpointDeg(Number(e.target.value) || 0)}
            />
          </label>
          <button className="clean-btn clean-btn-compact" onClick={() => void applySetpointSave()} disabled={busy}>
            Setpoint + Save
          </button>
          <label>
            Run Intent
            <select value={runIntent} onChange={(e) => setRunIntent(e.target.value as CleanRunIntent)}>
              <option value="unassisted_tuning">unassisted_tuning</option>
              <option value="assisted_safety_catch">assisted_safety_catch</option>
              <option value="bench_test">bench_test</option>
            </select>
          </label>
          <label>
            Changed Parameter (single)
            <select value={changedParam} onChange={(e) => setChangedParam(e.target.value)}>
              <option value="setpoint">setpoint</option>
              <option value="pid">pid</option>
              <option value="limits">limits</option>
              <option value="motion">motion</option>
              <option value="firmware">firmware</option>
              <option value="none">none</option>
            </select>
          </label>
          <button className="clean-btn clean-btn-compact" onClick={() => void recoverRearm()} disabled={busy}>
            Recover + Re-arm
          </button>
        </div>
        <div className="row burst-controls-row clean-tuning-controls clean-check-grid">
          <label className="check-item clean-check-item">
            <input type="checkbox" checked={chkBattery} onChange={(e) => setChkBattery(e.target.checked)} />
            battery connected
          </label>
          <label className="check-item clean-check-item">
            <input type="checkbox" checked={chkSlack} onChange={(e) => setChkSlack(e.target.checked)} />
            cable slack ready
          </label>
          <label className="check-item clean-check-item">
            <input type="checkbox" checked={chkRunway} onChange={(e) => setChkRunway(e.target.checked)} />
            clear runway
          </label>
          <label className="check-item clean-check-item">
            <input type="checkbox" checked={chkUpright} onChange={(e) => setChkUpright(e.target.checked)} />
            upright hold confirmed
          </label>
        </div>
        <div className="row burst-controls-row clean-tuning-controls">
          <label>
            Burst Delay ms
            <input
              type="number"
              min={0}
              step={100}
              value={delayMs}
              onChange={(e) => setDelayMs(Math.max(0, Number(e.target.value) || 0))}
            />
          </label>
          <label>
            Burst Lines
            <input
              type="number"
              min={1}
              step={10}
              value={lines}
              onChange={(e) => setLines(Math.max(1, Number(e.target.value) || 1))}
            />
          </label>
          <label>
            Burst Freq Hz
            <input
              type="number"
              min={1}
              max={100}
              step={0.5}
              value={freqHz}
              onChange={(e) => setFreqHz(Math.max(1, Math.min(100, Number(e.target.value) || 1)))}
            />
          </label>
          <button className="clean-btn clean-btn-compact" onClick={() => void armBurst()} disabled={busy}>
            Arm Capture
          </button>
        </div>
        <div className="burst-progress" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(progress)}>
          <svg className="burst-progress-svg" viewBox="0 0 100 10" preserveAspectRatio="none" aria-hidden="true" focusable="false">
            <defs>
              <linearGradient id="burstBeamGradientCleanTune" x1="0" y1="0" x2="1" y2="0">
                <stop offset="0%" stopColor="var(--burst-beam-stop-0)" />
                <stop offset="50%" stopColor="var(--burst-beam-stop-1)" />
                <stop offset="100%" stopColor="var(--burst-beam-stop-2)" />
              </linearGradient>
            </defs>
            <rect className="burst-progress-track" x={0} y={0} width={100} height={10} rx={2} ry={2} />
            <rect className="burst-progress-fill" x={0} y={0} width={progress} height={10} rx={2} ry={2} fill="url(#burstBeamGradientCleanTune)" />
          </svg>
        </div>
        <p className="burst-rig-status">
          {burstInfo
            ? `host=${burstInfo.host_capture.state} (${burstInfo.host_capture.rows}/${burstInfo.host_capture.target_lines}) @ ${(burstInfo.host_capture.freq_hz ?? freqHz).toFixed(1)}Hz`
            : 'No burst status yet'}
        </p>
        {burstInfo?.host_capture?.latest_summary && (
          <>
            <p className="burst-event-chip">
              diagnosis={String((burstInfo.host_capture.latest_summary as Record<string, unknown>).diagnosis ?? 'n/a')}
            </p>
            <p className="burst-event-chip">
              run_valid_for_tuning={
                String((burstInfo.host_capture.latest_summary as Record<string, unknown>).run_valid_for_tuning ?? 'false')
              }
            </p>
            <p className="burst-event-chip">
              invalid_reasons={
                JSON.stringify((burstInfo.host_capture.latest_summary as Record<string, unknown>).run_invalid_reasons ?? [])
              }
            </p>
          </>
        )}
        {burstInfo?.last_event && <p className="burst-event-chip">{burstInfo.last_event}</p>}
      </div>

      <div className="clean-tuning-events">
        <h3>Run Label (Hard Gate Input)</h3>
        <div className="row burst-controls-row clean-tuning-controls">
          <label>
            Outcome
            <select value={operatorOutcome} onChange={(e) => setOperatorOutcome(e.target.value)}>
              <option value="unknown">unknown</option>
              <option value="stable_window">stable_window</option>
              <option value="runaway_forward_saved">runaway_forward_saved</option>
              <option value="runaway_backward_saved">runaway_backward_saved</option>
              <option value="fell_forward">fell_forward</option>
              <option value="fell_backward">fell_backward</option>
            </select>
          </label>
          <label>
            Assisted
            <select value={operatorAssisted ? 'yes' : 'no'} onChange={(e) => setOperatorAssisted(e.target.value === 'yes')}>
              <option value="no">no</option>
              <option value="yes">yes</option>
            </select>
          </label>
          <label>
            Notes
            <input
              type="text"
              value={operatorNotes}
              onChange={(e) => setOperatorNotes(e.target.value)}
              placeholder="cable catch, floor hit, battery miss, etc."
            />
          </label>
          <button className="clean-btn clean-btn-compact" onClick={() => void applyRunLabel()} disabled={busy}>
            Apply Run Label
          </button>
        </div>
      </div>

      <div className="clean-tuning-events">
        <h3>Recent Burst Events</h3>
        {recentEvents.length === 0 && <div className="clean-subtle">No events yet</div>}
        {recentEvents.map((evt, idx) => (
          <div key={`${idx}-${evt}`} className="clean-tuning-event-row">{evt}</div>
        ))}
      </div>

      <div className="clean-subtle">{msg}</div>
    </section>
  );
}
