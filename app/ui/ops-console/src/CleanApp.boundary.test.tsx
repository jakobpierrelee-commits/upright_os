import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { CleanAppState } from './clean/cleanAppTypes';
import CleanApp from './CleanApp';

const stateFixture: CleanAppState = {
  health: {
    connected: true,
    port: '/dev/cu.usbserial-2210',
    baud: 115200,
    last_status: {},
    recent_line_count: 12,
  },
  apiContractOk: true,
  control: {
    arm_prepared: false,
    estop_latched: false,
  },
  actionGates: null,
  status: { mode: 'safe_idle', ang: '0.01', raw: '0.02', gyro: '0.00', out: '0.00' },
  busy: false,
  msg: 'fixture message',
  actions: [{ label: 'Prepare Arm', run: async () => undefined }],
  globalDock: {
    level: 'ok',
    summary: 'Agent status synced',
    source: 'codex',
    ts: 1700000000000,
  },
  refresh: async () => undefined,
  runAction: async () => undefined,
  onGlobalStatus: () => undefined,
};

const useCleanAppStateMock = vi.fn(() => stateFixture);
const telemetryPropsSpy = vi.fn();
const commandPropsSpy = vi.fn();
const firmwarePropsSpy = vi.fn();
const codexPropsSpy = vi.fn();

vi.mock('./clean/useCleanAppState', () => ({
  useCleanAppState: () => useCleanAppStateMock(),
}));

vi.mock('./clean/CleanTelemetryPanel', () => ({
  CleanTelemetryPanel: (props: unknown) => {
    telemetryPropsSpy(props);
    return <div data-testid="telemetry-panel">telemetry-panel</div>;
  },
}));

vi.mock('./clean/CleanCommandRail', () => ({
  CleanCommandRail: (props: unknown) => {
    commandPropsSpy(props);
    return <div data-testid="command-panel">command-panel</div>;
  },
}));

vi.mock('./clean/CleanFirmwareSection', () => ({
  CleanFirmwareSection: (props: unknown) => {
    firmwarePropsSpy(props);
    return <div data-testid="firmware-section">firmware-section</div>;
  },
}));

vi.mock('./clean/CleanCodexSection', async () => {
  const React = await import('react');
  return {
    CleanCodexSection: React.forwardRef<HTMLElement, { mode: string; onGlobalStatus: unknown }>(
      (props, ref) => {
        codexPropsSpy(props);
        return (
          <section ref={ref} data-testid="codex-section">
            codex-section
          </section>
        );
      },
    ),
  };
});

describe('CleanApp composition boundaries', () => {
  it('renders boundary modules and keeps shell contract', () => {
    render(<CleanApp />);

    expect(screen.getByText('UPRIGHT.OS CLEAN CONSOLE')).toBeInTheDocument();
    expect(screen.getByText('CLEAN LANE LOCKED: 127.0.0.1 (line 8797)')).toBeInTheDocument();
    expect(screen.getByText('BRIDGE LAUNCH MODE: ISOLATED (IDE-SAFE DEFAULT)')).toBeInTheDocument();
    expect(screen.getByText('CONNECTED')).toBeInTheDocument();

    expect(screen.getByTestId('telemetry-panel')).toBeInTheDocument();
    expect(screen.getByTestId('command-panel')).toBeInTheDocument();
    expect(screen.getByTestId('firmware-section')).toBeInTheDocument();
    expect(screen.getByTestId('codex-section')).toBeInTheDocument();

    expect(telemetryPropsSpy).toHaveBeenCalledOnce();
    expect(commandPropsSpy).toHaveBeenCalledOnce();
    expect(firmwarePropsSpy).toHaveBeenCalledWith(
      expect.objectContaining({ mode: 'app_dev' }),
    );
    expect(codexPropsSpy).toHaveBeenCalledWith(
      expect.objectContaining({ mode: 'app_dev' }),
    );
  });
});
