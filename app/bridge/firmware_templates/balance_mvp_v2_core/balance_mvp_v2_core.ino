#include <Arduino.h>
#include <math.h>
#include <Wire.h>
#include <EEPROM.h>
#include <MPU6050_light.h>
#include <avr/interrupt.h>
#include <stdlib.h>
#include <ctype.h>

#include "feature_profile.h"
#include "module_contracts.h"
#include "release_version.h"

#ifndef UPRIGHT_BUILD_ID
#define UPRIGHT_BUILD_ID "bmv2c"
#endif

#ifndef UPRIGHT_BUILD_HASH
#define UPRIGHT_BUILD_HASH "na"
#endif

#ifndef UPRIGHT_RUNTIME_VERSION
#define UPRIGHT_RUNTIME_VERSION "balance_mvp_v2_core.1.1"
#endif

#ifndef UPRIGHT_TUNE_VERSION
#define UPRIGHT_TUNE_VERSION "tune_v1"
#endif

namespace Pins {
  const uint8_t LED = LED_BUILTIN;
  const uint8_t ENC_LEFT = 2;
  const uint8_t ENC_RIGHT = 4;
  const uint8_t PWMA = 5;
  const uint8_t PWMB = 6;
  const uint8_t AIN1 = 7;
  const uint8_t STBY = 8;
  const uint8_t BIN1 = 12;
  const uint8_t VOL = A2;
}

struct RuntimeConfigV21 {
  uint32_t magic;
  uint8_t version;
  uint8_t reserved0;

  float kp;
  float ki;
  float kd;
  float set_deg;

  float out_max;
  float tip_deg;
  float i_max;
  float i_term_max;
  float d_cutoff_hz;
  float kaw;

  float q_angle;
  float q_bias;
  float r_measure;

  float kv;
  float kx;
  float out_slew_per_s;
  uint16_t arm_engage_ramp_ms;
  float motion_angle_gate_deg;
  float motion_term_max_deg;

  float sched_err_deg;
  float sched_boost;

  float angle_zero_deg;
  int8_t motor_polarity;
  int8_t imu_polarity;
  char imu_axis;
  uint8_t swap_axes;

  uint16_t autorun_delay_ms;
  uint8_t reserved1;
  uint8_t autotrim_enabled;
  float autotrim_trim_deg;
  float autotrim_trim_max_deg;
  float autotrim_step_max_deg_per_s;
  float autotrim_angle_gate_deg;
  float autotrim_gyro_gate_dps;
  float autotrim_wspd_gate_counts;
  float autotrim_out_frac_gate;
  float autotrim_err_deadband_deg;
  uint16_t crc16;
};

struct ImuCalV1 {
  uint32_t magic;
  uint8_t version;
  uint8_t reserved0;
  float gyro_x_offset;
  float gyro_y_offset;
  float gyro_z_offset;
  float acc_x_offset;
  float acc_y_offset;
  float acc_z_offset;
  uint16_t crc16;
};

static const uint32_t CFG_MAGIC = 0x32565055UL;  // "UPV2"
static const uint8_t CFG_VERSION = 21;
static const int EEPROM_CFG_ADDR = 0;

static const uint32_t IMU_CAL_MAGIC = 0x31434955UL;  // "UIC1"
static const uint8_t IMU_CAL_VERSION = 1;
static const int EEPROM_IMU_CAL_ADDR = EEPROM_CFG_ADDR + static_cast<int>(sizeof(RuntimeConfigV21));

static const uint16_t FAULT_ESTOP_LATCH_CODE = 32;

enum FaultNoteCode : uint8_t {
  NOTE_NONE = 0,
  NOTE_IMU_NOT_READY = 1,
  NOTE_SENSOR_INVALID = 2,
  NOTE_ANGLE_INVALID = 3,
  NOTE_TIP_LIMIT = 4,
  NOTE_ENCODER_STALE = 5,
  NOTE_LOOP_OVERRUN = 6,
  NOTE_IMU_BEGIN_FAILED = 7
};

static RuntimeConfigV21 g_cfg;
static RuntimeState g_state = {true, false, 0.0f, 0.0f, 0.0f, 0, FAULT_NONE};

static float g_raw = 0.0f;
static float g_out = 0.0f;
static float g_vol_raw = 0.0f;

static float g_wpos_raw_counts = 0.0f;
static float g_wpos_unclamped_counts = 0.0f;
static float g_wdelta_counts = 0.0f;
static float g_wdelta_tick_counts = 0.0f;
static float g_wspd_counts = 0.0f;
static float g_wpos_target_counts = 0.0f;

static float g_pid_err = 0.0f;
static float g_pid_p = 0.0f;
static float g_pid_i = 0.0f;
static float g_pid_d = 0.0f;
static float g_pid_u_unsat = 0.0f;
static float g_pid_u_sat = 0.0f;
static float g_i_state = 0.0f;
static float g_prev_err = 0.0f;
static bool g_output_saturated = false;
static bool g_conditional_i = true;

static float g_d_alpha = 1.0f;
static bool g_d_init = false;
static float g_d_unfilt = 0.0f;
static float g_d_filt = 0.0f;

static float g_kf_angle = 0.0f;
static float g_kf_bias = 0.0f;
static float g_kf_P00 = 1.0f;
static float g_kf_P01 = 0.0f;
static float g_kf_P10 = 0.0f;
static float g_kf_P11 = 1.0f;

volatile long g_enc_l = 0;
volatile long g_enc_r = 0;
volatile uint8_t g_prev_port_d = 0;
static long g_prev_enc_l = 0;
static long g_prev_enc_r = 0;
static uint32_t g_last_moving_enc_ms = 0;

static uint32_t g_next_tick_us = 0;
static uint32_t g_last_tick_us = 0;
static uint32_t g_last_status_ms = 0;
static uint32_t g_arm_enter_ms = 0;

static uint32_t g_loop_missed = 0;
static uint16_t g_loop_overrun_consecutive = 0;
static uint32_t g_last_step_us = 0;

static uint32_t g_fault_count = 0;
static uint8_t g_last_fault_note = NOTE_NONE;

static float g_runaway_score = 0.0f;
static float g_sched_scale = 1.0f;
static float g_set_eff_deg = 0.0f;
static uint16_t g_trim_stable_ticks = 0;

static int16_t g_out_left_cmd = 0;
static int16_t g_out_right_cmd = 0;
static float g_fault_ang_snapshot = 0.0f;
static float g_fault_out_snapshot = 0.0f;
static float g_fault_runaway_snapshot = 0.0f;
static float g_fault_wpos_snapshot = 0.0f;

static bool g_imu_ok = false;
static bool g_imu_cal_loaded = false;
MPU6050 g_mpu(Wire);

#if FEAT_AUTORUN_CMD || FEAT_BOOT_AUTORUN
static bool g_autorun_pending = false;
static uint32_t g_autorun_due_ms = 0;
#endif

static char g_cmd_buf[128];
static uint8_t g_cmd_len = 0;

static const float DT_S = static_cast<float>(LOOP_PERIOD_US) * 1.0e-6f;
#if FEAT_AUTORUN_CMD
static const uint16_t AUTORUN_DELAY_MAX_MS = 15000U;
#endif

static float clampf(float v, float lo, float hi) {
  if (v < lo) return lo;
  if (v > hi) return hi;
  return v;
}

static bool isFinitef(float v) {
  return isfinite(v) != 0;
}

static const char* modeName() {
  if (g_state.active_fault != FAULT_NONE) return "FAULT";
  return g_state.armed ? "BALANCING" : "SAFE_IDLE";
}

