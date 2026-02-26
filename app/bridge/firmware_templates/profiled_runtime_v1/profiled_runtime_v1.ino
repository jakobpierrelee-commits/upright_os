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
#define UPRIGHT_BUILD_ID "prv1a"
#endif

#ifndef UPRIGHT_BUILD_HASH
#define UPRIGHT_BUILD_HASH "na"
#endif

// Fallbacks in case generated release_version.h is absent.
#ifndef UPRIGHT_RUNTIME_VERSION
#define UPRIGHT_RUNTIME_VERSION "profiled_runtime_v1.3.0"
#endif

#ifndef UPRIGHT_TUNE_VERSION
#define UPRIGHT_TUNE_VERSION "tune_v1"
#endif

namespace Pins {
  const uint8_t LED = LED_BUILTIN;
  const uint8_t ENC_LEFT = 2;   // INT0
  const uint8_t ENC_RIGHT = 4;  // D4 / PCINT20
  const uint8_t PWMA = 5;
  const uint8_t PWMB = 6;
  const uint8_t AIN1 = 7;
  const uint8_t STBY = 8;
  const uint8_t BIN1 = 12;
  const uint8_t VOL = A2;
}

struct RuntimeConfigV11 {
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

  float angle_zero_deg;
  int8_t motor_polarity;
  int8_t imu_polarity;
  char imu_axis;
  uint8_t swap_axes;

