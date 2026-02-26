import type { CleanAppState } from './cleanAppTypes';
import { modeLabel, statusValue } from './cleanAppTypes';

type CleanTelemetryPanelProps = {
  status: CleanAppState['status'];
  control: CleanAppState['control'];
  busy: boolean;
  msg: string;
  onRefresh: () => void;
};

export function CleanTelemetryPanel({
  status,
  control,
  busy,
  msg,
  onRefresh,
}: CleanTelemetryPanelProps): JSX.Element {
  return (
    <section className="clean-card clean-gradient">
      <div className="clean-card-head">
        <h2>Live Telemetry</h2>
        <button className="clean-link" onClick={onRefresh} disabled={busy}>
          Refresh
        </button>
      </div>
      <div className="clean-metrics">
        <div>
          <span>Mode</span>
          <strong>{modeLabel(status.mode)}</strong>
        </div>
        <div>
          <span>Angle</span>
          <strong>{statusValue(status, 'ang')}</strong>
        </div>
        <div>
          <span>Raw</span>
          <strong>{statusValue(status, 'raw')}</strong>
        </div>
        <div>
          <span>Gyro</span>
          <strong>{statusValue(status, 'gyro')}</strong>
        </div>
        <div>
          <span>Output</span>
          <strong>{statusValue(status, 'out')}</strong>
        </div>
        <div>
          <span>E-Stop</span>
          <strong>{control?.estop_latched ? 'Latched' : 'Clear'}</strong>
        </div>
      </div>
      <div className="clean-subtle">{msg}</div>
    </section>
  );
}
