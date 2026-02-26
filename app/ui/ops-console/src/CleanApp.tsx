import { useRef, useState } from 'react';
import { CleanCodexSection } from './clean/CleanCodexSection';
import { CleanCommandRail } from './clean/CleanCommandRail';
import { CleanFirmwareSection } from './clean/CleanFirmwareSection';
import { CleanTuningSection } from './clean/CleanTuningSection';
import { CleanTelemetryPanel } from './clean/CleanTelemetryPanel';
import { useCleanAppState } from './clean/useCleanAppState';

export default function CleanApp(): JSX.Element {
  const codexAnchorRef = useRef<HTMLElement | null>(null);
  const [workspaceView, setWorkspaceView] = useState<'workflow' | 'split' | 'codex' | 'tuning'>('split');
  const {
    health,
    apiContractOk,
    status,
    control,
    msg,
    busy,
    actions,
    globalDock,
    refresh,
    runAction,
    onGlobalStatus,
  } = useCleanAppState();

  return (
    <div className="clean-shell">
      <header className="clean-topbar">
        <div className="clean-brand">UPRIGHT.OS CLEAN CONSOLE</div>
        <div className={`clean-pill ${!health?.connected ? 'bad' : (apiContractOk ? 'ok' : 'warn')}`}>
          {!health?.connected ? 'DISCONNECTED' : (apiContractOk ? 'CONNECTED' : 'CONNECTED (LEGACY API)')}
        </div>
      </header>
      <div className="clean-startup-lock-banner" role="status" aria-live="polite">
        CLEAN LANE LOCKED: 127.0.0.1 (line 8797)
      </div>
      <div className="clean-startup-launch-mode" role="status" aria-live="polite">
        BRIDGE LAUNCH MODE: ISOLATED (IDE-SAFE DEFAULT)
      </div>

      <div className="clean-workspace-tabs" role="tablist" aria-label="Workspace view">
        <button
          role="tab"
          aria-selected={workspaceView === 'workflow'}
          className={`clean-workspace-tab ${workspaceView === 'workflow' ? 'active' : ''}`}
          onClick={() => setWorkspaceView('workflow')}
        >
          Workflow
        </button>
        <button
          role="tab"
          aria-selected={workspaceView === 'split'}
          className={`clean-workspace-tab ${workspaceView === 'split' ? 'active' : ''}`}
          onClick={() => setWorkspaceView('split')}
        >
          Split
        </button>
        <button
          role="tab"
          aria-selected={workspaceView === 'codex'}
          className={`clean-workspace-tab ${workspaceView === 'codex' ? 'active' : ''}`}
          onClick={() => setWorkspaceView('codex')}
        >
          Codex
        </button>
        <button
          role="tab"
          aria-selected={workspaceView === 'tuning'}
          className={`clean-workspace-tab ${workspaceView === 'tuning' ? 'active' : ''}`}
          onClick={() => setWorkspaceView('tuning')}
        >
          Tuning
        </button>
      </div>

      <main className={`clean-grid mode-${workspaceView}`}>
        {workspaceView === 'tuning' && (
          <CleanTuningSection mode="app_dev" onRefreshStatus={() => void refresh()} />
        )}

        {workspaceView !== 'codex' && workspaceView !== 'tuning' && (
          <div className="clean-left-column">
            <CleanTelemetryPanel
              status={status}
              control={control}
              busy={busy}
              msg={msg}
              onRefresh={() => void refresh()}
            />
            <CleanCommandRail actions={actions} busy={busy} onRunAction={runAction} />
            <CleanFirmwareSection mode="app_dev" onGlobalStatus={onGlobalStatus} />
          </div>
        )}

        {workspaceView !== 'workflow' && workspaceView !== 'tuning' && (
          <CleanCodexSection ref={codexAnchorRef} mode="app_dev" onGlobalStatus={onGlobalStatus} />
        )}
      </main>
      <button
        className={`clean-global-dock ${globalDock.level}`}
        onClick={() => codexAnchorRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })}
        title="Open Codex status in panel"
      >
        <span className="label">{globalDock.level.toUpperCase()}</span>
        <span className="text">{globalDock.summary}</span>
        <span className="meta">
          {globalDock.source} · {new Date(globalDock.ts).toLocaleTimeString()}
        </span>
      </button>
    </div>
  );
}