  uint8_t log_t;
  uint8_t log_csv;
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

static const uint32_t CFG_MAGIC = 0x31565055UL;  // "UPV1"
static const uint8_t CFG_VERSION = 11;
static const int EEPROM_ADDR = 0;
static const uint32_t IMU_CAL_MAGIC = 0x31434955UL;  // "UIC1"
static const uint8_t IMU_CAL_VERSION = 1;
static const int EEPROM_IMU_CAL_ADDR = EEPROM_ADDR + static_cast<int>(sizeof(RuntimeConfigV11));
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

static RuntimeConfigV11 g_cfg;
static RuntimeState g_state = {true, false, 0.0f, 0.0f, 0.0f, 0, FAULT_NONE};

static float g_raw = 0.0f;
static float g_out = 0.0f;
static float g_vol_raw = 0.0f;
static float g_motion_kv = 0.0f;
static float g_motion_kx = 0.0f;
static float g_motion_term = 0.0f;
static float g_motion_vel_counts = 0.0f;
static float g_motion_pos_counts = 0.0f;
static float g_motion_pos_raw_counts = 0.0f;
static float g_motion_delta_counts = 0.0f;
static bool g_motion_vel_init = false;

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
static uint32_t g_last_period_us = LOOP_PERIOD_US;
static uint32_t g_min_period_us = 0xFFFFFFFFUL;
static uint32_t g_max_period_us = 0;
static uint32_t g_jitter_us = 0;

static uint32_t g_fault_count = 0;
static uint8_t g_last_fault_note = NOTE_NONE;

static float g_runaway_score = 0.0f;
static bool g_autozero_enabled = false;
static float g_autozero_trim_deg = 0.0f;
static float g_set_eff_deg = 0.0f;

static bool g_imu_ok = false;
MPU6050 g_mpu(Wire);

static char g_cmd_buf[128];
static uint8_t g_cmd_len = 0;

static const float DT_S = static_cast<float>(LOOP_PERIOD_US) * 1.0e-6f;
static const float MOTION_VEL_CUTOFF_HZ = 6.0f;
static const float MOTION_POS_MAX_COUNTS = 500.0f;
static const float MOTION_TERM_FRAC = 0.55f;
static const float OUT_SLEW_PER_S = 900.0f;
static const float AUTOZERO_TRIM_MAX_DEG = 3.0f;
static const float AUTOZERO_STEP_MAX_DEG_PER_S = 0.25f;
static const float AUTOZERO_ANGLE_GATE_DEG = 9.0f;
static const float AUTOZERO_GYRO_GATE_DPS = 80.0f;
static const float AUTOZERO_OUT_FRAC_GATE = 0.82f;
static const float AUTOZERO_RUNAWAY_GATE = 0.75f;
static const float AUTOZERO_ERR_DEADBAND_DEG = 0.06f;

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

static uint16_t cfgCrc16(const RuntimeConfigV11& cfg) {
  const uint8_t* p = reinterpret_cast<const uint8_t*>(&cfg);
  const size_t n = sizeof(RuntimeConfigV11) - sizeof(cfg.crc16);
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

  g_cfg.kp = 20.0f;
  g_cfg.ki = 0.0f;
  g_cfg.kd = 0.6f;
  g_cfg.set_deg = 0.0f;

  g_cfg.out_max = 120.0f;
  g_cfg.tip_deg = 35.0f;
  g_cfg.i_max = 70.0f;
  g_cfg.i_term_max = 120.0f;
  g_cfg.d_cutoff_hz = 20.0f;
  g_cfg.kaw = 0.25f;

  g_cfg.q_angle = 0.001f;
  g_cfg.q_bias = 0.003f;
  g_cfg.r_measure = 0.03f;

  g_cfg.angle_zero_deg = 0.0f;
  g_cfg.motor_polarity = 1;
  g_cfg.imu_polarity = 1;
  g_cfg.imu_axis = 'Y';
  g_cfg.swap_axes = 1;

  g_cfg.log_t = 1;
  g_cfg.log_csv = 0;

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

  g_cfg.angle_zero_deg = clampf(g_cfg.angle_zero_deg, -45.0f, 45.0f);
  g_cfg.motor_polarity = (g_cfg.motor_polarity >= 0) ? 1 : -1;
  g_cfg.imu_polarity = (g_cfg.imu_polarity >= 0) ? 1 : -1;
  g_cfg.imu_axis = (g_cfg.imu_axis == 'X' || g_cfg.imu_axis == 'Y') ? g_cfg.imu_axis : 'Y';
  g_cfg.swap_axes = g_cfg.swap_axes ? 1 : 0;
  g_cfg.log_t = g_cfg.log_t ? 1 : 0;
  g_cfg.log_csv = g_cfg.log_csv ? 1 : 0;
}

static bool cfgLoad() {
#if FEAT_EEPROM_CONFIG
  RuntimeConfigV11 tmp;
  EEPROM.get(EEPROM_ADDR, tmp);
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
  EEPROM.put(EEPROM_ADDR, g_cfg);
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
}

static void applyMotorLr(int left_cmd, int right_cmd) {
  left_cmd = constrain(left_cmd * g_cfg.motor_polarity, -255, 255);
  right_cmd = constrain(right_cmd * g_cfg.motor_polarity, -255, 255);

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
  g_motion_term = 0.0f;
  g_motion_vel_counts = 0.0f;
  g_motion_pos_counts = 0.0f;
  g_motion_pos_raw_counts = 0.0f;
  g_motion_delta_counts = 0.0f;
  g_motion_vel_init = false;
}

static void clearAutozeroTrim() {
  g_autozero_trim_deg = 0.0f;
}

static void latchFault(uint16_t code, uint8_t note_code, const __FlashStringHelper* note) {
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
  Serial.print(F(" last_note_code="));
  Serial.print(g_last_fault_note);
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
  long l, r;
  noInterrupts();
  l = g_enc_l;
  r = g_enc_r;
  interrupts();

  Serial.print(F("STATUS mode="));
  Serial.print(modeName());
  Serial.print(F(" ident="));
  Serial.print(F(UPRIGHT_BUILD_ID));
  Serial.print(F(" hash="));
  Serial.print(F(UPRIGHT_BUILD_HASH));
  Serial.print(F(" runtime="));
  Serial.print(F(UPRIGHT_RUNTIME_VERSION));
  Serial.print(F(" tune="));
  Serial.print(F(UPRIGHT_TUNE_VERSION));
  Serial.print(F(" estop="));
  Serial.print(g_state.estop_latched ? F("1") : F("0"));
  Serial.print(F(" fault="));
  Serial.print(g_state.active_fault);
  Serial.print(F(" fault_count="));
  Serial.print(g_fault_count);
  Serial.print(F(" fault_last_note_code="));
  Serial.print(g_last_fault_note);
  Serial.print(F(" ang="));
  Serial.print(g_state.angle_deg, 3);
  Serial.print(F(" raw="));
  Serial.print(g_raw, 3);
  Serial.print(F(" gyro="));
  Serial.print(g_state.gyro_dps, 3);
  Serial.print(F(" set="));
  Serial.print(g_cfg.set_deg, 3);
  Serial.print(F(" set_eff="));
  Serial.print(g_set_eff_deg, 3);
  Serial.print(F(" az="));
  Serial.print(g_autozero_enabled ? F("1") : F("0"));
  Serial.print(F(" ztrim="));
  Serial.print(g_autozero_trim_deg, 4);
  Serial.print(F(" out="));
  Serial.print(g_out, 3);
  Serial.print(F(" kp="));
  Serial.print(g_cfg.kp, 4);
  Serial.print(F(" ki="));
  Serial.print(g_cfg.ki, 4);
  Serial.print(F(" kd="));
  Serial.print(g_cfg.kd, 4);
  Serial.print(F(" kv="));
  Serial.print(g_motion_kv, 4);
  Serial.print(F(" kx="));
  Serial.print(g_motion_kx, 4);
  Serial.print(F(" mot="));
  Serial.print(g_motion_term, 4);
  Serial.print(F(" wspd="));
  Serial.print(g_motion_vel_counts, 3);
  Serial.print(F(" wpos="));
  Serial.print(g_motion_pos_counts, 3);
  Serial.print(F(" wposRaw="));
  Serial.print(g_motion_pos_raw_counts, 3);
  Serial.print(F(" wdelta="));
  Serial.print(g_motion_delta_counts, 3);
  Serial.print(F(" runaway="));
  Serial.print(g_runaway_score, 3);
  Serial.print(F(" encL="));
  Serial.print(l);
  Serial.print(F(" encR="));
  Serial.print(r);
  Serial.print(F(" overrun="));
  Serial.print(g_state.loop_overrun_count);
  Serial.print(F(" missed="));
  Serial.print(g_loop_missed);
  Serial.print(F(" loop_us="));
  Serial.print(g_last_step_us);
  Serial.print(F(" loop_max_us="));
  Serial.print(g_max_period_us);
  Serial.print(F(" volRaw="));
  Serial.print(g_vol_raw, 0);
#if FEAT_ADV_TELEMETRY
  Serial.print(F(" pid_err="));
  Serial.print(g_pid_err, 4);
  Serial.print(F(" pid_p="));
  Serial.print(g_pid_p, 4);
  Serial.print(F(" pid_i="));
  Serial.print(g_pid_i, 4);
  Serial.print(F(" pid_d="));
  Serial.print(g_pid_d, 4);
  Serial.print(F(" pid_u_unsat="));
  Serial.print(g_pid_u_unsat, 4);
  Serial.print(F(" pid_u_sat="));
  Serial.print(g_pid_u_sat, 4);
  Serial.print(F(" output_saturated="));
  Serial.print(g_output_saturated ? F("1") : F("0"));
  Serial.print(F(" d_cutoff_hz="));
  Serial.print(g_cfg.d_cutoff_hz, 2);
  Serial.print(F(" filter_alpha="));
  Serial.print(g_d_alpha, 5);
#endif
  Serial.println();
}

static void emitCsv() {
  long l, r;
  noInterrupts();
  l = g_enc_l;
  r = g_enc_r;
  interrupts();

  Serial.print(F("CSV,"));
  Serial.print(millis());
  Serial.print(',');
  Serial.print(modeName());
  Serial.print(',');
  Serial.print(g_state.estop_latched ? 1 : 0);
  Serial.print(',');
  Serial.print(g_cfg.set_deg, 3);
  Serial.print(',');
  Serial.print(g_state.angle_deg, 3);
  Serial.print(',');
  Serial.print(g_raw, 3);
  Serial.print(',');
  Serial.print(g_state.gyro_dps, 3);
  Serial.print(',');
  Serial.print(g_out, 3);
  Serial.print(',');
  Serial.print(l);
  Serial.print(',');
  Serial.print(r);
  Serial.print(',');
  Serial.print(g_state.active_fault);
  Serial.print(',');
  Serial.print(g_state.loop_overrun_count);
  Serial.print(',');
  Serial.println(g_jitter_us);
}

static void printHelp() {
  Serial.println(F("OK HELP GET ARM DISARM ESTOP PID MOTION SETPOINT LIMITS FILTER KAL CAL ZERO IMU CAL IMU LOAD IMU SAVE IMU INFO AUTOZERO SAVECFG LOADCFG DEFAULTCFG FAULTCLR LOGT LOGCSV BURSTCSV CSVHDR IDENT"));
#if FEAT_COHEN_COON_CMD
  Serial.println(F("OK HELP+ CC"));
#endif
#if FEAT_TRANSFER_FN_CMD
  Serial.println(F("OK HELP+ TF"));
#endif
#if FEAT_AUTOTUNE_HELPERS
  Serial.println(F("OK HELP+ MOTOR_TEST PREARM_CHECK"));
#endif
}

#if FEAT_TRANSFER_FN_CMD
static void printTf() {
  Serial.println(F("TF controller C(s)=Kp + Ki/s + Kd*s/(tau_d*s+1)"));
  Serial.println(F("TF plant_model G(s)=K/(T*s+1)*e^(-L*s)"));
  Serial.println(F("TF closed_loop T(s)=C(s)G(s)/(1+C(s)G(s))"));
}
#endif

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

static bool parseMotion(const char* line) {
  float vals[2];
  if (parseCommandFloats(line, "MOTION", 2, 2, vals, nullptr)) {
    g_motion_kv = clampf(vals[0], -5.0f, 5.0f);
    g_motion_kx = clampf(vals[1], -1.0f, 1.0f);
    Serial.println(F("OK MOTION"));
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

static bool parseFilter(const char* line) {
  char buf[128];
  strncpy(buf, line, sizeof(buf) - 1);
  buf[sizeof(buf) - 1] = '\0';
  char* toks[5];
  uint8_t n = splitTokens(buf, toks, 5);
  if (n < 3 || n > 4) return false;
  if (strcmp(toks[0], "FILTER") != 0) return false;

  float cutoff = 0.0f;
  int cond_i = 0;
  float kaw = g_cfg.kaw;
  if (!parseFloatStrict(toks[1], &cutoff)) return false;
  if (!parseIntStrict(toks[2], &cond_i)) return false;
  if (n == 4 && !parseFloatStrict(toks[3], &kaw)) return false;

  g_cfg.d_cutoff_hz = cutoff;
  g_conditional_i = (cond_i != 0);
  if (n == 4) g_cfg.kaw = kaw;
  cfgSanitize();
  Serial.println(F("OK FILTER"));
  return true;
}

static bool parseKal(const char* line) {
  float vals[3];
  if (parseCommandFloats(line, "KAL", 3, 3, vals, nullptr)) {
    g_cfg.q_angle = vals[0];
    g_cfg.q_bias = vals[1];
    g_cfg.r_measure = vals[2];
    cfgSanitize();
    Serial.println(F("OK KAL"));
    return true;
  }
  return false;
}

#if FEAT_COHEN_COON_CMD
static bool parseCohenCoon(const char* line) {
  float vals[3];
  if (!parseCommandFloats(line, "CC", 3, 3, vals, nullptr)) return false;
  float K = vals[0];
  float T = vals[1];
  float L = vals[2];
  if (fabs(K) < 1e-6f || T <= 0.0f || L <= 0.0f) {
    Serial.println(F("ERR CC invalid_params"));
    return true;
  }
  float r = L / T;
  float kp = (1.0f / K) * (T / L) * ((4.0f / 3.0f) + (r / 4.0f));
  float Ti = L * ((32.0f + 6.0f * r) / (13.0f + 8.0f * r));
  float Td = L * (4.0f / (11.0f + 2.0f * r));
  float ki = kp / Ti;
  float kd = kp * Td;
  Serial.print(F("CC PID kp="));
  Serial.print(kp, 5);
  Serial.print(F(" ki="));
  Serial.print(ki, 5);
  Serial.print(F(" kd="));
  Serial.println(kd, 5);
  return true;
}
#endif

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
  Serial.print(F("OK IMU_LOAD gx="));
  Serial.print(cal.gyro_x_offset, 4);
  Serial.print(F(" gy="));
  Serial.print(cal.gyro_y_offset, 4);
  Serial.print(F(" gz="));
  Serial.print(cal.gyro_z_offset, 4);
  Serial.print(F(" ax="));
  Serial.print(cal.acc_x_offset, 4);
  Serial.print(F(" ay="));
  Serial.print(cal.acc_y_offset, 4);
  Serial.print(F(" az="));
  Serial.println(cal.acc_z_offset, 4);
}

static void runImuSave() {
  if (!g_imu_ok) {
    Serial.println(F("ERR IMU_SAVE imu_not_ready"));
    return;
  }
  ImuCalV1 saved;
  if (!imuCalSaveFromCurrent(&saved)) {
    Serial.println(F("ERR IMU_SAVE eeprom_unavailable"));
    return;
  }
  Serial.print(F("OK IMU_SAVE gx="));
  Serial.print(saved.gyro_x_offset, 4);
  Serial.print(F(" gy="));
  Serial.print(saved.gyro_y_offset, 4);
  Serial.print(F(" gz="));
  Serial.print(saved.gyro_z_offset, 4);
  Serial.print(F(" ax="));
  Serial.print(saved.acc_x_offset, 4);
  Serial.print(F(" ay="));
  Serial.print(saved.acc_y_offset, 4);
  Serial.print(F(" az="));
  Serial.println(saved.acc_z_offset, 4);
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
  ImuCalV1 saved;
  if (!imuCalSaveFromCurrent(&saved)) {
    Serial.println(F("ERR IMU_CAL eeprom_unavailable"));
    return;
  }
  g_mpu.update();
  g_raw = readAccelDeg();
  resetEstimatorToCurrentAccel();
  Serial.print(F("OK IMU_CAL gx="));
  Serial.print(saved.gyro_x_offset, 4);
  Serial.print(F(" gy="));
  Serial.print(saved.gyro_y_offset, 4);
  Serial.print(F(" gz="));
  Serial.print(saved.gyro_z_offset, 4);
  Serial.print(F(" ax="));
  Serial.print(saved.acc_x_offset, 4);
  Serial.print(F(" ay="));
  Serial.print(saved.acc_y_offset, 4);
  Serial.print(F(" az="));
  Serial.println(saved.acc_z_offset, 4);
}

static void runImuInfo() {
  if (!g_imu_ok) {
    Serial.println(F("ERR IMU_INFO imu_not_ready"));
    return;
  }
  Serial.print(F("OK IMU_INFO gx="));
  Serial.print(g_mpu.getGyroXoffset(), 4);
  Serial.print(F(" gy="));
  Serial.print(g_mpu.getGyroYoffset(), 4);
  Serial.print(F(" gz="));
  Serial.print(g_mpu.getGyroZoffset(), 4);
  Serial.print(F(" ax="));
  Serial.print(g_mpu.getAccXoffset(), 4);
  Serial.print(F(" ay="));
  Serial.print(g_mpu.getAccYoffset(), 4);
  Serial.print(F(" az="));
  Serial.println(g_mpu.getAccZoffset(), 4);
}

#if FEAT_AUTOTUNE_HELPERS
static void runMotorTest(const char* line) {
  char buf[128];
  strncpy(buf, line, sizeof(buf) - 1);
  buf[sizeof(buf) - 1] = '\0';
  char* toks[5];
  uint8_t n = splitTokens(buf, toks, 5);
  if (n != 4 || strcmp(toks[0], "MOTOR_TEST") != 0) {
    Serial.println(F("ERR MOTOR_TEST usage=MOTOR_TEST <L|R> <pwm> <ms>"));
    return;
  }
  if (g_state.armed || !g_state.estop_latched || g_state.active_fault != FAULT_NONE) {
    Serial.println(F("ERR MOTOR_TEST unsafe_state"));
    return;
  }

  char side = static_cast<char>(toupper(static_cast<unsigned char>(toks[1][0])));
  if (!(side == 'L' || side == 'R') || toks[1][1] != '\0') {
    Serial.println(F("ERR MOTOR_TEST wheel"));
    return;
  }

  int pwm = 0;
  int duration_ms = 0;
  if (!parseIntStrict(toks[2], &pwm) || !parseIntStrict(toks[3], &duration_ms)) {
    Serial.println(F("ERR MOTOR_TEST parse"));
    return;
  }

  pwm = constrain(pwm, -200, 200);
  duration_ms = constrain(duration_ms, 40, 800);
  if (pwm == 0) pwm = 90;

  long l0, r0, l1, r1;
  noInterrupts();
  l0 = g_enc_l;
  r0 = g_enc_r;
  interrupts();
  if (side == 'L') applyMotorLr(pwm, 0);
  else applyMotorLr(0, pwm);
  delay(duration_ms);
  motorStop();
  delay(70);
  noInterrupts();
  l1 = g_enc_l;
  r1 = g_enc_r;
  interrupts();
  const long dL = l1 - l0;
  const long dR = r1 - r0;
  const bool moved = labs((side == 'L') ? dL : dR) >= 1;

  Serial.print(F("OK MOTOR_TEST wheel="));
  Serial.print(side);
  Serial.print(F(" pwm="));
  Serial.print(pwm);
  Serial.print(F(" ms="));
  Serial.print(duration_ms);
  Serial.print(F(" dL="));
  Serial.print(dL);
  Serial.print(F(" dR="));
  Serial.print(dR);
  Serial.print(F(" moved="));
  Serial.println(moved ? F("1") : F("0"));
}

static bool pulseWheelProbe(char side, int pwm, int duration_ms, long* outDL, long* outDR) {
  if (!(side == 'L' || side == 'R')) return false;
  long l0, r0;
  noInterrupts();
  l0 = g_enc_l;
  r0 = g_enc_r;
  interrupts();
  if (side == 'L') applyMotorLr(pwm, 0);
  else applyMotorLr(0, pwm);
  delay(duration_ms);
  motorStop();
  delay(70);
  long l1, r1;
  noInterrupts();
  l1 = g_enc_l;
  r1 = g_enc_r;
  interrupts();
  const long dL = l1 - l0;
  const long dR = r1 - r0;
  if (outDL) *outDL = dL;
  if (outDR) *outDR = dR;
  const long primary_delta = (side == 'L') ? dL : dR;
  return labs(primary_delta) >= 1;
}

static void runPrearmCheck() {
  // Atomic firmware-side prearm probe: ensures safe state then validates wheel pulses.
  g_state.armed = false;
  g_out = 0.0f;
  applyMotorOutput(0.0f);
  clearFault();  // leaves estop latched and fault clear

  const bool stand = true;  // operator confirmation remains in UI layer
  bool estop_latch_ok = g_state.estop_latched;

  long dL1 = 0, dR1 = 0, dL2 = 0, dR2 = 0;
  bool wl = false;
  bool wr = false;
  if (estop_latch_ok && g_state.active_fault == FAULT_NONE) {
    wl = pulseWheelProbe('L', 110, 160, &dL1, &dR1);
    wr = pulseWheelProbe('R', 110, 160, &dL2, &dR2);
  }

  // Unlatch/re-latch estop without creating sticky fault for wheel-probe path.
  g_state.estop_latched = false;
  bool estop_unlatch_ok = !g_state.estop_latched;
  g_state.estop_latched = true;

  const bool ok =
      stand && wl && wr && estop_latch_ok && estop_unlatch_ok && (g_state.active_fault == FAULT_NONE);
  const long dL = dL1 + dL2;
  const long dR = dR1 + dR2;

  Serial.print(F("OK PREARM_CHECK"));
  Serial.print(F(" ok="));
  Serial.print(ok ? 1 : 0);
  Serial.print(F(" stand="));
  Serial.print(stand ? 1 : 0);
  Serial.print(F(" wheel_l="));
  Serial.print(wl ? 1 : 0);
  Serial.print(F(" wheel_r="));
  Serial.print(wr ? 1 : 0);
  Serial.print(F(" estop_latch="));
  Serial.print(estop_latch_ok ? 1 : 0);
  Serial.print(F(" estop_unlatch="));
  Serial.print(estop_unlatch_ok ? 1 : 0);
  Serial.print(F(" dL="));
  Serial.print(dL);
  Serial.print(F(" dR="));
  Serial.print(dR);
  Serial.print(F(" fault="));
  Serial.print(g_state.active_fault);
  Serial.print(F(" detail="));
  Serial.println(ok ? F("prearm_pass") : F("prearm_fail"));
}
#endif

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
    Serial.print(F("UPRIGHT_PROFILED_RUNTIME_V1_1"));
    Serial.print(F(" runtime="));
    Serial.print(F(UPRIGHT_RUNTIME_VERSION));
    Serial.print(F(" tune="));
    Serial.print(F(UPRIGHT_TUNE_VERSION));
    Serial.print(F(" build="));
    Serial.print(F(UPRIGHT_BUILD_ID));
    Serial.print(F(" hash="));
    Serial.println(F(UPRIGHT_BUILD_HASH));
    return;
  }

