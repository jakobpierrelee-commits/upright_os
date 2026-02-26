import { useEffect, useMemo, useState } from 'react';
import { strings } from '../../strings';
import type { ControlState, Status } from '../../types';

type Props = {
  bridgeOnline: boolean;
  status: Status;
  control: ControlState;
  imuHistory: unknown[];
  refreshBridge: () => Promise<void>;
  setMsg: (text: string, source?: string) => void;
};

type LessonKey = 'kp' | 'pd' | 'windup' | 'filter' | 'workflow';

type LessonDef = {
  key: LessonKey;
  title: string;
  objective: string;
  why: string;
  sourceRefs: Array<{ label: string; url: string }>;
  passCriteria: string[];
  tips: string[];
  editable: {
    kp: boolean;
    ki: boolean;
    kd: boolean;
    iMax: boolean;
    outMax: boolean;
    conditionalI: boolean;
    noise: boolean;
    cutoff: boolean;
  };
  defaults: {
    kp: number;
    ki: number;
    kd: number;
    setpoint: number;
    durationS: number;
    disturbance: number;
    noiseAmp: number;
    cutoffHz: number;
    iMax: number;
    outMax: number;
    conditionalI: boolean;
  };
};

type BenchSample = {
  t: number;
  y: number;
  yMeas: number;
  yFilt: number;
  u: number;
  set: number;
};

type BenchMetrics = {
  riseS: number | null;
  overshootPct: number;
  settleS: number | null;
  steadyStateError: number;
  saturationPct: number;
  iae: number;
  score: number;
};

type BenchRun = {
  id: string;
  lesson: LessonKey;
  samples: BenchSample[];
  metrics: BenchMetrics;
  pass: boolean;
  notes: string[];
};