static uint16_t cfgCrc16(const RuntimeConfigV21& cfg) {
  const uint8_t* p = reinterpret_cast<const uint8_t*>(&cfg);
  const size_t n = sizeof(RuntimeConfigV21) - sizeof(cfg.crc16);
  uint16_t crc = 0xFFFFU;
  for (size_t i = 0; i < n; ++i) {
    crc ^= static_cast<uint16_t>(p[i]);
    for (uint8_t b = 0; b < 8; ++b) {
      if (crc & 1U) crc = static_cast<uint16_t>((crc >> 1) ^ 0xA001U);
      else crc >>= 1;
    }
  }
  return crc;
}

static uint16_t imuCalCrc16(const ImuCalV1& cal) {
  const uint8_t* p = reinterpret_cast<const uint8_t*>(&cal);
  const size_t n = sizeof(ImuCalV1) - sizeof(cal.crc16);
  uint16_t crc = 0xFFFFU;
  for (size_t i = 0; i < n; ++i) {
    crc ^= static_cast<uint16_t>(p[i]);
    for (uint8_t b = 0; b < 8; ++b) {
      if (crc & 1U) crc = static_cast<uint16_t>((crc >> 1) ^ 0xA001U);
      else crc >>= 1;
    }
  }
  return crc;
}

static void imuCalCapture(ImuCalV1* out) {
  if (out == nullptr) return;
  out->magic = IMU_CAL_MAGIC;
  out->version = IMU_CAL_VERSION;
  out->reserved0 = 0;
  out->gyro_x_offset = g_mpu.getGyroXoffset();
  out->gyro_y_offset = g_mpu.getGyroYoffset();
  out->gyro_z_offset = g_mpu.getGyroZoffset();
  out->acc_x_offset = g_mpu.getAccXoffset();
  out->acc_y_offset = g_mpu.getAccYoffset();
  out->acc_z_offset = g_mpu.getAccZoffset();
  out->crc16 = imuCalCrc16(*out);
}

static void imuCalApply(const ImuCalV1& cal) {
  g_mpu.setGyroOffsets(cal.gyro_x_offset, cal.gyro_y_offset, cal.gyro_z_offset);
  g_mpu.setAccOffsets(cal.acc_x_offset, cal.acc_y_offset, cal.acc_z_offset);
}

static bool imuCalLoad(ImuCalV1* out) {
#if FEAT_EEPROM_CONFIG
  ImuCalV1 tmp;
  EEPROM.get(EEPROM_IMU_CAL_ADDR, tmp);
  if (tmp.magic != IMU_CAL_MAGIC || tmp.version != IMU_CAL_VERSION) return false;
  if (tmp.crc16 != imuCalCrc16(tmp)) return false;
  if (out != nullptr) *out = tmp;
  return true;
#else
  (void)out;
  return false;
#endif
}

static bool imuCalSaveFromCurrent(ImuCalV1* out_saved) {
#if FEAT_EEPROM_CONFIG
  ImuCalV1 now;
  imuCalCapture(&now);
  EEPROM.put(EEPROM_IMU_CAL_ADDR, now);
  if (out_saved != nullptr) *out_saved = now;
  return true;
#else
  (void)out_saved;
  return false;
#endif
}

static void cfgDefaults() {
  g_cfg.magic = CFG_MAGIC;
  g_cfg.version = CFG_VERSION;
  g_cfg.reserved0 = 0;

  g_cfg.kp = 30.0f;
  g_cfg.ki = 0.0f;
  g_cfg.kd = 0.8f;
  g_cfg.set_deg = 0.0f;

  g_cfg.out_max = 230.0f;
  g_cfg.tip_deg = 35.0f;
  g_cfg.i_max = 90.0f;
  g_cfg.i_term_max = 120.0f;
  g_cfg.d_cutoff_hz = 18.0f;
  g_cfg.kaw = 0.25f;

  g_cfg.q_angle = 0.001f;
  g_cfg.q_bias = 0.003f;
  g_cfg.r_measure = 0.03f;

  g_cfg.kv = 0.008f;
  g_cfg.kx = 0.0015f;
  g_cfg.out_slew_per_s = 6000.0f;
  g_cfg.arm_engage_ramp_ms = 350U;
  g_cfg.motion_angle_gate_deg = 12.0f;
  g_cfg.motion_term_max_deg = 5.0f;

  g_cfg.sched_err_deg = 3.0f;
  g_cfg.sched_boost = 0.40f;

  g_cfg.angle_zero_deg = 0.0f;
  g_cfg.motor_polarity = 1;
  g_cfg.imu_polarity = 1;
  g_cfg.imu_axis = 'Y';
  g_cfg.swap_axes = 1;

  g_cfg.autorun_delay_ms = 2000U;
  g_cfg.reserved1 = 0;
  g_cfg.autotrim_enabled = 0;
  g_cfg.autotrim_trim_deg = 0.0f;
  g_cfg.autotrim_trim_max_deg = 3.0f;
  g_cfg.autotrim_step_max_deg_per_s = 0.20f;
  g_cfg.autotrim_angle_gate_deg = 6.0f;
  g_cfg.autotrim_gyro_gate_dps = 25.0f;
  g_cfg.autotrim_wspd_gate_counts = 100.0f;
  g_cfg.autotrim_out_frac_gate = 0.60f;
  g_cfg.autotrim_err_deadband_deg = 0.05f;

  g_cfg.crc16 = cfgCrc16(g_cfg);
}

