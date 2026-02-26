/*
  upright_mvp_baseline_v1 (hardened v1.1)
  UpRight.os-compatible firmware baseline for Arduino Nano / ATmega328P.

  Core guarantees:
  - Deterministic 200 Hz control loop
  - Right encoder on D4 via PCINT, left encoder on D2 via external interrupt
  - Fixed-size command buffer parser (no String use in RT path)
  - Fault-latched safety path with clearable fault reason
  - EEPROM-backed versioned config with safe defaults

  Optional lab features are compile-gated by profile flags.
*/

#include <Arduino.h>
#include <math.h>
#include <Wire.h>
#include <EEPROM.h>
#include <MPU6050_light.h>
#include <avr/interrupt.h>

#ifndef UPRIGHT_PROFILE
// Default to FIELD_HARDENED behavior when profile header is available.
#define UPRIGHT_PROFILE 3
#endif

#if defined(__has_include)
#if __has_include("../profiled_runtime_v1/feature_profile.h")
#include "../profiled_runtime_v1/feature_profile.h"
#define UPRIGHT_HAS_PROFILE_TEMPLATE 1
#endif
#if __has_include("../profiled_runtime_v1/module_contracts.h")
#include "../profiled_runtime_v1/module_contracts.h"
#define UPRIGHT_HAS_MODULE_CONTRACTS 1
#endif
#endif

#ifndef UPRIGHT_HAS_PROFILE_TEMPLATE
#define FEAT_FIXED_RATE_LOOP 1
#define FEAT_SAFETY_STATE_MACHINE 1
#define FEAT_ESTOP_LATCH 1
#define FEAT_WATCHDOG 1
#define FEAT_SENSOR_PLAUSIBILITY 1
#define FEAT_NO_HEAP_RT_PATH 1
#define FEAT_ADV_TELEMETRY 1
#define FEAT_VERBOSE_DIAGNOSTICS 0
#define FEAT_COHEN_COON_CMD 0
#define FEAT_TRANSFER_FN_CMD 0
#define FEAT_BURST_LOGGING 1
#define FEAT_EEPROM_CONFIG 1
#define LOOP_HZ 200U
#define LOOP_PERIOD_US (1000000UL / LOOP_HZ)
#define STATUS_PERIOD_MS 100U
#define MAX_CONTROL_STEP_US 3500U
#endif

#ifndef UPRIGHT_HAS_MODULE_CONTRACTS
enum FaultCode : uint16_t {
  FAULT_NONE = 0,
  FAULT_SENSOR_INVALID = 10,
  FAULT_LOOP_OVERRUN = 11,
  FAULT_WATCHDOG = 12,
  FAULT_ENCODER_STALE = 13,
  FAULT_MODULE_UNHEALTHY = 20,
  FAULT_IMU_INIT = 30,
  FAULT_TIP_OVER = 31,
  FAULT_ESTOP_LATCH = 32
};
#endif

namespace Pins {
  const uint8_t LED = LED_BUILTIN;
  const uint8_t ENC_LEFT = 2;   // INT0
  const uint8_t ENC_RIGHT = 4;  // D4 / PCINT20 (Nano classic)
  const uint8_t PWMA = 5;
  const uint8_t PWMB = 6;
  const uint8_t AIN1 = 7;
  const uint8_t STBY = 8;
  const uint8_t BIN1 = 12;
  const uint8_t VOL = A2;
}

enum RuntimeMode : uint8_t {
  MODE_SAFE_IDLE = 0,
  MODE_BALANCING = 1,
  MODE_FAULT = 2
};

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

static const uint32_t CFG_MAGIC = 0x31565055UL;  // "UPV1"
static const uint8_t CFG_VERSION = 11;
static const int EEPROM_ADDR = 0;

static RuntimeConfigV11 g_cfg;
static RuntimeMode g_mode = MODE_SAFE_IDLE;
static bool g_armed = false;
static bool g_estop = true;
static uint16_t g_fault = FAULT_NONE;

static float g_ang = 0.0f;
static float g_raw = 0.0f;
static float g_gyro = 0.0f;
static float g_out = 0.0f;
static float g_vol_raw = 0.0f;

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

static uint32_t g_next_tick_us = 0;
static uint32_t g_last_tick_us = 0;
static uint32_t g_last_status_ms = 0;
static uint32_t g_last_moving_enc_ms = 0;

static uint32_t g_loop_overrun = 0;
static uint32_t g_loop_missed = 0;
static uint32_t g_last_step_us = 0;
static uint32_t g_last_period_us = LOOP_PERIOD_US;
static uint32_t g_min_period_us = 0xFFFFFFFFUL;
static uint32_t g_max_period_us = 0;
static uint32_t g_jitter_us = 0;

static bool g_imu_ok = false;
MPU6050 g_mpu(Wire);

