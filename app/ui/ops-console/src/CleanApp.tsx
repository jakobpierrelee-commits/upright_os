import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  armPrecheck,
  armConfirm,
  armPrepare,
  disarm,
  estopLatch,
  estopReset,
  getHealth,
  getStatus,
  heartbeat,
} from './api';
import { cleanStatus } from './clean/cleanApi';
import { CleanIdeFirmwarePanel } from './clean/CleanIdeFirmwarePanel';
import { CodexPanelClean } from './clean/CodexPanelClean';
import type { ControlState, Health, Status } from './types';

type Action = {
  label: string;
  run: () => Promise<unknown>;
  className?: string;
  disabled?: boolean;
};

function v(status: Status, key: string): string {
  if (key === 'gyro') return String(status.gyro ?? status.gyr ?? status.gx ?? '-');
  return String(status[key] ?? '-');
}

function modeLabel(raw: unknown): string {
  const val = String(raw ?? '').trim().toLowerCase();
  if (!val || val === '-' || val === 'unknown') return 'Unknown';
  if (val === '0' || val === 'safe_idle' || val === 'idle') return 'Safe Idle';
  if (val === '1' || val === 'armed') return 'Armed';
  if (val === '2' || val === 'balancing' || val === 'run') return 'Balancing';
  if (val === '3' || val === 'estop') return 'E-Stop';
  return String(raw);
}

