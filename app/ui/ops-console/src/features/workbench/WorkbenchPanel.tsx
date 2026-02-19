import { useEffect, useRef } from 'react';
import Editor from '@monaco-editor/react';
import type { FirmwareBoards, FirmwareCheck, FirmwareStatus, SerialDiag } from '../../api';
import type { WorkbenchTab } from './workbenchReducer';
import { strings } from '../../strings';

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
  insertKalmanTemplate: () => void;
  ideMode?: boolean;
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
    insertKalmanTemplate,
    ideMode = false,
  } = props;
  const serialLogRef = useRef<HTMLPreElement | null>(null);

  useEffect(() => {
    if (!serialLogRef.current) return;
    serialLogRef.current.scrollTop = serialLogRef.current.scrollHeight;
  }, [lines]);

  return (
    <section className={`panel tool-panel ${ideMode ? 'workbench-ide' : ''}`} aria-label="Firmware workbench">
      <div className="tool-panel-head">
        <h3>{strings.workbench.title}</h3>
        <span className="workflow-label">{strings.workbench.subtitle}</span>
      </div>
      <nav className="tabs firmware-tabs" aria-label="Firmware workbench tabs">
        <button className={`btn-sm ${workbenchTab === 'sketch' ? 'active' : ''}`} onClick={() => setWorkbenchTab('sketch')}>{strings.workbench.tabSketch}</button>
        <button className={`btn-sm ${workbenchTab === 'board' ? 'active' : ''}`} onClick={() => setWorkbenchTab('board')}>{strings.workbench.tabBoard}</button>
        <button className={`btn-sm ${workbenchTab === 'serial' ? 'active' : ''}`} onClick={() => setWorkbenchTab('serial')}>{strings.workbench.tabSerial}</button>
      </nav>

      <div className="tool-panel-body">
        {workbenchTab === 'sketch' && (
          <section className="firmware-pane">
            <label>
              {strings.workbench.sketchFile}
              <input type="text" value={sketchPath} onChange={(e) => setSketchPath(e.target.value)} />
            </label>
            <div className="row">
              <button className="btn-secondary btn-sm" onClick={() => void loadSketch()}>{strings.workbench.loadSketch}</button>
              <button className="btn-primary btn-lg" onClick={() => void saveSketch()}>{strings.workbench.saveSketch}</button>
              <button className="btn-secondary btn-sm" onClick={insertKalmanTemplate}>{strings.workbench.insertKalman}</button>
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
              <input type="text" value={fwCfg.sketch} onChange={(e) => setFwCfg((p) => ({ ...p, sketch: e.target.value }))} />
            </label>
            <div className="row">
              <button className="btn-secondary btn-sm btn-intent-build" disabled={fw.running} onClick={() => void runFirmwareCompile()}>{strings.workbench.compile}</button>
              <button className="btn-primary btn-lg btn-intent-safety" disabled={fw.running} onClick={() => void runFirmwareUpload()}>{strings.workbench.upload}</button>
              <button className="btn-danger btn-md btn-intent-safety" disabled={fw.running} onClick={() => void runFirmwareUploadGuarded()}>
                {strings.workbench.guardedFlash}
              </button>
            </div>
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
          <section className="firmware-pane serial-pane">
            <p className="wizard-subtitle">{strings.workbench.serialSubtitle}</p>
            <form
              className="row serial-send-row"
              onSubmit={(e) => {
                e.preventDefault();
                void sendSerialLine();
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
                onClick={() => void sendSerialCommand('HELP')}
              >
                {strings.workbench.showCommands}
              </button>
              <button type="button" className="btn-secondary btn-sm" onClick={() => void refreshLogs()}>{strings.workbench.refreshTail}</button>
            </form>
            <pre ref={serialLogRef} className="logbox firmware-log serial-log">{lines.join('\n')}</pre>
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
        )}
      </div>
    </section>
  );
}
