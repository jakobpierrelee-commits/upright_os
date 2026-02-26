import { useCallback, useEffect, useRef, useState } from 'react';
import Editor from '@monaco-editor/react';
import type { FirmwareBoards, FirmwareCheck, FirmwareStatus, SerialDiag } from '../../api';
import type { WorkbenchTab } from './workbenchReducer';
import { strings } from '../../strings';

const SERIAL_SYNC_CHANNEL = 'upright-serial-sync-v1';

type Props = {
  workbenchTab: WorkbenchTab;
  setWorkbenchTab: (tab: WorkbenchTab) => void;
  sketchPath: string;
  setSketchPath: (value: string) => void;
  sketchContent: string;
  setSketchContent: (value: string) => void;
  loadSketch: () => Promise<void>;
  saveSketch: () => Promise<void>;
  runFirmwareCheck: () => Promise<void>;
  runFirmwareInstall: () => Promise<void>;
  refreshBoards: () => Promise<void>;
  fw: FirmwareStatus;
  fwCheck: FirmwareCheck | null;
  fwCfg: { sketch: string; fqbn: string; port: string };
  setFwCfg: (next: { sketch: string; fqbn: string; port: string } | ((prev: { sketch: string; fqbn: string; port: string }) => { sketch: string; fqbn: string; port: string })) => void;
  boardScan: FirmwareBoards | null;
  sketchFolders: string[];
  pickSketchFolder: () => Promise<void>;
  runFirmwareCompile: () => Promise<void>;
  runFirmwareUpload: () => Promise<void>;
  runFirmwareUploadGuarded: () => Promise<void>;
  unifiedSketchName: string;
  setUnifiedSketchName: (value: string) => void;
  unifiedProfileJson: string;
  setUnifiedProfileJson: (value: string) => void;
  runGenerateUnified: () => Promise<void>;
  serialWrite: string;
  setSerialWrite: (value: string) => void;
  sendSerialLine: () => Promise<void>;
  sendSerialCommand: (cmd: string) => Promise<void>;
  refreshLogs: () => Promise<void>;
  serialDiag: SerialDiag | null;
  refreshSerialDiag: () => Promise<void>;
  lines: string[];
  ideMode?: boolean;
  serialWindowMode?: boolean;
};

