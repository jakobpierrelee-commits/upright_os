import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  cleanStatus,
  cleanFirmwareBoards,
  cleanFirmwareTargets,
  cleanFirmwareCompile,
  cleanFirmwareStatus,
  cleanFirmwareUpload,
  cleanFirmwareUploadPrecheck,
  cleanKnownGoodRecovery,
  cleanPreflightStream,
  cleanFailureDetailFromError,
  cleanFailureKindFromError,
  cleanIsNotFoundError,
  type CleanFirmwareBoards,
  type CleanFirmwareTargets,
  type CleanFirmwareStatus,
  type CleanMode,
} from './cleanApi';

type IdeStatusLevel = 'ok' | 'warn' | 'fail';
type RunbookActionKey =
  | 'detect_port'
  | 'select_port'
  | 'compile'
  | 'upload'
  | 'retry_upload'
  | 'refresh_status'
  | 'check'
  | 'copy_restart_cmd'
  | 'set_bootloader';
type UploadRetryGuideStep = { id: string; label: string; actionKey?: RunbookActionKey };
type UploadRetryGuide = {
  title: string;
  steps: UploadRetryGuideStep[];
  notes?: string[];
  lockSequence?: boolean;
};
type TargetRunbook = {
  target: {
    fqbn: string;
    board_id: string;
    board_family: string;
    board_label: string;
  };
  upload_sequence: string[];
  upload_sequence_steps?: UploadRetryGuideStep[];
  recovery: Record<string, string[]>;
  recovery_steps?: Record<string, UploadRetryGuideStep[]>;
};

type FirmwareFlowStepId = 'detect' | 'compile' | 'upload' | 'reconnect' | 'verify';
type FirmwareFlowStepState = 'idle' | 'running' | 'pass' | 'fail';
type FirmwareFlowStep = { state: FirmwareFlowStepState; detail: string };
type FirmwareFlowMap = Record<FirmwareFlowStepId, FirmwareFlowStep>;

type FirmwareTargetBoard = CleanFirmwareTargets['boards'][number];
type FirmwareTargetFamily = CleanFirmwareTargets['families'][number];

const FLOW_STEPS: Array<{ id: FirmwareFlowStepId; label: string }> = [
  { id: 'detect', label: 'Detect' },
  { id: 'compile', label: 'Compile' },
  { id: 'upload', label: 'Upload' },
  { id: 'reconnect', label: 'Reconnect' },
  { id: 'verify', label: 'Verify' },
];

function createInitialFlowMap(): FirmwareFlowMap {
  return {
    detect: { state: 'idle', detail: 'idle' },
    compile: { state: 'idle', detail: 'idle' },
    upload: { state: 'idle', detail: 'idle' },
    reconnect: { state: 'idle', detail: 'idle' },
    verify: { state: 'idle', detail: 'idle' },
  };
}

function plainFlowDetail(step: FirmwareFlowStepId, raw: string): string {
  return cleanFailureDetailFromError(step, raw);
}

function fqbnFromSelection(
  targets: CleanFirmwareTargets | null,
  boardId: string,
  bootloaderId: string,
): string {
  if (!targets) return 'arduino:avr:nano';
  const board = targets.boards.find((b) => b.id === boardId) ?? targets.boards[0];
  if (!board) return 'arduino:avr:nano';
  const boot = board.bootloaders.find((b) => b.id === bootloaderId) ?? board.bootloaders[0];
  return `${board.fqbn_base}${boot?.fqbn_suffix ?? ''}`;
}

function matchSelectionFromFqbn(
  targets: CleanFirmwareTargets | null,
  fqbnRaw: string,
): { boardId: string; bootloaderId: string } | null {
  if (!targets) return null;
  const fqbn = String(fqbnRaw || '').trim().toLowerCase();
  for (const board of targets.boards) {
    for (const boot of board.bootloaders) {
      const candidate = `${board.fqbn_base}${boot.fqbn_suffix}`.toLowerCase();
      if (candidate === fqbn) return { boardId: board.id, bootloaderId: boot.id };
    }
  }
  return null;
}

function looksLikeTargetPort(row: CleanFirmwareBoards['ports'][number], family: string): boolean {
  const addr = String(row?.address ?? '').toLowerCase();
  const fqbn = String(row?.fqbn ?? '').toLowerCase();
  const name = String(row?.board_name ?? '').toLowerCase();
  if (family === 'teensy') return fqbn.includes('teensy') || name.includes('teensy') || addr.includes('usbmodem');
  if (family === 'esp32') return fqbn.includes('esp32') || name.includes('esp32') || addr.includes('usbserial') || addr.includes('wchusbserial');
  if (family === 'rp2040') return fqbn.includes('rp2040') || name.includes('rp2040') || name.includes('pico') || addr.includes('usbmodem');
  if (fqbn.includes('arduino')) return true;
  if (name.includes('arduino') || name.includes('nano') || name.includes('uno')) return true;
  if (addr.includes('usbserial') || addr.includes('usbmodem') || addr.includes('wchusbserial')) return true;
  return false;
}

function familyOptionsFromTargets(targets: CleanFirmwareTargets | null): FirmwareTargetFamily[] {
  if (!targets || !Array.isArray(targets.families) || targets.families.length === 0) {
    return [
      { id: 'arduino_avr', label: 'Arduino AVR' },
      { id: 'esp32', label: 'ESP32' },
      { id: 'rp2040', label: 'RP2040' },
      { id: 'teensy', label: 'Teensy' },
    ];
  }
  return targets.families;
}

function boardOptionsForFamily(targets: CleanFirmwareTargets | null, familyId: string): FirmwareTargetBoard[] {
  if (!targets || !Array.isArray(targets.boards)) return [];
  return targets.boards.filter((b) => b.family === familyId);
}

function resolveBoard(targets: CleanFirmwareTargets | null, familyId: string, boardId: string): FirmwareTargetBoard | null {
  const options = boardOptionsForFamily(targets, familyId);
  if (options.length === 0) return null;
  return options.find((b) => b.id === boardId) ?? options[0];
}

function resolveBootloaderId(board: FirmwareTargetBoard | null, bootloaderId: string): string {
  if (!board || !Array.isArray(board.bootloaders) || board.bootloaders.length === 0) return 'default';
  const found = board.bootloaders.find((b) => b.id === bootloaderId);
  if (found) return found.id;
  return board.default_bootloader || board.bootloaders[0].id;
}

