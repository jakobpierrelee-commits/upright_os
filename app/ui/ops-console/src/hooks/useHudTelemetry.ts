import { useEffect, useMemo, useRef, useState } from 'react';
import type { Status } from '../types';

export type ImuSample = {
  t: number;
  mode?: string;
  kf: number;
  raw: number;
  gyro: number;
  out: number;
  bridgeTxMs?: number | null;
};

type HudTone = 'good' | 'warn' | 'bad' | 'unknown';

export type HudCard = {
  id:
    | 'filteredAngle'
    | 'rawAngle'
    | 'gyroRate'
    | 'output'
    | 'wheelPos'
    | 'setpoint'
    | 'pidError'
    | 'innovation'
    | 'clampState'
    | 'loopFeed'
    | 'contract';
  label: string;
  value: string;
  unit: string;
  tone: HudTone;
  detail?: string;
};

type SmoothedHud = {
  angle: number;
  rawAngle: number;
  gyroRate: number;
  output: number;
};

function clamp(v: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, v));
}

function n(v: string | undefined, fallback = 0): number {
  const parsed = Number.parseFloat(v ?? '');
  return Number.isFinite(parsed) ? parsed : fallback;
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

function seriesPointsFromValues(values: number[], minY: number, maxY: number): string {
  if (values.length <= 1) return '';
  const w = 820;
  const h = 160;
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

function calcKalmanReference(samples: ImuSample[]): number[] {
  if (samples.length === 0) return [];
  if (samples.length === 1) return [samples[0].raw];

  // Conservative defaults for a UI-side reference estimator.
  const qAngle = 0.001;
  const qBias = 0.003;
  const rMeasure = 0.03;

  let angle = samples[0].raw;
  let bias = 0;
  let p00 = 1;
  let p01 = 0;
  let p10 = 0;
  let p11 = 1;

  const out: number[] = [angle];

  for (let i = 1; i < samples.length; i += 1) {
    const prevT = samples[i - 1].t;
    const currT = samples[i].t;
    const rawDt = (currT - prevT) / 1000;
    const dt = Number.isFinite(rawDt) && rawDt > 0 ? clamp(rawDt, 0.005, 0.5) : 0.25;

    const rate = samples[i].gyro - bias;
    angle += dt * rate;

    p00 += dt * (dt * p11 - p01 - p10 + qAngle);
    p01 -= dt * p11;
    p10 -= dt * p11;
    p11 += qBias * dt;

    const innovation = samples[i].raw - angle;
    const s = p00 + rMeasure;
    const k0 = p00 / s;
    const k1 = p10 / s;

    angle += k0 * innovation;
    bias += k1 * innovation;

    const nextP00 = p00;
    const nextP01 = p01;
    p00 -= k0 * nextP00;
    p01 -= k0 * nextP01;
    p10 -= k1 * nextP00;
    p11 -= k1 * nextP01;

    out.push(angle);
  }

  return out;
}

export function useHudTelemetry(status: Status, imuHistory: ImuSample[], labels: {
  filteredAngle: string;
  rawAngle: string;
  gyroRate: string;
  output: string;
  wheelPos: string;
  setpoint: string;
  pidError: string;
  innovation: string;
  clampState: string;
  loopFeed: string;
  contract: string;
  contractOk: string;
  contractMissing: string;
}, healthLastStatusAgeMs?: number | null) {
  const latestImuSample = useMemo(() => {
    if (!imuHistory.length) return null;
    return imuHistory[imuHistory.length - 1];
  }, [imuHistory]);
  const [smoothedHud, setSmoothedHud] = useState<SmoothedHud | null>(null);
  const smoothedHudRef = useRef<SmoothedHud | null>(null);

  useEffect(() => {
    if (!latestImuSample) {
      setSmoothedHud(null);
      smoothedHudRef.current = null;
      return;
    }
    const target: SmoothedHud = {
      angle: latestImuSample.kf,
      rawAngle: latestImuSample.raw,
      gyroRate: latestImuSample.gyro,
      output: latestImuSample.out,
    };

    const start = smoothedHudRef.current ?? target;
    const durationMs = 220;
    const startAt = performance.now();
    let rafId = 0;

    const tick = (now: number) => {
      const p = clamp((now - startAt) / durationMs, 0, 1);
      // cosine ease-in-out for a "breathing" but responsive blend
      const eased = 0.5 - 0.5 * Math.cos(Math.PI * p);
      const next: SmoothedHud = {
        angle: start.angle + (target.angle - start.angle) * eased,
        rawAngle: start.rawAngle + (target.rawAngle - start.rawAngle) * eased,
        gyroRate: start.gyroRate + (target.gyroRate - start.gyroRate) * eased,
        output: start.output + (target.output - start.output) * eased,
      };
      smoothedHudRef.current = next;
      setSmoothedHud(next);
      if (p < 1) {
        rafId = window.requestAnimationFrame(tick);
      }
    };

    rafId = window.requestAnimationFrame(tick);
    return () => window.cancelAnimationFrame(rafId);
  }, [latestImuSample]);

  const kalmanReference = useMemo(() => calcKalmanReference(imuHistory), [imuHistory]);

  const chartBounds = useMemo(() => {
    if (imuHistory.length === 0) return { min: -10, max: 10 };
    const maxAbs = Math.max(
      5,
      ...imuHistory.map((sample) => Math.abs(sample.kf)),
      ...imuHistory.map((sample) => Math.abs(sample.raw)),
      ...kalmanReference.map((value) => Math.abs(value)),
    );
    return { min: -maxAbs, max: maxAbs };
  }, [imuHistory, kalmanReference]);

  const chartPointsKf = useMemo(() => seriesPoints(imuHistory, (sample) => sample.kf, chartBounds.min, chartBounds.max), [imuHistory, chartBounds.max, chartBounds.min]);
  const chartPointsRaw = useMemo(() => seriesPoints(imuHistory, (sample) => sample.raw, chartBounds.min, chartBounds.max), [imuHistory, chartBounds.max, chartBounds.min]);
  const chartPointsRef = useMemo(() => seriesPointsFromValues(kalmanReference, chartBounds.min, chartBounds.max), [kalmanReference, chartBounds.max, chartBounds.min]);

  const angleDelta = useMemo(() => {
    if (imuHistory.length < 2) return 0;
    const current = smoothedHud?.angle ?? imuHistory[imuHistory.length - 1].kf;
    return current - imuHistory[imuHistory.length - 2].kf;
  }, [imuHistory, smoothedHud?.angle]);

  const outputDelta = useMemo(() => {
    if (imuHistory.length < 2) return 0;
    const current = smoothedHud?.output ?? imuHistory[imuHistory.length - 1].out;
    return current - imuHistory[imuHistory.length - 2].out;
  }, [imuHistory, smoothedHud?.output]);

  const hud = useMemo(() => {
    const angle = smoothedHud?.angle ?? n(status.ang, 0);
    const rawAngle = smoothedHud?.rawAngle ?? n(status.raw, 0);
    const output = smoothedHud?.output ?? n(status.out, 0);
    const voltageRaw = n(status.volRaw, 0);
    return { angle, rawAngle, output, voltageRaw };
  }, [smoothedHud, status]);

  const outputLimit = useMemo(() => {
    const candidates = [status.outMax, status.out_max];
    for (const candidate of candidates) {
      if (candidate == null) continue;
      const parsed = Number.parseFloat(String(candidate));
      if (Number.isFinite(parsed) && parsed > 0) return parsed;
    }
    return null as number | null;
  }, [status.outMax, status.out_max]);

  const outputNormBase = outputLimit ?? 120;
  const hasOutput = Object.prototype.hasOwnProperty.call(status, 'out');

  const outputPercent = useMemo(() => {
    if (!hasOutput || outputNormBase <= 0) return null as number | null;
    return clamp((Math.abs(hud.output) / outputNormBase) * 100, 0, 100);
  }, [hasOutput, hud.output, outputNormBase]);

  const armedSessionPeakPct = useMemo(() => {
    if (imuHistory.length === 0 || outputNormBase <= 0) return null as number | null;
    let end = -1;
    for (let i = imuHistory.length - 1; i >= 0; i -= 1) {
      if (String(imuHistory[i].mode ?? '').toUpperCase() === 'BALANCING') {
        end = i;
        break;
      }
    }
    if (end < 0) return null as number | null;
    let start = end;
    for (let i = end - 1; i >= 0; i -= 1) {
      if (String(imuHistory[i].mode ?? '').toUpperCase() !== 'BALANCING') break;
      start = i;
    }
    const segment = imuHistory.slice(start, end + 1);
    if (!segment.length) return null as number | null;
    return Math.max(...segment.map((s) => clamp((Math.abs(s.out) / outputNormBase) * 100, 0, 100)));
  }, [imuHistory, outputNormBase]);

  const outputAlertLevel = useMemo(() => {
    if (outputPercent == null) return null as 'high' | 'caution' | null;
    const peak = Math.max(outputPercent, armedSessionPeakPct ?? 0);
    if (peak >= 95) return 'caution';
    if (peak >= 75) return 'high';
    return null;
  }, [armedSessionPeakPct, outputPercent]);

  const angleDialPct = clamp(Math.abs(hud.angle) / 20, 0, 1);
  const rawAngleDialPct = clamp(Math.abs(hud.rawAngle) / 20, 0, 1);
  const outputDialPct = clamp(Math.abs(hud.output) / outputNormBase, 0, 1);
  const voltageDialPct = clamp((hud.voltageRaw - 120) / 120, 0, 1);

  const requiredInputState = useMemo(() => {
    const hasAng = Object.prototype.hasOwnProperty.call(status, 'ang');
    const hasRaw = Object.prototype.hasOwnProperty.call(status, 'raw');
    const hasGyro = ['gyro', 'gyr', 'gx'].some((k) => Object.prototype.hasOwnProperty.call(status, k));
    return {
      hasAng,
      hasRaw,
      hasGyro,
      ok: hasAng && hasRaw && hasGyro,
    };
  }, [status]);

  const hasSetpoint = Object.prototype.hasOwnProperty.call(status, 'set');
  const setpointNum = hasSetpoint ? n(status.set, 0) : null;
  const hasPidErr = Object.prototype.hasOwnProperty.call(status, 'pid_err') || Object.prototype.hasOwnProperty.call(status, 'err');
  const pidErr = hasPidErr
    ? n(status.pid_err ?? status.err, 0)
    : (setpointNum != null ? setpointNum - hud.angle : null);

  const hasInnovation = Object.prototype.hasOwnProperty.call(status, 'kal_innov') || Object.prototype.hasOwnProperty.call(status, 'innovation');
  const innovation = hasInnovation
    ? n(status.kal_innov ?? status.innovation, 0)
    : (requiredInputState.hasRaw && requiredInputState.hasAng ? hud.rawAngle - hud.angle : null);

  const hasUnsat = Object.prototype.hasOwnProperty.call(status, 'pid_u_unsat') || Object.prototype.hasOwnProperty.call(status, 'pid_u') || Object.prototype.hasOwnProperty.call(status, 'u');
  const hasSat = Object.prototype.hasOwnProperty.call(status, 'pid_u_sat') || Object.prototype.hasOwnProperty.call(status, 'out');
  const uUnsat = hasUnsat ? n(status.pid_u_unsat ?? status.pid_u ?? status.u, 0) : null;
  const uSat = hasSat ? n(status.pid_u_sat ?? status.out, 0) : null;
  const hasSatFlag = Object.prototype.hasOwnProperty.call(status, 'output_saturated');
  const saturatedFlag = hasSatFlag ? String(status.output_saturated).toLowerCase() === '1' || String(status.output_saturated).toLowerCase() === 'true' : false;
  const clampDelta = (uUnsat != null && uSat != null) ? Math.abs(uUnsat - uSat) : null;
  const clampTone: HudTone = (() => {
    if (clampDelta == null && !hasSatFlag) return 'unknown';
    if (saturatedFlag || (clampDelta != null && clampDelta >= 6.0)) return 'bad';
    if (clampDelta != null && clampDelta >= 1.0) return 'warn';
    return 'good';
  })();
  const clampDetail = uUnsat != null && uSat != null
    ? `u_unsat:${uUnsat.toFixed(1)} | u_sat:${uSat.toFixed(1)}`
    : (hasSatFlag ? `output_saturated:${saturatedFlag ? '1' : '0'}` : 'n/a');

  const sampleRateHz = useMemo(() => {
    if (imuHistory.length < 4) return 0;
    const take = imuHistory.slice(-20);
    const dtMs = take[take.length - 1].t - take[0].t;
    if (dtMs <= 0) return 0;
    return ((take.length - 1) * 1000) / dtMs;
  }, [imuHistory]);

  const liveTelemetryDecayMs = useMemo(() => {
    if (typeof healthLastStatusAgeMs === 'number' && Number.isFinite(healthLastStatusAgeMs)) {
      return Math.max(0, healthLastStatusAgeMs);
    }
    const lastT = imuHistory[imuHistory.length - 1]?.t;
    if (!lastT) return null as number | null;
    return Math.max(0, Date.now() - lastT);
  }, [healthLastStatusAgeMs, imuHistory]);

  const livePerceivedDecayMs = useMemo(() => {
    if (imuHistory.length < 2) return liveTelemetryDecayMs;
    const ANGLE_EVENT_DEG = 0.08;
    const GYRO_EVENT_DPS = 1.2;
    const OUTPUT_EVENT_UNITS = 0.8;

    let eventTs: number | null = null;
    for (let i = imuHistory.length - 1; i > 0; i -= 1) {
      const cur = imuHistory[i];
      const prev = imuHistory[i - 1];
      const isEvent =
        Math.abs(cur.kf - prev.kf) >= ANGLE_EVENT_DEG ||
        Math.abs(cur.raw - prev.raw) >= ANGLE_EVENT_DEG ||
        Math.abs(cur.gyro - prev.gyro) >= GYRO_EVENT_DPS ||
        Math.abs(cur.out - prev.out) >= OUTPUT_EVENT_UNITS;
      if (isEvent) {
        eventTs = (typeof cur.bridgeTxMs === 'number' && Number.isFinite(cur.bridgeTxMs)) ? cur.bridgeTxMs : cur.t;
        break;
      }
    }
    if (eventTs == null) {
      const last = imuHistory[imuHistory.length - 1];
      eventTs = (typeof last.bridgeTxMs === 'number' && Number.isFinite(last.bridgeTxMs)) ? last.bridgeTxMs : last.t;
    }
    if (!Number.isFinite(eventTs)) return liveTelemetryDecayMs;
    return Math.max(0, Date.now() - eventTs);
  }, [imuHistory, liveTelemetryDecayMs]);

  const sourceDecayBucketRef = useRef({ sum: 0, count: 0 });
  const perceivedDecayBucketRef = useRef({ sum: 0, count: 0 });
  const [telemetryDecayMs, setTelemetryDecayMs] = useState<number | null>(null);
  const [perceivedDecayMs, setPerceivedDecayMs] = useState<number | null>(null);

  useEffect(() => {
    if (liveTelemetryDecayMs == null) return;
    sourceDecayBucketRef.current.sum += liveTelemetryDecayMs;
    sourceDecayBucketRef.current.count += 1;
    if (telemetryDecayMs == null) setTelemetryDecayMs(liveTelemetryDecayMs);
  }, [liveTelemetryDecayMs, telemetryDecayMs]);

  useEffect(() => {
    if (livePerceivedDecayMs == null) return;
    perceivedDecayBucketRef.current.sum += livePerceivedDecayMs;
    perceivedDecayBucketRef.current.count += 1;
    if (perceivedDecayMs == null) setPerceivedDecayMs(livePerceivedDecayMs);
  }, [livePerceivedDecayMs, perceivedDecayMs]);

  useEffect(() => {
    const id = setInterval(() => {
      const source = sourceDecayBucketRef.current;
      if (source.count > 0) {
        setTelemetryDecayMs(source.sum / source.count);
        sourceDecayBucketRef.current = { sum: 0, count: 0 };
      }
      const perceived = perceivedDecayBucketRef.current;
      if (perceived.count > 0) {
        setPerceivedDecayMs(perceived.sum / perceived.count);
        perceivedDecayBucketRef.current = { sum: 0, count: 0 };
      }
    }, 10_000);
    return () => clearInterval(id);
  }, []);

  const gyroRate = useMemo(() => {
    if (smoothedHud) return smoothedHud.gyroRate;
    const raw = status.gyro ?? status.gyr ?? status.gx;
    if (raw == null) return null;
    const parsed = Number.parseFloat(String(raw));
    return Number.isFinite(parsed) ? parsed : null;
  }, [smoothedHud, status.gx, status.gyro, status.gyr]);

  const loopFeedRates5m = useMemo(() => {
    if (imuHistory.length < 3) return [] as number[];
    const latestT = imuHistory[imuHistory.length - 1].t;
    const windowStart = latestT - (5 * 60 * 1000);
    const windowSamples = imuHistory.filter((s) => s.t >= windowStart);
    if (windowSamples.length < 3) return [] as number[];
    const rates: number[] = [];
    for (let i = 1; i < windowSamples.length; i += 1) {
      const dt = windowSamples[i].t - windowSamples[i - 1].t;
      if (dt > 0) rates.push(1000 / dt);
    }
    return rates;
  }, [imuHistory]);

  // Freeze avg updates to 10s cadence for readability.
  const avg5mBucket10s = useMemo(() => {
    const latestT = imuHistory[imuHistory.length - 1]?.t ?? Date.now();
    return Math.floor(latestT / 10_000);
  }, [imuHistory]);

  const loopFeedAvg5mHz = useMemo(() => {
    if (!loopFeedRates5m.length) return null as number | null;
    return loopFeedRates5m.reduce((sum, r) => sum + r, 0) / loopFeedRates5m.length;
  }, [avg5mBucket10s]);

  const loopFeedMin5mHz = useMemo(() => {
    if (!loopFeedRates5m.length) return null as number | null;
    return Math.min(...loopFeedRates5m);
  }, [loopFeedRates5m]);

  const outputSessionStats = useMemo(() => {
    if (outputLimit == null || outputLimit <= 0 || imuHistory.length === 0) {
      return { meanPct: null as number | null, maxPct: null as number | null };
    }

    // Find the most recent COMPLETED BALANCING segment:
    // mode BALANCING followed by a non-BALANCING sample (disarmed/exited).
    let end = -1;
    for (let i = imuHistory.length - 2; i >= 0; i -= 1) {
      const curBal = String(imuHistory[i].mode ?? '').toUpperCase() === 'BALANCING';
      const nextBal = String(imuHistory[i + 1].mode ?? '').toUpperCase() === 'BALANCING';
      if (curBal && !nextBal) {
        end = i;
        break;
      }
    }
    if (end < 0) return { meanPct: null as number | null, maxPct: null as number | null };

    let start = end;
    for (let i = end - 1; i >= 0; i -= 1) {
      if (String(imuHistory[i].mode ?? '').toUpperCase() !== 'BALANCING') break;
      start = i;
    }

    const segment = imuHistory.slice(start, end + 1);
    if (!segment.length) return { meanPct: null as number | null, maxPct: null as number | null };

    const percents = segment.map((s) => clamp((Math.abs(s.out) / outputLimit) * 100, 0, 100));
    const meanPct = percents.reduce((sum, p) => sum + p, 0) / percents.length;
    const maxPct = Math.max(...percents);
    return { meanPct, maxPct };
  }, [imuHistory, outputLimit]);

  const loopFeedQuality = useMemo(() => {
    if (sampleRateHz <= 0) return 'n/a';
    if (sampleRateHz < 20) return 'LOW';
    if (sampleRateHz <= 44) return 'SUFFICIENT';
    return 'OPTIMAL';
  }, [sampleRateHz]);

  const cards = useMemo<HudCard[]>(() => ([
    { id: 'filteredAngle', label: labels.filteredAngle, value: hud.angle.toFixed(3), unit: 'deg', tone: requiredInputState.hasAng ? 'good' : 'bad' },
    { id: 'rawAngle', label: labels.rawAngle, value: hud.rawAngle.toFixed(3), unit: 'deg', tone: requiredInputState.hasRaw ? 'good' : 'bad' },
    { id: 'gyroRate', label: labels.gyroRate, value: gyroRate != null ? gyroRate.toFixed(3) : 'n/a', unit: 'dps', tone: requiredInputState.hasGyro ? 'good' : 'bad' },
    {
      id: 'output',
      label: labels.output,
      value: outputPercent != null ? outputPercent.toFixed(0) : 'n/a',
      unit: '%',
      tone: outputPercent == null ? 'unknown' : (outputAlertLevel === 'caution' ? 'bad' : outputAlertLevel === 'high' ? 'warn' : 'good'),
    },
    { id: 'wheelPos', label: labels.wheelPos, value: status.wpos ?? 'n/a', unit: '', tone: 'unknown' },
    { id: 'setpoint', label: labels.setpoint, value: status.set ?? 'n/a', unit: 'deg', tone: 'unknown' },
    {
      id: 'pidError',
      label: labels.pidError,
      value: pidErr != null ? pidErr.toFixed(3) : 'n/a',
      unit: 'deg',
      tone: pidErr == null ? 'unknown' : Math.abs(pidErr) >= 12 ? 'bad' : Math.abs(pidErr) >= 4 ? 'warn' : 'good',
    },
    {
      id: 'innovation',
      label: labels.innovation,
      value: innovation != null ? innovation.toFixed(3) : 'n/a',
      unit: 'deg',
      tone: innovation == null ? 'unknown' : Math.abs(innovation) >= 12 ? 'bad' : Math.abs(innovation) >= 5 ? 'warn' : 'good',
    },
    {
      id: 'clampState',
      label: labels.clampState,
      value: clampTone === 'unknown' ? 'n/a' : clampTone === 'good' ? 'tracking' : clampTone === 'warn' ? 'partial' : 'clamped',
      unit: '',
      tone: clampTone,
      detail: clampDetail,
    },
    {
      id: 'loopFeed',
      label: labels.loopFeed,
      value: sampleRateHz > 0 ? sampleRateHz.toFixed(1) : 'n/a',
      unit: 'Hz',
      tone: sampleRateHz <= 0 ? 'bad' : sampleRateHz < 20 ? 'bad' : sampleRateHz <= 44 ? 'warn' : 'good',
    },
    { id: 'contract', label: labels.contract, value: requiredInputState.ok ? labels.contractOk : labels.contractMissing, unit: '', tone: requiredInputState.ok ? 'good' : 'bad' },
  ]), [clampDetail, clampTone, gyroRate, hud.angle, hud.rawAngle, innovation, labels, outputAlertLevel, outputPercent, pidErr, requiredInputState.hasAng, requiredInputState.hasGyro, requiredInputState.hasRaw, requiredInputState.ok, sampleRateHz, status.set, status.wpos]);

  return {
    chartBounds,
    chartPointsKf,
    chartPointsRaw,
    chartPointsRef,
    angleDelta,
    outputDelta,
    hud,
    angleDialPct,
    rawAngleDialPct,
    outputDialPct,
    voltageDialPct,
    cards,
    requiredInputState,
    sampleRateHz,
    loopFeedQuality,
    gyroRate,
    loopFeedAvg5mHz,
    loopFeedMin5mHz,
    outputSessionMeanPct: outputSessionStats.meanPct,
    outputSessionMaxPct: outputSessionStats.maxPct,
    outputAlertLevel,
    telemetryDecayMs,
    perceivedDecayMs,
  };
}
