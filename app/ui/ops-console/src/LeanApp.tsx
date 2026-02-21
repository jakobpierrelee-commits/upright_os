import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  armConfirm,
  armPrepare,
  calZero,
  disarm,
  estopLatch,
  estopReset,
  firmwareBoards,
  firmwareStatus,
  firmwareUploadGuarded,
  getHealth,
  getLines,
  getStatus,
  postCommand,
  probeCompat,
  probeConnect,
  type CompatReport,
  type ConnectProbeReport,
  type FirmwareBoards,
  type FirmwareStatus,
} from './api';
import type { ControlState, Health, Status } from './types';

const REQUIRED_STATUS_KEYS = ['mode', 'ang', 'raw', 'gyro', 'out', 'kp', 'ki', 'kd', 'set'] as const;

function s(status: Status, key: string): string {
  if (key === 'gyro') {
    const gyro = status.gyro ?? status.gyr ?? status.gx;
    return String(gyro ?? '');
  }
  return String(status[key] ?? '');
}

export default function LeanApp(): JSX.Element {
  const [health, setHealth] = useState<Health | null>(null);
  const [control, setControl] = useState<ControlState | null>(null);
  const [status, setStatus] = useState<Status>({});
  const [lines, setLines] = useState<string[]>([]);
  const [compat, setCompat] = useState<CompatReport | null>(null);
  const [connect, setConnect] = useState<ConnectProbeReport | null>(null);
  const [msg, setMsg] = useState<string>('lean console ready');
  const [busy, setBusy] = useState<boolean>(false);

  const [boards, setBoards] = useState<FirmwareBoards | null>(null);
  const [fw, setFw] = useState<FirmwareStatus | null>(null);
  const [sketch, setSketch] = useState<string>('/Users/jvke/Documents/UpRight.os-lean/app/bridge/firmware_templates/profiled_runtime_v1');
  const [fqbn, setFqbn] = useState<string>('arduino:avr:nano:cpu=atmega328old');
  const [port, setPort] = useState<string>('/dev/cu.usbserial-2210');

  const refreshCore = useCallback(async () => {
    try {
      const [h, st, ln, fws] = await Promise.all([
        getHealth(),
        getStatus(),
        getLines(50),
        firmwareStatus(),
      ]);
      setHealth(h.health);
      setStatus(st.status ?? {});
      setControl(st.control ?? null);
      setLines(ln);
      setFw(fws);
    } catch (err) {
      setMsg(`refresh failed: ${String(err)}`);
    }
  }, []);

  const refreshBoards = useCallback(async () => {
    try {
      const b = await firmwareBoards();
      setBoards(b);
      if (b.recommended_port) setPort(b.recommended_port);
      if (b.recommended_fqbn) setFqbn(b.recommended_fqbn);
    } catch (err) {
      setMsg(`boards failed: ${String(err)}`);
    }
  }, []);

  useEffect(() => {
    void refreshCore();
    void refreshBoards();
    const id = window.setInterval(() => { void refreshCore(); }, 700);
    return () => window.clearInterval(id);
  }, [refreshCore, refreshBoards]);

  const withBusy = useCallback(async (label: string, fn: () => Promise<void>) => {
    if (busy) return;
    setBusy(true);
    try {
      await fn();
      setMsg(`${label}: ok`);
    } catch (err) {
      setMsg(`${label}: ${String(err)}`);
    } finally {
      setBusy(false);
      await refreshCore();
    }
  }, [busy, refreshCore]);

  const requiredMissing = useMemo(() => REQUIRED_STATUS_KEYS.filter((k) => !s(status, k)), [status]);
  const leanCompatOk = Boolean(compat?.ok) && compat?.profile === 'lean_v1';
  const armPrepareBlockedReasons = useMemo(() => {
    const reasons: string[] = [];
    if (!leanCompatOk) reasons.push('lean compat not passed');
    if (requiredMissing.length) reasons.push(`missing status keys: ${requiredMissing.join(', ')}`);
    if (control?.estop_latched) reasons.push('estop latched');
    return reasons;
  }, [leanCompatOk, requiredMissing, control?.estop_latched]);
  const armPrepareEnabled = armPrepareBlockedReasons.length === 0;
  const armConfirmBlockedReasons = useMemo(() => {
    const reasons: string[] = [];
    if (!leanCompatOk) reasons.push('lean compat not passed');
    if (requiredMissing.length) reasons.push(`missing status keys: ${requiredMissing.join(', ')}`);
    if (control?.estop_latched) reasons.push('estop latched');
    if (!control?.arm_prepared) reasons.push('arm not prepared');
    return reasons;
  }, [leanCompatOk, requiredMissing, control?.estop_latched, control?.arm_prepared]);
  const armConfirmEnabled = armConfirmBlockedReasons.length === 0;

  return (
    <div className="app-shell app-rebuild tab-tune theme-midnight surface-floating">
      <div className="topbar">
        <div className="brand">
          <strong>UPRIGHT.OS LEAN CONSOLE</strong>
        </div>
        <div className="topbar-status">{health?.connected ? 'CONNECTED' : 'DISCONNECTED'}</div>
      </div>

      <main className="ops-main-grid">
        <section className="panel tool-panel">
          <div className="tool-panel-head"><h2>Telemetry</h2></div>
          <div className="tool-panel-body">
            <div className="status-grid">
              <div><span className="telemetry-label">Port:</span> <span className="telemetry-field">{health?.port ?? '-'}</span></div>
              <div><span className="telemetry-label">Mode:</span> <span className="telemetry-field">{s(status, 'mode') || '-'}</span></div>
              <div><span className="telemetry-label">Angle:</span> <span className="telemetry-field">{s(status, 'ang') || '-'}</span></div>
              <div><span className="telemetry-label">Raw:</span> <span className="telemetry-field">{s(status, 'raw') || '-'}</span></div>
              <div><span className="telemetry-label">Gyro:</span> <span className="telemetry-field">{s(status, 'gyro') || '-'}</span></div>
              <div><span className="telemetry-label">Out:</span> <span className="telemetry-field">{s(status, 'out') || '-'}</span></div>
            </div>
            <div className="status-grid">
              <div><span className="telemetry-label">KP:</span> <span className="telemetry-field">{s(status, 'kp') || '-'}</span></div>
              <div><span className="telemetry-label">KI:</span> <span className="telemetry-field">{s(status, 'ki') || '-'}</span></div>
              <div><span className="telemetry-label">KD:</span> <span className="telemetry-field">{s(status, 'kd') || '-'}</span></div>
              <div><span className="telemetry-label">Set:</span> <span className="telemetry-field">{s(status, 'set') || '-'}</span></div>
              <div><span className="telemetry-label">E-Stop:</span> <span className="telemetry-field">{control?.estop_latched ? 'LATCHED' : 'CLEAR'}</span></div>
              <div><span className="telemetry-label">Arm Prepared:</span> <span className="telemetry-field">{control?.arm_prepared ? 'YES' : 'NO'}</span></div>
            </div>
            <p className="hint">Missing required status keys: {requiredMissing.length ? requiredMissing.join(', ') : 'none'}</p>
            <div className="btn-row">
              <button className="btn-sm" disabled={busy} onClick={() => void refreshCore()}>Refresh</button>
              <button className="btn-sm" disabled={busy} onClick={() => void withBusy('probe connect', async () => { setConnect(await probeConnect()); })}>Probe Connect</button>
              <button className="btn-sm" disabled={busy} onClick={() => void withBusy('probe compat', async () => { setCompat(await probeCompat('lean_v1')); })}>Probe Compat</button>
            </div>
            <pre className="serial-console">{lines.join('\n')}</pre>
          </div>
        </section>

        <section className="panel tool-panel">
          <div className="tool-panel-head"><h2>Controls</h2></div>
          <div className="tool-panel-body">
            <div className="btn-row">
              <button className="btn-sm btn-arm" disabled={busy || !armPrepareEnabled} onClick={() => void withBusy('prepare arm', async () => { await armPrepare(); })}>Prepare Arm</button>
              <button className="btn-sm btn-arm" disabled={busy || !armConfirmEnabled} onClick={() => void withBusy('confirm arm', async () => { await armConfirm(); })}>Confirm Arm</button>
              <button className="btn-sm btn-disarm" disabled={busy} onClick={() => void withBusy('disarm', async () => { await disarm(); })}>Disarm</button>
              <button className="btn-sm btn-danger" disabled={busy} onClick={() => void withBusy('estop', async () => { await estopLatch(); })}>E-Stop</button>
              <button className="btn-sm" disabled={busy} onClick={() => void withBusy('reset estop', async () => { await estopReset(); })}>Reset E-Stop</button>
              <button className="btn-sm" disabled={busy} onClick={() => void withBusy('cal zero', async () => { await calZero(); })}>Cal Zero</button>
              <button className="btn-sm" disabled={busy} onClick={() => void withBusy('clear fault', async () => { await postCommand('FAULTCLR', 'OK FAULTCLR', 2.0); })}>Clear Fault</button>
            </div>
            <p className="hint">
              Arm prepare gate: {armPrepareEnabled ? 'ready' : armPrepareBlockedReasons.join(' | ')}
            </p>
            <p className="hint">
              Arm confirm gate: {armConfirmEnabled ? 'ready' : armConfirmBlockedReasons.join(' | ')}
            </p>
            <p className="hint">{msg}</p>
            <pre className="serial-console">{JSON.stringify({ connect, compat }, null, 2)}</pre>
          </div>
        </section>

        <section className="panel tool-panel">
          <div className="tool-panel-head"><h2>Firmware</h2></div>
          <div className="tool-panel-body">
            <div className="control-grid">
              <label>Sketch</label>
              <input value={sketch} onChange={(e) => setSketch(e.target.value)} />
              <label>FQBN</label>
              <input value={fqbn} onChange={(e) => setFqbn(e.target.value)} />
              <label>Port</label>
              <input value={port} onChange={(e) => setPort(e.target.value)} />
            </div>
            <div className="btn-row">
              <button className="btn-sm" disabled={busy} onClick={() => void refreshBoards()}>Detect Boards</button>
              <button className="btn-sm" disabled={busy} onClick={() => void withBusy('guarded upload', async () => { setFw(await firmwareUploadGuarded(sketch, fqbn, port)); })}>Upload Guarded</button>
            </div>
            <pre className="serial-console">{JSON.stringify({ boards, firmware: fw }, null, 2)}</pre>
          </div>
        </section>
      </main>
    </div>
  );
}
