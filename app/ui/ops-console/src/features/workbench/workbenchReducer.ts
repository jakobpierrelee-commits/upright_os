import type { FirmwareBoards, FirmwareCheck, FirmwareStatus } from '../../api';

export type WorkbenchTab = 'sketch' | 'board' | 'serial';

export type FirmwareCfg = { sketch: string; fqbn: string; port: string };

export type WorkbenchState = {
  fw: FirmwareStatus;
  fwCheck: FirmwareCheck | null;
  fwCfg: FirmwareCfg;
  workbenchTab: WorkbenchTab;
  boardScan: FirmwareBoards | null;
  sketchPath: string;
  sketchContent: string;
  serialWrite: string;
};

type WorkbenchAction =
  | { type: 'set_fw'; payload: FirmwareStatus }
  | { type: 'set_fw_check'; payload: FirmwareCheck | null }
  | { type: 'set_fw_cfg'; payload: FirmwareCfg }
  | { type: 'patch_fw_cfg'; payload: Partial<FirmwareCfg> }
  | { type: 'set_workbench_tab'; payload: WorkbenchTab }
  | { type: 'set_board_scan'; payload: FirmwareBoards | null }
  | { type: 'set_sketch_path'; payload: string }
  | { type: 'set_sketch_content'; payload: string }
  | { type: 'set_serial_write'; payload: string };

export const initialWorkbenchState: WorkbenchState = {
  fw: {
    state: 'idle',
    phase: 'none',
    running: false,
    started_at: null,
    finished_at: null,
    returncode: null,
    last_cmd: [],
    log_tail: [],
    defaults: { sketch: '', fqbn: 'arduino:avr:nano', port: '' },
  },
  fwCheck: null,
  fwCfg: {
    sketch: '',
    fqbn: 'arduino:avr:nano',
    port: '',
  },
  workbenchTab: 'board',
  boardScan: null,
  sketchPath: '',
  sketchContent: '',
  serialWrite: '',
};

export function workbenchReducer(state: WorkbenchState, action: WorkbenchAction): WorkbenchState {
  switch (action.type) {
    case 'set_fw':
      return { ...state, fw: action.payload };
    case 'set_fw_check':
      return { ...state, fwCheck: action.payload };
    case 'set_fw_cfg':
      return { ...state, fwCfg: action.payload };
    case 'patch_fw_cfg':
      return { ...state, fwCfg: { ...state.fwCfg, ...action.payload } };
    case 'set_workbench_tab':
      return { ...state, workbenchTab: action.payload };
    case 'set_board_scan':
      return { ...state, boardScan: action.payload };
    case 'set_sketch_path':
      return { ...state, sketchPath: action.payload };
    case 'set_sketch_content':
      return { ...state, sketchContent: action.payload };
    case 'set_serial_write':
      return { ...state, serialWrite: action.payload };
    default:
      return state;
  }
}