const LESSONS: LessonDef[] = [
  {
    key: 'kp',
    title: '1) Proportional Response',
    objective: 'Find a Kp that is responsive without sustained oscillation.',
    why: 'Kp is the fastest way to improve correction, but too much creates oscillation and saturation.',
    sourceRefs: [
      { label: 'Part 1: What Is PID Control?', url: 'https://www.youtube.com/watch?v=wkfEZmsQqiA' },
      { label: 'Part 7: Important PID Concepts', url: 'https://www.youtube.com/watch?v=tbgV6caAVcs' },
    ],
    passCriteria: [
      'Overshoot < 35%',
      'Saturation < 45%',
      'No sustained oscillation trend',
    ],
    tips: [
      'Raise Kp in small steps.',
      'Watch overshoot and saturation together.',
      'Stop increasing when response starts ringing.',
    ],
    editable: { kp: true, ki: false, kd: false, iMax: false, outMax: false, conditionalI: false, noise: false, cutoff: false },
    defaults: {
      kp: 16,
      ki: 0,
      kd: 0,
      setpoint: 1,
      durationS: 5,
      disturbance: 0.35,
      noiseAmp: 0,
      cutoffHz: 0,
      iMax: 70,
      outMax: 180,
      conditionalI: false,
    },
  },
  {
    key: 'pd',
    title: '2) Add Damping (PD)',
    objective: 'Use Kd to reduce overshoot and tighten settling time.',
    why: 'Derivative opposes fast movement and helps stop ringing caused by aggressive Kp.',
    sourceRefs: [
      { label: 'Part 1: What Is PID Control?', url: 'https://www.youtube.com/watch?v=wkfEZmsQqiA' },
      { label: 'Part 3: Noise Filtering in PID', url: 'https://www.youtube.com/watch?v=7dUVdrs1e18' },
    ],
    passCriteria: [
      'Overshoot < 18%',
      'Settle < 3.2 s',
      'No obvious derivative chatter',
    ],
    tips: [
      'Keep Kp near your good value from step 1.',
      'Increase Kd until overshoot drops.',
      'If output gets noisy, Kd is too high for the signal quality.',
    ],
    editable: { kp: true, ki: false, kd: true, iMax: false, outMax: false, conditionalI: false, noise: false, cutoff: false },
    defaults: {
      kp: 21,
      ki: 0,
      kd: 0.9,
      setpoint: 1,
      durationS: 5,
      disturbance: 0.35,
      noiseAmp: 0,
      cutoffHz: 0,
      iMax: 70,
      outMax: 180,
      conditionalI: false,
    },
  },
  {
    key: 'windup',
    title: '3) Integral + Anti-Windup',
    objective: 'Use Ki to remove offset while preventing windup with I limit/conditional integration.',
    why: 'Integral fixes steady-state bias but can store too much energy when the actuator is saturated.',
    sourceRefs: [
      { label: 'Part 2: Anti-windup for PID', url: 'https://www.youtube.com/watch?v=NVLXCwc8HzM' },
      { label: 'Part 7: Important PID Concepts', url: 'https://www.youtube.com/watch?v=tbgV6caAVcs' },
    ],
    passCriteria: [
      '|Steady-state error| < 0.06',
      'Saturation < 45%',
      'No slow hunting after disturbance',
    ],
    tips: [
      'Add Ki slowly after PD is stable.',
      'If recovery is sluggish or oscillatory, reduce Ki or iMax.',
      'Enable conditional integration when saturation is frequent.',
    ],
    editable: { kp: true, ki: true, kd: true, iMax: true, outMax: true, conditionalI: true, noise: false, cutoff: false },
    defaults: {
      kp: 20,
      ki: 0.06,
      kd: 0.95,
      setpoint: 1,
      durationS: 6,
      disturbance: 0.55,
      noiseAmp: 0,
      cutoffHz: 0,
      iMax: 70,
      outMax: 180,
      conditionalI: true,
    },
  },
  {
    key: 'filter',
    title: '4) Noise + Filter',
    objective: 'Balance noise rejection and lag using cutoff frequency.',
    why: 'Lower cutoff smooths noise but increases lag; higher cutoff is quicker but noisier.',
    sourceRefs: [
      { label: 'Part 3: Noise Filtering in PID', url: 'https://www.youtube.com/watch?v=7dUVdrs1e18' },
      { label: 'Part 7: Important PID Concepts', url: 'https://www.youtube.com/watch?v=tbgV6caAVcs' },
    ],
    passCriteria: [
      'Overshoot < 22%',
      'IAE < 2.8',
      'Acceptable control smoothness',
    ],
    tips: [
      'Start moderate, then lower only if output chatter is high.',
      'Too low cutoff increases delay and can hurt stability.',
      'Tune Kd with realistic noise and filter settings.',
    ],
    editable: { kp: true, ki: false, kd: true, iMax: false, outMax: false, conditionalI: false, noise: true, cutoff: true },
    defaults: {
      kp: 19,
      ki: 0,
      kd: 1.2,
      setpoint: 1,
      durationS: 6,
      disturbance: 0.3,
      noiseAmp: 0.35,
      cutoffHz: 6,
      iMax: 70,
      outMax: 180,
      conditionalI: false,
    },
  },
  {
    key: 'workflow',
    title: '5) Practical Tuning Workflow',
    objective: 'Run structured A/B comparisons and pick the safer/better tune.',
    why: 'Reliable tuning is a process: isolate variables, compare runs, and promote only measurable improvements.',
    sourceRefs: [
      { label: 'Part 4: PID Tuning Guide', url: 'https://www.youtube.com/watch?v=sFOEsA0Irjs' },
      { label: 'Part 5: Build a Model', url: 'https://www.youtube.com/watch?v=qhIjIu-Zk10' },
      { label: 'Part 6: Manual/Auto Tuning Methods', url: 'https://www.youtube.com/watch?v=qj8vTO1eIHo' },
    ],
    passCriteria: [
      'Score >= 75',
      'Saturation < 40%',
      'Settle < 3.5 s',
    ],
    tips: [
      'Change one family at a time (P/D/I/limits/filter).',
      'Compare A/B with the same disturbance profile.',
      'Prefer lower saturation and better settling over just fast rise.',
    ],
    editable: { kp: true, ki: true, kd: true, iMax: true, outMax: true, conditionalI: true, noise: true, cutoff: true },
    defaults: {
      kp: 20,
      ki: 0.05,
      kd: 1.05,
      setpoint: 1,
      durationS: 6,
      disturbance: 0.45,
      noiseAmp: 0.25,
      cutoffHz: 6,
      iMax: 70,
      outMax: 180,
      conditionalI: true,
    },
  },
];

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

