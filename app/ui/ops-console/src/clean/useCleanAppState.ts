import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  armConfirm,
  armPrecheck,
  armPrepare,
  calZero,
  defaultCfg,
  disarm,
  estopLatch,
  estopReset,
  getHealth,
  getStatus,
  heartbeat,
  imuCalibrate,
  imuInfo,
  imuLoad,
  imuSave,
  loadCfg,
  saveCfg,
} from '../api';
import { cleanStatus } from './cleanApi';
import type { CleanAction, CleanAppState } from './cleanAppTypes';

type PrearmCheck = {
  summary?: unknown;
  motor_test_supported?: unknown;
  checks?: unknown;
};

type PrearmCheckResult = {
  id?: unknown;
  status?: unknown;
  detail?: unknown;
};

function firstPrearmFailure(check: PrearmCheck): PrearmCheckResult | null {
  const checks = Array.isArray(check.checks) ? (check.checks as PrearmCheckResult[]) : [];
  return checks.find((entry) => String(entry?.status ?? '') === 'fail') ?? null;
}

function prearmError(prefix: string, check: PrearmCheck): Error {
  const fail = firstPrearmFailure(check);
  const summary = String(check.summary ?? 'safety checks failed');
  if (!fail) return new Error(`${prefix}: ${summary}`);
  return new Error(
    `${prefix}: ${summary} (${String(fail.id ?? 'check')}: ${String(fail.detail ?? 'failed')})`,
  );
}