static void cfgSanitize() {
  g_cfg.kp = clampf(g_cfg.kp, 0.0f, 500.0f);
  g_cfg.ki = clampf(g_cfg.ki, 0.0f, 100.0f);
  g_cfg.kd = clampf(g_cfg.kd, 0.0f, 500.0f);
  g_cfg.set_deg = clampf(g_cfg.set_deg, -30.0f, 30.0f);

  g_cfg.out_max = clampf(g_cfg.out_max, 20.0f, 255.0f);
  g_cfg.tip_deg = clampf(g_cfg.tip_deg, 5.0f, 60.0f);
  g_cfg.i_max = clampf(g_cfg.i_max, 1.0f, 500.0f);
  g_cfg.i_term_max = clampf(g_cfg.i_term_max, 1.0f, 500.0f);
  g_cfg.d_cutoff_hz = clampf(g_cfg.d_cutoff_hz, 0.1f, 120.0f);
  g_cfg.kaw = clampf(g_cfg.kaw, 0.0f, 5.0f);

  g_cfg.q_angle = clampf(g_cfg.q_angle, 0.000001f, 10.0f);
  g_cfg.q_bias = clampf(g_cfg.q_bias, 0.000001f, 10.0f);
  g_cfg.r_measure = clampf(g_cfg.r_measure, 0.000001f, 10.0f);

  g_cfg.kv = clampf(g_cfg.kv, 0.0f, 0.20f);
  g_cfg.kx = clampf(g_cfg.kx, 0.0f, 0.02f);
  g_cfg.out_slew_per_s = clampf(g_cfg.out_slew_per_s, 50.0f, 20000.0f);
  g_cfg.arm_engage_ramp_ms = static_cast<uint16_t>(constrain(g_cfg.arm_engage_ramp_ms, 0, 5000));
  g_cfg.motion_angle_gate_deg = clampf(g_cfg.motion_angle_gate_deg, 1.0f, 45.0f);
  g_cfg.motion_term_max_deg = clampf(g_cfg.motion_term_max_deg, 0.1f, 20.0f);

  g_cfg.sched_err_deg = clampf(g_cfg.sched_err_deg, 0.5f, 20.0f);
  g_cfg.sched_boost = clampf(g_cfg.sched_boost, 0.0f, 2.0f);

  g_cfg.angle_zero_deg = clampf(g_cfg.angle_zero_deg, -45.0f, 45.0f);
  g_cfg.motor_polarity = (g_cfg.motor_polarity >= 0) ? 1 : -1;
  g_cfg.imu_polarity = (g_cfg.imu_polarity >= 0) ? 1 : -1;
  g_cfg.imu_axis = (g_cfg.imu_axis == 'X' || g_cfg.imu_axis == 'Y') ? g_cfg.imu_axis : 'Y';
  g_cfg.swap_axes = g_cfg.swap_axes ? 1 : 0;
  g_cfg.autorun_delay_ms = static_cast<uint16_t>(constrain(g_cfg.autorun_delay_ms, 0, 15000));
  g_cfg.autotrim_enabled = g_cfg.autotrim_enabled ? 1 : 0;
  g_cfg.autotrim_trim_max_deg = clampf(g_cfg.autotrim_trim_max_deg, 0.0f, 10.0f);
  g_cfg.autotrim_step_max_deg_per_s = clampf(g_cfg.autotrim_step_max_deg_per_s, 0.0f, 5.0f);
  g_cfg.autotrim_angle_gate_deg = clampf(g_cfg.autotrim_angle_gate_deg, 0.1f, 30.0f);
  g_cfg.autotrim_gyro_gate_dps = clampf(g_cfg.autotrim_gyro_gate_dps, 0.1f, 300.0f);
  g_cfg.autotrim_wspd_gate_counts = clampf(g_cfg.autotrim_wspd_gate_counts, 0.0f, 2000.0f);
  g_cfg.autotrim_out_frac_gate = clampf(g_cfg.autotrim_out_frac_gate, 0.01f, 1.00f);
  g_cfg.autotrim_err_deadband_deg = clampf(g_cfg.autotrim_err_deadband_deg, 0.0f, 2.0f);
  g_cfg.autotrim_trim_deg = clampf(g_cfg.autotrim_trim_deg, -g_cfg.autotrim_trim_max_deg, g_cfg.autotrim_trim_max_deg);
}

static bool cfgLoad() {
#if FEAT_EEPROM_CONFIG
  RuntimeConfigV21 tmp;
  EEPROM.get(EEPROM_CFG_ADDR, tmp);
  if (tmp.magic != CFG_MAGIC || tmp.version != CFG_VERSION) return false;
  const uint16_t expected_crc = cfgCrc16(tmp);
  if (tmp.crc16 != expected_crc) return false;
  g_cfg = tmp;
  cfgSanitize();
  return true;
#else
  return false;
#endif
}

static void cfgSave() {
#if FEAT_EEPROM_CONFIG
  cfgSanitize();
  g_cfg.crc16 = cfgCrc16(g_cfg);
  EEPROM.put(EEPROM_CFG_ADDR, g_cfg);
#endif
}

void isrEncLeft() {
  g_enc_l++;
}

ISR(PCINT2_vect) {
  uint8_t now_d = PIND;
  uint8_t changed = now_d ^ g_prev_port_d;
  if (changed & _BV(PD4)) g_enc_r++;
  g_prev_port_d = now_d;
}

static void motorStop() {
  analogWrite(Pins::PWMA, 0);
  analogWrite(Pins::PWMB, 0);
  digitalWrite(Pins::STBY, LOW);
  g_out_left_cmd = 0;
  g_out_right_cmd = 0;
}

static void applyMotorLr(int left_cmd, int right_cmd) {
  left_cmd = constrain(left_cmd * g_cfg.motor_polarity, -255, 255);
  right_cmd = constrain(right_cmd * g_cfg.motor_polarity, -255, 255);
  g_out_left_cmd = static_cast<int16_t>(left_cmd);
  g_out_right_cmd = static_cast<int16_t>(right_cmd);

  const bool left_backward = (left_cmd > 0);
  const bool right_backward = (right_cmd > 0);
  const int left_pwm = abs(left_cmd);
  const int right_pwm = abs(right_cmd);

  digitalWrite(Pins::AIN1, left_backward ? HIGH : LOW);
  digitalWrite(Pins::BIN1, right_backward ? HIGH : LOW);

  if (left_pwm == 0 && right_pwm == 0) {
    motorStop();
    return;
  }

  digitalWrite(Pins::STBY, HIGH);
  analogWrite(Pins::PWMA, left_pwm);
  analogWrite(Pins::PWMB, right_pwm);
}

static void applyMotorOutput(float out) {
  int cmd = static_cast<int>(clampf(out, -255.0f, 255.0f));
  applyMotorLr(cmd, cmd);
}

static float readAccelDeg() {
  float x = g_mpu.getAngleX();
  float y = g_mpu.getAngleY();
  if (!g_cfg.swap_axes) return (g_cfg.imu_axis == 'X') ? x : y;
  return (g_cfg.imu_axis == 'X') ? y : x;
}

static float readGyroDps() {
  float x = g_mpu.getGyroX();
  float y = g_mpu.getGyroY();
  if (!g_cfg.swap_axes) return (g_cfg.imu_axis == 'X') ? x : y;
  return (g_cfg.imu_axis == 'X') ? y : x;
}

static void kalmanUpdate(float accel_angle_deg, float gyro_rate_dps, float dt_s) {
  if (dt_s <= 0.0f) dt_s = 0.01f;

  float rate = gyro_rate_dps - g_kf_bias;
  g_kf_angle += dt_s * rate;

  g_kf_P00 += dt_s * (dt_s * g_kf_P11 - g_kf_P01 - g_kf_P10 + g_cfg.q_angle);
  g_kf_P01 -= dt_s * g_kf_P11;
  g_kf_P10 -= dt_s * g_kf_P11;
  g_kf_P11 += g_cfg.q_bias * dt_s;

  float innov = accel_angle_deg - g_kf_angle;
  float S = g_kf_P00 + g_cfg.r_measure;
  if (S <= 1e-9f) return;

  float K0 = g_kf_P00 / S;
  float K1 = g_kf_P10 / S;

  g_kf_angle += K0 * innov;
  g_kf_bias += K1 * innov;

  float p00 = g_kf_P00;
  float p01 = g_kf_P01;
  g_kf_P00 -= K0 * p00;
  g_kf_P01 -= K0 * p01;
  g_kf_P10 -= K1 * p00;
  g_kf_P11 -= K1 * p01;
}

static float alphaFromCutoffHz(float cutoff_hz, float dt_s) {
  if (cutoff_hz <= 0.0f || dt_s <= 0.0f) return 1.0f;
  float tau = 1.0f / (2.0f * PI * cutoff_hz);
  return dt_s / (tau + dt_s);
}

static float lowPass(float x, float y_prev, float alpha) {
  return y_prev + alpha * (x - y_prev);
}

static void resetMotionState() {
  g_wpos_raw_counts = 0.0f;
  g_wdelta_counts = 0.0f;
  g_wpos_unclamped_counts = 0.0f;
  g_wdelta_tick_counts = 0.0f;
  g_wspd_counts = 0.0f;
  g_wpos_target_counts = 0.0f;
  g_trim_stable_ticks = 0;
}