function lpfAlpha(cutoffHz: number, dt: number): number {
  if (cutoffHz <= 0) return 1;
  const tau = 1 / (2 * Math.PI * cutoffHz);
  return dt / (tau + dt);
}

function seededNoise(seedRef: { v: number }): number {
  seedRef.v = (1664525 * seedRef.v + 1013904223) >>> 0;
  return (seedRef.v / 0xffffffff) * 2 - 1;
}

function evaluateRun(lesson: LessonKey, m: BenchMetrics): { pass: boolean; notes: string[] } {
  const notes: string[] = [];
  if (m.overshootPct > 30) notes.push('Overshoot is high.');
  if (m.saturationPct > 40) notes.push('Output saturation is high.');
  if (m.settleS == null) notes.push('Response did not settle in window.');

  let pass = false;
  if (lesson === 'kp') {
    pass = m.overshootPct < 35 && m.saturationPct < 45;
  } else if (lesson === 'pd') {
    pass = m.overshootPct < 18 && (m.settleS ?? 99) < 3.2;
  } else if (lesson === 'windup') {
    pass = Math.abs(m.steadyStateError) < 0.06 && m.saturationPct < 45;
  } else if (lesson === 'filter') {
    pass = m.overshootPct < 22 && m.iae < 2.8;
  } else {
    pass = m.score >= 75 && m.saturationPct < 40 && (m.settleS ?? 99) < 3.5;
  }

  if (pass) notes.unshift('Objective met.');
  return { pass, notes: notes.slice(0, 3) };
}

