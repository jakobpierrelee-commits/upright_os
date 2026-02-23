type ImuSample = {
  t: number;
  kf: number;
  raw: number;
  gyro: number;
  out: number;
};

type Props = {
  show: boolean;
  hud: {
    angle: number;
    rawAngle: number;
  };
  angleDelta: number;
  angleDialPct: number;
  rawAngleDialPct: number;
  chartPointsRaw: string;
  chartPointsKf: string;
  chartPointsRef: string;
  imuHistory: ImuSample[];
  chartBounds: { min: number; max: number };
};

function polar(cx: number, cy: number, r: number, degFromTopCw: number) {
  const t = ((degFromTopCw - 90) * Math.PI) / 180;
  return { x: cx + (r * Math.cos(t)), y: cy + (r * Math.sin(t)) };
}

function sideArcPath(radius: number, value: number, pct: number): string {
  const cx = 60;
  const cy = 60;
  const mag = Math.max(0, Math.min(1, pct));
  if (mag <= 0.0001) return '';
  const maxSweepDeg = 170;
  const sweep = maxSweepDeg * mag;
  const start = polar(cx, cy, radius, 0);
  const end = polar(cx, cy, radius, value >= 0 ? sweep : -sweep);
  const sweepFlag = value >= 0 ? 1 : 0;
  return `M ${start.x.toFixed(2)} ${start.y.toFixed(2)} A ${radius} ${radius} 0 0 ${sweepFlag} ${end.x.toFixed(2)} ${end.y.toFixed(2)}`;
}

function sideSemiTrackPath(radius: number): string {
  const cx = 60;
  const cy = 60;
  const start = polar(cx, cy, radius, -90);
  const end = polar(cx, cy, radius, 90);
  return `M ${start.x.toFixed(2)} ${start.y.toFixed(2)} A ${radius} ${radius} 0 0 1 ${end.x.toFixed(2)} ${end.y.toFixed(2)}`;
}

function sideSemiFillPath(radius: number, value: number, pct: number): string {
  const cx = 60;
  const cy = 60;
  const mag = Math.max(0, Math.min(1, pct));
  if (mag <= 0.0001) return '';
  const sweep = 90 * mag;
  const start = polar(cx, cy, radius, 0);
  const end = polar(cx, cy, radius, value >= 0 ? sweep : -sweep);
  const sweepFlag = value >= 0 ? 1 : 0;
  return `M ${start.x.toFixed(2)} ${start.y.toFixed(2)} A ${radius} ${radius} 0 0 ${sweepFlag} ${end.x.toFixed(2)} ${end.y.toFixed(2)}`;
}

export function HudVisuals(props: Props) {
  const {
    show,
    hud,
    angleDelta,
    angleDialPct,
    rawAngleDialPct,
    chartPointsRaw,
    chartPointsKf,
    chartPointsRef,
    imuHistory,
    chartBounds,
  } = props;

  if (!show) return null;

  return (
    <section className="hud-visuals" aria-label="Persistent telemetry visuals">
      <article className="dial-panel">
        <h3>Amplified Reactor Dials</h3>
        <div className="dial-row">
          <div className="dial-card amplified-angle-card">
            <span className="dial-label">AMPLIFIED FILTERED ANGLE</span>
            <svg className="dial dial-semi telemetry-semi" viewBox="0 0 120 88" role="img" aria-label="Filtered angle semicircle gauge">
              <path d={sideSemiTrackPath(46)} className="dial-semi-track" />
              <path d={sideSemiFillPath(46, hud.angle, angleDialPct)} className="dial-fill dial-side telemetry-gauge-value" />
              <text x="60" y="58" textAnchor="middle" className="telemetry-semi-readout">
                {hud.angle.toFixed(2)}
              </text>
              <text x="60" y="74" textAnchor="middle" className="telemetry-semi-unit">
                DEG
              </text>
            </svg>
            <span className={`trend ${Math.abs(angleDelta) < 0.05 ? 'flat' : angleDelta > 0 ? 'up' : 'down'}`}>
              Δ {angleDelta.toFixed(3)}
            </span>
          </div>

          <div className="dial-card amplified-angle-card">
            <span className="dial-label">AMPLIFIED RAW ANGLE</span>
            <svg className="dial dial-semi telemetry-semi" viewBox="0 0 120 88" role="img" aria-label="Raw angle semicircle gauge">
              <path d={sideSemiTrackPath(46)} className="dial-semi-track" />
              <path d={sideSemiFillPath(46, hud.rawAngle, rawAngleDialPct)} className="dial-fill dial-side telemetry-gauge-value" />
              <text x="60" y="58" textAnchor="middle" className="telemetry-semi-readout">
                {hud.rawAngle.toFixed(2)}
              </text>
              <text x="60" y="74" textAnchor="middle" className="telemetry-semi-unit">
                DEG
              </text>
            </svg>
            <span className="trend flat">SIDE PROFILE</span>
          </div>

        </div>
      </article>

      <article className="imu-chart-panel">
        <h3>IMU Overlay (True Signal History)</h3>
        <div className="chart-legend">
          <span className="legend-item"><i className="legend-dot raw" /> raw angle</span>
          <span className="legend-item"><i className="legend-dot kf" /> kalman angle</span>
          <span className="legend-item"><i className="legend-dot ref" /> ui kalman ref</span>
        </div>
        <svg className="imu-chart" viewBox="0 0 820 160" role="img" aria-label="IMU and Kalman overlay chart">
          <line x1="0" y1="80" x2="820" y2="80" className="chart-axis" />
          {chartPointsRaw && <polyline className="chart-line raw" points={chartPointsRaw} />}
          {chartPointsKf && <polyline className="chart-line kf" points={chartPointsKf} />}
          {chartPointsRef && <polyline className="chart-line ref" points={chartPointsRef} />}
        </svg>
        <div className="chart-meta">
          <span>samples: {imuHistory.length}</span>
          <span>range: {chartBounds.min.toFixed(1)}° to {chartBounds.max.toFixed(1)}°</span>
        </div>
      </article>
    </section>
  );
}
