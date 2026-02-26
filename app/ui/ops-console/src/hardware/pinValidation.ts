import type { BoardProfile, PinMap, PinValidationIssue, PinValidationResult } from './types';
import { pinNumberFromLabel } from './boardResolver';

const REQUIRED_FIELDS: Array<keyof PinMap> = [
  'motor_l_pwm',
  'motor_l_dir',
  'motor_r_pwm',
  'motor_r_dir',
  'imu_sda',
  'imu_scl',
  'gate_enable',
  'led',
];

const OPTIONAL_ENCODER_FIELDS: Array<keyof PinMap> = ['enc_l_a', 'enc_l_b', 'enc_r_a', 'enc_r_b'];

function boardPins(profile: BoardProfile): Set<number> {
  const values = [...profile.leftPins, ...profile.rightPins];
  const out = new Set<number>();
  values.forEach((label) => {
    const n = pinNumberFromLabel(label);
    if (n != null) out.add(n);
    if (profile.family === 'arduino') {
      const analog = label.toUpperCase().match(/A(\d{1,2})/);
      if (analog) {
        const a = Number.parseInt(analog[1], 10);
        if (Number.isFinite(a) && a >= 0 && a <= 15) {
          out.add(a);
          out.add(14 + a);
        }
      }
    }
  });
  return out;
}

function esp32StrapPins(): Set<number> {
  return new Set([0, 2, 5, 12, 15]);
}

function pwmHints(profile: BoardProfile): Set<number> {
  if (profile.family === 'arduino') {
    return new Set([3, 5, 6, 9, 10, 11]);
  }
  if (profile.family === 'esp32') {
    return new Set([
      2, 4, 5, 12, 13, 14, 15, 16, 17, 18, 19,
      21, 22, 23, 25, 26, 27, 32, 33,
    ]);
  }
  if (profile.family === 'teensy') {
    return new Set([2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13]);
  }
  return new Set<number>();
}

function pushIssue(
  issues: PinValidationIssue[],
  level: PinValidationIssue['level'],
  code: string,
  message: string,
  field?: keyof PinMap,
  pin?: number,
): void {
  issues.push({ level, code, message, field, pin });
}

export function validatePinMap(profile: BoardProfile, pinMap: PinMap): PinValidationResult {
  const issues: PinValidationIssue[] = [];
  const allowedPins = boardPins(profile);
  const seen = new Map<number, Array<keyof PinMap>>();
  const pwmCapable = pwmHints(profile);
  const strapPins = profile.family === 'esp32' ? esp32StrapPins() : new Set<number>();

  REQUIRED_FIELDS.forEach((field) => {
    const pin = pinMap[field];
    if (!Number.isFinite(pin) || pin < 0) {
      pushIssue(issues, 'error', 'missing_required_pin', `${field} must be assigned to a valid pin.`, field, pin);
      return;
    }
    if (!allowedPins.has(pin)) {
      pushIssue(issues, 'error', 'pin_not_on_board', `${field} pin ${pin} is not present on ${profile.label}.`, field, pin);
    }
    const row = seen.get(pin) ?? [];
    row.push(field);
    seen.set(pin, row);
  });

  OPTIONAL_ENCODER_FIELDS.forEach((field) => {
    const pin = pinMap[field];
    if (!Number.isFinite(pin) || pin < 0) return;
    if (!allowedPins.has(pin)) {
      pushIssue(issues, 'warn', 'optional_pin_not_on_board', `${field} pin ${pin} is not present on ${profile.label}.`, field, pin);
    }
    const row = seen.get(pin) ?? [];
    row.push(field);
    seen.set(pin, row);
  });

  Array.from(seen.entries()).forEach(([pin, fields]) => {
    if (fields.length <= 1) return;
    pushIssue(issues, 'error', 'duplicate_pin_assignment', `Pin ${pin} is assigned to multiple roles: ${fields.join(', ')}.`, undefined, pin);
  });

  (['motor_l_pwm', 'motor_r_pwm'] as const).forEach((field) => {
    const pin = pinMap[field];
    if (Number.isFinite(pin) && pin >= 0 && !pwmCapable.has(pin)) {
      pushIssue(issues, 'warn', 'pwm_capability_unknown', `${field} pin ${pin} may not support PWM on ${profile.label}.`, field, pin);
    }
  });

  if (profile.family === 'esp32') {
    REQUIRED_FIELDS.forEach((field) => {
      const pin = pinMap[field];
      if (Number.isFinite(pin) && pin >= 0 && strapPins.has(pin)) {
        pushIssue(issues, 'warn', 'esp32_boot_strap_pin', `${field} uses ESP32 boot strap pin ${pin}; avoid if possible.`, field, pin);
      }
    });
  }

  if (Number.isFinite(pinMap.imu_sda) && Number.isFinite(pinMap.imu_scl) && pinMap.imu_sda === pinMap.imu_scl) {
    pushIssue(issues, 'error', 'i2c_pin_collision', 'imu_sda and imu_scl cannot be the same pin.', 'imu_sda', pinMap.imu_sda);
  }

  const errors = issues.filter((i) => i.level === 'error').length;
  const warnings = issues.filter((i) => i.level === 'warn').length;
  const infos = issues.filter((i) => i.level === 'info').length;
  return {
    ok: errors === 0,
    summary: { errors, warnings, infos },
    issues,
  };
}