function runBench(opts: {
  lesson: LessonKey;
  seed: number;
  kp: number;
  ki: number;
  kd: number;
  setpoint: number;
  durationS: number;
  disturbance: number;
  noiseAmp: number;
  cutoffHz: number;
  iMax: number;
  outMax: number;
  conditionalI: boolean;
}): BenchRun {
  const dt = 0.01;
  const steps = Math.max(100, Math.floor(opts.durationS / dt));
  const gain = 0.05;
  const tau = 0.34;
  const delayTicks = 3;
  const cmdQueue: number[] = Array.from({ length: delayTicks }, () => 0);
  const seedRef = { v: opts.seed >>> 0 };

  let y = 0;
  let yFilt = 0;
  let iTerm = 0;
  let prevFilt = 0;
  let iae = 0;
  let satCount = 0;

  const samples: BenchSample[] = [];

  for (let i = 0; i < steps; i += 1) {
    const t = i * dt;
    const disturbancePulse = t > 0.3 ? (opts.disturbance * Math.exp(-(t - 0.3) * 1.6)) : 0;

    const noise = seededNoise(seedRef) * opts.noiseAmp;
    const yMeas = y + noise;
    const alpha = lpfAlpha(opts.cutoffHz, dt);
    yFilt = yFilt + alpha * (yMeas - yFilt);

    const err = opts.setpoint - yFilt;
    const dTerm = -(yFilt - prevFilt) / dt;
    prevFilt = yFilt;

    const wouldInt = iTerm + (err * dt);
    const tentative = (opts.kp * err) + (opts.ki * wouldInt) + (opts.kd * dTerm);
    const saturated = Math.abs(tentative) > opts.outMax;
    const pushesOutward = Math.sign(tentative) === Math.sign(err) && Math.abs(err) > 0.001;
    const allowI = !opts.conditionalI || !saturated || !pushesOutward;

    if (allowI) {
      iTerm = clamp(wouldInt, -opts.iMax, opts.iMax);
    }

    let u = (opts.kp * err) + (opts.ki * iTerm) + (opts.kd * dTerm);
    if (Math.abs(u) > opts.outMax) satCount += 1;
    u = clamp(u, -opts.outMax, opts.outMax);

    cmdQueue.push(u);
    const uDelayed = cmdQueue.shift() ?? u;

    const yDot = (-(y) + (gain * uDelayed) + disturbancePulse) / tau;
    y += yDot * dt;
    iae += Math.abs(err) * dt;

    samples.push({ t, y, yMeas, yFilt, u: uDelayed, set: opts.setpoint });
  }

  const setAbs = Math.max(0.001, Math.abs(opts.setpoint));
  const maxY = Math.max(...samples.map((s) => s.y));
  const minY = Math.min(...samples.map((s) => s.y));
  const peak = opts.setpoint >= 0 ? maxY : minY;
  const overshootPct = Math.max(0, (Math.abs(peak - opts.setpoint) / setAbs) * 100);

  let t10: number | null = null;
  let t90: number | null = null;
  const lo = opts.setpoint * 0.1;
  const hi = opts.setpoint * 0.9;
  for (const s of samples) {
    if (opts.setpoint >= 0) {
      if (t10 == null && s.y >= lo) t10 = s.t;
      if (t90 == null && s.y >= hi) t90 = s.t;
    } else {
      if (t10 == null && s.y <= lo) t10 = s.t;
      if (t90 == null && s.y <= hi) t90 = s.t;
    }
  }
  const riseS = t10 != null && t90 != null && t90 >= t10 ? (t90 - t10) : null;

  let settleS: number | null = null;
  const settleBand = setAbs * 0.02;
  for (let i = 0; i < samples.length; i += 1) {
    const tail = samples.slice(i);
    if (tail.every((s) => Math.abs(s.y - opts.setpoint) <= settleBand)) {
      settleS = samples[i].t;
      break;
    }
  }

  const steadyStateError = opts.setpoint - samples[samples.length - 1].y;
  const saturationPct = (satCount / samples.length) * 100;

  const score = clamp(
    100
    - Math.min(40, overshootPct * 0.8)
    - Math.min(28, Math.abs(steadyStateError) * 95)
    - Math.min(24, saturationPct * 0.6)
    - Math.min(20, iae * 1.2)
    - (settleS == null ? 10 : 0),
    0,
    100,
  );

  const metrics: BenchMetrics = {
    riseS,
    overshootPct,
    settleS,
    steadyStateError,
    saturationPct,
    iae,
    score,
  };

  const verdict = evaluateRun(opts.lesson, metrics);
  return {
    id: `bench-${Date.now()}-${Math.round(Math.random() * 10_000)}`,
    lesson: opts.lesson,
    samples,
    metrics,
    pass: verdict.pass,
    notes: verdict.notes,
  };
}

function coachingNotes(lesson: LessonKey, m: BenchMetrics): string[] {
  const notes: string[] = [];
  if (lesson === 'kp') {
    if (m.overshootPct > 35) notes.push('Reduce Kp slightly; you crossed into aggressive proportional behavior.');
    if (m.saturationPct > 45) notes.push('Output is clipping; reduce Kp or raise outMax only if safe.');
    if ((m.riseS ?? 99) > 1.7) notes.push('Response is slow; raise Kp in small increments.');
  } else if (lesson === 'pd') {
    if (m.overshootPct > 18) notes.push('Increase Kd gradually to add damping.');
    if ((m.settleS ?? 99) > 3.2) notes.push('Tune Kd first, then rebalance Kp for settle performance.');
    if (m.saturationPct > 40) notes.push('High control effort: reduce Kp before increasing Kd further.');
  } else if (lesson === 'windup') {
    if (Math.abs(m.steadyStateError) > 0.06) notes.push('Increase Ki slightly to remove residual offset.');
    if (m.saturationPct > 45) notes.push('Reduce Ki or iMax; enable conditional integration to prevent windup.');
    if ((m.settleS ?? 99) > 4.0) notes.push('Integral action may be too strong; reduce Ki and retest.');
  } else if (lesson === 'filter') {
    if (m.iae > 2.8) notes.push('Lower cutoff or reduce Kd if control reacts too strongly to noise.');
    if ((m.riseS ?? 99) > 2.2) notes.push('Cutoff may be too low; raise cutoff slightly to reduce lag.');
    if (m.overshootPct > 22) notes.push('Rebalance Kd/Kp after filter change; filter shifts phase response.');
  } else {
    if (m.score < 75) notes.push('Use A/B comparisons and change one family at a time before promotion.');
    if ((m.settleS ?? 99) > 3.5) notes.push('Prioritize stability and settle over raw speed.');
    if (m.saturationPct > 40) notes.push('Candidate is too aggressive for safe promotion.');
  }
  if (!notes.length) {
    notes.push('Good run. Save this as candidate A and validate against a small perturbation in B.');
  }
  return notes.slice(0, 3);
}