function buildUploadRetryGuide(rawText: string, boardId: string, bootloaderId: string): UploadRetryGuide | null {
  const t = String(rawText || '').toLowerCase();
  if (!t.trim()) return null;
  if (t.includes('upload_port_missing') || t.includes('selected_port_not_detected') || t.includes('no serial port detected')) {
    return {
      title: 'Port mismatch',
      steps: [
        { id: 'port_mismatch_detect', label: 'Run Detect to refresh serial ports.', actionKey: 'detect_port' },
        { id: 'port_mismatch_select', label: 'Select the active USB serial port in Port.', actionKey: 'select_port' },
        { id: 'port_mismatch_retry', label: 'Retry Upload.', actionKey: 'retry_upload' },
      ],
      lockSequence: true,
    };
  }
  if (t.includes('stk500_recv') || t.includes('programmer is not responding') || t.includes('not in sync')) {
    const bootloaderHint = boardId === 'nano' && bootloaderId === 'old'
      ? 'Switch Nano Bootloader to New, then retry Upload within 2s of reset.'
      : (boardId === 'nano' && bootloaderId === 'new'
        ? 'Switch Nano Bootloader to Old (classic Nano), then retry Upload within 2s of reset.'
        : (boardId === 'esp32_devkit'
          ? 'For ESP32, hold BOOT and tap EN/RESET once, then retry Upload.'
          : (boardId === 'rp2040_pico'
            ? 'For Pico, hold BOOTSEL while plugging in and verify the board is in upload mode.'
            : (boardId === 'teensy40' || boardId === 'teensy41'
              ? 'For Teensy, press the Program button once, then retry Upload.'
              : 'Try board-specific boot/reset sequence, then retry Upload.'))));
    return {
      title: 'Bootloader sync failure',
      steps: [
        { id: 'boot_sync_select', label: bootloaderHint, actionKey: 'set_bootloader' },
        { id: 'boot_sync_retry', label: 'Retry Upload.', actionKey: 'retry_upload' },
      ],
      notes: ['Press reset once on the board right before retry. If it still fails, swap USB cable/port and retry.'],
      lockSequence: true,
    };
  }
  if (t.includes('ser_open') || t.includes('resource busy') || t.includes('permission denied')) {
    return {
      title: 'Serial port busy',
      steps: [
        { id: 'port_busy_restart', label: 'Copy and run bridge restart command.', actionKey: 'copy_restart_cmd' },
        { id: 'port_busy_check', label: 'Run Recovery Check / Detect.', actionKey: 'check' },
        { id: 'port_busy_retry', label: 'Retry Upload.', actionKey: 'retry_upload' },
      ],
      notes: ['Close any serial monitor/terminal using the same port before retrying.'],
      lockSequence: true,
    };
  }
  if (t.includes('reconnect failed') || t.includes('no status response')) {
    return {
      title: 'Post-flash reconnect issue',
      steps: [
        { id: 'reconnect_restart', label: 'Copy and run bridge restart command.', actionKey: 'copy_restart_cmd' },
        { id: 'reconnect_check', label: 'Run Recovery Check.', actionKey: 'check' },
        { id: 'reconnect_retry', label: 'Retry Upload after bridge reconnect.', actionKey: 'retry_upload' },
      ],
      lockSequence: true,
    };
  }
  if (t.includes('timed out') || t.includes('timeout')) {
    return {
      title: 'Timeout during upload',
      steps: [
        { id: 'timeout_detect', label: 'Run Detect to confirm selected port is still present.', actionKey: 'detect_port' },
        { id: 'timeout_refresh', label: 'Run Refresh.', actionKey: 'refresh_status' },
        { id: 'timeout_retry', label: 'Retry Upload.', actionKey: 'retry_upload' },
      ],
      notes: ['Keep board powered and cable stable; avoid hubs during upload.'],
      lockSequence: true,
    };
  }
  return null;
}

function buildTargetRunbookGuide(
  runbook: TargetRunbook | null,
  failureDetail: string,
): UploadRetryGuide | null {
  if (!runbook) return null;
  const detail = String(failureDetail || '').toLowerCase();
  const recoverySteps = runbook.recovery_steps ?? {};
  if (detail.includes('runtime_manifest_invalid') && Array.isArray(recoverySteps.runtime_manifest_invalid)) {
    return { title: `${runbook.target.board_label} runbook: Manifest`, steps: recoverySteps.runtime_manifest_invalid, lockSequence: true };
  }
  if (detail.includes('selected_port_not_detected') && Array.isArray(recoverySteps.selected_port_not_detected)) {
    return { title: `${runbook.target.board_label} runbook: Port`, steps: recoverySteps.selected_port_not_detected, lockSequence: true };
  }
  if (detail.includes('upload_port_missing') && Array.isArray(recoverySteps.upload_port_missing)) {
    return { title: `${runbook.target.board_label} runbook: Port`, steps: recoverySteps.upload_port_missing, lockSequence: true };
  }
  if (detail.includes('firmware_busy') && Array.isArray(recoverySteps.firmware_busy)) {
    return { title: `${runbook.target.board_label} runbook: Busy`, steps: recoverySteps.firmware_busy, lockSequence: true };
  }
  if ((detail.includes('not in sync') || detail.includes('stk500') || detail.includes('programmer is not responding'))
    && Array.isArray(recoverySteps.bootloader_sync)) {
    return { title: `${runbook.target.board_label} runbook: Bootloader`, steps: recoverySteps.bootloader_sync, lockSequence: true };
  }
  if (Array.isArray(runbook.upload_sequence_steps) && runbook.upload_sequence_steps.length > 0) {
    return { title: `${runbook.target.board_label} upload sequence`, steps: runbook.upload_sequence_steps, lockSequence: true };
  }
  if (Array.isArray(runbook.upload_sequence) && runbook.upload_sequence.length > 0) {
    return {
      title: `${runbook.target.board_label} upload sequence`,
      steps: runbook.upload_sequence.map((label, idx) => ({ id: `upload_seq_${idx}`, label: String(label) })),
    };
  }
  return null;
}

