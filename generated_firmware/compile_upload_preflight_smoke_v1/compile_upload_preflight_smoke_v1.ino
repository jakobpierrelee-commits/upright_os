/*
  compile_upload_preflight_smoke_v1
  Minimal firmware to sanity-check compile, upload, and preflight flow in UpRight.os.

  Behavior
  --------
  - Emits deterministic STATUS frames that include the required bridge keys.
  - Responds to GET, PID, MOTION, SETPOINT, LIMITS, ARM/DISARM, ESTOP, CAL ZERO, and SAVECFG.
  - Uses synthetic telemetry so graphs and guardrails exercise without real hardware.
*/

#include <Arduino.h>
#include <math.h>
#include "config_board.h"

enum Mode : uint8_t {
  MODE_SAFE_IDLE = 0,
  MODE_ARMED = 1
};

struct Limits {
  float out_max;
  float tip_deg;
  float i_max;
};

static Mode g_mode = MODE_SAFE_IDLE;
static bool g_estop = false;
static bool g_outer_loop_enabled = false;
static bool g_output_saturated = false;

static Limits g_limits = {90.0f, 25.0f, 2.0f};
static float g_kp = 20.0f;
static float g_ki = 0.04f;
static float g_kd = 0.8f;
static float g_kv = 0.0f;
static float g_kx = 0.0f;

static float g_set = 0.0f;
static float g_ang = 0.0f;
static float g_raw = 0.0f;
static float g_gyro = 0.0f;
static float g_out = 0.0f;
static float g_pid_err = 0.0f;
static float g_pid_p = 0.0f;
static float g_pid_i = 0.0f;
static float g_pid_d = 0.0f;
static float g_vel_meas = 0.0f;
static float g_vel_target = 0.0f;
static float g_target_angle_from_velocity = 0.0f;
static float g_gyro_bias = 0.0f;
static float g_accel_level_offset = 0.0f;
static float g_upright_trim = 0.0f;
static uint32_t g_last_save_ms = 0;

static float g_integral = 0.0f;
static float g_prev_err = 0.0f;
static float g_phase = 0.0f;
static uint32_t g_last_loop_us = 0;
static uint32_t g_last_status_ms = 0;

static constexpr uint32_t LOOP_PERIOD_US = 5000;
static constexpr uint32_t STATUS_PERIOD_MS = 250;

static float clampf(float value, float lo, float hi) {
  if (value < lo) return lo;
  if (value > hi) return hi;
  return value;
}

static void emitStatus() {
  Serial.print(F("STATUS mode="));
  Serial.print(g_mode == MODE_ARMED ? F("ARMED") : F("SAFE_IDLE"));
  Serial.print(F(" estop="));
  Serial.print(g_estop ? 1 : 0);
  Serial.print(F(" ang="));
  Serial.print(g_ang, 4);
  Serial.print(F(" raw="));
  Serial.print(g_raw, 4);
  Serial.print(F(" gyro="));
  Serial.print(g_gyro, 4);
  Serial.print(F(" set="));
  Serial.print(g_set, 4);
  Serial.print(F(" out="));
  Serial.print(g_out, 4);
  Serial.print(F(" kp="));
  Serial.print(g_kp, 4);
  Serial.print(F(" ki="));
  Serial.print(g_ki, 4);
  Serial.print(F(" kd="));
  Serial.print(g_kd, 4);
  Serial.print(F(" kv="));
  Serial.print(g_kv, 4);
  Serial.print(F(" kx="));
  Serial.print(g_kx, 4);
  Serial.print(F(" pid_err="));
  Serial.print(g_pid_err, 4);
  Serial.print(F(" pid_p="));
  Serial.print(g_pid_p, 4);
  Serial.print(F(" pid_i="));
  Serial.print(g_pid_i, 4);
  Serial.print(F(" pid_d="));
  Serial.print(g_pid_d, 4);
  Serial.print(F(" pid_u_unsat="));
  Serial.print(g_pid_p + g_pid_i + g_pid_d, 4);
  Serial.print(F(" pid_u_sat="));
  Serial.print(g_out, 4);
  Serial.print(F(" output_saturated="));
  Serial.print(g_output_saturated ? 1 : 0);
  Serial.print(F(" out_max="));
  Serial.print(g_limits.out_max, 2);
  Serial.print(F(" tip_deg="));
  Serial.print(g_limits.tip_deg, 2);
  Serial.print(F(" i_max="));
  Serial.print(g_limits.i_max, 2);
  Serial.print(F(" vel_meas="));
  Serial.print(g_vel_meas, 4);
  Serial.print(F(" vel_target="));
  Serial.print(g_vel_target, 4);
  Serial.print(F(" outer_loop_enabled="));
  Serial.print(g_outer_loop_enabled ? 1 : 0);
  Serial.print(F(" target_angle_from_velocity="));
  Serial.print(g_target_angle_from_velocity, 4);
  Serial.print(F(" gyro_bias="));
  Serial.print(g_gyro_bias, 6);
  Serial.print(F(" accel_level_offset="));
  Serial.print(g_accel_level_offset, 6);
  Serial.print(F(" upright_trim="));
  Serial.print(g_upright_trim, 4);
  Serial.print(F(" saved_ms="));
  Serial.print(g_last_save_ms);
  Serial.print(F(" uptime_ms="));
  Serial.print(millis());
  Serial.println();
}

