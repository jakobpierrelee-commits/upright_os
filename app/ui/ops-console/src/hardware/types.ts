export type BoardProfile = {
  id: string;
  family: 'arduino' | 'esp32' | 'teensy';
  label: string;
  fqbn: string;
  aliases: string[];
  leftPins: string[];
  rightPins: string[];
  capabilities: {
    cpu: string;
    maxClockMhz: number;
    ramKb: number;
    flashKb: number;
    storageKb?: number;
    wireless: string[];
    otaSupported: boolean;
  };
  assets?: BoardAssetBundle;
};

export type BoardAssetBundle = {
  vendor: string;
  docsUrl: string;
  pinoutUrl?: string;
  schematicUrl?: string;
  cadStepUrl?: string;
  cad3dUrl?: string;
  localDocsPath?: string;
  localPinoutPath?: string;
  localSchematicPath?: string;
  localCadPath?: string;
  notes?: string[];
};

export type BoardResolution = {
  profile: BoardProfile;
  confidence: number;
  ambiguous: boolean;
  reason: string;
  candidates: Array<{ id: string; label: string; score: number }>;
};

export type PinMap = {
  motor_l_pwm: number;
  motor_l_dir: number;
  motor_r_pwm: number;
  motor_r_dir: number;
  imu_sda: number;
  imu_scl: number;
  gate_enable: number;
  led: number;
  enc_l_a: number;
  enc_l_b: number;
  enc_r_a: number;
  enc_r_b: number;
};

export type PinValidationIssue = {
  level: 'error' | 'warn' | 'info';
  code: string;
  field?: keyof PinMap;
  pin?: number;
  message: string;
};

export type PinValidationResult = {
  ok: boolean;
  summary: {
    errors: number;
    warnings: number;
    infos: number;
  };
  issues: PinValidationIssue[];
};