export function useCleanAppState(): CleanAppState {
  const [health, setHealth] = useState<CleanAppState['health']>(null);
  const [apiContractOk, setApiContractOk] = useState<boolean>(true);
  const [control, setControl] = useState<CleanAppState['control']>(null);
  const [actionGates, setActionGates] = useState<CleanAppState['actionGates']>(null);
  const [status, setStatus] = useState<CleanAppState['status']>({});
  const [busy, setBusy] = useState<boolean>(false);
  const [msg, setMsg] = useState<string>('Clean console ready');
  const [globalDock, setGlobalDock] = useState<CleanAppState['globalDock']>({
    level: 'warn',
    summary: 'Waiting for first Codex update',
    source: 'codex',
    ts: Date.now(),
  });

  const refresh = useCallback(async () => {
    await heartbeat().catch(() => undefined);
    const [h, st, clean] = await Promise.all([getHealth(), getStatus(), cleanStatus('app_dev')]);
    const cleanVersion = Number(clean.clean_api?.version ?? 0);
    const capabilities = clean.clean_api?.capabilities ?? [];
    const contractOk = cleanVersion >= 2
      && capabilities.includes('firmware_upload_precheck')
      && capabilities.includes('clean_chat_stream');

    setHealth(h.health);
    setApiContractOk(contractOk);
    setStatus(st.status ?? {});
    setControl(st.control ?? null);
    setActionGates(st.action_gates ?? null);
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

  const runAction = useCallback(
    async (label: string, fn: () => Promise<unknown>) => {
      if (busy) return;
      setBusy(true);
      try {
        await fn();
        setMsg(`${label}: ok`);
      } catch (err) {
        const em = String(err ?? '');
        if (em.includes('imu_commands_unsupported')) {
          setMsg(
            `${label}: IMU calibration commands are not available on current firmware. Flash updated runtime first.`,
          );
        } else if (em.includes('imu_eeprom_unavailable')) {
          setMsg(
            `${label}: IMU offset persistence is unavailable on current firmware build (EEPROM storage disabled).`,
          );
        } else {
          setMsg(`${label}: ${em}`);
        }
      } finally {
        setBusy(false);
        await refresh().catch(() => undefined);
      }
    },
    [busy, refresh],
  );

  const actions: CleanAction[] = useMemo(
    () => [
      {
        label: 'Pre-Arm Check',
        run: async () => {
          const onStand = window.confirm(
            'Safety gate: Is the robot lifted / on a stand with wheels free?',
          );
          if (!onStand) {
            throw new Error('Place robot on stand/lift first, then rerun Pre-Arm Check.');
          }

          const first = await armPrecheck({
            bot_on_stand_ok: onStand,
            auto_wheel_probe: true,
            auto_estop_probe: true,
          });
          if (first.ok) return;

          const firstCheck = (first.prearm_check ?? {}) as PrearmCheck;
          if (!Boolean(firstCheck.motor_test_supported)) {
            const left = window.confirm(
              'Firmware lacks MOTOR_TEST. Confirm LEFT wheel pulse was observed.',
            );
            const right = window.confirm('Confirm RIGHT wheel pulse was observed.');
            const manual = await armPrecheck({
              bot_on_stand_ok: onStand,
              left_wheel_pulse_ok: left,
              right_wheel_pulse_ok: right,
              auto_wheel_probe: false,
              auto_estop_probe: true,
            });
            if (manual.ok) return;
            throw prearmError('Pre-Arm failed', (manual.prearm_check ?? {}) as PrearmCheck);
          }

          throw prearmError('Pre-Arm failed', firstCheck);
        },
      },
      {
        label: 'Prepare Arm',
        run: armPrepare,
        disabled: Boolean(control?.estop_latched) || actionGates?.arm_prepare?.ok === false,
      },
      {
        label: 'Confirm Arm',
        run: armConfirm,
        disabled:
          !Boolean(control?.arm_prepared)
          || Boolean(control?.estop_latched)
          || actionGates?.arm_confirm?.ok === false,
      },
      { label: 'Disarm', run: disarm, className: 'clean-btn-alt' },
      {
        label: 'Cal Zero + Save',
        run: async () => {
          const ok = window.confirm(
            'Run CAL ZERO now? Keep robot upright and stationary until complete.',
          );
          if (!ok) return;
          await calZero();
          await saveCfg();
        },
        className: 'clean-btn-alt',
        disabled: actionGates?.cal_zero?.ok === false,
      },
      {
        label: 'Save Config',
        run: saveCfg,
        className: 'clean-btn-alt',
      },
      {
        label: 'IMU Calibrate',
        run: async () => {
          const ok = window.confirm(
            'Run IMU CAL now? Keep robot flat/still and disarmed until complete.',
          );
          if (!ok) return;
          await imuCalibrate();
        },
        className: 'clean-btn-alt',
        disabled: actionGates?.cal_zero?.ok === false,
      },
      {
        label: 'IMU Load',
        run: async () => {
          await imuLoad();
        },
        className: 'clean-btn-alt',
      },
      {
        label: 'IMU Save',
        run: async () => {
          await imuSave();
        },
        className: 'clean-btn-alt',
      },
      {
        label: 'IMU Info',
        run: async () => {
          await imuInfo();
        },
        className: 'clean-btn-alt',
      },
      {
        label: 'Load Config',
        run: async () => {
          const ok = window.confirm(
            'Load saved config from controller memory now?',
          );
          if (!ok) return;
          await loadCfg();
        },
        className: 'clean-btn-alt',
      },
      {
        label: 'Default Config',
        run: async () => {
          const ok = window.confirm(
            'Reset controller config to defaults now? This overwrites saved values on device.',
          );
          if (!ok) return;
          await defaultCfg();
        },
        className: 'clean-btn-alt',
      },
      { label: 'E-Stop', run: estopLatch, className: 'clean-btn-danger' },
      { label: 'Reset E-Stop', run: estopReset, className: 'clean-btn-alt' },
    ],
    [
      actionGates?.arm_confirm?.ok,
      actionGates?.arm_prepare?.ok,
      actionGates?.cal_zero?.ok,
      control?.arm_prepared,
      control?.estop_latched,
    ],
  );

  const onGlobalStatus = useCallback((evt: CleanAppState['globalDock']) => {
    setGlobalDock({
      level: evt.level,
      summary: evt.summary,
      source: evt.source,
      ts: evt.ts,
    });
  }, []);

  return {
    health,
    apiContractOk,
    control,
    actionGates,
    status,
    busy,
    msg,
    actions,
    globalDock,
    refresh,
    runAction,
    onGlobalStatus,
  };
}