static void updateSyntheticTelemetry(float dt_s) {
  if (dt_s <= 0.0f) return;
  g_phase += dt_s * 0.8f;
  const float motion = sinf(g_phase);
  g_raw = g_accel_level_offset + motion * 1.2f;
  g_gyro = cosf(g_phase) * 12.0f;
  g_vel_meas = motion * 0.1f;
  g_vel_target = g_outer_loop_enabled ? 0.05f : 0.0f;
  g_target_angle_from_velocity = g_vel_target * g_kv;
  g_ang = (g_raw - g_upright_trim) * 0.9f + g_upright_trim;

  const float err = (g_set + g_target_angle_from_velocity) - g_ang;
  g_pid_err = err;
  g_integral += err * dt_s;
  g_integral = clampf(g_integral, -g_limits.i_max, g_limits.i_max);
  const float deriv = (err - g_prev_err) / dt_s;

  g_pid_p = g_kp * err;
  g_pid_i = g_ki * g_integral;
  g_pid_d = g_kd * deriv;
  float unsat = g_pid_p + g_pid_i + g_pid_d;
  g_out = clampf(unsat, -g_limits.out_max, g_limits.out_max);
  g_output_saturated = fabsf(unsat - g_out) > 0.001f;
  g_prev_err = err;

  const bool led = (g_mode == MODE_ARMED) && !g_estop;
  digitalWrite(PIN_LED, led ? HIGH : LOW);
  if (PIN_GATE_ENABLE >= 0) {
    digitalWrite(PIN_GATE_ENABLE, led ? HIGH : LOW);
  }
}

static void sendOk(const __FlashStringHelper* tag) {
  Serial.print(F("OK "));
  Serial.println(tag);
}

static bool equalsToken(const char* token, const char* literal) {
  if (!token || !literal) return false;
  while (*token && *literal) {
    char a = *token;
    char b = *literal;
    if (a >= 'a' && a <= 'z') a = a - 'a' + 'A';
    if (b >= 'a' && b <= 'z') b = b - 'a' + 'A';
    if (a != b) return false;
    ++token;
    ++literal;
  }
  return (*token == '\0' || *token == '\r') && *literal == '\0';
}

