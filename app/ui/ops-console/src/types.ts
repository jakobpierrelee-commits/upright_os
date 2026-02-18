export type Status = Record<string, string>;

export type ControlState = {
  arm_prepared: boolean;
  estop_latched: boolean;
};

export type Health = {
  connected: boolean;
  port: string;
  baud: number;
  last_status: Status;
  recent_line_count: number;
};
