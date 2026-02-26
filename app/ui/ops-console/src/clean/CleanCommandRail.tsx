import type { CleanAction } from './cleanAppTypes';

type CleanCommandRailProps = {
  actions: CleanAction[];
  busy: boolean;
  onRunAction: (label: string, run: () => Promise<unknown>) => Promise<void>;
};

export function CleanCommandRail({
  actions,
  busy,
  onRunAction,
}: CleanCommandRailProps): JSX.Element {
  return (
    <section className="clean-card clean-gradient">
      <div className="clean-card-head">
        <h2>Command Rail</h2>
      </div>
      <div className="clean-actions">
        {actions.map((action) => (
          <button
            key={action.label}
            className={`clean-btn ${action.className ?? ''}`}
            disabled={busy || Boolean(action.disabled)}
            onClick={() => void onRunAction(action.label, action.run)}
          >
            {action.label}
          </button>
        ))}
      </div>
    </section>
  );
}