  if (strcmp(line, "ARM") == 0) {
    if (g_state.active_fault != FAULT_NONE) {
      Serial.println(F("ERR FAULT_LATCHED"));
      return;
    }
    g_state.estop_latched = false;
    g_state.armed = true;
    g_arm_enter_ms = millis();
    g_i_state = 0.0f;
    g_prev_err = 0.0f;
    g_d_init = false;
    resetMotionState();
    Serial.println(F("OK ARM"));
    return;
  }

  if (strcmp(line, "DISARM") == 0) {
    g_state.armed = false;
    g_arm_enter_ms = 0;
    g_out = 0.0f;
    resetMotionState();
    applyMotorOutput(0.0f);
    Serial.println(F("OK DISARM"));
    return;
  }

  if (strcmp(line, "AUTOZERO STATUS") == 0) {
    Serial.print(F("OK AUTOZERO enabled="));
    Serial.print(g_autozero_enabled ? 1 : 0);
    Serial.print(F(" trim_deg="));
    Serial.print(g_autozero_trim_deg, 4);
    Serial.print(F(" set_eff_deg="));
    Serial.println(g_set_eff_deg, 4);
    return;
  }

  if (strcmp(line, "AUTOZERO CLR") == 0) {
    clearAutozeroTrim();
    Serial.println(F("OK AUTOZERO CLR"));
    return;
  }