static char g_cmd_buf[128];
static uint8_t g_cmd_len = 0;

static float clampf(float v, float lo, float hi) {
  if (v < lo) return lo;
  if (v > hi) return hi;
  return v;
}

static bool isFinitef(float v) {
  return isfinite(v) != 0;
}

static const char* modeName(RuntimeMode mode) {
  if (mode == MODE_BALANCING) return "BALANCING";
  if (mode == MODE_FAULT) return "FAULT";
  return "SAFE_IDLE";
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

static void applyMotorOutput(float out) {
  float signed_out = clampf(out, -255.0f, 255.0f);
  int cmd = static_cast<int>(signed_out);
  cmd *= g_cfg.motor_polarity;
  cmd = constrain(cmd, -255, 255);

  const bool backward = (cmd > 0);
  const int pwm = abs(cmd);

  digitalWrite(Pins::AIN1, backward ? HIGH : LOW);
  digitalWrite(Pins::BIN1, backward ? HIGH : LOW);

  if (pwm == 0) {
    motorStop();
    return;
  }

  digitalWrite(Pins::STBY, HIGH);
  analogWrite(Pins::PWMA, pwm);
  analogWrite(Pins::PWMB, pwm);
}

static float readAccelDeg() {
  const float x = g_mpu.getAngleX();
  const float y = g_mpu.getAngleY();
  if (!g_cfg.swap_axes) return (g_cfg.imu_axis == 'X') ? x : y;
  return (g_cfg.imu_axis == 'X') ? y : x;
}

static float readGyroDps() {
  const float x = g_mpu.getGyroX();
  const float y = g_mpu.getGyroY();
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

static void latchFault(uint16_t code, const char* note) {
  const uint16_t prior_fault = g_fault;
  if (g_fault == FAULT_NONE) g_fault = code;
  g_estop = true;
  g_armed = false;
  g_mode = MODE_FAULT;
  g_out = 0.0f;
  applyMotorOutput(0.0f);

  if (prior_fault == FAULT_NONE) {
    Serial.print(F("FAULT code="));
    Serial.print(g_fault);
    Serial.print(F(" note="));
    Serial.println(note);
  } else {
    Serial.print(F("FAULT2 latched="));
    Serial.print(g_fault);
    Serial.print(F(" code="));
    Serial.print(code);
    Serial.print(F(" note="));
    Serial.println(note);
  }
}

static void clearFault() {
  g_fault = FAULT_NONE;
  g_mode = MODE_SAFE_IDLE;
  g_estop = true;
  g_armed = false;
  g_out = 0.0f;
  g_i_state = 0.0f;
  g_prev_err = 0.0f;
  g_d_init = false;
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
  Serial.print(modeName(g_mode));
  Serial.print(F(" estop="));
  Serial.print(g_estop ? "1" : "0");
  Serial.print(F(" fault="));
  Serial.print(g_fault);
  Serial.print(F(" ang="));
  Serial.print(g_ang, 3);
  Serial.print(F(" raw="));
  Serial.print(g_raw, 3);
  Serial.print(F(" gyro="));
  Serial.print(g_gyro, 3);
  Serial.print(F(" set="));
  Serial.print(g_cfg.set_deg, 3);
  Serial.print(F(" out="));
  Serial.print(g_out, 3);
  Serial.print(F(" kp="));
  Serial.print(g_cfg.kp, 4);
  Serial.print(F(" ki="));
  Serial.print(g_cfg.ki, 4);
  Serial.print(F(" kd="));
  Serial.print(g_cfg.kd, 4);
  Serial.print(F(" encL="));
  Serial.print(l);
  Serial.print(F(" encR="));
  Serial.print(r);
  Serial.print(F(" overrun="));
  Serial.print(g_loop_overrun);
  Serial.print(F(" missed="));
  Serial.print(g_loop_missed);
  Serial.print(F(" loop_us="));
  Serial.print(g_last_step_us);
  Serial.print(F(" period_us="));
  Serial.print(g_last_period_us);
  Serial.print(F(" jitter_us="));
  Serial.print(g_jitter_us);
  Serial.print(F(" loop_min_us="));
  Serial.print(g_min_period_us == 0xFFFFFFFFUL ? 0 : g_min_period_us);
  Serial.print(F(" loop_max_us="));
  Serial.print(g_max_period_us);
  Serial.print(F(" volRaw="));
  Serial.print(g_vol_raw, 0);
#if FEAT_VERBOSE_DIAGNOSTICS
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
  Serial.print(g_output_saturated ? "1" : "0");
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
  Serial.print(modeName(g_mode));
  Serial.print(',');
  Serial.print(g_estop ? 1 : 0);
  Serial.print(',');
  Serial.print(g_cfg.set_deg, 3);
  Serial.print(',');
  Serial.print(g_ang, 3);
  Serial.print(',');
  Serial.print(g_raw, 3);
  Serial.print(',');
  Serial.print(g_gyro, 3);
  Serial.print(',');
  Serial.print(g_out, 3);
  Serial.print(',');
  Serial.print(l);
  Serial.print(',');
  Serial.print(r);
  Serial.print(',');
  Serial.print(g_fault);
  Serial.print(',');
  Serial.print(g_loop_overrun);
  Serial.print(',');
  Serial.println(g_jitter_us);
}

static void printHelp() {
  Serial.println(F("OK HELP GET ARM DISARM ESTOP PID SETPOINT LIMITS FILTER KAL CAL ZERO SAVECFG LOADCFG DEFAULTCFG FAULTCLR LOGT LOGCSV BURSTCSV CSVHDR IDENT"));
#if FEAT_COHEN_COON_CMD
  Serial.println(F("OK HELP+ CC"));
#endif
#if FEAT_TRANSFER_FN_CMD
  Serial.println(F("OK HELP+ TF"));
#endif
}

static void printTf() {
  Serial.println(F("TF controller C(s)=Kp + Ki/s + Kd*s/(tau_d*s+1)"));
  Serial.println(F("TF plant_model G(s)=K/(T*s+1)*e^(-L*s)"));
  Serial.println(F("TF closed_loop T(s)=C(s)G(s)/(1+C(s)G(s))"));
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
  char* end = nullptr;
  float v = strtof(text, &end);
  if (end == text || *end != '\0') return false;
  *out = v;
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

static void handleCommandLine(char* line) {
  while (*line == ' ') line++;
  if (*line == '\0') return;

  size_t n = strlen(line);
  while (n > 0 && (line[n - 1] == ' ' || line[n - 1] == '\t')) {
    line[--n] = '\0';
  }

  if (strcmp(line, "GET") == 0) {
    emitStatus();
    return;
  }
  if (strcmp(line, "HELP") == 0) {
    printHelp();
    return;
  }
  if (strcmp(line, "IDENT") == 0) {
    Serial.println(F("UPRIGHT_MVP_BASELINE_V1_1"));
    return;
  }
  if (strcmp(line, "ARM") == 0) {
    if (g_fault != FAULT_NONE) {
      Serial.println(F("ERR FAULT_LATCHED"));
      return;
    }
    g_armed = true;
    g_estop = false;
    g_mode = MODE_BALANCING;
    g_i_state = 0.0f;
    g_prev_err = 0.0f;
    g_d_init = false;
    Serial.println(F("OK ARM"));
    return;
  }
  if (strcmp(line, "DISARM") == 0) {
    g_armed = false;
    g_mode = MODE_SAFE_IDLE;
    g_out = 0.0f;
    applyMotorOutput(0.0f);
    Serial.println(F("OK DISARM"));
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
      g_estop = true;
      g_armed = false;
      g_mode = MODE_SAFE_IDLE;
      g_out = 0.0f;
      applyMotorOutput(0.0f);
      if (g_fault == FAULT_NONE) g_fault = FAULT_ESTOP_LATCH;
    } else {
      if (g_fault == FAULT_ESTOP_LATCH) {
        g_fault = FAULT_NONE;
        g_estop = false;
        if (g_mode == MODE_FAULT) g_mode = MODE_SAFE_IDLE;
      } else if (g_fault == FAULT_NONE) {
        g_estop = false;
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

#if FEAT_TRANSFER_FN_CMD
  if (strcmp(line, "TF") == 0) {
    printTf();
    return;
  }
#endif

#if FEAT_COHEN_COON_CMD
  if (parseCohenCoon(line)) return;
#endif

  if (parsePID(line) || parseSetpoint(line) || parseLimits(line) || parseFilter(line) || parseKal(line)) {
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
  const uint32_t step_start = micros();

  if (!g_imu_ok) {
    latchFault(FAULT_IMU_INIT, "imu_not_ready");
  } else {
    g_mpu.update();
    g_raw = readAccelDeg();
    g_gyro = readGyroDps();

    if (!isFinitef(g_raw) || !isFinitef(g_gyro) || fabs(g_gyro) > 2200.0f || fabs(g_raw) > 180.0f) {
      latchFault(FAULT_SENSOR_INVALID, "sensor_invalid");
    }

    kalmanUpdate(g_raw, g_gyro, static_cast<float>(LOOP_PERIOD_US) * 1.0e-6f);
    g_ang = (g_cfg.imu_polarity * g_kf_angle) - g_cfg.angle_zero_deg;

    if (!isFinitef(g_ang)) {
      latchFault(FAULT_SENSOR_INVALID, "angle_invalid");
    }
  }

  g_vol_raw = analogRead(Pins::VOL);

  long l_now, r_now;
  noInterrupts();
  l_now = g_enc_l;
  r_now = g_enc_r;
  interrupts();

  const long dL = l_now - g_prev_enc_l;
  const long dR = r_now - g_prev_enc_r;
  g_prev_enc_l = l_now;
  g_prev_enc_r = r_now;

  if (dL != 0 || dR != 0) {
    g_last_moving_enc_ms = millis();
  }

  if (g_armed && !g_estop && g_mode == MODE_BALANCING) {
    if (fabs(g_ang) > g_cfg.tip_deg) {
      latchFault(FAULT_TIP_OVER, "tip_limit");
    } else {
      g_pid_err = g_cfg.set_deg - g_ang;
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

      const bool pushing_sat = g_output_saturated &&
        ((g_pid_err > 0.0f && g_pid_u_unsat > g_cfg.out_max) ||
         (g_pid_err < 0.0f && g_pid_u_unsat < -g_cfg.out_max));

      if (!g_conditional_i || !pushing_sat) {
        g_i_state += g_pid_err * (static_cast<float>(LOOP_PERIOD_US) * 1.0e-6f);
      }

      g_i_state = clampf(g_i_state, -g_cfg.i_max, g_cfg.i_max);
      g_pid_i = g_cfg.ki * g_i_state;
      g_pid_i = clampf(g_pid_i, -g_cfg.i_term_max, g_cfg.i_term_max);

      g_pid_u_unsat = g_pid_p + g_pid_i + g_pid_d;
      g_pid_u_sat = clampf(g_pid_u_unsat, -g_cfg.out_max, g_cfg.out_max);
      g_output_saturated = (fabs(g_pid_u_unsat - g_pid_u_sat) > 0.001f);

      // Back-calculation anti-windup path.
      g_i_state += g_cfg.kaw * (g_pid_u_sat - g_pid_u_unsat) * (static_cast<float>(LOOP_PERIOD_US) * 1.0e-6f);
      g_i_state = clampf(g_i_state, -g_cfg.i_max, g_cfg.i_max);

      g_out = g_pid_u_sat;
      applyMotorOutput(g_out);
      g_prev_err = g_pid_err;

      if (fabs(g_out) > 70.0f && (millis() - g_last_moving_enc_ms) > 500U) {
        latchFault(FAULT_ENCODER_STALE, "encoder_stale");
      }
    }
  } else {
    g_out = 0.0f;
    g_pid_err = 0.0f;
    g_pid_p = 0.0f;
    g_pid_i = 0.0f;
    g_pid_d = 0.0f;
    g_pid_u_unsat = 0.0f;
    g_pid_u_sat = 0.0f;
    g_output_saturated = false;
    applyMotorOutput(0.0f);
  }

  g_last_step_us = micros() - step_start;
  if (g_last_step_us > MAX_CONTROL_STEP_US) {
    g_loop_overrun++;
    if (g_loop_overrun >= 5U) {
      latchFault(FAULT_LOOP_OVERRUN, "loop_overrun");
    }
  }
}

void setup() {
  Serial.begin(115200);
  delay(120);
  Serial.println(F("UPRIGHT_MVP_BOOT"));

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
    g_mpu.calcOffsets();
    g_mpu.update();
    g_raw = readAccelDeg();
    resetEstimatorToCurrentAccel();
    g_imu_ok = true;
  } else {
    g_imu_ok = false;
    latchFault(FAULT_IMU_INIT, "imu_begin_failed");
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

  const uint32_t now_us = micros();
  if (static_cast<int32_t>(now_us - g_next_tick_us) >= 0) {
    const uint32_t actual_period_us = now_us - g_last_tick_us;
    g_last_tick_us = now_us;
    g_last_period_us = actual_period_us;

    if (actual_period_us < g_min_period_us) g_min_period_us = actual_period_us;
    if (actual_period_us > g_max_period_us) g_max_period_us = actual_period_us;

    const uint32_t target_period = LOOP_PERIOD_US;
    g_jitter_us = (actual_period_us > target_period)
      ? (actual_period_us - target_period)
      : (target_period - actual_period_us);

    controlTick();

    g_next_tick_us += LOOP_PERIOD_US;
    if (static_cast<int32_t>(now_us - g_next_tick_us) >= 0) {
      const uint32_t behind = now_us - g_next_tick_us;
      const uint32_t missed = (behind / LOOP_PERIOD_US) + 1U;
      g_loop_missed += missed;
      g_next_tick_us += missed * LOOP_PERIOD_US;
    }
  }

  const uint32_t now_ms = millis();
  if (now_ms - g_last_status_ms >= STATUS_PERIOD_MS) {
    g_last_status_ms = now_ms;
    if (g_cfg.log_t) emitStatus();
    if (g_cfg.log_csv) emitCsv();
    digitalWrite(Pins::LED, !digitalRead(Pins::LED));
  }
}