static void latchFault(uint16_t code, uint8_t note_code, const __FlashStringHelper* note) {
  g_fault_ang_snapshot = g_state.angle_deg;
  g_fault_out_snapshot = g_out;
  g_fault_runaway_snapshot = g_runaway_score;
  g_fault_wpos_snapshot = g_wpos_unclamped_counts;
  g_fault_count++;
  g_last_fault_note = note_code;
  if (g_state.active_fault == FAULT_NONE) {
    g_state.active_fault = code;
  }
  g_state.estop_latched = true;
  g_state.armed = false;
  g_state.output_cmd = 0.0f;
  g_out = 0.0f;
  applyMotorOutput(0.0f);

  Serial.print(F("FAULT code="));
  Serial.print(g_state.active_fault);
  Serial.print(F(" count="));
  Serial.print(g_fault_count);
  Serial.print(F(" note_code="));
  Serial.print(g_last_fault_note);
  Serial.print(F(" fault_ang="));
  Serial.print(g_fault_ang_snapshot, 3);
  Serial.print(F(" fault_out="));
  Serial.print(g_fault_out_snapshot, 3);
  Serial.print(F(" fault_runaway="));
  Serial.print(g_fault_runaway_snapshot, 3);
  Serial.print(F(" fault_wpos="));
  Serial.print(g_fault_wpos_snapshot, 3);
  Serial.print(F(" note="));
  Serial.println(note);
}

static void clearFault() {
  g_state.active_fault = FAULT_NONE;
  g_state.estop_latched = true;
  g_state.armed = false;
  g_state.output_cmd = 0.0f;
  g_out = 0.0f;
  g_i_state = 0.0f;
  g_prev_err = 0.0f;
  g_d_init = false;
  g_loop_overrun_consecutive = 0;
  g_runaway_score = 0.0f;
  resetMotionState();
  applyMotorOutput(0.0f);
}

static void resetEstimatorToCurrentAccel() {
  g_kf_P00 = 1.0f;
  g_kf_P01 = 0.0f;
  g_kf_P10 = 0.0f;
  g_kf_P11 = 1.0f;
  g_kf_bias = 0.0f;
  g_kf_angle = g_raw;
}

static void emitStatus() {
  const char* mode = modeName();
  Serial.print(F("S mode="));
  Serial.print(mode);
  Serial.print(F(" estop="));
  Serial.print(g_state.estop_latched ? 1 : 0);
  Serial.print(F(" armed="));
  Serial.print(g_state.armed ? 1 : 0);
  Serial.print(F(" fault="));
  Serial.print(g_state.active_fault);
  Serial.print(F(" fault_count="));
  Serial.print(g_fault_count);
  Serial.print(F(" ang="));
  Serial.print(g_state.angle_deg, 3);
  Serial.print(F(" raw="));
  Serial.print(g_raw, 3);
  Serial.print(F(" gyro="));
  Serial.print(g_state.gyro_dps, 3);
  Serial.print(F(" set="));
  Serial.print(g_cfg.set_deg, 3);
  g_set_eff_deg = clampf(g_cfg.set_deg + g_cfg.autotrim_trim_deg, -30.0f, 30.0f);
  Serial.print(F(" set_eff="));
  Serial.print(g_set_eff_deg, 3);
  Serial.print(F(" out="));
  Serial.print(g_out, 2);
  Serial.print(F(" kp="));
  Serial.print(g_cfg.kp, 2);
  Serial.print(F(" ki="));
  Serial.print(g_cfg.ki, 2);
  Serial.print(F(" kd="));
  Serial.print(g_cfg.kd, 2);
  Serial.print(F(" kv="));
  Serial.print(g_cfg.kv, 4);
  Serial.print(F(" kx="));
  Serial.print(g_cfg.kx, 4);
  Serial.print(F(" gse="));
  Serial.print(g_cfg.sched_err_deg, 2);
  Serial.print(F(" gsb="));
  Serial.print(g_cfg.sched_boost, 2);
  Serial.print(F(" gss="));
  Serial.print(g_sched_scale, 2);
  Serial.print(F(" sl="));
  Serial.print(g_cfg.out_slew_per_s, 0);
  Serial.print(F(" rp="));
  Serial.print(g_cfg.arm_engage_ramp_ms);
  Serial.print(F(" mg="));
  Serial.print(g_cfg.motion_angle_gate_deg, 1);
  Serial.print(F(" mm="));
  Serial.print(g_cfg.motion_term_max_deg, 1);
  Serial.print(F(" dcf="));
  Serial.print(g_cfg.d_cutoff_hz, 1);
  Serial.print(F(" kaw="));
  Serial.print(g_cfg.kaw, 2);
  Serial.print(F(" wspd="));
  Serial.print(g_wspd_counts, 2);
  Serial.print(F(" wpos="));
  Serial.print(g_wpos_unclamped_counts, 2);
  Serial.print(F(" wdelta="));
  Serial.print(g_wdelta_counts, 2);
  Serial.print(F(" outL="));
  Serial.print(g_out_left_cmd);
  Serial.print(F(" outR="));
  Serial.print(g_out_right_cmd);
  Serial.print(F(" runaway="));
  Serial.print(g_runaway_score, 3);
  Serial.print(F(" outMax="));
  Serial.print(g_cfg.out_max, 1);
  Serial.print(F(" tipDeg="));
  Serial.print(g_cfg.tip_deg, 1);
  Serial.print(F(" loop_us="));
  Serial.print(g_last_step_us);
  Serial.print(F(" missed="));
  Serial.print(g_loop_missed);
  Serial.print(F(" overrun="));
  Serial.print(g_state.loop_overrun_count);
  Serial.print(F(" imu_zero="));
  Serial.print(g_cfg.angle_zero_deg, 3);
  Serial.print(F(" ar_delay="));
  Serial.print(g_cfg.autorun_delay_ms);
  Serial.print(F(" at="));
  Serial.print(g_cfg.autotrim_enabled ? 1 : 0);
  Serial.print(F(" tr="));
  Serial.print(g_cfg.autotrim_trim_deg, 3);
  Serial.println();
}

static void printHelp() {
  Serial.println(F("OK HELP GET PID SETPOINT MOTION AUTOTRIM SAVECFG"));
}

static uint8_t splitTokens(char* text, char* tokens[], uint8_t max_tokens) {
  uint8_t count = 0;
  char* save = nullptr;
  char* tok = strtok_r(text, " \t", &save);
  while (tok != nullptr && count < max_tokens) {
    tokens[count++] = tok;
    tok = strtok_r(nullptr, " \t", &save);
  }
  return count;
}

static bool parseFloatStrict(const char* text, float* out) {
  if (text == nullptr || out == nullptr) return false;
  bool saw_digit = false;
  bool saw_dot = false;
  bool saw_exp = false;
  for (const char* p = text; *p != '\0'; ++p) {
    char c = *p;
    if (c >= '0' && c <= '9') {
      saw_digit = true;
      continue;
    }
    if ((c == '+' || c == '-') && (p == text || (*(p - 1) == 'e' || *(p - 1) == 'E'))) {
      continue;
    }
    if (c == '.' && !saw_dot && !saw_exp) {
      saw_dot = true;
      continue;
    }
    if ((c == 'e' || c == 'E') && !saw_exp && saw_digit) {
      saw_exp = true;
      continue;
    }
    return false;
  }
  if (!saw_digit) return false;
  *out = static_cast<float>(atof(text));
  return true;
}

static bool parseIntStrict(const char* text, int* out) {
  if (text == nullptr || out == nullptr) return false;
  char* end = nullptr;
  long v = strtol(text, &end, 10);
  if (end == text || *end != '\0') return false;
  *out = static_cast<int>(v);
  return true;
}