export function WorkbenchPanel(props: Props) {
  const {
    workbenchTab,
    setWorkbenchTab,
    sketchPath,
    setSketchPath,
    sketchContent,
    setSketchContent,
    loadSketch,
    saveSketch,
    runFirmwareCheck,
    runFirmwareInstall,
    refreshBoards,
    fw,
    fwCheck,
    fwCfg,
    setFwCfg,
    boardScan,
    sketchFolders,
    pickSketchFolder,
    runFirmwareCompile,
    runFirmwareUpload,
    runFirmwareUploadGuarded,
    unifiedSketchName,
    setUnifiedSketchName,
    unifiedProfileJson,
    setUnifiedProfileJson,
    runGenerateUnified,
    serialWrite,
    setSerialWrite,
    sendSerialLine,
    sendSerialCommand,
    refreshLogs,
    serialDiag,
    refreshSerialDiag,
    lines,
    ideMode = false,
    serialWindowMode = false,
  } = props;
  const serialLogRef = useRef<HTMLPreElement | null>(null);
  const sketchFileInputRef = useRef<HTMLInputElement | null>(null);
  const serialDockLogRef = useRef<HTMLPreElement | null>(null);
  const serialDockRef = useRef<HTMLDivElement | null>(null);
  const serialDockPosRef = useRef({ x: 24, y: 118 });
  const serialDockDragRef = useRef<{ active: boolean; pointerId: number; offsetX: number; offsetY: number }>({
    active: false,
    pointerId: -1,
    offsetX: 0,
    offsetY: 0,
  });
  const serialDockResizeRef = useRef<{
    active: boolean;
    pointerId: number;
    startX: number;
    startY: number;
    startW: number;
    startH: number;
  }>({
    active: false,
    pointerId: -1,
    startX: 0,
    startY: 0,
    startW: 0,
    startH: 0,
  });
  const [serialDockOpen, setSerialDockOpen] = useState(false);
  const [saveConfirmOpen, setSaveConfirmOpen] = useState(false);
  const [saveConfirmAck, setSaveConfirmAck] = useState(false);
  const [saveConfirmBusy, setSaveConfirmBusy] = useState(false);
  const serialSyncChannelRef = useRef<BroadcastChannel | null>(null);
  const serialSyncIdRef = useRef(`serial-${Math.random().toString(36).slice(2, 10)}`);
  const serialSyncDebounceRef = useRef<number | null>(null);

  const emitSerialSync = useCallback((event: string) => {
    const ch = serialSyncChannelRef.current;
    if (!ch) return;
    try {
      ch.postMessage({ source: serialSyncIdRef.current, event, ts: Date.now() });
    } catch {
      // Ignore sync-channel errors in restricted browser contexts.
    }
  }, []);

  const scheduleSerialSyncRefresh = useCallback(() => {
    if (serialSyncDebounceRef.current !== null) {
      window.clearTimeout(serialSyncDebounceRef.current);
    }
    serialSyncDebounceRef.current = window.setTimeout(() => {
      serialSyncDebounceRef.current = null;
      void refreshLogs();
      void refreshSerialDiag();
    }, 120);
  }, [refreshLogs, refreshSerialDiag]);

  const applySerialDockPosition = useCallback((x: number, y: number) => {
    const dock = serialDockRef.current;
    if (!dock) return;
    const nextX = Math.round(x);
    const nextY = Math.round(y);
    dock.style.setProperty('--serial-dock-x', `${nextX}px`);
    dock.style.setProperty('--serial-dock-y', `${nextY}px`);
    serialDockPosRef.current = { x: nextX, y: nextY };
  }, []);

  const applySerialDockSize = useCallback((w: number, h: number) => {
    const dock = serialDockRef.current;
    if (!dock) return;
    const nextW = Math.round(w);
    const nextH = Math.round(h);
    dock.style.setProperty('--serial-dock-w', `${nextW}px`);
    dock.style.setProperty('--serial-dock-h', `${nextH}px`);
  }, []);

  const clampSerialDockSize = useCallback((w: number, h: number) => {
    if (typeof window === 'undefined') return { w, h };
    const margin = 16;
    const minW = 560;
    const maxW = 980;
    const minH = 420;
    const maxH = 860;
    const viewportMaxW = Math.max(minW, window.innerWidth - margin);
    const viewportMaxH = Math.max(minH, window.innerHeight - margin);
    return {
      w: Math.min(Math.min(maxW, viewportMaxW), Math.max(minW, w)),
      h: Math.min(Math.min(maxH, viewportMaxH), Math.max(minH, h)),
    };
  }, []);

  const clampSerialDockPosition = useCallback((x: number, y: number) => {
    const dock = serialDockRef.current;
    if (!dock || typeof window === 'undefined') return { x, y };
    const margin = 8;
    const dockWidth = dock.offsetWidth || 640;
    const dockHeight = dock.offsetHeight || 520;
    const maxX = Math.max(margin, window.innerWidth - dockWidth - margin);
    const maxY = Math.max(margin, window.innerHeight - dockHeight - margin);
    return {
      x: Math.min(maxX, Math.max(margin, x)),
      y: Math.min(maxY, Math.max(margin, y)),
    };
  }, []);

  const openSerialWindow = useCallback(() => {
    if (typeof window === 'undefined') return;
    const url = new URL(window.location.href);
    url.searchParams.set('tab', 'ide');
    url.searchParams.set('workbench', 'serial');
    url.searchParams.set('view', 'serial');
    const popup = window.open(url.toString(), 'upright_serial_console', 'popup=yes,width=1080,height=760');
    popup?.focus();
    emitSerialSync('open-window');
  }, [emitSerialSync]);

  const openSketchUploadPicker = useCallback(() => {
    sketchFileInputRef.current?.click();
  }, []);

  const openSaveSketchConfirm = useCallback(() => {
    setSaveConfirmAck(false);
    setSaveConfirmOpen(true);
  }, []);

  const runConfirmedSaveSketch = useCallback(async () => {
    if (saveConfirmBusy || !saveConfirmAck || !sketchPath.trim()) return;
    setSaveConfirmBusy(true);
    try {
      const slash = sketchPath.lastIndexOf('/');
      if (slash > 0) {
        setFwCfg((prev) => ({ ...prev, sketch: sketchPath.slice(0, slash) }));
      }
      await saveSketch();
      setSaveConfirmOpen(false);
      setSaveConfirmAck(false);
    } finally {
      setSaveConfirmBusy(false);
    }
  }, [saveConfirmAck, saveConfirmBusy, setFwCfg, saveSketch, sketchPath]);

  const sendSerialLineLinked = useCallback(async () => {
    await sendSerialLine();
    emitSerialSync('send-line');
  }, [emitSerialSync, sendSerialLine]);

  const sendSerialCommandLinked = useCallback(async (cmd: string) => {
    await sendSerialCommand(cmd);
    emitSerialSync(`send-cmd:${cmd}`);
  }, [emitSerialSync, sendSerialCommand]);

  const refreshLogsLinked = useCallback(async () => {
    await refreshLogs();
    await refreshSerialDiag();
    emitSerialSync('refresh');
  }, [emitSerialSync, refreshLogs, refreshSerialDiag]);

  const onSketchUploadSelected = useCallback(async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    const content = await file.text();
    const defaultsSketch = (fw.defaults?.sketch ?? '').trim();
    const defaultsSlash = defaultsSketch.lastIndexOf('/');
    const defaultFolder = defaultsSlash > 0 ? defaultsSketch.slice(0, defaultsSlash) : '';
    const baseFolder = (fwCfg.sketch || defaultFolder).replace(/\/+$/, '');
    const inferredPath = baseFolder ? `${baseFolder}/${file.name}` : file.name;
    setSketchContent(content);
    setSketchPath(inferredPath);
    if (baseFolder) {
      setFwCfg((prev) => ({ ...prev, sketch: baseFolder }));
    }
    event.target.value = '';
  }, [fw.defaults?.sketch, fwCfg.sketch, setFwCfg, setSketchContent, setSketchPath]);

  const onSerialDockPointerDown = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    const target = event.target as HTMLElement;
    if (target.closest('button')) return;
    const dock = serialDockRef.current;
    if (!dock) return;
    const rect = dock.getBoundingClientRect();
    serialDockDragRef.current = {
      active: true,
      pointerId: event.pointerId,
      offsetX: event.clientX - rect.left,
      offsetY: event.clientY - rect.top,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
  }, []);

  const onSerialDockPointerMove = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    const drag = serialDockDragRef.current;
    if (!drag.active || drag.pointerId !== event.pointerId) return;
    const next = clampSerialDockPosition(event.clientX - drag.offsetX, event.clientY - drag.offsetY);
    applySerialDockPosition(next.x, next.y);
  }, [applySerialDockPosition, clampSerialDockPosition]);

  const onSerialDockPointerRelease = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    const drag = serialDockDragRef.current;
    if (!drag.active || drag.pointerId !== event.pointerId) return;
    serialDockDragRef.current = { active: false, pointerId: -1, offsetX: 0, offsetY: 0 };
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }, []);

  const onSerialDockResizePointerDown = useCallback((event: React.PointerEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    const dock = serialDockRef.current;
    if (!dock) return;
    const rect = dock.getBoundingClientRect();
    serialDockResizeRef.current = {
      active: true,
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      startW: rect.width,
      startH: rect.height,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
  }, []);

  const onSerialDockResizePointerMove = useCallback((event: React.PointerEvent<HTMLButtonElement>) => {
    const resize = serialDockResizeRef.current;
    if (!resize.active || resize.pointerId !== event.pointerId) return;
    const next = clampSerialDockSize(resize.startW + (event.clientX - resize.startX), resize.startH + (event.clientY - resize.startY));
    applySerialDockSize(next.w, next.h);
    const clampedPos = clampSerialDockPosition(serialDockPosRef.current.x, serialDockPosRef.current.y);
    applySerialDockPosition(clampedPos.x, clampedPos.y);
  }, [applySerialDockPosition, applySerialDockSize, clampSerialDockPosition, clampSerialDockSize]);

  const onSerialDockResizePointerRelease = useCallback((event: React.PointerEvent<HTMLButtonElement>) => {
    const resize = serialDockResizeRef.current;
    if (!resize.active || resize.pointerId !== event.pointerId) return;
    serialDockResizeRef.current = { active: false, pointerId: -1, startX: 0, startY: 0, startW: 0, startH: 0 };
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }, []);

  const renderSerialPane = (logRef: React.MutableRefObject<HTMLPreElement | null>, docked = false) => (
    <section className={`firmware-pane serial-pane${docked ? ' serial-pane-docked' : ''}`}>
      <p className="wizard-subtitle">{strings.workbench.serialSubtitle}</p>
      <form
        className="row serial-send-row"
        onSubmit={(e) => {
          e.preventDefault();
          void sendSerialLineLinked();
        }}
      >
        <input
          type="text"
          value={serialWrite}
          onChange={(e) => setSerialWrite(e.target.value)}
          placeholder={strings.workbench.serialPlaceholder}
        />
        <button type="submit" className="btn-primary btn-lg">{strings.workbench.send}</button>
        <button
          type="button"
          className="btn-secondary btn-sm"
          onClick={() => void sendSerialCommandLinked('HELP')}
        >
          {strings.workbench.showCommands}
        </button>
        <button type="button" className="btn-secondary btn-sm" onClick={() => void refreshLogsLinked()}>{strings.workbench.refreshTail}</button>
      </form>
      <pre ref={logRef} className="logbox firmware-log serial-log">{lines.join('\n')}</pre>
      <div className="serial-diag-card">
        <div className="serial-diag-head">
          <strong>Serial Diagnostics</strong>
          <button type="button" className="btn-secondary btn-xs" onClick={() => void refreshSerialDiag()}>Refresh Diag</button>
        </div>
        {!serialDiag ? (
          <p className="wizard-subtitle">No diagnostics available.</p>
        ) : (
          <div className="serial-diag-grid">
            <span>connected: <strong>{serialDiag.connected ? 'yes' : 'no'}</strong></span>
            <span>port: <strong>{serialDiag.port}</strong></span>
            <span>baud: <strong>{serialDiag.baud}</strong></span>
            <span>worker: <strong>{serialDiag.worker_alive ? 'alive' : 'down'}</strong></span>
            <span>queue: <strong>{serialDiag.queue_depth ?? 0}</strong></span>
            <span>status age: <strong>{serialDiag.last_status_age_ms != null ? `${Math.round(serialDiag.last_status_age_ms)}ms` : 'n/a'}</strong></span>
            <span>cmd ok: <strong>{serialDiag.serial_metrics?.commands_ok ?? 0}</strong></span>
            <span>cmd err: <strong>{serialDiag.serial_metrics?.commands_err ?? 0}</strong></span>
            <span>timeouts: <strong>{serialDiag.serial_metrics?.timeouts ?? 0}</strong></span>
            <span>p50: <strong>{serialDiag.serial_metrics?.latency_p50_ms != null ? `${Math.round(serialDiag.serial_metrics.latency_p50_ms)}ms` : 'n/a'}</strong></span>
            <span>p95: <strong>{serialDiag.serial_metrics?.latency_p95_ms != null ? `${Math.round(serialDiag.serial_metrics.latency_p95_ms)}ms` : 'n/a'}</strong></span>
            <span>last error: <strong>{serialDiag.serial_metrics?.last_error ?? 'none'}</strong></span>
          </div>
        )}
      </div>
    </section>
  );

  useEffect(() => {
    if (serialLogRef.current) {
      serialLogRef.current.scrollTop = serialLogRef.current.scrollHeight;
    }
    if (serialDockLogRef.current) {
      serialDockLogRef.current.scrollTop = serialDockLogRef.current.scrollHeight;
    }
  }, [lines]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const workbenchFromUrl = new URLSearchParams(window.location.search).get('workbench');
    if (workbenchFromUrl === 'serial') {
      setWorkbenchTab('serial');
      setSerialDockOpen(true);
    }
  }, [setWorkbenchTab]);

  useEffect(() => {
    if (!serialDockOpen) return;
    const updatePosition = () => {
      const next = clampSerialDockPosition(serialDockPosRef.current.x, serialDockPosRef.current.y);
      applySerialDockPosition(next.x, next.y);
    };
    const rafId = window.requestAnimationFrame(updatePosition);
    window.addEventListener('resize', updatePosition);
    return () => {
      window.cancelAnimationFrame(rafId);
      window.removeEventListener('resize', updatePosition);
    };
  }, [applySerialDockPosition, clampSerialDockPosition, serialDockOpen]);

  useEffect(() => {
    if (typeof window === 'undefined' || typeof BroadcastChannel === 'undefined') return;
    const channel = new BroadcastChannel(SERIAL_SYNC_CHANNEL);
    serialSyncChannelRef.current = channel;
    channel.onmessage = (ev: MessageEvent) => {
      const payload = ev.data as { source?: string; event?: string } | null;
      if (!payload || payload.source === serialSyncIdRef.current) return;
      if (!payload.event) return;
      scheduleSerialSyncRefresh();
    };
    return () => {
      if (serialSyncDebounceRef.current !== null) {
        window.clearTimeout(serialSyncDebounceRef.current);
        serialSyncDebounceRef.current = null;
      }
      channel.close();
      serialSyncChannelRef.current = null;
    };
  }, [scheduleSerialSyncRefresh]);

  if (serialWindowMode) {
    return (
      <section className="panel tool-panel workbench-serial-window" aria-label="Serial console window">
        <div className="tool-panel-head">
          <h3>{strings.workbench.tabSerial}</h3>
          <span className="workflow-label">{strings.workbench.serialSubtitle}</span>
        </div>
        <div className="tool-panel-body">
          {renderSerialPane(serialLogRef)}
        </div>
      </section>
    );
  }

  return (
    <>
    <section className={`panel tool-panel ${ideMode ? 'workbench-ide' : ''}`} aria-label="Firmware workbench">
      <div className="tool-panel-head workbench-panel-head">
        <div className="tool-panel-head-left">
          <h3>{strings.workbench.title}</h3>
          <span className="workflow-label workflow-label-sm">{strings.workbench.subtitle}</span>
        </div>
      </div>
      <nav className="tabs firmware-tabs" aria-label="Firmware workbench tabs">
        <button className={`btn-sm ${workbenchTab === 'board' ? 'active' : ''}`} onClick={() => setWorkbenchTab('board')}>{strings.workbench.tabBoard}</button>
        <button className={`btn-sm ${workbenchTab === 'sketch' ? 'active' : ''}`} onClick={() => setWorkbenchTab('sketch')}>{strings.workbench.tabSketch}</button>
        <button className={`btn-sm ${workbenchTab === 'serial' ? 'active' : ''}`} onClick={() => setWorkbenchTab('serial')}>{strings.workbench.tabSerial}</button>
        <span className="tabs-spacer" aria-hidden="true" />
        <button
          className={`btn-sm dock-menu-action ${serialDockOpen ? 'active' : ''}`}
          onClick={() => setSerialDockOpen((prev) => !prev)}
        >
          {serialDockOpen ? strings.workbench.hideSerialDock : strings.workbench.openSerialDock}
          <svg
            className="btn-inline-icon"
            viewBox="0 0 24 24"
            fill="none"
            aria-hidden="true"
            focusable="false"
          >
            <path
              d="M7 17L17 7"
              stroke="currentColor"
              strokeWidth="1.9"
              strokeLinecap="round"
              strokeLinejoin="round"
              vectorEffect="non-scaling-stroke"
            />
            <path
              d="M10 7H17V14"
              stroke="currentColor"
              strokeWidth="1.9"
              strokeLinecap="round"
              strokeLinejoin="round"
              vectorEffect="non-scaling-stroke"
            />
          </svg>
        </button>
      </nav>

      <div className="tool-panel-body">
        {workbenchTab === 'sketch' && (
          <section className="firmware-pane">
            <input
              ref={sketchFileInputRef}
              type="file"
              accept=".ino,.pde,.cpp,.c,.h,.hpp,.txt"
              hidden
              onChange={(event) => { void onSketchUploadSelected(event); }}
            />
            <label>
              {strings.workbench.sketchFile}
              <input type="text" value={sketchPath} onChange={(e) => setSketchPath(e.target.value)} />
            </label>
            <div className="row">
              <button className="btn-secondary btn-sm" type="button" onClick={openSketchUploadPicker}>{strings.workbench.uploadSketchFile}</button>
              <button className="btn-secondary btn-sm" onClick={() => void loadSketch()}>{strings.workbench.loadSketch}</button>
              <button
                className="btn-primary btn-lg"
                onClick={openSaveSketchConfirm}
              >
                {strings.workbench.saveSketch}
              </button>
            </div>
            <p className="wizard-subtitle">{strings.workbench.sketchUploadHint}</p>
            <div className="row">
              <button className="btn-secondary btn-sm btn-intent-build" disabled={fw.running} onClick={() => void runFirmwareCompile()}>{strings.workbench.compile}</button>
              <button className="btn-primary btn-lg btn-intent-safety" disabled={fw.running} onClick={() => void runFirmwareUpload()}>{strings.workbench.upload}</button>
              <button className="btn-danger btn-md btn-intent-safety" disabled={fw.running} onClick={() => void runFirmwareUploadGuarded()}>
                {strings.workbench.guardedFlash}
              </button>
            </div>
            <div className="sketch-editor">
              <Editor
                height={ideMode ? '68vh' : '420px'}
                defaultLanguage="cpp"
                value={sketchContent}
                onChange={(v) => setSketchContent(v ?? '')}
                options={{
                  minimap: { enabled: false },
                  fontSize: 13,
                  wordWrap: 'on',
                  smoothScrolling: true,
                  scrollBeyondLastLine: false,
                  automaticLayout: true,
                }}
                theme="vs-dark"
              />
            </div>
          </section>
        )}

        {workbenchTab === 'board' && (
          <section className="firmware-pane">
            <h4>{strings.workbench.selectBoardPortTitle}</h4>
            <p className="wizard-subtitle">{strings.workbench.selectBoardPortSubtitle}</p>
            <div className="row">
              <button className="btn-secondary btn-sm btn-intent-discover" onClick={() => void runFirmwareCheck()}>{strings.workbench.checkCli}</button>
              <button className="btn-secondary btn-sm btn-intent-build" disabled={fw.running} onClick={() => void runFirmwareInstall()}>{strings.workbench.installCli}</button>
              <button className="btn-secondary btn-sm btn-intent-discover" onClick={() => void refreshBoards()}>{strings.workbench.scanBoards}</button>
            </div>
            <label>
              {strings.workbench.boardFqbn}
              <select value={fwCfg.fqbn} onChange={(e) => setFwCfg((p) => ({ ...p, fqbn: e.target.value }))}>
                <option value={fwCfg.fqbn}>{fwCfg.fqbn || 'arduino:avr:nano'}</option>
                {boardScan?.ports
                  .filter((p) => Boolean(p.fqbn) && p.fqbn !== fwCfg.fqbn)
                  .map((p) => (
                    <option key={`${p.address}-${p.fqbn}`} value={p.fqbn ?? ''}>
                      {p.board_name ?? strings.workbench.boardDetected} · {p.fqbn}
                    </option>
                  ))}
              </select>
            </label>
            <label>
              {strings.workbench.port}
              <select value={fwCfg.port} onChange={(e) => setFwCfg((p) => ({ ...p, port: e.target.value }))}>
                <option value={fwCfg.port}>{fwCfg.port || '/dev/cu.usbserial-...'}</option>
                {boardScan?.ports
                  .filter((p) => Boolean(p.address) && p.address !== fwCfg.port)
                  .map((p) => (
                    <option key={p.address ?? 'unknown'} value={p.address ?? ''}>
                      {p.address} {p.board_name ? `(${p.board_name})` : ''}
                    </option>
                  ))}
              </select>
            </label>
            <label>
              {strings.workbench.sketchFolder}
              <div className="row">
                <select value={fwCfg.sketch} onChange={(e) => setFwCfg((p) => ({ ...p, sketch: e.target.value }))}>
                <option value={fwCfg.sketch}>{fwCfg.sketch || fw.defaults?.sketch || 'Select sketch folder'}</option>
                {sketchFolders
                  .filter((folder) => Boolean(folder) && folder !== fwCfg.sketch)
                  .map((folder) => (
                    <option key={folder} value={folder}>
                      {folder}
                    </option>
                  ))}
                </select>
                <button className="btn-secondary btn-sm" type="button" onClick={() => void pickSketchFolder()}>
                  {strings.workbench.pickSketchFolder}
                </button>
              </div>
            </label>
            <hr />
            <h4>{strings.workbench.unifiedTitle}</h4>
            <p className="wizard-subtitle">{strings.workbench.unifiedSubtitle}</p>
            <label>
              {strings.workbench.unifiedSketchName}
              <input type="text" value={unifiedSketchName} onChange={(e) => setUnifiedSketchName(e.target.value)} />
            </label>
            <label>
              {strings.workbench.unifiedProfileJson}
              <textarea
                rows={12}
                value={unifiedProfileJson}
                onChange={(e) => setUnifiedProfileJson(e.target.value)}
                spellCheck={false}
                style={{ width: '100%', fontFamily: 'monospace' }}
              />
            </label>
            <div className="row">
              <button className="btn-primary btn-lg btn-intent-build" disabled={fw.running} onClick={() => void runGenerateUnified()}>
                {strings.workbench.generateUnified}
              </button>
            </div>
            {boardScan?.recommended_fqbn && (
              <p className="wizard-profile-summary">
                {strings.workbench.recommended}: <strong>{boardScan.recommended_fqbn}</strong> on {boardScan.recommended_port ?? 'n/a'}
              </p>
            )}
            <p className="wizard-profile-summary">
              {strings.workbench.state}: <strong>{fw.state}</strong> · phase={fw.phase} · running={fw.running ? 'yes' : 'no'} · return={String(fw.returncode)}
            </p>
            {fwCheck && (
              <p className="wizard-profile-summary">
                {strings.workbench.cli}: <strong>{fwCheck.ok ? strings.workbench.pass : strings.workbench.fail}</strong>{fwCheck.version ? ` · ${fwCheck.version}` : ''}{fwCheck.error ? ` · ${fwCheck.error}` : ''}
              </p>
            )}
            <pre className="logbox firmware-log">{fw.log_tail.join('\n')}</pre>
          </section>
        )}

        {workbenchTab === 'serial' && (
          renderSerialPane(serialLogRef)
        )}
      </div>
      {serialDockOpen && (
        <aside ref={serialDockRef} className="serial-dock surface-dock" role="dialog" aria-label="Floating serial dock">
          <div
            className="serial-dock-head"
            onPointerDown={onSerialDockPointerDown}
            onPointerMove={onSerialDockPointerMove}
            onPointerUp={onSerialDockPointerRelease}
            onPointerCancel={onSerialDockPointerRelease}
          >
            <div className="serial-dock-title">
              <strong>{strings.workbench.tabSerial}</strong>
              <span>{strings.workbench.serialSubtitle}</span>
            </div>
            <div className="serial-dock-actions">
              <button
                type="button"
                className="btn-sm dock-menu-action dock-icon-action"
                aria-label={strings.workbench.openSerialWindow}
                onClick={openSerialWindow}
              >
                <svg className="dock-action-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false">
                  <path
                    d="M7 17L17 7"
                    stroke="currentColor"
                    strokeWidth="1.9"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    vectorEffect="non-scaling-stroke"
                  />
                  <path
                    d="M10 7H17V14"
                    stroke="currentColor"
                    strokeWidth="1.9"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    vectorEffect="non-scaling-stroke"
                  />
                </svg>
              </button>
              <button
                type="button"
                className="btn-sm dock-menu-action dock-icon-action"
                aria-label={strings.workbench.closeSerialDock}
                onClick={() => setSerialDockOpen(false)}
              >
                <svg className="dock-action-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false">
                  <path
                    d="M7.5 7.5L16.5 16.5"
                    stroke="currentColor"
                    strokeWidth="1.9"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    vectorEffect="non-scaling-stroke"
                  />
                  <path
                    d="M16.5 7.5L7.5 16.5"
                    stroke="currentColor"
                    strokeWidth="1.9"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    vectorEffect="non-scaling-stroke"
                  />
                </svg>
              </button>
            </div>
          </div>
          {renderSerialPane(serialDockLogRef, true)}
          <button
            type="button"
            className="serial-dock-resize-handle"
            aria-label="Resize serial dock"
            onPointerDown={onSerialDockResizePointerDown}
            onPointerMove={onSerialDockResizePointerMove}
            onPointerUp={onSerialDockResizePointerRelease}
            onPointerCancel={onSerialDockResizePointerRelease}
          />
        </aside>
      )}
    </section>
    {saveConfirmOpen && (
      <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="Save sketch overwrite confirmation">
        <div className="preflight-modal surface-dock" onClick={(e) => e.stopPropagation()}>
          <h3>{strings.workbench.saveSketchConfirmTitle}</h3>
          <p className="wizard-subtitle">{strings.workbench.saveSketchConfirmSubtitle}</p>
          <div className="save-overwrite-path">
            <strong>{strings.workbench.sketchFile}:</strong>
            <code>{sketchPath || 'not set'}</code>
          </div>
          <label className="check-item">
            <input type="checkbox" checked={saveConfirmAck} onChange={(e) => setSaveConfirmAck(e.target.checked)} />
            {strings.workbench.saveSketchConfirmAcknowledge}
          </label>
          <div className="row preflight-actions">
            <button className="btn-secondary" onClick={() => setSaveConfirmOpen(false)} disabled={saveConfirmBusy}>{strings.modal.cancel}</button>
            <button
              className="btn-primary btn-lg"
              onClick={() => void runConfirmedSaveSketch()}
              disabled={saveConfirmBusy || !saveConfirmAck || !sketchPath.trim()}
            >
              {strings.workbench.saveSketchConfirmAction}
            </button>
          </div>
        </div>
      </div>
    )}
    </>
  );
}
