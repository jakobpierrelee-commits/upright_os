import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { UploadConfirmModal, extractPendingUpload, type PendingUpload } from './UploadConfirmModal';

const createMockPending = (overrides?: Partial<PendingUpload>): PendingUpload => ({
  confirmation_token: 'test-token-abc123',
  sketch_path: '/path/to/sketch/balance_v2',
  board: 'arduino:avr:nano',
  port: '/dev/ttyUSB0',
  expires_in_s: 300,
  created_at: Date.now(),
  ...overrides,
});

describe('UploadConfirmModal', () => {
  it('opens modal when pending upload token is present', () => {
    const pending = createMockPending();
    const onApprove = vi.fn().mockResolvedValue({ ok: true });
    const onReject = vi.fn();

    render(
      <UploadConfirmModal
        pending={pending}
        onApprove={onApprove}
        onReject={onReject}
      />
    );

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText('⚠️ Firmware Upload Confirmation')).toBeInTheDocument();
    expect(screen.getByText('balance_v2')).toBeInTheDocument();
    expect(screen.getByText('arduino:avr:nano')).toBeInTheDocument();
    expect(screen.getByText('/dev/ttyUSB0')).toBeInTheDocument();
  });

  it('renders countdown timer with initial value', () => {
    const pending = createMockPending({ expires_in_s: 300 });
    const onApprove = vi.fn().mockResolvedValue({ ok: true });
    const onReject = vi.fn();

    render(
      <UploadConfirmModal
        pending={pending}
        onApprove={onApprove}
        onReject={onReject}
      />
    );

    // Initial display should show ~5:00
    expect(screen.getByText(/Expires in 5:00/)).toBeInTheDocument();
  });

  it('calls onApprove with token when approve button clicked', async () => {
    const pending = createMockPending();
    const onApprove = vi.fn().mockResolvedValue({ ok: true });
    const onReject = vi.fn();

    render(
      <UploadConfirmModal
        pending={pending}
        onApprove={onApprove}
        onReject={onReject}
      />
    );

    const approveBtn = screen.getByText('Approve Upload');
    await act(async () => {
      fireEvent.click(approveBtn);
    });

    expect(onApprove).toHaveBeenCalledWith('test-token-abc123');
  });

  it('calls onReject when cancel button clicked', () => {
    const pending = createMockPending();
    const onApprove = vi.fn().mockResolvedValue({ ok: true });
    const onReject = vi.fn();

    render(
      <UploadConfirmModal
        pending={pending}
        onApprove={onApprove}
        onReject={onReject}
      />
    );

    const cancelBtn = screen.getByText('Cancel');
    fireEvent.click(cancelBtn);

    expect(onReject).toHaveBeenCalled();
    expect(onApprove).not.toHaveBeenCalled();
  });

  it('shows expired state when created_at is past expiry', () => {
    const pending = createMockPending({
      expires_in_s: 300,
      created_at: Date.now() - 400000, // 400 seconds ago, past 300s expiry
    });
    const onApprove = vi.fn().mockResolvedValue({ ok: true });
    const onReject = vi.fn();

    render(
      <UploadConfirmModal
        pending={pending}
        onApprove={onApprove}
        onReject={onReject}
      />
    );

    expect(screen.getByText('Expired')).toBeInTheDocument();
    // Approve button should not be visible after expiry
    expect(screen.queryByText('Approve Upload')).not.toBeInTheDocument();
  });

  it('shows error message when onApprove returns error', async () => {
    const pending = createMockPending();
    const onApprove = vi.fn().mockResolvedValue({ ok: false, error: 'Upload failed: connection lost' });
    const onReject = vi.fn();

    render(
      <UploadConfirmModal
        pending={pending}
        onApprove={onApprove}
        onReject={onReject}
      />
    );

    const approveBtn = screen.getByText('Approve Upload');
    await act(async () => {
      fireEvent.click(approveBtn);
    });

    expect(screen.getByText('Upload failed: connection lost')).toBeInTheDocument();
  });

  it('shows success state after successful upload', async () => {
    const pending = createMockPending();
    const onApprove = vi.fn().mockResolvedValue({ ok: true });
    const onReject = vi.fn();

    render(
      <UploadConfirmModal
        pending={pending}
        onApprove={onApprove}
        onReject={onReject}
      />
    );

    const approveBtn = screen.getByText('Approve Upload');
    await act(async () => {
      fireEvent.click(approveBtn);
    });

    expect(screen.getByText('Upload completed successfully!')).toBeInTheDocument();
  });

  it('handles exception during approve', async () => {
    const pending = createMockPending();
    const onApprove = vi.fn().mockRejectedValue(new Error('Network error'));
    const onReject = vi.fn();

    render(
      <UploadConfirmModal
        pending={pending}
        onApprove={onApprove}
        onReject={onReject}
      />
    );

    const approveBtn = screen.getByText('Approve Upload');
    await act(async () => {
      fireEvent.click(approveBtn);
    });

    expect(screen.getByText('Network error')).toBeInTheDocument();
  });

  it('disables approve button during loading', async () => {
    const pending = createMockPending();
    let resolveApprove: (value: { ok: boolean }) => void = () => {};
    const onApprove = vi.fn().mockImplementation(() => new Promise((resolve) => {
      resolveApprove = resolve;
    }));
    const onReject = vi.fn();

    render(
      <UploadConfirmModal
        pending={pending}
        onApprove={onApprove}
        onReject={onReject}
      />
    );

    const approveBtn = screen.getByText('Approve Upload');
    
    // Start the approval
    act(() => {
      fireEvent.click(approveBtn);
    });

    // Button text should change to indicate loading
    expect(screen.getByText('Uploading...')).toBeInTheDocument();
    
    // Complete the upload
    await act(async () => {
      resolveApprove({ ok: true });
    });
  });
});

