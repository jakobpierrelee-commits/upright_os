import type { AlertTone } from '../../hooks/useUiAlerts';

type AlertItemProps = {
  id: string;
  tone: AlertTone;
  text: string;
  ts: number;
  onDismiss: (id: string) => void;
};

export function AlertItem({ id, tone, text, ts, onDismiss }: AlertItemProps) {
  const handleDismiss = () => onDismiss(id);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onDismiss(id);
    }
  };

  return (
    <div className={`alert-item ${tone}`}>
      <span className="alert-item-time">
        {new Date(ts).toLocaleTimeString()}
      </span>
      <span className="alert-item-text">{text}</span>
      <button
        type="button"
        className="alert-item-dismiss"
        onClick={handleDismiss}
        onKeyDown={handleKeyDown}
        aria-label="Dismiss alert"
      >
        ×
      </button>
    </div>
  );
}
