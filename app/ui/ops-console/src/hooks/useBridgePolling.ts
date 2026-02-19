import { useEffect, useRef } from 'react';
import { getHealth, getStatus, heartbeat } from '../api';
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

  useEffect(() => {
    let mounted = true;
    let ws: WebSocket | null = null;
    let wsActive = false;
    let fallbackId: ReturnType<typeof setInterval> | null = null;
    let healthId: ReturnType<typeof setInterval> | null = null;
    let hbId: ReturnType<typeof setInterval> | null = null;
    let lastErrorAt = 0;
    let healthFailures = 0;
    let lastHealthOkAt = 0;

    const processStatus = (status: Status, control?: ControlState, bridgeTxSeconds?: number | null) => {
      const bridgeTxMs =
        typeof bridgeTxSeconds === 'number' && Number.isFinite(bridgeTxSeconds)
          ? bridgeTxSeconds * 1000
          : null;
      setBridgeOnline(true);
      setStatus(status);
      setImuHistory((prev) => {
        const next = [...prev, {
          t: Date.now(),
          mode: String(status.mode ?? ''),
          kf: n(status.ang, 0),
          raw: n(status.raw, 0),
          gyro: n(status.gyro ?? status.gyr ?? status.gx, 0),
          out: n(status.out, 0),
          bridgeTxMs,
        }];
        if (next.length > historyMax) next.splice(0, next.length - historyMax);
        return next;
      });
      if (control) setControl(control);
      if (!draftsInitedRef.current) {
        initDraftsFromStatus(status);
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
        runCompatProbe();
      }
    };

    const reportError = (err: unknown, source = 'bridge.poll') => {
      const now = Date.now();
      // Avoid flooding alert rail with identical bridge errors.
      if (now - lastErrorAt < 1200) return;
      lastErrorAt = now;
      setMsg(`bridge error: ${(err as Error).message}`, source);
    };

    const tickStatusFallback = async () => {
      try {
        const s = await getStatus();
        if (!mounted) return;
        processStatus(s.status, s.control, Date.now() / 1000);
      } catch (e) {
        if (!mounted) return;
        reportError(e);
      }
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

        if (h.telemetry_enabled && h.telemetry_ws && !wsActive && !ws) {
          ws = new WebSocket(h.telemetry_ws);
          ws.onopen = () => {
            wsActive = true;
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
          };
          ws.onerror = () => {
            wsActive = false;
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

    healthId = setInterval(() => {
      void refreshHealth();
    }, 1500);

    hbId = setInterval(() => {
      void heartbeatTick();
    }, 800);

    // Keep a low-frequency HTTP fallback path in case websocket is unavailable.
    fallbackId = setInterval(() => {
      if (!wsActive) {
        void tickStatusFallback();
      }
    }, 450);

    return () => {
      mounted = false;
      if (fallbackId) clearInterval(fallbackId);
      if (healthId) clearInterval(healthId);
      if (hbId) clearInterval(hbId);
      if (ws) {
        try {
          ws.close();
        } catch {
          // ignore close errors
        }
      }
    };
  }, [
    historyMax,
    initDraftsFromStatus,
    n,
    runCompatProbe,
    setControl,
    setHealth,
    setImuHistory,
    setBridgeOnline,
    setMsg,
    setStatus,
  ]);
}
