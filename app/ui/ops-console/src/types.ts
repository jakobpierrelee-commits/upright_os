export type Status = Record<string, string>;

export type ControlState = {
  arm_prepared: boolean;
  estop_latched: boolean;
  heartbeat_age_s?: number | null;
  watchdog_timeout_s?: number;
  watchdog_tripped?: boolean;
  watchdog_disarm_count?: number;
  watchdog_last_reason?: string;
};

export type Health = {
  connected: boolean;
  port: string;
  baud: number;
  last_status: Status;
  last_status_age_ms?: number | null;
  recent_line_count: number;
};
