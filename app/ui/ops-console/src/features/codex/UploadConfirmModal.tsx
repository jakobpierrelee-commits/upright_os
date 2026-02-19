import { useState, useEffect, useCallback } from 'react';

export type PendingUpload = {
  confirmation_token: string;
  sketch_path: string;
  board: string;
  port: string;
  expires_in_s: number;
  created_at: number;
};

type Props = {
  pending: PendingUpload;
  onApprove: (token: string) => Promise<{ ok: boolean; error?: string }>;
  onReject: () => void;
};

export function UploadConfirmModal({ pending, onApprove, onReject }: Props) {
  const [status, setStatus] = useState<'idle' | 'approving' | 'success' | 'error'>('idle');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [remainingMs, setRemainingMs] = useState(() => {
    const elapsed = Date.now() - pending.created_at;
    return Math.max(0, pending.expires_in_s * 1000 - elapsed);
  });

  const expired = remainingMs <= 0;
  const sketchName = pending.sketch_path.split('/').pop() || pending.sketch_path;

  useEffect(() => {
    if (expired || status === 'success') return;

    const interval = setInterval(() => {
      const elapsed = Date.now() - pending.created_at;
      const remaining = Math.max(0, pending.expires_in_s * 1000 - elapsed);
      setRemainingMs(remaining);

      if (remaining <= 0) {
        setStatus('error');
        setErrorMessage('Confirmation token expired. Please request a new upload.');
      }
    }, 1000);

    return () => clearInterval(interval);
  }, [expired, pending.created_at, pending.expires_in_s, status]);

  const handleApprove = useCallback(async () => {
    if (expired || status === 'approving') return;

    setStatus('approving');
    setErrorMessage(null);

    try {
      const result = await onApprove(pending.confirmation_token);
      if (result.ok) {
        setStatus('success');
      } else {
        setStatus('error');
        setErrorMessage(result.error || 'Upload failed');
      }
    } catch (e) {
      setStatus('error');
      setErrorMessage((e as Error).message || 'Upload failed');
    }
  }, [expired, onApprove, pending.confirmation_token, status]);

  const handleReject = useCallback(() => {
    if (status === 'approving') return;
    onReject();
  }, [onReject, status]);

  const formatTime = (ms: number) => {
    const totalSeconds = Math.ceil(ms / 1000);
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    return `${minutes}:${seconds.toString().padStart(2, '0')}`;
  };

  const progressPct = Math.max(0, Math.min(100, (remainingMs / (pending.expires_in_s * 1000)) * 100));

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="Upload confirmation">
      <div className="preflight-modal upload-confirm-modal">
        <div className="upload-confirm-header">
          <h3>⚠️ Firmware Upload Confirmation</h3>
          <p className="upload-confirm-warning">
            This action will flash firmware to your robot. Ensure the robot is safely positioned.
          </p>
        </div>

        <div className="upload-confirm-details">
          <div className="upload-confirm-row">
            <span className="upload-confirm-label">Sketch:</span>
            <span className="upload-confirm-value">{sketchName}</span>
          </div>
          <div className="upload-confirm-row">
            <span className="upload-confirm-label">Board:</span>
            <span className="upload-confirm-value">{pending.board}</span>
          </div>
          <div className="upload-confirm-row">
            <span className="upload-confirm-label">Port:</span>
            <span className="upload-confirm-value">{pending.port || 'auto-detect'}</span>
          </div>
        </div>

        {status !== 'success' && (
          <div className={`upload-confirm-timer ${expired ? 'expired' : ''}`}>
            <div className="upload-confirm-timer-bar">
              <span style={{ width: `${progressPct}%` }} />
            </div>
            <span className="upload-confirm-timer-text">
              {expired ? 'Expired' : `Expires in ${formatTime(remainingMs)}`}
            </span>
          </div>
        )}

        {errorMessage && (
          <div className="upload-confirm-error">
            <span className="upload-confirm-error-icon">✗</span>
            <span>{errorMessage}</span>
          </div>
        )}

        {status === 'success' && (
          <div className="upload-confirm-success">
            <span className="upload-confirm-success-icon">✓</span>
            <span>Upload completed successfully!</span>
          </div>
        )}

        {status === 'approving' && (
          <div className="upload-confirm-progress">
            <span className="upload-confirm-spinner" />
            <span>Uploading firmware...</span>
          </div>
        )}

        <div className="upload-confirm-actions">
          {status === 'success' ? (
            <button className="btn-primary btn-lg" onClick={onReject}>
              Close
            </button>
          ) : expired ? (
            <button className="btn-secondary btn-lg" onClick={onReject}>
              Close
            </button>
          ) : (
            <>
              <button
                className="btn-danger btn-lg upload-confirm-approve"
                onClick={() => void handleApprove()}
                disabled={status === 'approving' || expired}
              >
                {status === 'approving' ? 'Uploading...' : 'Approve Upload'}
              </button>
              <button
                className="btn-secondary btn-lg"
                onClick={handleReject}
                disabled={status === 'approving'}
              >
                Cancel
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export function extractPendingUpload(
  toolCalls: Array<{
    tool: string;
    args: Record<string, unknown>;
    result: { ok: boolean; data: Record<string, unknown>; error?: string };
  }> | undefined,
): PendingUpload | null {
  if (!toolCalls) return null;

  for (const tc of toolCalls) {
    if (
      tc.tool === 'upload_firmware' &&
      !tc.result.ok &&
      tc.result.error === 'CONFIRMATION_REQUIRED' &&
      tc.result.data?.confirmation_token
    ) {
      return {
        confirmation_token: String(tc.result.data.confirmation_token),
        sketch_path: String(tc.result.data.sketch_path || ''),
        board: String(tc.result.data.board || 'arduino:avr:nano'),
        port: String(tc.result.data.port || ''),
        expires_in_s: Number(tc.result.data.expires_in_s) || 300,
        created_at: Date.now(),
      };
    }
  }

  return null;
}
