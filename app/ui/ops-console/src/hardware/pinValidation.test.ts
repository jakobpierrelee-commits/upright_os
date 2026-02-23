import { describe, expect, it } from 'vitest';
import { BOARD_PROFILES } from './boardRegistry';
import { validatePinMap } from './pinValidation';

const basePins = {
  motor_l_pwm: 5,
  motor_l_dir: 4,
  motor_r_pwm: 6,
  motor_r_dir: 7,
  imu_sda: 18,
  imu_scl: 19,
  gate_enable: 8,
  led: 13,
  enc_l_a: -1,
  enc_l_b: -1,
  enc_r_a: -1,
  enc_r_b: -1,
};

describe('pinValidation', () => {
  it('passes valid nano baseline map', () => {
    const profile = BOARD_PROFILES.find((p) => p.id === 'nano');
    expect(profile).toBeTruthy();
    const out = validatePinMap(profile!, basePins);
    expect(out.ok).toBe(true);
    expect(out.summary.errors).toBe(0);
  });

  it('flags duplicate assignments as errors', () => {
    const profile = BOARD_PROFILES.find((p) => p.id === 'nano');
    const out = validatePinMap(profile!, { ...basePins, motor_r_pwm: 5 });
    expect(out.ok).toBe(false);
    expect(out.issues.some((i) => i.code === 'duplicate_pin_assignment')).toBe(true);
  });

  it('flags missing required pins', () => {
    const profile = BOARD_PROFILES.find((p) => p.id === 'nano');
    const out = validatePinMap(profile!, { ...basePins, imu_sda: -1 });
    expect(out.ok).toBe(false);
    expect(out.issues.some((i) => i.code === 'missing_required_pin')).toBe(true);
  });

  it('warns on esp32 strap pins', () => {
    const profile = BOARD_PROFILES.find((p) => p.id === 'esp32_devkitc_v4');
    const out = validatePinMap(profile!, { ...basePins, gate_enable: 0 });
    expect(out.issues.some((i) => i.code === 'esp32_boot_strap_pin')).toBe(true);
  });
});