export function CleanIdeFirmwarePanel(
  { mode, onGlobalStatus }: { mode: CleanMode; onGlobalStatus?: (evt: { level: IdeStatusLevel; summary: string; source: string; ts: number }) => void },
): JSX.Element {
  const didInitialStatusRefreshRef = useRef(false);
  const [apiContractOk, setApiContractOk] = useState(true);
  const [apiContractDetail, setApiContractDetail] = useState('');
  const [busyAction, setBusyAction] = useState<'none' | 'compile' | 'upload' | 'preflight'>('none');
  const [statusLine, setStatusLine] = useState('Firmware tools ready');
  const [firmwareState, setFirmwareState] = useState<CleanFirmwareStatus | null>(null);
  const [boardHints, setBoardHints] = useState<CleanFirmwareBoards | null>(null);
  const [targetRegistry, setTargetRegistry] = useState<CleanFirmwareTargets | null>(null);
  const [detectingBoards, setDetectingBoards] = useState(false);
  const [boardFamilyId, setBoardFamilyId] = useState<string>(() => {
    try {
      const v = String(window.localStorage.getItem('clean.firmware.board_family') || '').trim();
      if (v) return v;
      return 'arduino_avr';
    } catch {
      return 'arduino_avr';
    }
  });
  const [boardId, setBoardId] = useState<string>(() => {
    try {
      const v = String(window.localStorage.getItem('clean.firmware.board_id') || '').trim();
      if (v) return v;
      return 'nano';
    } catch {
      return 'nano';
    }
  });
  const [bootloaderId, setBootloaderId] = useState<string>(() => {
    try {
      const v = String(window.localStorage.getItem('clean.firmware.bootloader_id') || '').trim();
      if (v) return v;
      const legacyBoot = String(window.localStorage.getItem('clean.firmware.nano_bootloader') || '').trim();
      if (legacyBoot === 'old') return 'old';
      return 'new';
    } catch {
      return 'new';
    }
  });
  const [selectedPort, setSelectedPort] = useState<string>(() => {
    try {
      return window.localStorage.getItem('clean.firmware.port') ?? '';
    } catch {
      return '';
    }
  });
  const [opsLog, setOpsLog] = useState<Array<{ ts: number; text: string }>>([]);
  const [failureBanner, setFailureBanner] = useState<{ kind: string; detail: string } | null>(null);
  const [firmwareLastResult, setFirmwareLastResult] = useState<{
    action: 'compile' | 'upload' | 'preflight';
    ok: boolean;
    returncode: number | null;
    ts: number;
  } | null>(null);
  const [logOpen, setLogOpen] = useState(false);
  const [firmwareLog, setFirmwareLog] = useState<string>('');
  const [logBusy, setLogBusy] = useState(false);
  const [runbookStatus, setRunbookStatus] = useState('');
  const [targetRunbook, setTargetRunbook] = useState<TargetRunbook | null>(null);
  const [flow, setFlow] = useState<FirmwareFlowMap>(() => createInitialFlowMap());
  const lastGlobalKeyRef = useRef<string>('');

  const familyOptions = useMemo(() => familyOptionsFromTargets(targetRegistry), [targetRegistry]);
  const boardOptions = useMemo(
    () => boardOptionsForFamily(targetRegistry, boardFamilyId),
    [targetRegistry, boardFamilyId],
  );
  const selectedBoard = useMemo(
    () => resolveBoard(targetRegistry, boardFamilyId, boardId),
    [targetRegistry, boardFamilyId, boardId],
  );
  const selectedBootloaderId = useMemo(
    () => resolveBootloaderId(selectedBoard, bootloaderId),
    [selectedBoard, bootloaderId],
  );
  const bootloaderOptions = useMemo(
    () => selectedBoard?.bootloaders ?? [],
    [selectedBoard],
  );
  const effectiveFqbn = useMemo(
    () => fqbnFromSelection(targetRegistry, selectedBoard?.id ?? boardId, selectedBootloaderId),
    [targetRegistry, selectedBoard?.id, boardId, selectedBootloaderId],
  );

  const publishGlobalStatus = useCallback((level: IdeStatusLevel, summary: string, source: string): void => {
    if (!onGlobalStatus) return;
    const key = `${level}|${source}|${summary}`;
    if (lastGlobalKeyRef.current === key) return;
    lastGlobalKeyRef.current = key;
    onGlobalStatus({ level, summary, source, ts: Date.now() });
  }, [onGlobalStatus]);

  const classifyFailure = useCallback((errText: string): { kind: string; detail: string } => {
    return {
      kind: cleanFailureKindFromError(errText),
      detail: cleanFailureDetailFromError('generic', errText),
    };
  }, []);

  const uploadGuide = useMemo(() => {
    const fromRunbook = buildTargetRunbookGuide(targetRunbook, failureBanner?.detail ?? '');
    if (fromRunbook) return fromRunbook;
    const tail = (firmwareState?.log_tail ?? []).slice(-12).join('\n');
    const raw = `${statusLine}\n${failureBanner?.detail ?? ''}\n${tail}\n${firmwareLog}\nboard=${selectedBoard?.id ?? boardId}`;
    return buildUploadRetryGuide(raw, selectedBoard?.id ?? boardId, selectedBootloaderId);
  }, [boardId, failureBanner?.detail, firmwareLog, firmwareState?.log_tail, selectedBoard?.id, selectedBootloaderId, statusLine, targetRunbook]);

  const setFlowStep = useCallback((id: FirmwareFlowStepId, state: FirmwareFlowStepState, detail: string): void => {
    setFlow((prev) => ({ ...prev, [id]: { state, detail } }));
  }, []);

  const resetFlowFrom = useCallback((id: FirmwareFlowStepId): void => {
    const idx = FLOW_STEPS.findIndex((s) => s.id === id);
    if (idx < 0) return;
    const downstream = FLOW_STEPS.slice(idx + 1).map((s) => s.id);
    setFlow((prev) => {
      const next = { ...prev };
      for (const stepId of downstream) next[stepId] = { state: 'idle', detail: 'idle' };
      return next;
    });
  }, []);

  const nextStep = useMemo<FirmwareFlowStepId>(() => {
    const running = FLOW_STEPS.find((s) => flow[s.id].state === 'running');
    if (running) return running.id;
    const pending = FLOW_STEPS.find((s) => flow[s.id].state !== 'pass');
    return pending?.id ?? 'verify';
  }, [flow]);

  const flowSummary = useMemo(() => {
    if (FLOW_STEPS.every((s) => flow[s.id].state === 'pass')) return 'flow complete';
    const next = FLOW_STEPS.find((s) => s.id === nextStep)?.label ?? 'Detect';
    return `current step: ${next}`;
  }, [flow, nextStep]);

  const pushOpLog = useCallback((text: string): void => {
    setOpsLog((prev) => [{ ts: Date.now(), text }, ...prev].slice(0, 12));
  }, []);

  const persistOverrides = useCallback((): void => {
    try {
      window.localStorage.setItem('clean.firmware.fqbn', effectiveFqbn);
      window.localStorage.setItem('clean.firmware.port', selectedPort.trim());
      window.localStorage.setItem('clean.firmware.board_family', boardFamilyId);
      window.localStorage.setItem('clean.firmware.board_id', selectedBoard?.id ?? boardId);
      window.localStorage.setItem('clean.firmware.bootloader_id', selectedBootloaderId);
      window.localStorage.removeItem('clean.firmware.board_target');
      window.localStorage.setItem('clean.firmware.board_profile', (selectedBoard?.id ?? boardId) === 'uno' ? 'uno' : 'nano');
      window.localStorage.setItem('clean.firmware.nano_bootloader', selectedBootloaderId === 'old' ? 'old' : 'new');
    } catch {
      // ignore storage failures
    }
  }, [boardFamilyId, boardId, effectiveFqbn, selectedBoard?.id, selectedBootloaderId, selectedPort]);

  const refreshBoardHints = useCallback(async (markFlow = false): Promise<void> => {
    setDetectingBoards(true);
    if (markFlow) {
      setFlowStep('detect', 'running', 'detecting ports...');
      resetFlowFrom('detect');
    }
    try {
      const [boards, targets] = await Promise.all([cleanFirmwareBoards(), cleanFirmwareTargets()]);
      setBoardHints(boards);
      setTargetRegistry(targets);

      const fallbackFamily = familyOptionsFromTargets(targets)[0]?.id ?? 'arduino_avr';
      let nextFamily = boardFamilyId;
      let nextBoardId = boardId;
      let nextBootloaderId = bootloaderId;

      const families = familyOptionsFromTargets(targets);
      if (!families.some((f) => f.id === nextFamily)) nextFamily = fallbackFamily;

      if (boards.recommended_fqbn) {
        const fromFqbn = matchSelectionFromFqbn(targets, String(boards.recommended_fqbn));
        if (fromFqbn) {
          const recBoard = targets.boards.find((b) => b.id === fromFqbn.boardId);
          if (recBoard) {
            nextFamily = recBoard.family;
            nextBoardId = recBoard.id;
            nextBootloaderId = fromFqbn.bootloaderId;
          }
        }
      }

      const resolvedBoard = resolveBoard(targets, nextFamily, nextBoardId);
      if (resolvedBoard) {
        nextBoardId = resolvedBoard.id;
        nextBootloaderId = resolveBootloaderId(resolvedBoard, nextBootloaderId);
      } else {
        const firstBoard = targets.boards[0];
        if (firstBoard) {
          nextFamily = firstBoard.family;
          nextBoardId = firstBoard.id;
          nextBootloaderId = resolveBootloaderId(firstBoard, nextBootloaderId);
        }
      }

      if (nextFamily !== boardFamilyId) setBoardFamilyId(nextFamily);
      if (nextBoardId !== boardId) setBoardId(nextBoardId);
      if (nextBootloaderId !== bootloaderId) setBootloaderId(nextBootloaderId);

      const current = selectedPort.trim();
      const rows = (boards.ports ?? []).filter((p) => String(p.address ?? '').trim().length > 0);
      const detected = rows
        .map((p) => String(p.address ?? '').trim())
        .filter((v) => v.length > 0);
      const currentStillDetected = current.length > 0 && detected.includes(current);
      const currentRow = rows.find((p) => String(p.address ?? '').trim() === current);
      const currentLooksTarget = currentRow ? looksLikeTargetPort(currentRow, nextFamily) : false;
      const targetCandidate = (boards.ports ?? []).find((p) => looksLikeTargetPort(p, nextFamily));
      const preferredPort = String(
        boards.recommended_port
        || targetCandidate?.address
        || detected[0]
        || '',
      ).trim();
      // Safety policy: auto-select only when port is empty.
      // Never silently override an explicit user-selected port; let precheck block with a clear reason.
      if (!current && preferredPort && preferredPort !== current) {
        setSelectedPort(preferredPort);
        pushOpLog(`port auto-selected: ${preferredPort}`);
      }
      pushOpLog('board/port auto-detect refreshed');
      if (markFlow) {
        const found = detected.length;
        setFlowStep('detect', 'pass', found > 0 ? `${found} port(s)` : 'detected');
      }
    } catch (err) {
      const em = String(err);
      pushOpLog(`board detect error: ${em.slice(0, 120)}`);
      if (markFlow) setFlowStep('detect', 'fail', plainFlowDetail('detect', em));
    } finally {
      setDetectingBoards(false);
    }
  }, [boardFamilyId, boardId, bootloaderId, pushOpLog, resetFlowFrom, selectedPort, setFlowStep]);

  const waitForFirmwareDone = useCallback(async (): Promise<CleanFirmwareStatus> => {
    const start = Date.now();
    const maxMs = 180000;
    let last: CleanFirmwareStatus | null = null;
    while ((Date.now() - start) < maxMs) {
      const st = await cleanFirmwareStatus();
      last = st;
      setFirmwareState(st);
      if (!st.running) return st;
      await new Promise((resolve) => window.setTimeout(resolve, 700));
    }
    if (last) return last;
    throw new Error('firmware_status_timeout');
  }, []);

  const loadFirmwareLog = useCallback(async (): Promise<void> => {
    setLogBusy(true);
    try {
      const st = await cleanFirmwareStatus();
      setFirmwareState(st);
      const lines = st.log_tail ?? [];
      setFirmwareLog(lines.length ? lines.join('\n') : '(no firmware log lines yet)');
      pushOpLog('firmware log refreshed');
    } catch (err) {
      const em = String(err);
      setFirmwareLog(`log load failed: ${em}`);
      pushOpLog(`firmware log error: ${em.slice(0, 120)}`);
      publishGlobalStatus('fail', 'Firmware log refresh failed', 'ide');
    } finally {
      setLogBusy(false);
    }
  }, [publishGlobalStatus, pushOpLog]);

  const refreshStatus = useCallback(async () => {
    persistOverrides();
    try {
      const [st, api] = await Promise.all([cleanFirmwareStatus(), cleanStatus(mode)]);
      const version = Number(api.clean_api?.version ?? 0);
      const caps = api.clean_api?.capabilities ?? [];
      const hasPrecheck = caps.includes('firmware_upload_precheck');
      const contractOk = version >= 2 && hasPrecheck;
      setApiContractOk(contractOk);
      setApiContractDetail(
        contractOk ? '' : `Bridge API outdated (version=${version || 0}). Restart bridge to load latest clean runtime.`,
      );
      setFirmwareState(st);
      const activeOp = st.operation?.active;
      const opSuffix = activeOp
        ? ` lock=${String(activeOp.phase || '')}:${String(activeOp.op_id || '').slice(0, 8)}`
        : '';
      setStatusLine(`state=${st.state} phase=${st.phase} running=${st.running ? 'yes' : 'no'}${opSuffix}`);
      if (flow.upload.state === 'pass' && String(st.state || '').length > 0) {
        setFlowStep('reconnect', 'pass', `state=${st.state}`);
      }
      if (contractOk) setFailureBanner(null);
      else setFailureBanner({ kind: 'bridge_down', detail: `bridge_api_outdated: version=${version || 0}; restart bridge` });
      pushOpLog('firmware status refreshed');
      publishGlobalStatus(contractOk ? 'ok' : 'fail', contractOk ? 'Firmware status refreshed' : 'Bridge API outdated', 'ide');
    } catch (err) {
      const em = String(err);
      setApiContractOk(false);
      setApiContractDetail('Bridge status unavailable. Restart bridge.');
      setStatusLine(`status error: ${em}`);
      setFailureBanner(classifyFailure(em));
      pushOpLog(`firmware status error: ${em.slice(0, 120)}`);
      publishGlobalStatus('fail', 'Firmware status failed', 'ide');
    }
  }, [classifyFailure, flow.upload.state, mode, persistOverrides, publishGlobalStatus, pushOpLog, setFlowStep]);

  const verifyReconnectAfterUpload = useCallback(async (): Promise<boolean> => {
    setFlowStep('reconnect', 'running', 'waiting for bridge status...');
    const start = Date.now();
    const maxMs = 30000;
    let lastErr = '';
    while ((Date.now() - start) < maxMs) {
      try {
        const st = await cleanStatus(mode);
        if (Boolean(st.health.connected)) {
          setFlowStep('reconnect', 'pass', 'Bridge online and responding');
          pushOpLog('reconnect verified');
          publishGlobalStatus('ok', 'Reconnect verified', 'firmware');
          return true;
        }
      } catch (err) {
        lastErr = String(err);
      }
      await new Promise((resolve) => window.setTimeout(resolve, 700));
    }
    const detail = plainFlowDetail('reconnect', lastErr || 'bridge_offline');
    setFlowStep('reconnect', 'fail', detail);
    setFailureBanner({ kind: 'bridge_down', detail: lastErr || 'bridge_offline_after_upload' });
    pushOpLog(`reconnect verify failed: ${detail}`);
    publishGlobalStatus('fail', 'Reconnect verify failed', 'firmware');
    return false;
  }, [mode, publishGlobalStatus, pushOpLog, setFlowStep]);

  useEffect(() => {
    void refreshBoardHints();
  }, [refreshBoardHints]);
  useEffect(() => {
    if (didInitialStatusRefreshRef.current) return;
    didInitialStatusRefreshRef.current = true;
    void refreshStatus();
  }, [refreshStatus]);

  const runCompile = useCallback(async () => {
    if (busyAction !== 'none') return;
    persistOverrides();
    setBusyAction('compile');
    setFlowStep('compile', 'running', 'compiling...');
    resetFlowFrom('compile');
    setStatusLine('compile started...');
    pushOpLog('compile started');
    publishGlobalStatus('warn', 'Compile running', 'firmware');
    try {
      const out = await cleanFirmwareCompile(undefined, effectiveFqbn || undefined);
      if (!out.ok) {
        const em = out.error ?? 'unknown';
        setStatusLine(`compile failed: ${em}`);
        pushOpLog(`compile failed: ${em.slice(0, 120)}`);
        setFailureBanner(classifyFailure(em));
        setFirmwareLastResult({ action: 'compile', ok: false, returncode: null, ts: Date.now() });
        setFlowStep('compile', 'fail', plainFlowDetail('compile', em));
        publishGlobalStatus('fail', 'Compile failed', 'firmware');
        return;
      }
      const final = await waitForFirmwareDone();
      if ((final.returncode ?? 1) === 0) {
        setStatusLine('compile complete: PASS');
        pushOpLog('compile complete: PASS');
        setFailureBanner(null);
        setFirmwareLastResult({ action: 'compile', ok: true, returncode: final.returncode ?? 0, ts: Date.now() });
        setFlowStep('compile', 'pass', 'compile PASS');
        publishGlobalStatus('ok', 'Compile PASS', 'firmware');
      } else {
        const tail = (final.log_tail ?? []).slice(-1)[0] ?? `returncode=${String(final.returncode ?? 'n/a')}`;
        setStatusLine('compile complete: FAIL');
        pushOpLog(`compile complete: FAIL (${tail.slice(0, 120)})`);
        setFailureBanner(classifyFailure(tail));
        setFirmwareLastResult({ action: 'compile', ok: false, returncode: final.returncode ?? null, ts: Date.now() });
        setFlowStep('compile', 'fail', plainFlowDetail('compile', tail));
        publishGlobalStatus('fail', 'Compile FAIL', 'firmware');
      }
    } catch (err) {
      const em = String(err);
      setStatusLine(`compile error: ${em}`);
      pushOpLog(`compile error: ${em.slice(0, 120)}`);
      setFailureBanner(classifyFailure(em));
      setFirmwareLastResult({ action: 'compile', ok: false, returncode: null, ts: Date.now() });
      setFlowStep('compile', 'fail', plainFlowDetail('compile', em));
      publishGlobalStatus('fail', 'Compile error', 'firmware');
    } finally {
      setBusyAction('none');
    }
  }, [busyAction, classifyFailure, effectiveFqbn, persistOverrides, publishGlobalStatus, pushOpLog, resetFlowFrom, setFlowStep, waitForFirmwareDone]);

  const runUpload = useCallback(async () => {
    if (busyAction !== 'none') return;
    persistOverrides();
    setBusyAction('upload');
    setFlowStep('upload', 'running', 'upload precheck...');
    resetFlowFrom('upload');
    setStatusLine('upload precheck...');
    pushOpLog('upload precheck started');
    publishGlobalStatus('warn', 'Upload precheck', 'firmware');
    try {
      try {
        const pre = await cleanFirmwareUploadPrecheck(
          selectedPort.trim() || undefined,
          effectiveFqbn || undefined,
        );
        setTargetRunbook((pre.target_runbook as TargetRunbook | undefined) ?? null);
        if (!pre.ready) {
          const reasons = pre.hard_fail_reasons.length > 0 ? pre.hard_fail_reasons : pre.reasons;
          const reasonText = reasons.join(', ') || pre.error || 'upload_precheck_failed';
          setStatusLine(`upload blocked: ${reasonText}`);
          pushOpLog(`upload blocked: ${reasonText.slice(0, 120)}`);
          setFailureBanner({ kind: 'upload_failed', detail: `precheck: ${reasonText}` });
          setFirmwareLastResult({ action: 'upload', ok: false, returncode: null, ts: Date.now() });
          setFlowStep('upload', 'fail', plainFlowDetail('upload', reasonText));
          publishGlobalStatus('fail', `Upload blocked (${reasonText})`, 'firmware');
          return;
        }
      } catch (err) {
        if (cleanIsNotFoundError(err)) {
          pushOpLog('precheck endpoint unavailable on current bridge; continuing upload');
        } else {
          throw err;
        }
      }

      setStatusLine('upload started...');
      pushOpLog('upload started');
      publishGlobalStatus('warn', 'Upload running', 'firmware');
      const out = await cleanFirmwareUpload(undefined, effectiveFqbn || undefined, selectedPort.trim() || undefined);
      if (!out.ok) {
        const em = out.error ?? 'unknown';
        setStatusLine(`upload failed: ${em}`);
        pushOpLog(`upload failed: ${em.slice(0, 120)}`);
        setFailureBanner(classifyFailure(em));
        setFirmwareLastResult({ action: 'upload', ok: false, returncode: null, ts: Date.now() });
        setFlowStep('upload', 'fail', plainFlowDetail('upload', em));
        publishGlobalStatus('fail', 'Upload failed', 'firmware');
        return;
      }
      const final = await waitForFirmwareDone();
      if ((final.returncode ?? 1) === 0) {
        setStatusLine('upload complete: PASS; verifying reconnect...');
        pushOpLog('upload complete: PASS');
        setFailureBanner(null);
        setFirmwareLastResult({ action: 'upload', ok: true, returncode: final.returncode ?? 0, ts: Date.now() });
        setFlowStep('upload', 'pass', 'upload PASS');
        const reconnectOk = await verifyReconnectAfterUpload();
        if (reconnectOk) {
          setStatusLine('upload complete: PASS');
          publishGlobalStatus('ok', 'Upload PASS', 'firmware');
        } else {
          setStatusLine('upload complete, reconnect verify failed (run Check or Restart bridge)');
          publishGlobalStatus('warn', 'Upload PASS; reconnect pending recovery', 'firmware');
        }
      } else {
        const tail = (final.log_tail ?? []).slice(-1)[0] ?? `returncode=${String(final.returncode ?? 'n/a')}`;
        setStatusLine('upload complete: FAIL');
        pushOpLog(`upload complete: FAIL (${tail.slice(0, 120)})`);
        setFailureBanner(classifyFailure(tail));
        setFirmwareLastResult({ action: 'upload', ok: false, returncode: final.returncode ?? null, ts: Date.now() });
        setFlowStep('upload', 'fail', plainFlowDetail('upload', tail));
        publishGlobalStatus('fail', 'Upload FAIL', 'firmware');
      }
    } catch (err) {
      const em = String(err);
      setStatusLine(`upload error: ${em}`);
      pushOpLog(`upload error: ${em.slice(0, 120)}`);
      setFailureBanner(classifyFailure(em));
      setFirmwareLastResult({ action: 'upload', ok: false, returncode: null, ts: Date.now() });
      setFlowStep('upload', 'fail', plainFlowDetail('upload', em));
      publishGlobalStatus('fail', 'Upload error', 'firmware');
    } finally {
      setBusyAction('none');
    }
  }, [busyAction, classifyFailure, effectiveFqbn, persistOverrides, publishGlobalStatus, pushOpLog, resetFlowFrom, selectedPort, setFlowStep, verifyReconnectAfterUpload, waitForFirmwareDone]);

  const runPreflight = useCallback(async () => {
    if (busyAction !== 'none') return;
    setBusyAction('preflight');
    const startedAt = Date.now();
    let doneChecks = 0;
    let totalChecks = 0;
    setFlowStep('verify', 'running', 'starting preflight...');
    setStatusLine('preflight started...');
    pushOpLog('preflight started');
    publishGlobalStatus('warn', 'Preflight running', 'preflight');
    try {
      const out = await cleanPreflightStream(mode, false, {
        onStart: () => {
          setFlowStep('verify', 'running', 'preflight stream connected');
        },
        onCheckStart: ({ index, total, id }) => {
          totalChecks = Math.max(totalChecks, total);
          const elapsed = Math.max(0, Math.floor((Date.now() - startedAt) / 1000));
          const detail = `running ${id} (${index}/${total}) · ${elapsed}s`;
          setFlowStep('verify', 'running', detail);
          setStatusLine(`preflight: ${detail}`);
          pushOpLog(`preflight start ${id} (${index}/${total})`);
        },
        onCheckDone: ({ index, total, result }) => {
          doneChecks = Math.max(doneChecks, index);
          totalChecks = Math.max(totalChecks, total);
          const elapsed = Math.max(0, Math.floor((Date.now() - startedAt) / 1000));
          const mark = result.ok ? 'PASS' : 'FAIL';
          const detail = `completed ${result.id} ${mark} (${doneChecks}/${totalChecks}) · ${elapsed}s`;
          setFlowStep('verify', 'running', detail);
          setStatusLine(`preflight: ${detail}`);
          pushOpLog(`preflight ${result.id} ${mark} dt=${result.dt_ms}ms`);
        },
      });
      const pass = out.results.filter((r) => r.ok).length;
      if (out.ok) {
        setStatusLine(`preflight PASS (${pass}/${out.results.length})`);
        pushOpLog(`preflight PASS (${pass}/${out.results.length})`);
        setFailureBanner(null);
        setFirmwareLastResult({ action: 'preflight', ok: true, returncode: 0, ts: Date.now() });
        setFlowStep('verify', 'pass', `PASS ${pass}/${out.results.length}`);
        publishGlobalStatus('ok', `Preflight PASS (${pass}/${out.results.length})`, 'preflight');
      } else {
        setStatusLine(`preflight FAIL (${out.failures} failed of ${out.results.length})`);
        pushOpLog(`preflight FAIL (${out.failures}/${out.results.length})`);
        setFailureBanner({ kind: 'tool_failed', detail: `preflight_failures=${out.failures}/${out.results.length}` });
        setFirmwareLastResult({ action: 'preflight', ok: false, returncode: out.failures, ts: Date.now() });
        setFlowStep('verify', 'fail', `Failed ${out.failures} check(s)`);
        publishGlobalStatus('fail', `Preflight FAIL (${out.failures}/${out.results.length})`, 'preflight');
      }
    } catch (err) {
      const em = String(err);
      setStatusLine(`preflight error: ${em}`);
      pushOpLog(`preflight error: ${em.slice(0, 120)}`);
      setFailureBanner(classifyFailure(em));
      setFirmwareLastResult({ action: 'preflight', ok: false, returncode: null, ts: Date.now() });
      setFlowStep('verify', 'fail', plainFlowDetail('verify', em));
      publishGlobalStatus('fail', 'Preflight error', 'preflight');
    } finally {
      setBusyAction('none');
    }
  }, [busyAction, classifyFailure, mode, publishGlobalStatus, pushOpLog, setFlowStep]);

  const copyText = useCallback(async (text: string, label: string): Promise<void> => {
    try {
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
      } else {
        const node = document.createElement('textarea');
        node.value = text;
        node.style.position = 'fixed';
        node.style.opacity = '0';
        document.body.appendChild(node);
        node.select();
        document.execCommand('copy');
        document.body.removeChild(node);
      }
      setRunbookStatus(`${label} copied`);
      pushOpLog(`${label} copied`);
      publishGlobalStatus('ok', `${label} copied`, 'runbook');
    } catch (err) {
      const em = String(err);
      setRunbookStatus(`${label} copy failed: ${em}`);
      pushOpLog(`${label} copy failed: ${em.slice(0, 120)}`);
      publishGlobalStatus('fail', `${label} copy failed`, 'runbook');
    }
  }, [publishGlobalStatus, pushOpLog]);

  const runRecoveryCheck = useCallback(async (): Promise<void> => {
    if (busyAction !== 'none') return;
    setFlowStep('reconnect', 'running', 'recovery check...');
    setRunbookStatus('recovery check running...');
    pushOpLog('recovery check started');
    try {
      let preReady = true;
      let preSummary = 'ready';
      try {
        const pre = await cleanFirmwareUploadPrecheck(
          selectedPort.trim() || undefined,
          effectiveFqbn || undefined,
        );
        setTargetRunbook((pre.target_runbook as TargetRunbook | undefined) ?? null);
        preReady = pre.ready;
        preSummary = pre.ready ? 'ready' : 'blocked';
        if (!pre.ready) {
          const reasons = pre.hard_fail_reasons.length > 0 ? pre.hard_fail_reasons : pre.reasons;
          setFailureBanner({ kind: 'upload_failed', detail: `precheck: ${reasons.join(', ') || 'blocked'}` });
        }
      } catch (err) {
        if (cleanIsNotFoundError(err)) {
          preSummary = 'legacy_bridge_no_precheck';
          pushOpLog('recovery check: precheck endpoint unavailable on current bridge');
        } else {
          throw err;
        }
      }

      const [st, boards] = await Promise.all([
        cleanStatus(mode),
        cleanFirmwareBoards(),
      ]);
      const bridgeUp = Boolean(st.health.connected);
      const ports = (boards.ports ?? []).filter((p) => String(p.address ?? '').trim().length > 0).length;
      const summary = `Bridge ${bridgeUp ? 'online' : 'offline'} · ${ports} port(s) · precheck ${preSummary === 'ready' ? 'ready' : preSummary}`;
      setRunbookStatus(summary);
      pushOpLog(`recovery check: ${summary}`);
      setFlowStep('reconnect', bridgeUp ? 'pass' : 'fail', bridgeUp ? 'Bridge online and responding' : 'Bridge offline');
      publishGlobalStatus(preReady ? 'ok' : 'warn', `Recovery: ${summary}`, 'runbook');
    } catch (err) {
      const em = String(err);
      setRunbookStatus(`recovery check failed: ${em}`);
      pushOpLog(`recovery check failed: ${em.slice(0, 120)}`);
      setFlowStep('reconnect', 'fail', plainFlowDetail('reconnect', em));
      publishGlobalStatus('fail', 'Recovery check failed', 'runbook');
    }
  }, [busyAction, effectiveFqbn, mode, publishGlobalStatus, pushOpLog, selectedPort, setFlowStep]);

  const runPortRedetect = useCallback(async (): Promise<void> => {
    if (busyAction !== 'none') return;
    setRunbookStatus('port re-detect running...');
    await refreshBoardHints(true);
    setRunbookStatus('port re-detect complete');
    publishGlobalStatus('ok', 'Port re-detect complete', 'runbook');
  }, [busyAction, publishGlobalStatus, refreshBoardHints]);

  const runUploadRetry = useCallback(async (): Promise<void> => {
    if (busyAction !== 'none') return;
    setRunbookStatus('upload retry requested');
    await runUpload();
  }, [busyAction, runUpload]);

  const runKnownGoodRecovery = useCallback(async (): Promise<void> => {
    if (busyAction !== 'none') return;
    setFlowStep('reconnect', 'running', 'known-good running...');
    setRunbookStatus('known-good recovery running...');
    pushOpLog('known-good recovery started');
    try {
      const out = await cleanKnownGoodRecovery(
        selectedPort.trim() || undefined,
        effectiveFqbn || undefined,
      );
      const rec = out.recovery;
      if (rec?.selected_port && rec.selected_port !== selectedPort) {
        setSelectedPort(rec.selected_port);
      }
      const passCount = (rec?.steps ?? []).filter((s) => s.ok).length;
      const total = (rec?.steps ?? []).length;
      setTargetRunbook((rec?.precheck?.target_runbook as TargetRunbook | undefined) ?? null);
      if (out.ok) {
        setRunbookStatus(`known-good recovery PASS (${passCount}/${total})`);
        pushOpLog(`known-good recovery PASS (${passCount}/${total})`);
        setFlowStep('reconnect', 'pass', `PASS ${passCount}/${total}`);
        publishGlobalStatus('ok', `Known-good recovery PASS (${passCount}/${total})`, 'runbook');
      } else {
        const failed = (rec?.steps ?? []).filter((s) => !s.ok).map((s) => s.id).join(', ') || 'unknown';
        setRunbookStatus(`known-good recovery FAIL (${passCount}/${total})`);
        setFailureBanner({ kind: 'tool_failed', detail: `known_good_recovery_failed: ${failed}` });
        pushOpLog(`known-good recovery FAIL (${failed})`);
        setFlowStep('reconnect', 'fail', plainFlowDetail('reconnect', failed));
        publishGlobalStatus('warn', `Known-good recovery FAIL (${failed})`, 'runbook');
      }
      void refreshStatus();
    } catch (err) {
      const em = String(err);
      setRunbookStatus(`known-good recovery failed: ${em}`);
      setFailureBanner({ kind: 'tool_failed', detail: `known_good_recovery_error: ${em}` });
      pushOpLog(`known-good recovery error: ${em.slice(0, 120)}`);
      setFlowStep('reconnect', 'fail', plainFlowDetail('reconnect', em));
      publishGlobalStatus('fail', 'Known-good recovery error', 'runbook');
    }
  }, [busyAction, effectiveFqbn, publishGlobalStatus, pushOpLog, refreshStatus, selectedPort, setFlowStep]);

  const disableActions = busyAction !== 'none';
  const disableToolActions = disableActions || !apiContractOk;
  const detectDone = flow.detect.state === 'pass';
  const compileDone = flow.compile.state === 'pass';
  const uploadDone = flow.upload.state === 'pass';
  const reconnectDone = flow.reconnect.state === 'pass';
  const compileLocked = disableToolActions || !detectDone;
  const uploadLocked = disableToolActions || !compileDone || !selectedPort;
  const reconnectLocked = disableToolActions || !uploadDone;
  const verifyLocked = disableToolActions || !reconnectDone;
  const runningLabel = useMemo(() => (firmwareState?.running ? 'running' : 'idle'), [firmwareState?.running]);
  const detectedPortOptions = useMemo(
    () =>
      (boardHints?.ports ?? [])
        .map((p) => String(p.address ?? '').trim())
        .filter((v) => v.length > 0),
    [boardHints],
  );
  const recommendedPort = String(boardHints?.recommended_port ?? '').trim();
  const portOptions = useMemo(() => {
    const merged = new Set<string>();
    if (recommendedPort) merged.add(recommendedPort);
    for (const p of detectedPortOptions) merged.add(p);
    return Array.from(merged);
  }, [detectedPortOptions, recommendedPort]);
  const activeSketchPath = useMemo(() => {
    const raw = String(firmwareState?.defaults?.sketch ?? '').trim();
    return raw || '(unknown)';
  }, [firmwareState?.defaults?.sketch]);
  return (
    <section className="clean-card clean-gradient clean-ide-card">
      <div className="clean-card-head">
        <h2>IDE Firmware</h2>
        <div className="clean-codex-row">
          <span className="clean-subtle">state: {runningLabel}</span>
          <button
            className="clean-btn clean-btn-alt"
            onClick={() => void refreshBoardHints(true)}
            disabled={disableToolActions || detectingBoards}
          >
            {detectingBoards ? 'Detecting...' : 'Detect'}
          </button>
        </div>
      </div>
      <div className="clean-firmware-flow" aria-label="Firmware workflow steps">
        <div className="clean-firmware-flow-head">{flowSummary}</div>
        <div className="clean-firmware-flow-strip">
          {FLOW_STEPS.map((step) => {
            const info = flow[step.id];
            const active = step.id === nextStep;
            return (
              <div
                key={step.id}
                className={`clean-firmware-flow-step state-${info.state}${active ? ' active' : ''}`}
                aria-current={active ? 'step' : undefined}
              >
                <span className="name">{step.label}</span>
                <span className="state">{info.state}</span>
                <span className="detail">{info.detail}</span>
              </div>
            );
          })}
        </div>
      </div>
      <div className="clean-codex-meta">{statusLine}</div>
      <div className="clean-codex-meta">active sketch: {activeSketchPath}</div>
      <div className="clean-codex-meta">effective FQBN: {effectiveFqbn || '(none)'}</div>
      {!apiContractOk && <div className="clean-codex-meta">bridge contract: {apiContractDetail}</div>}
      {failureBanner && (
        <div className="clean-failure-banner" role="status" aria-live="polite">
          <span className="kind">{failureBanner.kind.replace('_', ' ')}</span>
          <span className="detail">{failureBanner.detail}</span>
        </div>
      )}
      {firmwareLastResult && (
        <div className="clean-last-result" aria-label="Last IDE firmware result">
          <span className="label">last run</span>
          <span className={`value ${firmwareLastResult.ok ? 'ok' : 'bad'}`}>
            {firmwareLastResult.action} {firmwareLastResult.ok ? 'PASS' : 'FAIL'}
          </span>
          <span className="meta">rc={String(firmwareLastResult.returncode ?? 'n/a')}</span>
          <span className="meta">{new Date(firmwareLastResult.ts).toLocaleTimeString()}</span>
        </div>
      )}
      <div className="clean-codex-row">
        <label className="clean-inline-label" htmlFor="clean-board-family">Family</label>
        <select
          id="clean-board-family"
          className="clean-inline-select"
          value={boardFamilyId}
          onChange={(e) => {
            const nextFamily = String(e.target.value || '').trim();
            setBoardFamilyId(nextFamily);
            const nextBoard = resolveBoard(targetRegistry, nextFamily, '');
            if (nextBoard) {
              setBoardId(nextBoard.id);
              setBootloaderId(resolveBootloaderId(nextBoard, ''));
            }
          }}
          disabled={disableToolActions}
        >
          {familyOptions.map((opt) => <option key={opt.id} value={opt.id}>{opt.label}</option>)}
        </select>
        <label className="clean-inline-label" htmlFor="clean-board-id">Board</label>
        <select
          id="clean-board-id"
          className="clean-inline-select"
          value={selectedBoard?.id ?? boardId}
          onChange={(e) => {
            const nextBoard = resolveBoard(targetRegistry, boardFamilyId, String(e.target.value || '').trim());
            if (!nextBoard) return;
            setBoardId(nextBoard.id);
            setBootloaderId(resolveBootloaderId(nextBoard, bootloaderId));
          }}
          disabled={disableToolActions || boardOptions.length === 0}
        >
          {boardOptions.length === 0 ? (
            <option value="">No boards</option>
          ) : (
            boardOptions.map((opt) => <option key={opt.id} value={opt.id}>{opt.label}</option>)
          )}
        </select>
        <label className="clean-inline-label" htmlFor="clean-bootloader-id">Bootloader</label>
        <select
          id="clean-bootloader-id"
          className="clean-inline-select"
          value={selectedBootloaderId}
          onChange={(e) => setBootloaderId(String(e.target.value || '').trim())}
          disabled={disableToolActions || bootloaderOptions.length === 0}
        >
          {bootloaderOptions.length === 0 ? (
            <option value="">No bootloaders</option>
          ) : (
            bootloaderOptions.map((opt) => <option key={opt.id} value={opt.id}>{opt.label}</option>)
          )}
        </select>
        <label className="clean-inline-label" htmlFor="clean-port">Port</label>
        <select
          id="clean-port"
          className="clean-inline-select clean-inline-select-port"
          value={selectedPort}
          onChange={(e) => setSelectedPort(e.target.value)}
          disabled={disableToolActions || portOptions.length === 0}
        >
          {portOptions.length === 0 ? (
            <option value="">No serial port detected</option>
          ) : (
            portOptions.map((v) => <option key={v} value={v}>{v}</option>)
          )}
        </select>
      </div>
      <div className="clean-codex-row">
        <button
          className="clean-btn clean-btn-alt"
          onClick={() => void refreshStatus()}
          disabled={disableToolActions}
        >
          Refresh
        </button>
        <button className="clean-btn clean-btn-alt" onClick={() => void runCompile()} disabled={compileLocked} title={!detectDone ? 'Run Detect first.' : undefined}>
          {busyAction === 'compile' ? 'Compiling...' : 'Compile'}
        </button>
        <button
          className="clean-btn clean-btn-alt"
          onClick={() => void runUpload()}
          disabled={uploadLocked}
          title={!compileDone ? 'Compile must pass before upload.' : (!selectedPort ? 'Select a serial port.' : undefined)}
        >
          {busyAction === 'upload' ? 'Uploading...' : 'Upload'}
        </button>
        <button className="clean-btn" onClick={() => void runPreflight()} disabled={verifyLocked} title={!reconnectDone ? 'Reconnect/validate before verify.' : undefined}>
          {busyAction === 'preflight' ? 'Preflight...' : 'Preflight'}
        </button>
        <button
          className="clean-btn"
          onClick={() => {
            setLogOpen(true);
            void loadFirmwareLog();
          }}
          disabled={disableToolActions}
        >
          Last Log
        </button>
      </div>
      <div className="clean-runbook-actions" aria-label="Recovery runbook actions">
        <div className="clean-runbook-title">Recovery</div>
        <div className="clean-codex-row">
          <button className="clean-btn clean-btn-alt" onClick={() => void runKnownGoodRecovery()} disabled={reconnectLocked} title={!uploadDone ? 'Upload must pass before reconnect checks.' : undefined}>Known-Good</button>
          <button className="clean-btn clean-btn-alt" onClick={() => void runRecoveryCheck()} disabled={reconnectLocked} title={!uploadDone ? 'Upload must pass before reconnect checks.' : undefined}>Check</button>
          <button className="clean-btn clean-btn-alt" onClick={() => void runPortRedetect()} disabled={disableToolActions}>Re-Detect Port</button>
          <button className="clean-btn clean-btn-alt" onClick={() => void runUploadRetry()} disabled={uploadLocked} title={!compileDone ? 'Compile must pass before upload.' : (!selectedPort ? 'Select a serial port.' : undefined)}>Retry Upload</button>
          <button
            className="clean-btn clean-btn-alt"
            onClick={() => void copyText('./tools/restart_bridge.sh', 'Restart command')}
            disabled={disableToolActions}
          >
            Copy Restart Cmd
          </button>
        </div>
        {runbookStatus && <div className="clean-runbook-status">{runbookStatus}</div>}
      </div>
      {uploadGuide && (
        <div className="clean-upload-guide" aria-label="Upload retry guidance">
          <div className="clean-upload-guide-head">{uploadGuide.title}</div>
          <div className="clean-codex-meta">Guidance only. `Check` does not compile or upload.</div>
          {uploadGuide.steps.map((step) => (
            <div key={step.id} className="clean-upload-guide-step">{step.label}</div>
          ))}
          {uploadGuide.notes && uploadGuide.notes.length > 0 && (
            <div className="clean-upload-guide-notes">
              {uploadGuide.notes.map((note, idx) => (
                <div key={`${uploadGuide.title}-note-${String(idx)}`} className="clean-codex-meta">{note}</div>
              ))}
            </div>
          )}
        </div>
      )}
      {opsLog.length > 0 && (
        <div className="clean-ops-log" aria-label="IDE operations log">
          {opsLog.slice(0, 5).map((row) => (
            <div key={`${row.ts}-${row.text}`} className="clean-ops-log-row">
              <span className="time">{new Date(row.ts).toLocaleTimeString()}</span>
              <span className="text">{row.text}</span>
            </div>
          ))}
        </div>
      )}
      {logOpen && (
        <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="Firmware log viewer" onClick={() => setLogOpen(false)}>
          <div className="preflight-modal clean-firmware-log-modal glass-surface glass-surface-strong" onClick={(e) => e.stopPropagation()}>
            <div className="clean-card-head">
              <h2>Firmware Log Tail</h2>
              <div className="clean-codex-row">
                <button className="clean-btn clean-btn-alt" onClick={() => void loadFirmwareLog()} disabled={logBusy}>
                  {logBusy ? 'Refreshing...' : 'Refresh Log'}
                </button>
                <button className="clean-btn" onClick={() => setLogOpen(false)}>Close</button>
              </div>
            </div>
            <pre className="clean-firmware-log-view">{firmwareLog || '(loading...)'}</pre>
          </div>
        </div>
      )}
    </section>
  );
}