static bool parseCommandFloats(const char* line, const char* cmd, uint8_t min_vals, uint8_t max_vals, float values[], uint8_t* count_out) {
  if (line == nullptr || cmd == nullptr || values == nullptr || min_vals > max_vals || max_vals > 8) return false;
  char buf[128];
  strncpy(buf, line, sizeof(buf) - 1);
  buf[sizeof(buf) - 1] = '\0';

  char* toks[9];
  uint8_t n = splitTokens(buf, toks, 9);
  if (n < (uint8_t)(1 + min_vals) || n > (uint8_t)(1 + max_vals)) return false;
  if (strcmp(toks[0], cmd) != 0) return false;

  for (uint8_t i = 1; i < n; ++i) {
    if (!parseFloatStrict(toks[i], &values[i - 1])) return false;
  }
  if (count_out != nullptr) *count_out = static_cast<uint8_t>(n - 1);
  return true;
}

static bool parseCommandInt(const char* line, const char* cmd, int* out_value) {
  if (line == nullptr || cmd == nullptr || out_value == nullptr) return false;
  char buf[64];
  strncpy(buf, line, sizeof(buf) - 1);
  buf[sizeof(buf) - 1] = '\0';

  char* toks[3];
  uint8_t n = splitTokens(buf, toks, 3);
  if (n != 2) return false;
  if (strcmp(toks[0], cmd) != 0) return false;
  return parseIntStrict(toks[1], out_value);
}

static void startArmedRun() {
  g_state.estop_latched = false;
  g_state.armed = true;
  g_arm_enter_ms = millis();
  g_i_state = 0.0f;
  g_prev_err = 0.0f;
  g_d_init = false;
  resetMotionState();
}

static bool parsePID(const char* line) {
  float vals[3];
  if (parseCommandFloats(line, "PID", 3, 3, vals, nullptr)) {
    g_cfg.kp = vals[0];
    g_cfg.ki = vals[1];
    g_cfg.kd = vals[2];
    cfgSanitize();
    Serial.println(F("OK PID"));
    return true;
  }
  return false;
}

static bool parseSetpoint(const char* line) {
  float vals[1];
  if (parseCommandFloats(line, "SETPOINT", 1, 1, vals, nullptr)) {
    g_cfg.set_deg = vals[0];
    cfgSanitize();
    Serial.println(F("OK SETPOINT"));
    return true;
  }
  return false;
}

static bool parseLimits(const char* line) {
  float vals[4];
  uint8_t n = 0;
  if (parseCommandFloats(line, "LIMITS", 2, 4, vals, &n)) {
    g_cfg.out_max = vals[0];
    g_cfg.tip_deg = vals[1];
    if (n >= 3) g_cfg.i_max = vals[2];
    if (n >= 4) g_cfg.i_term_max = vals[3];
    cfgSanitize();
    Serial.println(F("OK LIMITS"));
    return true;
  }
  return false;
}

static bool parseMotion(const char* line) {
  float vals[2];
  if (parseCommandFloats(line, "MOTION", 2, 2, vals, nullptr)) {
    g_cfg.kv = vals[0];
    g_cfg.kx = vals[1];
    cfgSanitize();
    Serial.println(F("OK MOTION"));
    return true;
  }
  return false;
}

static bool parseSlew(const char* line) {
  float vals[1];
  if (parseCommandFloats(line, "SLEW", 1, 1, vals, nullptr)) {
    g_cfg.out_slew_per_s = vals[0];
    cfgSanitize();
    Serial.println(F("OK SLEW"));
    return true;
  }
  return false;
}

static bool parseRamp(const char* line) {
  int v = 0;
  if (parseCommandInt(line, "RAMP", &v)) {
    g_cfg.arm_engage_ramp_ms = static_cast<uint16_t>(v);
    cfgSanitize();
    Serial.println(F("OK RAMP"));
    return true;
  }
  return false;
}

static bool parseMotionCfg(const char* line) {
  float vals[2];
  if (parseCommandFloats(line, "MOTIONCFG", 2, 2, vals, nullptr)) {
    g_cfg.motion_angle_gate_deg = vals[0];
    g_cfg.motion_term_max_deg = vals[1];
    cfgSanitize();
    Serial.println(F("OK MOTIONCFG"));
    return true;
  }
  return false;
}

static bool parseGsched(const char* line) {
  float vals[2];
  if (parseCommandFloats(line, "GSCHED", 2, 2, vals, nullptr)) {
    g_cfg.sched_err_deg = vals[0];
    g_cfg.sched_boost = vals[1];
    cfgSanitize();
    Serial.println(F("OK GSCHED"));
    return true;
  }
  return false;
}

static bool parseDcfg(const char* line) {
  float vals[2];
  if (parseCommandFloats(line, "DCFG", 2, 2, vals, nullptr)) {
    g_cfg.d_cutoff_hz = vals[0];
    g_cfg.kaw = vals[1];
    cfgSanitize();
    Serial.println(F("OK DCFG"));
    return true;
  }
  return false;
}

static bool parseAutotrim(const char* line) {
  int v = 0;
  if (parseCommandInt(line, "AUTOTRIM", &v)) {
    g_cfg.autotrim_enabled = (v != 0) ? 1 : 0;
    cfgSanitize();
    Serial.print(F("OK AUTOTRIM "));
    Serial.println(g_cfg.autotrim_enabled ? F("1") : F("0"));
    return true;
  }
  return false;
}

static bool parseTrimcfg(const char* line) {
  float vals[5];
  if (parseCommandFloats(line, "TRIMCFG", 5, 5, vals, nullptr)) {
    g_cfg.autotrim_step_max_deg_per_s = vals[0];
    g_cfg.autotrim_angle_gate_deg = vals[1];
    g_cfg.autotrim_gyro_gate_dps = vals[2];
    g_cfg.autotrim_wspd_gate_counts = vals[3];
    g_cfg.autotrim_out_frac_gate = vals[4];
    cfgSanitize();
    Serial.println(F("OK TRIMCFG"));
    return true;
  }
  return false;
}

static bool parseTrimlims(const char* line) {
  float vals[2];
  if (parseCommandFloats(line, "TRIMLIMS", 2, 2, vals, nullptr)) {
    g_cfg.autotrim_trim_max_deg = vals[0];
    g_cfg.autotrim_err_deadband_deg = vals[1];
    cfgSanitize();
    Serial.println(F("OK TRIMLIMS"));
    return true;
  }
  return false;
}

static void runCalZero() {
  if (!g_imu_ok) {
    Serial.println(F("ERR CAL imu_not_ready"));
    return;
  }

  const uint16_t n = 120;
  float sum = 0.0f;
  for (uint16_t i = 0; i < n; ++i) {
    g_mpu.update();
    float accel = readAccelDeg();
    float gyro = readGyroDps();
    g_raw = accel;
    kalmanUpdate(g_raw, gyro, 0.005f);
    sum += (g_cfg.imu_polarity * g_kf_angle);
    delay(5);
  }

  g_cfg.angle_zero_deg = sum / static_cast<float>(n);
  g_cfg.autotrim_trim_deg = 0.0f;
  cfgSanitize();
  cfgSave();
  Serial.print(F("OK CAL ZERO zero="));
  Serial.println(g_cfg.angle_zero_deg, 4);
}

static void runImuLoad() {
  if (!g_imu_ok) {
    Serial.println(F("ERR IMU_LOAD imu_not_ready"));
    return;
  }
  ImuCalV1 cal;
  if (!imuCalLoad(&cal)) {
    Serial.println(F("ERR IMU_LOAD no_saved_offsets"));
    return;
  }
  imuCalApply(cal);
  g_mpu.update();
  g_raw = readAccelDeg();
  resetEstimatorToCurrentAccel();
  Serial.println(F("OK IMU_LOAD"));
}