static void processCommand(char* line) {
  while (*line == ' ' || *line == '\t') ++line;
  if (*line == '\0') return;
  char* token = strtok(line, " ");
  if (!token) return;

  if (equalsToken(token, "GET")) {
    emitStatus();
    sendOk(F("GET"));
    return;
  }
  if (equalsToken(token, "HELP")) {
    Serial.println(F("OK HELP GET PID MOTION SETPOINT LIMITS ARM DISARM ESTOP CAL ZERO SAVECFG"));
    return;
  }
  if (equalsToken(token, "PID")) {
    char* kp = strtok(nullptr, " ");
    char* ki = strtok(nullptr, " ");
    char* kd = strtok(nullptr, " ");
    if (!kp || !ki || !kd) {
      Serial.println(F("ERR PID"));
      return;
    }
    g_kp = atof(kp);
    g_ki = atof(ki);
    g_kd = atof(kd);
    sendOk(F("PID"));
    return;
  }
  if (equalsToken(token, "MOTION")) {
    char* kv = strtok(nullptr, " ");
    char* kx = strtok(nullptr, " ");
    if (!kv || !kx) {
      Serial.println(F("ERR MOTION"));
      return;
    }
    g_kv = atof(kv);
    g_kx = atof(kx);
    g_outer_loop_enabled = fabsf(g_kv) > 0.0001f || fabsf(g_kx) > 0.0001f;
    sendOk(F("MOTION"));
    return;
  }
  if (equalsToken(token, "SETPOINT")) {
    char* deg = strtok(nullptr, " ");
    if (!deg) {
      Serial.println(F("ERR SETPOINT"));
      return;
    }
    g_set = atof(deg);
    sendOk(F("SETPOINT"));
    return;
  }
  if (equalsToken(token, "LIMITS")) {
    char* out = strtok(nullptr, " ");
    char* tip = strtok(nullptr, " ");
    char* imax = strtok(nullptr, " ");
    if (!out || !tip || !imax) {
      Serial.println(F("ERR LIMITS"));
      return;
    }
    g_limits.out_max = fabsf(atof(out));
    g_limits.tip_deg = fabsf(atof(tip));
    g_limits.i_max = fabsf(atof(imax));
    sendOk(F("LIMITS"));
    return;
  }
  if (equalsToken(token, "ARM")) {
    if (g_estop) {
      Serial.println(F("ERR ESTOP"));
      return;
    }
    g_mode = MODE_ARMED;
    sendOk(F("ARM"));
    return;
  }
  if (equalsToken(token, "DISARM")) {
    g_mode = MODE_SAFE_IDLE;
    sendOk(F("DISARM"));
    return;
  }
  if (equalsToken(token, "ESTOP")) {
    char* sub = strtok(nullptr, " ");
    if (sub && equalsToken(sub, "RESET")) {
      g_estop = false;
      sendOk(F("ESTOP RESET"));
      return;
    }
    g_estop = true;
    g_mode = MODE_SAFE_IDLE;
    sendOk(F("ESTOP LATCH"));
    return;
  }
  if (equalsToken(token, "CAL")) {
    char* sub = strtok(nullptr, " ");
    if (sub && equalsToken(sub, "ZERO")) {
      g_accel_level_offset = -g_raw;
      g_upright_trim = g_ang;
      sendOk(F("CAL ZERO"));
      return;
    }
    Serial.println(F("ERR CAL"));
    return;
  }
  if (equalsToken(token, "SAVECFG")) {
    g_last_save_ms = millis();
    sendOk(F("SAVECFG"));
    return;
  }

  Serial.println(F("ERR UNKNOWN"));
}

static void pumpSerial() {
  static char line[96];
  static size_t idx = 0;
  while (Serial.available() > 0) {
    const char c = Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      line[idx] = '\0';
      if (idx > 0) {
        processCommand(line);
      }
      idx = 0;
      continue;
    }
    if (idx + 1 < sizeof(line)) {
      line[idx++] = c;
    }
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_LED, OUTPUT);
  digitalWrite(PIN_LED, LOW);
  if (PIN_GATE_ENABLE >= 0) {
    pinMode(PIN_GATE_ENABLE, OUTPUT);
    digitalWrite(PIN_GATE_ENABLE, LOW);
  }
  g_last_loop_us = micros();
  g_last_status_ms = millis();
  Serial.println(F("# compile_upload_preflight_smoke_v1 ready"));
}

void loop() {
  const uint32_t now_us = micros();
  const uint32_t elapsed_us = now_us - g_last_loop_us;
  if (elapsed_us >= LOOP_PERIOD_US) {
    const float dt_s = elapsed_us / 1000000.0f;
    g_last_loop_us = now_us;
    updateSyntheticTelemetry(dt_s);
  }
  pumpSerial();
  const uint32_t now_ms = millis();
  if (now_ms - g_last_status_ms >= STATUS_PERIOD_MS) {
    emitStatus();
    g_last_status_ms = now_ms;
  }
}
