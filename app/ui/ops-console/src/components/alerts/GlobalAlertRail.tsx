import { useState } from 'react';
import type { AlertFilter, UiAlert } from '../../hooks/useUiAlerts';
import { AlertItem } from './AlertItem';

type GlobalAlertRailProps = {
  active: UiAlert[];
  activeTotal: number;
  history: UiAlert[];
  filter: AlertFilter;
  onDismiss: (id: string) => void;
  onClearNonError: () => void;
  onClearAll: () => void;
  onClearHistory: () => void;
  onSetFilter: (f: AlertFilter) => void;
};

const FILTER_OPTIONS: AlertFilter[] = ['all', 'error', 'warn', 'ok', 'info'];

export function GlobalAlertRail({
  active,
  activeTotal,
  history,
  filter,
  onDismiss,
  onClearNonError,
  onClearAll,
  onClearHistory,
  onSetFilter,
}: GlobalAlertRailProps) {
  const [expanded, setExpanded] = useState(false);
  const hasActive = active.length > 0;
  const hasAnyActive = activeTotal > 0;
  const hasHistory = history.length > 0;
  const current: UiAlert | null = active.length > 0 ? active[0] : history.length > 0 ? history[0] : null;
  if (!hasAnyActive && !hasHistory) return null;

  return (
    <aside className={`global-alert-rail ${expanded ? 'expanded' : 'collapsed'}`} aria-label="System alerts">
      <div className="global-alert-collapsed-row">
        <span className={`global-alert-pill ${current?.tone ?? 'info'}`}>{current?.tone ?? 'info'}</span>
        <span className="global-alert-summary">{current?.text ?? 'No active alerts'}</span>
        <button
          type="button"
          className="global-alert-expand-btn btn-xs"
          onClick={() => setExpanded((v) => !v)}
          aria-label={expanded ? 'Collapse alerts' : 'Expand alerts'}
          title={expanded ? 'Collapse alerts' : 'Expand alerts'}
        >
          {expanded ? '▾' : '▴'}
        </button>
      </div>
      {!expanded ? null : (
        <div className="global-alert-popout glass-surface glass-surface-strong" role="dialog" aria-label="Alert details">
          <div className="global-alert-header">
            <span className="global-alert-title">Alerts</span>
            <div className="global-alert-header-right">
              <div className="global-alert-filters">
                {FILTER_OPTIONS.map((f) => (
                  <button
                    key={f}
                    type="button"
                    className={`global-alert-filter-btn ${filter === f ? 'active' : ''}`}
                    onClick={() => onSetFilter(f)}
                    aria-pressed={filter === f}
                  >
                    {f}
                  </button>
                ))}
              </div>
              <button
                type="button"
                className="global-alert-expand-btn btn-xs"
                onClick={() => setExpanded(false)}
                aria-label="Collapse alerts"
                title="Collapse alerts"
              >
                ▾
              </button>
            </div>
          </div>

          <div className="global-alert-actions">
            <button
              type="button"
              onClick={onClearNonError}
              disabled={!hasAnyActive}
              className="global-alert-action-btn btn-danger btn-xs"
            >
              Clear non-error
            </button>
            <button
              type="button"
              onClick={onClearAll}
              disabled={!hasAnyActive}
              className="global-alert-action-btn btn-danger btn-xs"
            >
              Clear all
            </button>
          </div>

          <div className="global-alert-list" aria-live="polite" aria-atomic="false">
            {!hasActive && <p className="global-alert-empty">No active alerts.</p>}
            {active.map((alert) => (
              <AlertItem
                key={alert.id}
                id={alert.id}
                tone={alert.tone}
                text={alert.text}
                ts={alert.ts}
                onDismiss={onDismiss}
              />
            ))}
          </div>

          {hasHistory && (
            <div className="global-alert-history">
              <div className="global-alert-history-header">
                <span className="global-alert-history-title">History</span>
                <button
                  type="button"
                  onClick={onClearHistory}
                  className="global-alert-action-btn btn-xs"
                >
                  Clear
                </button>
              </div>
              <div className="global-alert-history-list">
                {history.map((alert) => (
                  <div key={alert.id} className={`alert-item history ${alert.tone}`}>
                    <span className="alert-item-time">
                      {new Date(alert.ts).toLocaleTimeString()}
                    </span>
                    <span className="alert-item-text">{alert.text}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </aside>
  );
}
