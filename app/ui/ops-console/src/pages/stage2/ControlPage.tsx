import type { ControlState, Status } from '../../types';

type Props = {
  control: ControlState;
  compatOk: boolean;
  setStatus: (s: Status) => void;
  setControl: (c: ControlState) => void;
  armPrepareAction: () => Promise<ControlState>;
  armConfirmAction: () => Promise<{ status: Status; control: ControlState }>;
  disarmAction: () => Promise<{ status: Status; control?: ControlState }>;
  calZeroAction: () => Promise<{ status: Status; control?: ControlState }>;
  saveCfgAction: () => Promise<void>;
  estopLatchAction: () => Promise<{ status: Status; control: ControlState }>;
  estopResetAction: () => Promise<{ status: Status; control: ControlState }>;
  setMsg: (msg: string) => void;
};

export function ControlPage(props: Props) {
  const {
    control,
    compatOk,
    setStatus,
    setControl,
    armPrepareAction,
    armConfirmAction,
    disarmAction,
    calZeroAction,
    saveCfgAction,
    estopLatchAction,
    estopResetAction,
    setMsg,
  } = props;

  return (
    <section>
      <h2>Control</h2>
      <div className="row">
        <button
          className="btn-arm-action"
          disabled={control.estop_latched || !compatOk}
          onClick={async () => {
            const c = await armPrepareAction();
            setControl(c);
            setMsg('Arm prepared. Press Confirm Arm to execute.');
          }}
        >
          Prepare Arm
        </button>
        <button
          className="btn-arm-action"
          disabled={!control.arm_prepared || control.estop_latched}
          onClick={async () => {
            const r = await armConfirmAction();
            setStatus(r.status);
            setControl(r.control);
            setMsg('Arm confirmed');
          }}
        >
          Confirm Arm
        </button>
        <button
          className="btn-disarm-action"
          onClick={async () => {
            const r = await disarmAction();
            setStatus(r.status);
            if (r.control) setControl(r.control);
            setMsg('Disarmed');
          }}
        >
          Disarm
        </button>
      </div>
      <div className="row">
        <button
          disabled={control.estop_latched}
          onClick={async () => {
            const r = await calZeroAction();
            setStatus(r.status);
            if (r.control) setControl(r.control);
            setMsg('CAL ZERO complete');
          }}
        >
          Cal Zero
        </button>
        <button
          className="btn-danger btn-estop-latch"
          onClick={async () => {
            await saveCfgAction();
            setMsg('Config saved');
          }}
        >
          Save Config
        </button>
        <button
          onClick={async () => {
            const r = control.estop_latched ? await estopResetAction() : await estopLatchAction();
            setStatus(r.status);
            setControl(r.control);
            setMsg(control.estop_latched ? 'E-Stop reset' : 'E-Stop latched');
          }}
        >
          {control.estop_latched ? 'RESET' : 'EMERGENCY STOP'}
        </button>
      </div>
    </section>
  );
}
