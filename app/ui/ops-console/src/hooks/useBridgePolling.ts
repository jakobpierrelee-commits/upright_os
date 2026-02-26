import { useEffect, useRef } from 'react';
import { getHealth, getStatus, heartbeat, type ActionGates } from '../api';
import type { ControlState, Health, Status } from '../types';

type ImuSample = {
  t: number;
  mode?: string;
  kf: number;
  raw: number;
  gyro: number;
  out: number;
  bridgeTxMs?: number | null;
};

type Params = {
  setHealth: (health: Health | null) => void;
  setBridgeOnline: (online: boolean) => void;
  setStatus: (status: Status) => void;
  setActionGates: (gates: ActionGates | null) => void;
  setControl: (control: ControlState) => void;
  setImuHistory: (next: (prev: ImuSample[]) => ImuSample[]) => void;
  initDraftsFromStatus: (status: Status) => void;
  runCompatProbe: () => void;
  setMsg: (msg: string, source?: string) => void;
  historyMax: number;
  n: (value: string | undefined, fallback?: number) => number;
};

export function useBridgePolling(params: Params) {
  const {
    setHealth,
    setBridgeOnline,
    setStatus,
    setActionGates,
    setControl,
    setImuHistory,
    initDraftsFromStatus,
    runCompatProbe,
    setMsg,
    historyMax,
    n,
  } = params;
  const draftsInitedRef = useRef(false);
  const compatRequestedRef = useRef(false);
  const initDraftsFromStatusRef = useRef(initDraftsFromStatus);
  const runCompatProbeRef = useRef(runCompatProbe);
  const setMsgRef = useRef(setMsg);
  const nRef = useRef(n);
  const historyMaxRef = useRef(historyMax);

  useEffect(() => {
    initDraftsFromStatusRef.current = initDraftsFromStatus;
  }, [initDraftsFromStatus]);

  useEffect(() => {
    runCompatProbeRef.current = runCompatProbe;
  }, [runCompatProbe]);

  useEffect(() => {
    setMsgRef.current = setMsg;
  }, [setMsg]);

  useEffect(() => {
    nRef.current = n;
  }, [n]);

  useEffect(() => {
    historyMaxRef.current = historyMax;
  }, [historyMax]);

  useEffect(() => {
    let mounted = true;
    let ws: WebSocket | null = null;
    let wsActive = false;
    let fallbackId: ReturnType<typeof setTimeout> | null = null;
    let healthId: ReturnType<typeof setTimeout> | null = null;
    let hbId: ReturnType<typeof setTimeout> | null = null;
    let lastErrorAt = 0;
    let healthFailures = 0;
    let lastHealthOkAt = 0;
    let lastMode = '';
    let wsRetryCount = 0;
    let wsRetryNotBefore = 0;
    const wsRetryBaseMs = 1000;
    const wsRetryMaxMs = 30_000;

    const scheduleWsReconnect = () => {
      wsRetryCount += 1;
      const expDelay = Math.min(wsRetryMaxMs, wsRetryBaseMs * (2 ** Math.min(wsRetryCount, 6)));
      const jitter = Math.floor(Math.random() * 250);
      wsRetryNotBefore = Date.now() + expDelay + jitter;
    };

    const healthIntervalMs = () => (document.hidden ? 10_000 : 3_000);
    const heartbeatIntervalMs = () => {
      const mode = String(lastMode || '').toUpperCase();
      const activelyControlling = mode === 'BALANCING' || mode === 'ARMED';
      if (activelyControlling) return document.hidden ? 2_500 : 1_000;
      return document.hidden ? 6_000 : 1_800;
    };
    const fallbackIntervalMs = () => (document.hidden ? 3_000 : 900);

    const processStatus = (status: Status, control?: ControlState, bridgeTxSeconds?: number | null) => {
      const bridgeTxMs =
        typeof bridgeTxSeconds === 'number' && Number.isFinite(bridgeTxSeconds)
          ? bridgeTxSeconds * 1000
          : null;
      setBridgeOnline(true);
      setStatus(status);
      lastMode = String(status.mode ?? '');
      setImuHistory((prev) => {
        const next = [...prev, {
          t: Date.now(),
          mode: String(status.mode ?? ''),
          kf: nRef.current(status.ang, 0),
          raw: nRef.current(status.raw, 0),
          gyro: nRef.current(status.gyro ?? status.gyr ?? status.gx, 0),
          out: nRef.current(status.out, 0),
          bridgeTxMs,
        }];
        if (next.length > historyMaxRef.current) next.splice(0, next.length - historyMaxRef.current);
        return next;
      });
      if (control) setControl(control);
      if (!draftsInitedRef.current) {
        initDraftsFromStatusRef.current(status);
        draftsInitedRef.current = true;
      }
      const hasCompatSignal =
        typeof status.mode === 'string' ||
        typeof status.ang === 'string' ||
        typeof status.raw === 'string' ||
        typeof status.gyro === 'string' ||
        typeof status.gyr === 'string' ||
        typeof status.gx === 'string';
      if (!compatRequestedRef.current && hasCompatSignal) {
        compatRequestedRef.current = true;
        runCompatProbeRef.current();
      }
    };

    const reportError = (err: unknown, source = 'bridge.poll') => {
      const now = Date.now();
      // Avoid flooding alert rail with identical bridge errors.
      if (now - lastErrorAt < 1200) return;
      lastErrorAt = now;
      setMsgRef.current(`bridge error: ${(err as Error).message}`, source);
    };

    const tickStatusFallback = async () => {
      try {
        const s = await getStatus();
        if (!mounted) return;
        processStatus(s.status, s.control, Date.now() / 1000);
        setActionGates(s.action_gates ?? null);
      } catch (e) {
        if (!mounted) return;
        reportError(e);
      }
    };

    const scheduleHealthTick = () => {
      if (!mounted) return;
      healthId = setTimeout(async () => {
        await refreshHealth();
        scheduleHealthTick();
      }, healthIntervalMs());
    };

    const scheduleHeartbeatTick = () => {
      if (!mounted) return;
      hbId = setTimeout(async () => {
        await heartbeatTick();
        scheduleHeartbeatTick();
      }, heartbeatIntervalMs());
    };

    const scheduleFallbackTick = () => {
      if (!mounted) return;
      fallbackId = setTimeout(async () => {
        // Keep action gates/control fresh even when telemetry websocket is active.
        await tickStatusFallback();
        scheduleFallbackTick();
      }, fallbackIntervalMs());
    };

    const refreshHealth = async () => {
      try {
        const h = await getHealth();
        if (!mounted) return;
        healthFailures = 0;
        lastHealthOkAt = Date.now();
        setBridgeOnline(true);
        setHealth(h.health);
        if (h.control) setControl(h.control);

        if (h.telemetry_enabled && h.telemetry_ws && !wsActive && !ws && Date.now() >= wsRetryNotBefore) {
          ws = new WebSocket(h.telemetry_ws);
          ws.onopen = () => {
            wsActive = true;
            wsRetryCount = 0;
            wsRetryNotBefore = 0;
          };
          ws.onmessage = (ev) => {
            if (!mounted) return;
            try {
              const payload = JSON.parse(String(ev.data)) as { ts?: number; status?: Status; control?: ControlState; error?: string };
              if (payload.control) setControl(payload.control);
              if (payload.status) processStatus(payload.status, payload.control, payload.ts);
            } catch {
              // ignore malformed ws payloads
            }
          };
          ws.onclose = () => {
            wsActive = false;
            ws = null;
            scheduleWsReconnect();
          };
          ws.onerror = () => {
            wsActive = false;
            if (ws) {
              try {
                ws.close();
              } catch {
                // ignore close errors
              }
            }
            ws = null;
            scheduleWsReconnect();
          };
        }
      } catch (e) {
        if (!mounted) return;
        healthFailures += 1;
        const staleMs = lastHealthOkAt > 0 ? Date.now() - lastHealthOkAt : Number.POSITIVE_INFINITY;
        // Prevent UI flapping to "offline" on a single transient poll failure.
        if (healthFailures >= 3 || staleMs > 5000) {
          setHealth(null);
          setBridgeOnline(false);
        }
        reportError(e, 'bridge.health');
      }
    };

    const heartbeatTick = async () => {
      try {
        const hb = await heartbeat();
        if (!mounted) return;
        setBridgeOnline(true);
        setControl(hb);
      } catch (e) {
        if (!mounted) return;
        reportError(e, 'bridge.heartbeat');
      }
    };

    void refreshHealth();
    void heartbeatTick();
    void tickStatusFallback();
    scheduleHealthTick();
    scheduleHeartbeatTick();
    scheduleFallbackTick();

    const onVisibilityChange = () => {
      if (!mounted || document.hidden) return;
      void refreshHealth();
      if (!wsActive) void tickStatusFallback();
    };
    document.addEventListener('visibilitychange', onVisibilityChange);

    return () => {
      mounted = false;
      document.removeEventListener('visibilitychange', onVisibilityChange);
      if (fallbackId) clearTimeout(fallbackId);
      if (healthId) clearTimeout(healthId);
      if (hbId) clearTimeout(hbId);
      if (ws) {
        try {
          ws.close();
        } catch {
          // ignore close errors
        }
      }
    };
  }, [setActionGates, setBridgeOnline, setControl, setHealth, setImuHistory, setStatus]);
}
