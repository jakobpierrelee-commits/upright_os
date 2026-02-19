import type { ControlState } from '../../types';

type Checkpoint = {
  id: string;
  ts: number;
  rating: 'poor' | 'ok' | 'good' | 'great';
  mode: string;
  angle: number;
  wpos: number;
  pid: { kp: number; ki: number; kd: number };
  motion: { kv: number; kx: number };
  setpoint: number;
};

type Props = {
  pid: { kp: number; ki: number; kd: number };
  setPidDraft: (next: { kp: number; ki: number; kd: number } | ((p: { kp: number; ki: number; kd: number }) => { kp: number; ki: number; kd: number })) => void;
  motion: { kv: number; kx: number };
  setMotionDraft: (next: { kv: number; kx: number } | ((m: { kv: number; kx: number }) => { kv: number; kx: number })) => void;
  setpoint: number;
  setSetpointDraft: (value: number) => void;
  control: ControlState;
  compatOk: boolean;
  checkpoints: Checkpoint[];
  checkpointMax: number;
  syncFromBot: () => void;
  applyPid: () => Promise<void>;
  applyMotion: () => Promise<void>;
  applySetpoint: () => Promise<void>;
  makeCheckpoint: (rating: Checkpoint['rating']) => void;
  restoreDraftFromCheckpoint: (cp: Checkpoint) => void;
  applyCheckpointToBot: (cp: Checkpoint, save?: boolean) => Promise<void>;
  deleteCheckpoint: (id: string) => void;
};

export function TuningPage(props: Props) {
  const {
    pid,
    setPidDraft,
    motion,
    setMotionDraft,
    setpoint,
    setSetpointDraft,
    control,
    compatOk,
    checkpoints,
    checkpointMax,
    syncFromBot,
    applyPid,
    applyMotion,
    applySetpoint,
    makeCheckpoint,
    restoreDraftFromCheckpoint,
    applyCheckpointToBot,
    deleteCheckpoint,
  } = props;

  return (
    <section>
      <h2>Tuning</h2>
      <div className="row">
        <button onClick={syncFromBot}>Sync From Bot</button>
      </div>

      <div className="grid3">
        <label>
          Kp
          <input type="number" step="0.1" value={pid.kp} onChange={(e) => setPidDraft((p) => ({ ...p, kp: Number(e.target.value) }))} />
        </label>
        <label>
          Ki
          <input type="number" step="0.01" value={pid.ki} onChange={(e) => setPidDraft((p) => ({ ...p, ki: Number(e.target.value) }))} />
        </label>
        <label>
          Kd
          <input type="number" step="0.01" value={pid.kd} onChange={(e) => setPidDraft((p) => ({ ...p, kd: Number(e.target.value) }))} />
        </label>
      </div>
      <button disabled={control.estop_latched || !compatOk} onClick={() => void applyPid()}>Apply PID</button>

      <div className="grid2">
        <label>
          Kv
          <input type="number" step="0.001" value={motion.kv} onChange={(e) => setMotionDraft((m) => ({ ...m, kv: Number(e.target.value) }))} />
        </label>
        <label>
          Kx
          <input type="number" step="0.0001" value={motion.kx} onChange={(e) => setMotionDraft((m) => ({ ...m, kx: Number(e.target.value) }))} />
        </label>
      </div>
      <button disabled={control.estop_latched || !compatOk} onClick={() => void applyMotion()}>Apply Motion</button>

      <div className="grid1">
        <label>
          Setpoint Deg
          <input type="number" step="0.01" value={setpoint} onChange={(e) => setSetpointDraft(Number(e.target.value))} />
        </label>
      </div>
      <button disabled={control.estop_latched || !compatOk} onClick={() => void applySetpoint()}>Apply Setpoint</button>

      <hr />
      <h3>Performance Checkpoints</h3>
      <p>One click rating saves current tuning as a checkpoint (keeps last {checkpointMax}).</p>
      <div className="row">
        <button onClick={() => makeCheckpoint('poor')}>Rate Poor</button>
        <button onClick={() => makeCheckpoint('ok')}>Rate OK</button>
        <button onClick={() => makeCheckpoint('good')}>Rate Good</button>
        <button onClick={() => makeCheckpoint('great')}>Rate Great</button>
      </div>

      <div className="checkpoint-list">
        {checkpoints.length === 0 && <p>No checkpoints yet.</p>}
        {checkpoints.map((cp) => (
          <div className="checkpoint-card" key={cp.id}>
            <div>
              <strong>{cp.rating.toUpperCase()}</strong> · {new Date(cp.ts).toLocaleString()}
            </div>
            <div>
              mode={cp.mode} angle={cp.angle.toFixed(3)} wpos={cp.wpos.toFixed(1)}
            </div>
            <div>
              PID {cp.pid.kp.toFixed(3)} / {cp.pid.ki.toFixed(3)} / {cp.pid.kd.toFixed(3)} · MOTION {cp.motion.kv.toFixed(4)} / {cp.motion.kx.toFixed(5)} · SP {cp.setpoint.toFixed(3)}
            </div>
            <div className="row">
              <button onClick={() => restoreDraftFromCheckpoint(cp)}>Load Draft</button>
              <button onClick={() => void applyCheckpointToBot(cp, false)}>Apply To Bot</button>
              <button onClick={() => void applyCheckpointToBot(cp, true)}>Apply + SaveCfg</button>
              <button onClick={() => deleteCheckpoint(cp.id)}>Delete</button>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