export function IterationPlaygroundPage(props: Props) {
  const { bridgeOnline: _bridgeOnline, status: _status, control: _control, refreshBridge: _refreshBridge, setMsg } = props;

  const [lessonIndex, setLessonIndex] = useState(0);
  const [seed, setSeed] = useState(42);

  const lesson = LESSONS[lessonIndex];

  const [kp, setKp] = useState(lesson.defaults.kp);
  const [ki, setKi] = useState(lesson.defaults.ki);
  const [kd, setKd] = useState(lesson.defaults.kd);
  const [setpoint, setSetpoint] = useState(lesson.defaults.setpoint);
  const [durationS, setDurationS] = useState(lesson.defaults.durationS);
  const [disturbance, setDisturbance] = useState(lesson.defaults.disturbance);
  const [noiseAmp, setNoiseAmp] = useState(lesson.defaults.noiseAmp);
  const [cutoffHz, setCutoffHz] = useState(lesson.defaults.cutoffHz);
  const [iMax, setIMax] = useState(lesson.defaults.iMax);
  const [outMax, setOutMax] = useState(lesson.defaults.outMax);
  const [conditionalI, setConditionalI] = useState(lesson.defaults.conditionalI);

  const [latestRun, setLatestRun] = useState<BenchRun | null>(null);
  const [runA, setRunA] = useState<BenchRun | null>(null);
  const [runB, setRunB] = useState<BenchRun | null>(null);

  useEffect(() => {
    setKp(lesson.defaults.kp);
    setKi(lesson.defaults.ki);
    setKd(lesson.defaults.kd);
    setSetpoint(lesson.defaults.setpoint);
    setDurationS(lesson.defaults.durationS);
    setDisturbance(lesson.defaults.disturbance);
    setNoiseAmp(lesson.defaults.noiseAmp);
    setCutoffHz(lesson.defaults.cutoffHz);
    setIMax(lesson.defaults.iMax);
    setOutMax(lesson.defaults.outMax);
    setConditionalI(lesson.defaults.conditionalI);
    setLatestRun(null);
    setRunA(null);
    setRunB(null);
  }, [lesson.key]);

  const doRun = (name: string) => {
    const out = runBench({
      lesson: lesson.key,
      seed,
      kp,
      ki,
      kd,
      setpoint,
      durationS,
      disturbance,
      noiseAmp,
      cutoffHz,
      iMax,
      outMax,
      conditionalI,
    });
    setSeed((s) => s + 17);
    setLatestRun(out);
    setMsg(
      `Lesson run ${name}: score=${out.metrics.score.toFixed(0)} overshoot=${out.metrics.overshootPct.toFixed(1)}% settle=${out.metrics.settleS?.toFixed(2) ?? 'n/a'}s`,
      'playground.lesson',
    );
  };

  const series = useMemo(() => {
    if (!latestRun || latestRun.samples.length < 2) {
      const fallback = [0, 0];
      return {
        set: fallback,
        y: fallback,
        yMeas: fallback,
        yFilt: fallback,
        u: fallback,
        yMin: -1,
        yMax: 1,
        uMin: -10,
        uMax: 10,
      };
    }
    const setVals = latestRun.samples.map((s) => s.set);
    const yVals = latestRun.samples.map((s) => s.y);
    const yMeasVals = latestRun.samples.map((s) => s.yMeas);
    const yFiltVals = latestRun.samples.map((s) => s.yFilt);
    const uVals = latestRun.samples.map((s) => s.u);

    const yAbs = Math.max(1, ...setVals.map((v) => Math.abs(v)), ...yVals.map((v) => Math.abs(v)), ...yMeasVals.map((v) => Math.abs(v)));
    const uAbs = Math.max(1, ...uVals.map((v) => Math.abs(v)));

    return {
      set: setVals,
      y: yVals,
      yMeas: yMeasVals,
      yFilt: yFiltVals,
      u: uVals,
      yMin: -yAbs * 1.15,
      yMax: yAbs * 1.15,
      uMin: -uAbs,
      uMax: uAbs,
    };
  }, [latestRun]);

  const responseSpark = useMemo(() => ({
    set: sparkline(series.set, series.yMin, series.yMax),
    y: sparkline(series.y, series.yMin, series.yMax),
    yMeas: sparkline(series.yMeas, series.yMin, series.yMax),
    yFilt: sparkline(series.yFilt, series.yMin, series.yMax),
  }), [series]);

  const controlSpark = useMemo(() => sparkline(series.u, series.uMin, series.uMax), [series]);

  const currentSample = latestRun?.samples[latestRun.samples.length - 1];
  const angle = currentSample ? clamp(currentSample.y * 18, -28, 28) : 0;
  const output = currentSample ? currentSample.u : 0;
  const outputPct = clamp((Math.abs(output) / Math.max(1, outMax)) * 100, 0, 100);

  const compare = useMemo(() => {
    if (!runA || !runB) return null;
    return {
      scoreDelta: runB.metrics.score - runA.metrics.score,
      overshootDelta: runB.metrics.overshootPct - runA.metrics.overshootPct,
      settleDelta: (runB.metrics.settleS ?? durationS) - (runA.metrics.settleS ?? durationS),
      sseDelta: runB.metrics.steadyStateError - runA.metrics.steadyStateError,
      satDelta: runB.metrics.saturationPct - runA.metrics.saturationPct,
    };
  }, [durationS, runA, runB]);

  return (
    <div className="playground-grid playground-theme-zone">
      <section className="panel tool-panel">
        <div className="tool-panel-head">
          <div>
            <h3>{strings.playground.title}</h3>
            <span className="workflow-label">Guided PID learning bench with interactive robot preview</span>
          </div>
        </div>

        <div className="tool-panel-body playground-body">
          <div className="playground-lesson-shell">
            <aside className="playground-lesson-rail">
              {LESSONS.map((ls, idx) => (
                <button
                  key={ls.key}
                  className={`playground-lesson-item ${idx === lessonIndex ? 'active' : ''}`}
                  onClick={() => setLessonIndex(idx)}
                >
                  <span>{ls.title}</span>
                </button>
              ))}
            </aside>

            <div className="playground-lesson-main">
              <div className="action-rig playground-lesson-card">
                <div className="action-rig-head">
                  <span className="action-rig-title">{lesson.title}</span>
                  <span className={`badge ${latestRun?.pass ? 'ok' : 'warn'}`}>{latestRun ? (latestRun.pass ? 'PASS' : 'IN PROGRESS') : 'NOT RUN'}</span>
                </div>
                <p className="playground-lesson-objective"><strong>Goal:</strong> {lesson.objective}</p>
                <p className="playground-lesson-why">{lesson.why}</p>
                <div className="playground-lesson-refs">
                  {lesson.sourceRefs.map((ref) => (
                    <a key={ref.url} href={ref.url} target="_blank" rel="noreferrer">
                      {ref.label}
                    </a>
                  ))}
                </div>
                <div className="playground-linear-hints">
                  {lesson.tips.map((tip) => <p key={tip}>{tip}</p>)}
                </div>
                <div className="playground-linear-hints">
                  {lesson.passCriteria.map((rule) => <p key={rule}><strong>Pass:</strong> {rule}</p>)}
                </div>
              </div>

              <div className="playground-visual-grid">
                <div className="playground-robot-card">
                  <div className="playground-card-head">
                    <span className="action-rig-title">Robot Preview</span>
                    <span className="badge ok">SIM</span>
                  </div>
                  <div className="playground-robot-stage">
                    <div className="playground-stage-grid" />
                    <div className="playground-ground" />
                    <div className="playground-setpoint-mark" style={{ left: `${50 + clamp(setpoint * 20, -24, 24)}%` }} />
                    <div className="playground-motion-axis">
                      <span className={`playground-motion-chip ${output > 1 ? 'fwd' : output < -1 ? 'rev' : 'hold'}`}>
                        {output > 1 ? 'FWD ->' : output < -1 ? '<- REV' : 'HOLD'}
                      </span>
                    </div>
                    <div
                      className="playground-bot-wrap"
                      style={{ transform: `translateX(calc(-50% + ${clamp((output / Math.max(1, outMax)) * 18, -18, 18)}px)) rotate(${angle}deg)` }}
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
                      <strong>{setpoint.toFixed(2)}</strong>
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
                      <label>Kp {kp.toFixed(2)}</label>
                      <div className="playground-gauge-track">
                        <div className="playground-gauge-fill kp" style={{ width: `${clamp((kp / 40) * 100, 0, 100)}%` }} />
                      </div>
                    </div>
                    <div className="playground-gauge-item">
                      <label>Ki {ki.toFixed(3)}</label>
                      <div className="playground-gauge-track">
                        <div className="playground-gauge-fill ki" style={{ width: `${clamp((ki / 0.3) * 100, 0, 100)}%` }} />
                      </div>
                    </div>
                    <div className="playground-gauge-item">
                      <label>Kd {kd.toFixed(3)}</label>
                      <div className="playground-gauge-track">
                        <div className="playground-gauge-fill kd" style={{ width: `${clamp((kd / 4) * 100, 0, 100)}%` }} />
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <div className="playground-scope-grid">
                <div className="playground-scope-card">
                  <div className="playground-card-head">
                    <span className="action-rig-title">Step Response</span>
                  </div>
                  <svg className="playground-scope" viewBox="0 0 640 140" role="img" aria-label="Step response chart">
                    <polyline className="scope-line set" points={responseSpark.set} />
                    <polyline className="scope-line raw" points={responseSpark.yMeas} />
                    <polyline className="scope-line kf" points={responseSpark.yFilt} />
                    <polyline className="scope-line out" points={responseSpark.y} />
                  </svg>
                </div>
                <div className="playground-scope-card">
                  <div className="playground-card-head">
                    <span className="action-rig-title">Control Effort</span>
                  </div>
                  <svg className="playground-scope" viewBox="0 0 640 140" role="img" aria-label="Control effort chart">
                    <polyline className="scope-line out" points={controlSpark} />
                  </svg>
                </div>
              </div>

              <div className="action-rig playground-linear-bench">
                <div className="action-rig-head">
                  <span className="action-rig-title">Lesson Controls</span>
                </div>
                <div className="row playground-sweep-row">
                  <label className="playground-label">Kp<input type="number" step="0.05" value={kp} disabled={!lesson.editable.kp} onChange={(e) => setKp(Number(e.target.value) || 0)} /></label>
                  <label className="playground-label">Ki<input type="number" step="0.01" value={ki} disabled={!lesson.editable.ki} onChange={(e) => setKi(Number(e.target.value) || 0)} /></label>
                  <label className="playground-label">Kd<input type="number" step="0.01" value={kd} disabled={!lesson.editable.kd} onChange={(e) => setKd(Number(e.target.value) || 0)} /></label>
                  <label className="playground-label">Setpoint<input type="number" step="0.1" value={setpoint} onChange={(e) => setSetpoint(Number(e.target.value) || 0)} /></label>
                  <label className="playground-label">Duration s<input type="number" min={2} step="0.5" value={durationS} onChange={(e) => setDurationS(Math.max(2, Number(e.target.value) || 2))} /></label>
                  <label className="playground-label">Disturbance<input type="number" step="0.05" value={disturbance} onChange={(e) => setDisturbance(Number(e.target.value) || 0)} /></label>
                  <label className="playground-label">Noise<input type="number" step="0.05" value={noiseAmp} disabled={!lesson.editable.noise} onChange={(e) => setNoiseAmp(Math.max(0, Number(e.target.value) || 0))} /></label>
                  <label className="playground-label">Cutoff Hz<input type="number" step="0.1" value={cutoffHz} disabled={!lesson.editable.cutoff} onChange={(e) => setCutoffHz(Math.max(0, Number(e.target.value) || 0))} /></label>
                  <label className="playground-label">I Max<input type="number" step="0.5" value={iMax} disabled={!lesson.editable.iMax} onChange={(e) => setIMax(Math.max(0, Number(e.target.value) || 0))} /></label>
                  <label className="playground-label">Out Max<input type="number" step="1" value={outMax} disabled={!lesson.editable.outMax} onChange={(e) => setOutMax(Math.max(1, Number(e.target.value) || 1))} /></label>
                  <label className="playground-label">Cond I
                    <select value={conditionalI ? 'on' : 'off'} disabled={!lesson.editable.conditionalI} onChange={(e) => setConditionalI(e.target.value === 'on')}>
                      <option value="off">Off</option>
                      <option value="on">On</option>
                    </select>
                  </label>
                </div>
                <div className="row action-rig-row">
                  <button className="btn-secondary btn-sm" onClick={() => doRun('Run')}>Run Lesson</button>
                  <button className="btn-secondary btn-sm" disabled={!latestRun} onClick={() => latestRun && setRunA(latestRun)}>Save A</button>
                  <button className="btn-primary btn-sm" disabled={!latestRun} onClick={() => latestRun && setRunB(latestRun)}>Save B</button>
                </div>
              </div>

              {latestRun && (
                <div className="compat-box">
                  <p><strong>Score:</strong> {latestRun.metrics.score.toFixed(0)} ({latestRun.pass ? 'PASS' : 'WORK NEEDED'})</p>
                  <p><strong>Rise:</strong> {latestRun.metrics.riseS != null ? `${latestRun.metrics.riseS.toFixed(3)} s` : 'n/a'}</p>
                  <p><strong>Overshoot:</strong> {latestRun.metrics.overshootPct.toFixed(2)}%</p>
                  <p><strong>Settle:</strong> {latestRun.metrics.settleS != null ? `${latestRun.metrics.settleS.toFixed(3)} s` : 'n/a'}</p>
                  <p><strong>SSE:</strong> {latestRun.metrics.steadyStateError.toFixed(4)}</p>
                  <p><strong>Saturation:</strong> {latestRun.metrics.saturationPct.toFixed(1)}%</p>
                  <p><strong>IAE:</strong> {latestRun.metrics.iae.toFixed(4)}</p>
                  {latestRun.notes.map((note) => <p key={note}><strong>Note:</strong> {note}</p>)}
                  {coachingNotes(lesson.key, latestRun.metrics).map((note) => <p key={note}><strong>Coach:</strong> {note}</p>)}
                </div>
              )}

              {runA && runB && compare && (
                <div className="compat-box playground-compare-box">
                  <p><strong>A/B Compare:</strong> Score Δ {compare.scoreDelta >= 0 ? '+' : ''}{compare.scoreDelta.toFixed(1)}</p>
                  <p><strong>Overshoot Δ:</strong> {compare.overshootDelta >= 0 ? '+' : ''}{compare.overshootDelta.toFixed(2)}%</p>
                  <p><strong>Settle Δ:</strong> {compare.settleDelta >= 0 ? '+' : ''}{compare.settleDelta.toFixed(3)} s</p>
                  <p><strong>SSE Δ:</strong> {compare.sseDelta >= 0 ? '+' : ''}{compare.sseDelta.toFixed(4)}</p>
                  <p><strong>Saturation Δ:</strong> {compare.satDelta >= 0 ? '+' : ''}{compare.satDelta.toFixed(2)}%</p>
                </div>
              )}
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