static void runImuSave() {
  if (!g_imu_ok) {
    Serial.println(F("ERR IMU_SAVE imu_not_ready"));
    return;
  }
  if (!imuCalSaveFromCurrent(nullptr)) {
    Serial.println(F("ERR IMU_SAVE eeprom_unavailable"));
    return;
  }
  Serial.println(F("OK IMU_SAVE"));
}

static void runImuCal() {
  if (!g_imu_ok) {
    Serial.println(F("ERR IMU_CAL imu_not_ready"));
    return;
  }
  if (g_state.armed) {
    Serial.println(F("ERR IMU_CAL unsafe_state"));
    return;
  }
  g_mpu.calcOffsets();
  if (!imuCalSaveFromCurrent(nullptr)) {
    Serial.println(F("ERR IMU_CAL eeprom_unavailable"));
    return;
  }
  g_mpu.update();
  g_raw = readAccelDeg();
  resetEstimatorToCurrentAccel();
  Serial.println(F("OK IMU_CAL"));
}

static void runImuInfo() {
  if (!g_imu_ok) {
    Serial.println(F("ERR IMU_INFO imu_not_ready"));
    return;
  }
  Serial.println(F("OK IMU_INFO"));
}

static void handleCommandLine(char* line) {
  while (*line == ' ') line++;
  if (*line == '\0') return;

  size_t n = strlen(line);
  while (n > 0 && (line[n - 1] == ' ' || line[n - 1] == '\t')) {
    line[--n] = '\0';
  }

  if (strcmp(line, "GET") == 0) { emitStatus(); return; }
  if (strcmp(line, "HELP") == 0) { printHelp(); return; }
  if (strcmp(line, "IDENT") == 0) {
    Serial.print(F("OK IDENT build="));
    Serial.print(F(UPRIGHT_BUILD_ID));
    Serial.print(F(" hash="));
    Serial.print(F(UPRIGHT_BUILD_HASH));
    Serial.print(F(" runtime="));
    Serial.print(F(UPRIGHT_RUNTIME_VERSION));
    Serial.print(F(" tune="));
    Serial.println(F(UPRIGHT_TUNE_VERSION));
    return;
  }

  if (strcmp(line, "ARM") == 0) {
    if (g_state.active_fault != FAULT_NONE) {
      Serial.println(F("ERR FAULT_LATCHED"));
      return;
    }
#if FEAT_AUTORUN_CMD || FEAT_BOOT_AUTORUN
    g_autorun_pending = false;
#endif
    startArmedRun();
    Serial.println(F("OK ARM"));
    return;
  }

  if (strcmp(line, "DISARM") == 0) {
    g_state.armed = false;
    g_arm_enter_ms = 0;
#if FEAT_AUTORUN_CMD || FEAT_BOOT_AUTORUN
    g_autorun_pending = false;
#endif
    g_out = 0.0f;
    resetMotionState();
    applyMotorOutput(0.0f);
    Serial.println(F("OK DISARM"));
    return;
  }

#if FEAT_AUTORUN_CMD
  if (strcmp(line, "AUTORUN STATUS") == 0) {
    Serial.print(F("OK AUTORUN pending="));
    Serial.print(g_autorun_pending ? 1 : 0);
    Serial.print(F(" due_ms="));
    if (g_autorun_pending) {
      uint32_t now_ms = millis();
      if (g_autorun_due_ms > now_ms) Serial.println(g_autorun_due_ms - now_ms);
      else Serial.println(0);
    } else {
      Serial.println(0);
    }
    return;
  }

  int autorun_v;
  if (parseCommandInt(line, "AUTORUN", &autorun_v)) {
    if (g_state.active_fault != FAULT_NONE) {
      Serial.println(F("ERR AUTORUN fault_latched"));
      return;
    }
    if (autorun_v < 0) autorun_v = 0;
    if (autorun_v > static_cast<int>(AUTORUN_DELAY_MAX_MS)) autorun_v = AUTORUN_DELAY_MAX_MS;
    g_cfg.autorun_delay_ms = static_cast<uint16_t>(autorun_v);
    cfgSanitize();
    g_state.armed = false;
    g_arm_enter_ms = 0;
    g_out = 0.0f;
    applyMotorOutput(0.0f);
    g_autorun_pending = true;
    g_autorun_due_ms = millis() + static_cast<uint32_t>(autorun_v);
    Serial.print(F("OK AUTORUN delay_ms="));
    Serial.println(autorun_v);
    return;
  }
#endif

  if (strcmp(line, "FAULTCLR") == 0) {
    clearFault();
    Serial.println(F("OK FAULTCLR"));
    return;
  }

  int estop_v;
  if (parseCommandInt(line, "ESTOP", &estop_v)) {
    if (estop_v != 0) {
      g_state.estop_latched = true;
      g_state.armed = false;
      g_out = 0.0f;
      applyMotorOutput(0.0f);
      if (g_state.active_fault == FAULT_NONE) g_state.active_fault = FAULT_ESTOP_LATCH_CODE;
    } else {
      if (g_state.active_fault == FAULT_ESTOP_LATCH_CODE) {
        g_state.active_fault = FAULT_NONE;
        g_state.estop_latched = false;
      } else if (g_state.active_fault == FAULT_NONE) {
        g_state.estop_latched = false;
      } else {
        Serial.println(F("ERR FAULT_LATCHED"));
        return;
      }
    }
    Serial.println(F("OK ESTOP"));
    return;
  }

  if (strcmp(line, "SAVECFG") == 0) {
    cfgSave();
    Serial.println(F("OK SAVECFG"));
    return;
  }

  if (strcmp(line, "LOADCFG") == 0) {
    if (cfgLoad()) {
      Serial.println(F("OK LOADCFG"));
    } else {
      Serial.println(F("ERR LOADCFG"));
    }
    return;
  }

  if (strcmp(line, "DEFAULTCFG") == 0) {
    cfgDefaults();
    cfgSave();
    Serial.println(F("OK DEFAULTCFG"));
    return;
  }

  if (strcmp(line, "CAL ZERO") == 0) {
    runCalZero();
    return;
  }

  if (strcmp(line, "IMU CAL") == 0) {
    runImuCal();
    return;
  }
  if (strcmp(line, "IMU LOAD") == 0) {
    runImuLoad();
    return;
  }
  if (strcmp(line, "IMU SAVE") == 0) {
    runImuSave();
    return;
  }
  if (strcmp(line, "IMU INFO") == 0) {
    runImuInfo();
    return;
  }

  if (strcmp(line, "TRIMCLR") == 0) {
    g_cfg.autotrim_trim_deg = 0.0f;
    cfgSanitize();
    Serial.println(F("OK TRIMCLR"));
    return;
  }

  bool parsed_tune_cmd =
    parsePID(line) ||
    parseSetpoint(line) ||
    parseLimits(line) ||
    parseMotion(line) ||
    parseSlew(line) ||
    parseRamp(line) ||
    parseMotionCfg(line) ||
    parseGsched(line) ||
    parseDcfg(line) ||
    parseAutotrim(line) ||
    parseTrimcfg(line) ||
    parseTrimlims(line);
  if (parsed_tune_cmd) {
    return;
  }

  Serial.print(F("ERR UNKNOWN "));
  Serial.println(line);
}