describe('extractPendingUpload', () => {
  it('extracts pending upload from tool calls with CONFIRMATION_REQUIRED', () => {
    const toolCalls = [
      {
        tool: 'upload_firmware',
        args: { sketch_path: '/path/to/sketch' },
        result: {
          ok: false,
          data: {
            confirmation_token: 'token-123',
            sketch_path: '/path/to/sketch',
            board: 'arduino:avr:nano',
            port: '/dev/ttyUSB0',
            expires_in_s: 300,
          },
          error: 'CONFIRMATION_REQUIRED',
        },
      },
    ];

    const pending = extractPendingUpload(toolCalls);

    expect(pending).not.toBeNull();
    expect(pending?.confirmation_token).toBe('token-123');
    expect(pending?.sketch_path).toBe('/path/to/sketch');
    expect(pending?.board).toBe('arduino:avr:nano');
    expect(pending?.port).toBe('/dev/ttyUSB0');
    expect(pending?.expires_in_s).toBe(300);
  });

  it('returns null when no upload_firmware tool call', () => {
    const toolCalls = [
      {
        tool: 'query_telemetry',
        args: { limit: 10 },
        result: { ok: true, data: { rows: [] } },
      },
    ];

    const pending = extractPendingUpload(toolCalls);
    expect(pending).toBeNull();
  });

  it('returns null when upload_firmware succeeded (no confirmation needed)', () => {
    const toolCalls = [
      {
        tool: 'upload_firmware',
        args: { sketch_path: '/path/to/sketch', confirmation_token: 'token-123' },
        result: {
          ok: true,
          data: { sketch: '/path/to/sketch', board: 'arduino:avr:nano' },
        },
      },
    ];

    const pending = extractPendingUpload(toolCalls);
    expect(pending).toBeNull();
  });

  it('returns null for undefined tool_calls', () => {
    const pending = extractPendingUpload(undefined);
    expect(pending).toBeNull();
  });

  it('returns null for empty tool_calls array', () => {
    const pending = extractPendingUpload([]);
    expect(pending).toBeNull();
  });
});