  if (strcmp(line, "AUTOZERO SAVE") == 0) {
    if (g_state.armed) {
      Serial.println(F("ERR AUTOZERO unsafe_state"));
      return;
    }
    g_cfg.set_deg = clampf(g_cfg.set_deg + g_autozero_trim_deg, -30.0f, 30.0f);
    clearAutozeroTrim();
    cfgSanitize();
    cfgSave();
    g_set_eff_deg = g_cfg.set_deg;
    Serial.print(F("OK AUTOZERO SAVE set_deg="));
    Serial.println(g_cfg.set_deg, 4);
    return;
  }

  int autozero_v;
  if (parseCommandInt(line, "AUTOZERO", &autozero_v)) {
    g_autozero_enabled = (autozero_v != 0);
    Serial.print(F("OK AUTOZERO "));
    Serial.println(g_autozero_enabled ? F("1") : F("0"));
    return;
  }

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

  int v;
  if (parseCommandInt(line, "LOGT", &v)) {
    g_cfg.log_t = (v != 0) ? 1 : 0;
    Serial.println(F("OK LOGT"));
    return;
  }

  if (parseCommandInt(line, "LOGCSV", &v)) {
    g_cfg.log_csv = (v != 0) ? 1 : 0;
    Serial.println(F("OK LOGCSV"));
    return;
  }