static void serviceSerial() {
  while (Serial.available() > 0) {
    char c = static_cast<char>(Serial.read());
    if (c == '\r') continue;

    if (c == '\n') {
      g_cmd_buf[g_cmd_len] = '\0';
      handleCommandLine(g_cmd_buf);
      g_cmd_len = 0;
      continue;
    }

    if (static_cast<uint8_t>(c) < 32 || static_cast<uint8_t>(c) > 126) {
      continue;
    }

    if (g_cmd_len + 1 < sizeof(g_cmd_buf)) {
      g_cmd_buf[g_cmd_len++] = c;
    } else {
      g_cmd_len = 0;
      Serial.println(F("ERR CMDLEN"));
    }
  }
}

static void controlTick() {
  uint32_t step_start = micros();

  if (!g_imu_ok) {
    latchFault(FAULT_SENSOR_INVALID, NOTE_IMU_NOT_READY, F("imu_not_ready"));
  } else {
    g_mpu.update();
    g_raw = readAccelDeg();
    g_state.gyro_dps = readGyroDps();

    if (!isFinitef(g_raw) || !isFinitef(g_state.gyro_dps) || fabs(g_state.gyro_dps) > 2200.0f || fabs(g_raw) > 180.0f) {
      latchFault(FAULT_SENSOR_INVALID, NOTE_SENSOR_INVALID, F("sensor_invalid"));
    }

    kalmanUpdate(g_raw, g_state.gyro_dps, DT_S);
    g_state.angle_deg = (g_cfg.imu_polarity * g_kf_angle) - g_cfg.angle_zero_deg;

    if (!isFinitef(g_state.angle_deg)) {
      latchFault(FAULT_SENSOR_INVALID, NOTE_ANGLE_INVALID, F("angle_invalid"));
    }
  }

  g_vol_raw = analogRead(Pins::VOL);

  long l_now, r_now;
  noInterrupts();
  l_now = g_enc_l;
  r_now = g_enc_r;
  interrupts();

  long dL = l_now - g_prev_enc_l;
  long dR = r_now - g_prev_enc_r;
  g_prev_enc_l = l_now;
  g_prev_enc_r = r_now;

  if (dL != 0 || dR != 0) {
    g_last_moving_enc_ms = millis();
  }

  const float wheel_delta = 0.5f * static_cast<float>(dL + dR);
  g_wdelta_tick_counts = wheel_delta;
  g_wdelta_counts = wheel_delta;
  g_wspd_counts = wheel_delta / DT_S;
  g_wpos_unclamped_counts += wheel_delta;
  g_wpos_raw_counts = g_wpos_unclamped_counts;

  if (g_state.armed && !g_state.estop_latched && g_state.active_fault == FAULT_NONE) {
    if (fabs(g_state.angle_deg) > g_cfg.tip_deg) {
      latchFault(FAULT_MODULE_UNHEALTHY, NOTE_TIP_LIMIT, F("tip_limit"));
    } else {
      float motion_term_deg = 0.0f;
      if (fabs(g_state.angle_deg) <= g_cfg.motion_angle_gate_deg) {
        const float wpos_err = g_wpos_target_counts - g_wpos_unclamped_counts;
        motion_term_deg = (g_cfg.kx * wpos_err) - (g_cfg.kv * g_wspd_counts);
        motion_term_deg = clampf(motion_term_deg, -g_cfg.motion_term_max_deg, g_cfg.motion_term_max_deg);
      }

      g_set_eff_deg = clampf(g_cfg.set_deg + g_cfg.autotrim_trim_deg, -30.0f, 30.0f);
      float set_cmd_deg = clampf(g_set_eff_deg + motion_term_deg, -30.0f, 30.0f);
      g_pid_err = set_cmd_deg - g_state.angle_deg;

      const float err_abs = fabs(g_pid_err);
      float sched = 0.0f;
      if (err_abs > g_cfg.sched_err_deg) {
        const float span = max(0.5f, g_cfg.tip_deg - g_cfg.sched_err_deg);
        sched = clampf((err_abs - g_cfg.sched_err_deg) / span, 0.0f, 1.0f);
      }
      g_sched_scale = 1.0f + (g_cfg.sched_boost * sched);

      g_pid_p = (g_cfg.kp * g_sched_scale) * g_pid_err;

      g_d_unfilt = (g_pid_err - g_prev_err) * (1.0f / DT_S);
      g_d_alpha = alphaFromCutoffHz(g_cfg.d_cutoff_hz, DT_S);
      if (!g_d_init) {
        g_d_filt = g_d_unfilt;
        g_d_init = true;
      } else {
        g_d_filt = lowPass(g_d_unfilt, g_d_filt, g_d_alpha);
      }
      const float kd_scale = 1.0f + (0.50f * g_cfg.sched_boost * sched);
      g_pid_d = (g_cfg.kd * kd_scale) * g_d_filt;

      bool pushing_sat = g_output_saturated &&
        ((g_pid_err > 0.0f && g_pid_u_unsat > g_cfg.out_max) ||
         (g_pid_err < 0.0f && g_pid_u_unsat < -g_cfg.out_max));

      if (!g_conditional_i || !pushing_sat) {
        g_i_state += g_pid_err * DT_S;
      }

      g_i_state = clampf(g_i_state, -g_cfg.i_max, g_cfg.i_max);
      g_pid_i = g_cfg.ki * g_i_state;
      g_pid_i = clampf(g_pid_i, -g_cfg.i_term_max, g_cfg.i_term_max);

      g_pid_u_unsat = g_pid_p + g_pid_i + g_pid_d;
      g_pid_u_sat = clampf(g_pid_u_unsat, -g_cfg.out_max, g_cfg.out_max);
      g_output_saturated = (fabs(g_pid_u_unsat - g_pid_u_sat) > 0.001f);

      g_i_state += g_cfg.kaw * (g_pid_u_sat - g_pid_u_unsat) * DT_S;
      g_i_state = clampf(g_i_state, -g_cfg.i_max, g_cfg.i_max);

      float max_step = g_cfg.out_slew_per_s * DT_S;
      float target_out = g_pid_u_sat;
      if (g_arm_enter_ms > 0U) {
        const uint32_t arm_dt_ms = millis() - g_arm_enter_ms;
        if (arm_dt_ms < g_cfg.arm_engage_ramp_ms) {
          const float ramp = clampf(
            static_cast<float>(arm_dt_ms) / static_cast<float>(max(1, static_cast<int>(g_cfg.arm_engage_ramp_ms))),
            0.0f,
            1.0f
          );
          const float ramp_limit = max(8.0f, g_cfg.out_max * ramp);
          target_out = clampf(target_out, -ramp_limit, ramp_limit);
        }
      }

      float out_err = target_out - g_out;
      if (out_err > max_step) out_err = max_step;
      if (out_err < -max_step) out_err = -max_step;
      g_out += out_err;
      g_state.output_cmd = g_out;
      applyMotorOutput(g_out);
      g_prev_err = g_pid_err;

      uint32_t now_ms = millis();
      const bool trim_gate = (g_arm_enter_ms > 0U)
        && ((now_ms - g_arm_enter_ms) > 1200U)
        && !g_output_saturated
        && (fabs(g_state.angle_deg) < g_cfg.autotrim_angle_gate_deg)
        && (fabs(g_state.gyro_dps) < g_cfg.autotrim_gyro_gate_dps)
        && (fabs(g_wspd_counts) < g_cfg.autotrim_wspd_gate_counts)
        && (fabs(g_out) < (g_cfg.autotrim_out_frac_gate * g_cfg.out_max));

      if (trim_gate) {
        if (g_trim_stable_ticks < 60000U) g_trim_stable_ticks++;
      } else if (g_trim_stable_ticks > 0U) {
        g_trim_stable_ticks--;
      }

      if (g_cfg.autotrim_enabled && g_trim_stable_ticks > 250U) {
        const float wpos_err = g_wpos_target_counts - g_wpos_unclamped_counts;
        const float pos_trim_term_deg = clampf((0.004f + 5.0f * g_cfg.kx) * wpos_err, -1.5f, 1.5f);
        const float err_to_trim = (g_state.angle_deg - g_set_eff_deg) + pos_trim_term_deg;
        if (fabs(err_to_trim) > g_cfg.autotrim_err_deadband_deg) {
          const float max_trim_step = g_cfg.autotrim_step_max_deg_per_s * DT_S;
          const float trim_step = clampf(err_to_trim, -max_trim_step, max_trim_step);
          g_cfg.autotrim_trim_deg = clampf(
            g_cfg.autotrim_trim_deg + trim_step,
            -g_cfg.autotrim_trim_max_deg,
            g_cfg.autotrim_trim_max_deg
          );
        }
      }
      bool arm_grace_elapsed = (g_arm_enter_ms > 0U)
        ? ((now_ms - g_arm_enter_ms) > ENCODER_STALE_ARM_GRACE_MS)
        : true;
      if (
        arm_grace_elapsed
        && fabs(g_out) > ENCODER_STALE_OUT_MIN
        && (now_ms - g_last_moving_enc_ms) > ENCODER_STALE_TIMEOUT_MS
      ) {
        latchFault(FAULT_ENCODER_STALE, NOTE_ENCODER_STALE, F("encoder_stale"));
      }
    }
  } else {
    g_out = 0.0f;
    g_state.output_cmd = 0.0f;
    g_pid_err = 0.0f;
    g_pid_p = 0.0f;
    g_pid_i = 0.0f;
    g_pid_d = 0.0f;
    g_pid_u_unsat = 0.0f;
    g_pid_u_sat = 0.0f;
    g_output_saturated = false;
    resetMotionState();
    applyMotorOutput(0.0f);
  }

  float a_norm = fabs(g_state.angle_deg) / max(1.0f, g_cfg.tip_deg);
  float o_norm = fabs(g_out) / max(1.0f, g_cfg.out_max);
  g_runaway_score = 0.7f * a_norm + 0.3f * o_norm;

  g_last_step_us = micros() - step_start;
  uint32_t now_ms_for_overrun = millis();
  bool overrun_grace_elapsed = (g_arm_enter_ms > 0U)
    ? ((now_ms_for_overrun - g_arm_enter_ms) > LOOP_OVERRUN_ARM_GRACE_MS)
    : true;

  if (g_last_step_us > MAX_CONTROL_STEP_US) {
    g_state.loop_overrun_count++;
    if (!g_state.armed || g_state.estop_latched || overrun_grace_elapsed) {
      g_loop_overrun_consecutive++;
    }
    if (
      LOOP_OVERRUN_LATCH_ENABLED
      && (g_loop_overrun_consecutive >= LOOP_OVERRUN_CONSEC_LIMIT)
    ) {
      latchFault(FAULT_LOOP_OVERRUN, NOTE_LOOP_OVERRUN, F("loop_overrun"));
    }
  } else {
    g_loop_overrun_consecutive = 0;
  }
}