export default function CleanApp(): JSX.Element {
  const codexAnchorRef = useRef<HTMLElement | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [apiContractOk, setApiContractOk] = useState<boolean>(true);
  const [control, setControl] = useState<ControlState | null>(null);
  const [actionGates, setActionGates] = useState<Record<string, { ok: boolean; reasons: string[] }> | null>(null);
  const [status, setStatus] = useState<Status>({});
  const [busy, setBusy] = useState<boolean>(false);
  const [msg, setMsg] = useState<string>('Clean console ready');
  const [globalDock, setGlobalDock] = useState<{
    level: 'ok' | 'warn' | 'fail';
    summary: string;
    source: string;
    ts: number;
  }>({
    level: 'warn',
    summary: 'Waiting for first Codex update',
    source: 'codex',
    ts: Date.now(),
  });

  const refresh = useCallback(async () => {
    await heartbeat().catch(() => undefined);
    const [h, st, clean] = await Promise.all([getHealth(), getStatus(), cleanStatus('app_dev')]);
    const cleanVersion = Number(clean.clean_api?.version ?? 0);
    const caps = clean.clean_api?.capabilities ?? [];
    const contractOk = cleanVersion >= 2 && caps.includes('firmware_upload_precheck') && caps.includes('clean_chat_stream');
    setHealth(h.health);
    setApiContractOk(contractOk);
    setStatus(st.status ?? {});
    setControl(st.control ?? null);
    setActionGates((st.action_gates as Record<string, { ok: boolean; reasons: string[] }>) ?? null);
    setGlobalDock((prev) => {
      if (h.health?.connected) return prev;
      return {
        level: 'warn',
        summary: 'Bridge disconnected',
        source: 'bridge',
        ts: Date.now(),
      };
    });
  }, []);

  useEffect(() => {
    void refresh();
    const id = window.setInterval(() => {
      void refresh().catch(() => undefined);
    }, 1200);
    return () => window.clearInterval(id);
  }, [refresh]);

  const runAction = useCallback(async (label: string, fn: () => Promise<unknown>) => {
    if (busy) return;
    setBusy(true);
    try {
      await fn();
      setMsg(`${label}: ok`);
    } catch (err) {
      setMsg(`${label}: ${String(err)}`);
    } finally {
      setBusy(false);
      await refresh().catch(() => undefined);
    }
  }, [busy, refresh]);

  const actions: Action[] = useMemo(() => [
    {
      label: 'Pre-Arm Check',
      run: async () => {
        const onStand = window.confirm('Safety gate: Is the robot lifted / on a stand with wheels free?');
        if (!onStand) {
          throw new Error('Place robot on stand/lift first, then rerun Pre-Arm Check.');
        }
        const first = await armPrecheck({
          bot_on_stand_ok: onStand,
          auto_wheel_probe: true,
          auto_estop_probe: true,
        });
        if (first.ok) return;

        const prearmCheck = (first.prearm_check ?? {}) as { motor_test_supported?: unknown; checks?: unknown };
        const motorTestSupported = Boolean(prearmCheck.motor_test_supported);

        if (!motorTestSupported) {
          const left = window.confirm('Firmware lacks MOTOR_TEST. Confirm LEFT wheel pulse was observed.');
          const right = window.confirm('Confirm RIGHT wheel pulse was observed.');
          const manual = await armPrecheck({
            bot_on_stand_ok: onStand,
            left_wheel_pulse_ok: left,
            right_wheel_pulse_ok: right,
            auto_wheel_probe: false,
            auto_estop_probe: true,
          });
          if (manual.ok) return;
          const checks = Array.isArray((manual.prearm_check as { checks?: unknown })?.checks)
            ? ((manual.prearm_check as { checks?: Array<{ id?: unknown; status?: unknown; detail?: unknown }> }).checks ?? [])
            : [];
          const firstFail = checks.find((c) => String(c?.status ?? '') === 'fail');
          throw new Error(
            `Pre-Arm failed: ${String((manual.prearm_check as { summary?: unknown })?.summary ?? 'safety checks failed')}`
            + (firstFail ? ` (${String(firstFail.id ?? 'check')}: ${String(firstFail.detail ?? 'failed')})` : ''),
          );
        }

        const checks = Array.isArray(prearmCheck.checks)
          ? (prearmCheck.checks as Array<{ id?: unknown; status?: unknown; detail?: unknown }>)
          : [];
        const firstFail = checks.find((c) => String(c?.status ?? '') === 'fail');
        throw new Error(
          `Pre-Arm failed: ${String((first.prearm_check as { summary?: unknown })?.summary ?? 'safety checks failed')}`
          + (firstFail ? ` (${String(firstFail.id ?? 'check')}: ${String(firstFail.detail ?? 'failed')})` : ''),
        );
      },
    },
    { label: 'Prepare Arm', run: armPrepare, disabled: Boolean(control?.estop_latched) || actionGates?.arm_prepare?.ok === false },
    { label: 'Confirm Arm', run: armConfirm, disabled: !Boolean(control?.arm_prepared) || Boolean(control?.estop_latched) || actionGates?.arm_confirm?.ok === false },
    { label: 'Disarm', run: disarm, className: 'clean-btn-alt' },
    { label: 'E-Stop', run: estopLatch, className: 'clean-btn-danger' },
    { label: 'Reset E-Stop', run: estopReset, className: 'clean-btn-alt' },
  ], [actionGates?.arm_confirm?.ok, actionGates?.arm_prepare?.ok, control?.arm_prepared, control?.estop_latched]);

  return (
    <div className="clean-shell">
      <header className="clean-topbar">
        <div className="clean-brand">UPRIGHT.OS CLEAN CONSOLE</div>
        <div className={`clean-pill ${!health?.connected ? 'bad' : (apiContractOk ? 'ok' : 'warn')}`}>
          {!health?.connected ? 'DISCONNECTED' : (apiContractOk ? 'CONNECTED' : 'CONNECTED (LEGACY API)')}
        </div>
      </header>
      <div className="clean-startup-lock-banner" role="status" aria-live="polite">
        CLEAN LANE LOCKED: 127.0.0.1 (line 8797)
      </div>
      <div className="clean-startup-launch-mode" role="status" aria-live="polite">
        BRIDGE LAUNCH MODE: ISOLATED (IDE-SAFE DEFAULT)
      </div>

      <main className="clean-grid">
        <div className="clean-left-column">
          <section className="clean-card clean-gradient">
            <div className="clean-card-head">
              <h2>Live Telemetry</h2>
              <button className="clean-link" onClick={() => void refresh()} disabled={busy}>Refresh</button>
            </div>
            <div className="clean-metrics">
              <div><span>Mode</span><strong>{modeLabel(status.mode)}</strong></div>
              <div><span>Angle</span><strong>{v(status, 'ang')}</strong></div>
              <div><span>Raw</span><strong>{v(status, 'raw')}</strong></div>
              <div><span>Gyro</span><strong>{v(status, 'gyro')}</strong></div>
              <div><span>Output</span><strong>{v(status, 'out')}</strong></div>
              <div><span>E-Stop</span><strong>{control?.estop_latched ? 'Latched' : 'Clear'}</strong></div>
            </div>
            <div className="clean-subtle">{msg}</div>
          </section>

          <section className="clean-card clean-gradient">
            <div className="clean-card-head">
              <h2>Command Rail</h2>
            </div>
            <div className="clean-actions">
              {actions.map((a) => (
                <button
                  key={a.label}
                  className={`clean-btn ${a.className ?? ''}`}
                  disabled={busy || Boolean(a.disabled)}
                  onClick={() => void runAction(a.label, a.run)}
                >
                  {a.label}
                </button>
              ))}
            </div>
          </section>

          <CleanIdeFirmwarePanel
            mode="app_dev"
            onGlobalStatus={(evt) => {
              setGlobalDock({
                level: evt.level,
                summary: evt.summary,
                source: evt.source,
                ts: evt.ts,
              });
            }}
          />
        </div>

        <section className="clean-codex" ref={codexAnchorRef}>
          <CodexPanelClean
            mode="app_dev"
            onGlobalStatus={(evt) => {
              setGlobalDock({
                level: evt.level,
                summary: evt.summary,
                source: evt.source,
                ts: evt.ts,
              });
            }}
          />
        </section>
      </main>
      <button
        className={`clean-global-dock ${globalDock.level}`}
        onClick={() => codexAnchorRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })}
        title="Open Codex status in panel"
      >
        <span className="label">{globalDock.level.toUpperCase()}</span>
        <span className="text">{globalDock.summary}</span>
        <span className="meta">
          {globalDock.source} · {new Date(globalDock.ts).toLocaleTimeString()}
        </span>
      </button>
    </div>
  );
}