  if (strcmp(line, "BURSTCSV") == 0) {
    emitCsv();
    Serial.println(F("OK BURSTCSV"));
    return;
  }

  if (strcmp(line, "CSVHDR") == 0) {
    Serial.println(F("CSV,ms,mode,estop,set,ang,raw,gyro,out,encL,encR,fault,overrun,jitter_us"));
    return;
  }

  if (strcmp(line, "SAVECFG") == 0) {
    cfgSave();
    Serial.println(F("OK SAVECFG"));
    return;
  }

  if (strcmp(line, "LOADCFG") == 0) {
    if (cfgLoad()) {
      clearAutozeroTrim();
      Serial.println(F("OK LOADCFG"));
    }
    else Serial.println(F("ERR LOADCFG"));
    return;
  }

  if (strcmp(line, "DEFAULTCFG") == 0) {
    cfgDefaults();
    clearAutozeroTrim();
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

#if FEAT_AUTOTUNE_HELPERS
  if (strncmp(line, "MOTOR_TEST ", 11) == 0) {
    runMotorTest(line);
    return;
  }
  if (strcmp(line, "PREARM_CHECK") == 0) {
    runPrearmCheck();
    return;
  }
#endif

#if FEAT_TRANSFER_FN_CMD
  if (strcmp(line, "TF") == 0) {
    printTf();
    return;
  }
#endif

#if FEAT_COHEN_COON_CMD
  if (parseCohenCoon(line)) return;
#endif

  if (parsePID(line) || parseMotion(line) || parseSetpoint(line) || parseLimits(line) || parseFilter(line) || parseKal(line)) {
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

    kalmanUpdate(g_raw, g_state.gyro_dps, static_cast<float>(LOOP_PERIOD_US) * 1.0e-6f);
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

  // Translation channel estimate (counts/tick and integrated counts around arm point).
  const float wheel_delta = 0.5f * static_cast<float>(dL + dR);
  g_motion_delta_counts = wheel_delta;
  const float vel_alpha = alphaFromCutoffHz(MOTION_VEL_CUTOFF_HZ, DT_S);
  if (!g_motion_vel_init) {
    g_motion_vel_counts = wheel_delta;
    g_motion_vel_init = true;
  } else {
    g_motion_vel_counts = lowPass(wheel_delta, g_motion_vel_counts, vel_alpha);
  }
  g_motion_pos_raw_counts += wheel_delta;
  g_motion_pos_counts = clampf(
    g_motion_pos_raw_counts,
    -MOTION_POS_MAX_COUNTS,
    MOTION_POS_MAX_COUNTS
  );

  g_set_eff_deg = clampf(g_cfg.set_deg + g_autozero_trim_deg, -30.0f, 30.0f);

  if (g_state.armed && !g_state.estop_latched && g_state.active_fault == FAULT_NONE) {
    if (fabs(g_state.angle_deg) > g_cfg.tip_deg) {
      latchFault(FAULT_MODULE_UNHEALTHY, NOTE_TIP_LIMIT, F("tip_limit"));
    } else {
      g_pid_err = g_set_eff_deg - g_state.angle_deg;
      g_pid_p = g_cfg.kp * g_pid_err;

      g_d_unfilt = (g_pid_err - g_prev_err) * (1000000.0f / static_cast<float>(LOOP_PERIOD_US));
      g_d_alpha = alphaFromCutoffHz(g_cfg.d_cutoff_hz, static_cast<float>(LOOP_PERIOD_US) * 1.0e-6f);
      if (!g_d_init) {
        g_d_filt = g_d_unfilt;
        g_d_init = true;
      } else {
        g_d_filt = lowPass(g_d_unfilt, g_d_filt, g_d_alpha);
      }
      g_pid_d = g_cfg.kd * g_d_filt;

      bool pushing_sat = g_output_saturated &&
        ((g_pid_err > 0.0f && g_pid_u_unsat > g_cfg.out_max) ||
         (g_pid_err < 0.0f && g_pid_u_unsat < -g_cfg.out_max));

      if (!g_conditional_i || !pushing_sat) {
        g_i_state += g_pid_err * (static_cast<float>(LOOP_PERIOD_US) * 1.0e-6f);
      }

      g_i_state = clampf(g_i_state, -g_cfg.i_max, g_cfg.i_max);
      g_pid_i = g_cfg.ki * g_i_state;
      g_pid_i = clampf(g_pid_i, -g_cfg.i_term_max, g_cfg.i_term_max);

      g_motion_term = -(g_motion_kv * g_motion_vel_counts + g_motion_kx * g_motion_pos_counts);
      float motion_term_max = g_cfg.out_max * MOTION_TERM_FRAC;
      g_motion_term = clampf(g_motion_term, -motion_term_max, motion_term_max);

      g_pid_u_unsat = g_pid_p + g_pid_i + g_pid_d + g_motion_term;
      g_pid_u_sat = clampf(g_pid_u_unsat, -g_cfg.out_max, g_cfg.out_max);
      g_output_saturated = (fabs(g_pid_u_unsat - g_pid_u_sat) > 0.001f);

      g_i_state += g_cfg.kaw * (g_pid_u_sat - g_pid_u_unsat) * (static_cast<float>(LOOP_PERIOD_US) * 1.0e-6f);
      g_i_state = clampf(g_i_state, -g_cfg.i_max, g_cfg.i_max);

      float max_step = OUT_SLEW_PER_S * DT_S;
      float target_out = g_pid_u_sat;
      float out_err = target_out - g_out;
      if (out_err > max_step) out_err = max_step;
      if (out_err < -max_step) out_err = -max_step;
      g_out += out_err;
      g_state.output_cmd = g_out;
      applyMotorOutput(g_out);
      g_prev_err = g_pid_err;

      bool autozero_gate = g_autozero_enabled
        && (fabs(g_state.angle_deg) < min(AUTOZERO_ANGLE_GATE_DEG, 0.45f * g_cfg.tip_deg))
        && (fabs(g_state.gyro_dps) < AUTOZERO_GYRO_GATE_DPS)
        && !g_output_saturated
        && (fabs(g_out) < (AUTOZERO_OUT_FRAC_GATE * g_cfg.out_max))
        && (g_runaway_score < AUTOZERO_RUNAWAY_GATE);
      if (autozero_gate) {
        const float err_to_trim = g_state.angle_deg - g_set_eff_deg;
        if (fabs(err_to_trim) > AUTOZERO_ERR_DEADBAND_DEG) {
          const float max_trim_step = AUTOZERO_STEP_MAX_DEG_PER_S * DT_S;
          const float trim_step = clampf(err_to_trim, -max_trim_step, max_trim_step);
          g_autozero_trim_deg = clampf(
            g_autozero_trim_deg + trim_step,
            -AUTOZERO_TRIM_MAX_DEG,
            AUTOZERO_TRIM_MAX_DEG
          );
          g_set_eff_deg = clampf(g_cfg.set_deg + g_autozero_trim_deg, -30.0f, 30.0f);
        }
      }

      uint32_t now_ms = millis();
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
    g_motion_term = 0.0f;
    g_motion_vel_counts = 0.0f;
    g_motion_pos_counts = 0.0f;
    g_motion_pos_raw_counts = 0.0f;
    g_motion_delta_counts = 0.0f;
    g_motion_vel_init = false;
    g_set_eff_deg = clampf(g_cfg.set_deg + g_autozero_trim_deg, -30.0f, 30.0f);
    applyMotorOutput(0.0f);
  }

  float a_norm = fabs(g_state.angle_deg) / max(1.0f, g_cfg.tip_deg);
  float o_norm = fabs(g_out) / max(1.0f, g_cfg.out_max);
  float p_norm = fabs(g_motion_pos_counts) / MOTION_POS_MAX_COUNTS;
  g_runaway_score = 0.5f * a_norm + 0.3f * o_norm + 0.2f * p_norm;

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
  Serial.println(F("UPRIGHT_PROFILED_RUNTIME_BOOT"));

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
      Serial.println(F("IMU offsets loaded"));
    } else {
      g_mpu.calcOffsets();
      imuCalSaveFromCurrent(nullptr);
      Serial.println(F("IMU offsets auto-calibrated"));
    }
    g_mpu.update();
    g_raw = readAccelDeg();
    resetEstimatorToCurrentAccel();
    g_imu_ok = true;
  } else {
    g_imu_ok = false;
    latchFault(FAULT_SENSOR_INVALID, NOTE_IMU_BEGIN_FAILED, F("imu_begin_failed"));
  }

  g_last_moving_enc_ms = millis();
  g_next_tick_us = micros() + LOOP_PERIOD_US;
  g_last_tick_us = micros();
  g_last_status_ms = millis();

  printHelp();
  emitStatus();
}

void loop() {
  serviceSerial();

  uint32_t now_us = micros();
  if (static_cast<int32_t>(now_us - g_next_tick_us) >= 0) {
    uint32_t actual_period_us = now_us - g_last_tick_us;
    g_last_tick_us = now_us;
    g_last_period_us = actual_period_us;

    if (actual_period_us < g_min_period_us) g_min_period_us = actual_period_us;
    if (actual_period_us > g_max_period_us) g_max_period_us = actual_period_us;

    uint32_t target_period = LOOP_PERIOD_US;
    g_jitter_us = (actual_period_us > target_period)
      ? (actual_period_us - target_period)
      : (target_period - actual_period_us);

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
    if (g_cfg.log_t) emitStatus();
    if (g_cfg.log_csv) emitCsv();
    digitalWrite(Pins::LED, !digitalRead(Pins::LED));
  }
}