void setup() {
  Serial.begin(115200);
  delay(120);
  Serial.println(F("UPRIGHT_BALANCE_MVP_V2_CORE_BOOT"));

  cfgDefaults();
  if (cfgLoad()) {
    Serial.println(F("CFG loaded"));
  } else {
    Serial.println(F("CFG defaults"));
    cfgSave();
  }

  pinMode(Pins::LED, OUTPUT);
  digitalWrite(Pins::LED, LOW);

  pinMode(Pins::ENC_LEFT, INPUT_PULLUP);
  pinMode(Pins::ENC_RIGHT, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(Pins::ENC_LEFT), isrEncLeft, CHANGE);
  g_prev_port_d = PIND;
  PCICR |= _BV(PCIE2);
  PCMSK2 |= _BV(PCINT20);

  pinMode(Pins::AIN1, OUTPUT);
  pinMode(Pins::BIN1, OUTPUT);
  pinMode(Pins::STBY, OUTPUT);
  pinMode(Pins::PWMA, OUTPUT);
  pinMode(Pins::PWMB, OUTPUT);
  pinMode(Pins::VOL, INPUT);
  motorStop();

  Wire.begin();
  byte imu_status = g_mpu.begin();
  Serial.print(F("MPU6050 status="));
  Serial.println(imu_status);
  if (imu_status == 0) {
    delay(500);
    ImuCalV1 imu_cal;
    if (imuCalLoad(&imu_cal)) {
      imuCalApply(imu_cal);
      g_imu_cal_loaded = true;
      Serial.println(F("IMU offsets loaded"));
    } else {
      g_mpu.calcOffsets();
      imuCalSaveFromCurrent(nullptr);
      g_imu_cal_loaded = true;
      Serial.println(F("IMU offsets auto-calibrated"));
    }
    g_mpu.update();
    g_raw = readAccelDeg();
    resetEstimatorToCurrentAccel();
    g_imu_ok = true;
  } else {
    g_imu_ok = false;
    g_imu_cal_loaded = false;
    latchFault(FAULT_SENSOR_INVALID, NOTE_IMU_BEGIN_FAILED, F("imu_begin_failed"));
  }

  g_last_moving_enc_ms = millis();
  g_next_tick_us = micros() + LOOP_PERIOD_US;
  g_last_tick_us = micros();
  g_last_status_ms = millis();

#if FEAT_AUTORUN_CMD || FEAT_BOOT_AUTORUN
  g_autorun_pending = true;
  g_autorun_due_ms = millis() + static_cast<uint32_t>(g_cfg.autorun_delay_ms);
  Serial.print(F("OK AUTORUN BOOT delay_ms="));
  Serial.println(g_cfg.autorun_delay_ms);
#endif

  printHelp();
  emitStatus();
}

void loop() {
  serviceSerial();

#if FEAT_AUTORUN_CMD || FEAT_BOOT_AUTORUN
  if (g_autorun_pending) {
    uint32_t now_ms = millis();
    if (static_cast<int32_t>(now_ms - g_autorun_due_ms) >= 0) {
      g_autorun_pending = false;
      if (!g_state.armed && g_state.active_fault == FAULT_NONE) {
        startArmedRun();
        Serial.println(F("OK AUTORUN ARM"));
      } else if (g_state.active_fault != FAULT_NONE) {
        Serial.println(F("ERR AUTORUN fault_latched"));
      }
    }
  }
#endif

  uint32_t now_us = micros();
  if (static_cast<int32_t>(now_us - g_next_tick_us) >= 0) {
    g_last_tick_us = now_us;

    controlTick();

    g_next_tick_us += LOOP_PERIOD_US;
    if (static_cast<int32_t>(now_us - g_next_tick_us) >= 0) {
      uint32_t behind = now_us - g_next_tick_us;
      uint32_t missed = (behind / LOOP_PERIOD_US) + 1U;
      g_loop_missed += missed;
      g_next_tick_us += missed * LOOP_PERIOD_US;
    }
  }

  uint32_t now_ms = millis();
  if (now_ms - g_last_status_ms >= STATUS_PERIOD_MS) {
    g_last_status_ms = now_ms;
    digitalWrite(Pins::LED, !digitalRead(Pins::LED));
  }
}
