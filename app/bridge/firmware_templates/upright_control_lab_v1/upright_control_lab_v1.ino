/*
  upright_control_lab_v1
  Fresh UpRight.os-compatible control sketch (Arduino Nano / ATmega328P).

  Includes:
  - Anti-windup (conditional integration + back-calculation integral feedback path)
  - Integrator clamping
  - Derivative low-pass filter from cutoff frequency (with alpha coefficient telemetry)
  - Cohen-Coon PID suggestion command
  - Laplace-domain transfer function printout command
  - Left encoder on D2 (external interrupt), right encoder on D4 (PCINT)
*/

#include <Arduino.h>
#include <math.h>
#include <avr/interrupt.h>

namespace Pins {
  const uint8_t LED = LED_BUILTIN;
  const uint8_t ENC_LEFT = 2;    // INT0
  const uint8_t ENC_RIGHT = 4;   // PCINT20
}

enum Mode : uint8_t {
  MODE_SAFE = 0,
  MODE_BALANCING = 1
};

// Contract state
static float g_kp = 31.0f;
static float g_ki = 0.05f;
static float g_kd = 1.05f;
static float g_kv = 0.0f;
static float g_kx = 0.0f;
static float g_set = 0.0f;
static float g_out = 0.0f;

static float g_ang = 0.0f;
static float g_raw = 0.0f;
static float g_gyro = 0.0f;
static float g_vol_raw = 0.0f;

// PID internals
static float g_pid_err = 0.0f;
static float g_pid_p = 0.0f;
static float g_pid_i = 0.0f;
static float g_pid_d = 0.0f;
static float g_pid_u_unsat = 0.0f;
static float g_pid_u_sat = 0.0f;
static bool g_output_saturated = false;
static bool g_conditional_i = true;
static bool g_estop = false;
static Mode g_mode = MODE_SAFE;

// Limits and anti-windup
static float g_out_max = 180.0f;
static float g_tip_deg = 35.0f;
static float g_i_max = 70.0f;       // integrator state clamp
static float g_i_term_max = 120.0f; // integral term clamp after Ki
static float g_kaw = 0.25f;         // back-calc gain (integral feedback path)

static float g_i_state = 0.0f;
static float g_prev_err = 0.0f;

// Derivative LPF
static float g_d_cutoff_hz = 20.0f;
static float g_d_alpha = 1.0f;
static bool g_d_init = false;
static float g_d_unfilt = 0.0f;
static float g_d_filt = 0.0f;

// Kalman (stub-friendly but contract-correct)
static float g_kf_angle = 0.0f;
static float g_kf_bias = 0.0f;
static float g_kf_P00 = 1.0f;
static float g_kf_P01 = 0.0f;
static float g_kf_P10 = 0.0f;
static float g_kf_P11 = 1.0f;
static float g_kf_q_angle = 0.001f;
static float g_kf_q_bias = 0.003f;
static float g_kf_r_measure = 0.03f;

// Encoders
volatile long g_enc_left = 0;
volatile long g_enc_right = 0;
volatile uint8_t g_prev_port_d = 0;
static long g_prev_enc_l = 0;
static long g_prev_enc_r = 0;
static float g_wpos = 0.0f;
static float g_wspd = 0.0f;

// Command-inferred wheel direction when only one encoder channel per wheel exists.
static int8_t g_cmd_sign_l = 0;
static int8_t g_cmd_sign_r = 0;

// Timing and logging
static uint32_t g_last_loop_us = 0;
static uint32_t g_last_status_ms = 0;
static bool g_log_csv = false;
static bool g_log_t = false;
static uint32_t g_status_period_ms = 100;

static float clampf(float v, float lo, float hi) {
  if (v < lo) return lo;
  if (v > hi) return hi;
  return v;
}

static const char* modeName(Mode m) {
  return (m == MODE_BALANCING) ? "BALANCING" : "SAFE_IDLE";
}

void isrEncLeft() { g_enc_left++; }

ISR(PCINT2_vect) {
  uint8_t now_d = PIND;
  uint8_t changed = now_d ^ g_prev_port_d;
  if (changed & _BV(PD4)) {
    g_enc_right++;
  }
  g_prev_port_d = now_d;
}

// Replace with real IMU reads for hardware integration.
static float readAccelAngleDegStub() { return 0.0f; }
static float readGyroRateDpsStub() { return 0.0f; }

static void kalmanUpdate(float accel_angle_deg, float gyro_rate_dps, float dt_s) {
  if (dt_s <= 0.0f) dt_s = 0.01f;
  float rate = gyro_rate_dps - g_kf_bias;
  g_kf_angle += dt_s * rate;

  g_kf_P00 += dt_s * (dt_s * g_kf_P11 - g_kf_P01 - g_kf_P10 + g_kf_q_angle);
  g_kf_P01 -= dt_s * g_kf_P11;
  g_kf_P10 -= dt_s * g_kf_P11;
  g_kf_P11 += g_kf_q_bias * dt_s;

  float innov = accel_angle_deg - g_kf_angle;
  float S = g_kf_P00 + g_kf_r_measure;
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

// Replace with your real motor output path.
static void applyMotorOutput(float out) {
  (void)out;
  if (out > 1.0f) {
    g_cmd_sign_l = 1;
    g_cmd_sign_r = 1;
  } else if (out < -1.0f) {
    g_cmd_sign_l = -1;
    g_cmd_sign_r = -1;
  } else {
    g_cmd_sign_l = 0;
    g_cmd_sign_r = 0;
  }
}

static void emitCsv() {
  long l, r;
  noInterrupts();
  l = g_enc_left;
  r = g_enc_right;
  interrupts();

  Serial.print("CSV,");
  Serial.print(millis());
  Serial.print(',');
  Serial.print(modeName(g_mode));
  Serial.print(',');
  Serial.print(g_estop ? 1 : 0);
  Serial.print(',');
  Serial.print(g_set, 3);
  Serial.print(',');
  Serial.print(g_ang, 3);
  Serial.print(',');
  Serial.print(g_raw, 3);
  Serial.print(',');
  Serial.print(g_gyro, 3);
  Serial.print(',');
  Serial.print(g_out, 3);
  Serial.print(',');
  Serial.print(g_wspd, 3);
  Serial.print(',');
  Serial.print(g_wpos, 3);
  Serial.print(',');
  Serial.print(l);
  Serial.print(',');
  Serial.print(r);
  Serial.print(',');
  Serial.print(g_pid_i, 4);
  Serial.print(',');
  Serial.print(g_d_alpha, 5);
  Serial.println();
}

static void emitStatus() {
  long l, r;
  noInterrupts();
  l = g_enc_left;
  r = g_enc_right;
  interrupts();

  Serial.print("STATUS mode=");
  Serial.print(modeName(g_mode));
  Serial.print(" estop=");
  Serial.print(g_estop ? "1" : "0");
  Serial.print(" ang=");
  Serial.print(g_ang, 3);
  Serial.print(" raw=");
  Serial.print(g_raw, 3);
  Serial.print(" gyro=");
  Serial.print(g_gyro, 3);
  Serial.print(" set=");
  Serial.print(g_set, 3);
  Serial.print(" out=");
  Serial.print(g_out, 3);
  Serial.print(" kp=");
  Serial.print(g_kp, 4);
  Serial.print(" ki=");
  Serial.print(g_ki, 4);
  Serial.print(" kd=");
  Serial.print(g_kd, 4);
  Serial.print(" kv=");
  Serial.print(g_kv, 4);
  Serial.print(" kx=");
  Serial.print(g_kx, 4);
  Serial.print(" pid_err=");
  Serial.print(g_pid_err, 4);
  Serial.print(" pid_p=");
  Serial.print(g_pid_p, 4);
  Serial.print(" pid_i=");
  Serial.print(g_pid_i, 4);
  Serial.print(" pid_d=");
  Serial.print(g_pid_d, 4);
  Serial.print(" pid_u_unsat=");
  Serial.print(g_pid_u_unsat, 4);
  Serial.print(" pid_u_sat=");
  Serial.print(g_pid_u_sat, 4);
  Serial.print(" output_saturated=");
  Serial.print(g_output_saturated ? "1" : "0");
  Serial.print(" out_max=");
  Serial.print(g_out_max, 2);
  Serial.print(" tip_deg=");
  Serial.print(g_tip_deg, 2);
  Serial.print(" i_max=");
  Serial.print(g_i_max, 2);
  Serial.print(" i_term_max=");
  Serial.print(g_i_term_max, 2);
  Serial.print(" conditional_i=");
  Serial.print(g_conditional_i ? "1" : "0");
  Serial.print(" kaw=");
  Serial.print(g_kaw, 4);
  Serial.print(" d_cutoff_hz=");
  Serial.print(g_d_cutoff_hz, 2);
  Serial.print(" filter_alpha=");
  Serial.print(g_d_alpha, 5);
  Serial.print(" wpos=");
  Serial.print(g_wpos, 3);
  Serial.print(" wspd=");
  Serial.print(g_wspd, 3);
  Serial.print(" encL=");
  Serial.print(l);
  Serial.print(" encR=");
  Serial.print(r);
  Serial.print(" volRaw=");
  Serial.print(g_vol_raw, 0);
  Serial.println();
}

static bool parsePID(const String& s) {
  float kp, ki, kd;
  if (sscanf(s.c_str(), "PID %f %f %f", &kp, &ki, &kd) == 3) {
    g_kp = kp;
    g_ki = ki;
    g_kd = kd;
    Serial.println("OK PID");
    return true;
  }
  return false;
}

static bool parseMotion(const String& s) {
  float kv, kx;
  if (sscanf(s.c_str(), "MOTION %f %f", &kv, &kx) == 2) {
    g_kv = kv;
    g_kx = kx;
    Serial.println("OK MOTION");
    return true;
  }
  return false;
}

static bool parseSetpoint(const String& s) {
  float set;
  if (sscanf(s.c_str(), "SETPOINT %f", &set) == 1) {
    g_set = set;
    Serial.println("OK SETPOINT");
    return true;
  }
  return false;
}

static bool parseLimits(const String& s) {
  float out_max, tip_deg, i_max, i_term_max;
  if (sscanf(s.c_str(), "LIMITS %f %f %f %f", &out_max, &tip_deg, &i_max, &i_term_max) >= 3) {
    g_out_max = clampf(out_max, 20.0f, 255.0f);
    g_tip_deg = clampf(tip_deg, 5.0f, 60.0f);
    g_i_max = clampf(i_max, 1.0f, 500.0f);
    if (sscanf(s.c_str(), "LIMITS %f %f %f %f", &out_max, &tip_deg, &i_max, &i_term_max) == 4) {
      g_i_term_max = clampf(i_term_max, 1.0f, 500.0f);
    }
    Serial.println("OK LIMITS");
    return true;
  }
  return false;
}

static bool parseFilter(const String& s) {
  float cutoff_hz;
  int conditional_i;
  float kaw;
  if (sscanf(s.c_str(), "FILTER %f %d %f", &cutoff_hz, &conditional_i, &kaw) >= 2) {
    g_d_cutoff_hz = clampf(cutoff_hz, 0.1f, 120.0f);
    g_conditional_i = conditional_i != 0;
    if (sscanf(s.c_str(), "FILTER %f %d %f", &cutoff_hz, &conditional_i, &kaw) == 3) {
      g_kaw = clampf(kaw, 0.0f, 5.0f);
    }
    Serial.println("OK FILTER");
    return true;
  }
  return false;
}

static bool parseKal(const String& s) {
  float qa, qb, rm;
  if (sscanf(s.c_str(), "KAL %f %f %f", &qa, &qb, &rm) == 3) {
    g_kf_q_angle = clampf(qa, 0.000001f, 10.0f);
    g_kf_q_bias = clampf(qb, 0.000001f, 10.0f);
    g_kf_r_measure = clampf(rm, 0.000001f, 10.0f);
    Serial.println("OK KAL");
    return true;
  }
  return false;
}

static bool parseCohenCoon(const String& s) {
  float K, T, L;
  if (sscanf(s.c_str(), "CC %f %f %f", &K, &T, &L) == 3) {
    if (fabs(K) < 1e-6f || T <= 0.0f || L <= 0.0f) {
      Serial.println("ERR CC invalid_params");
      return true;
    }
    float r = L / T;
    float kp = (1.0f / K) * (T / L) * ((4.0f / 3.0f) + (r / 4.0f));
    float Ti = L * ((32.0f + 6.0f * r) / (13.0f + 8.0f * r));
    float Td = L * (4.0f / (11.0f + 2.0f * r));
    float ki = kp / Ti;
    float kd = kp * Td;
    Serial.print("CC PID kp=");
    Serial.print(kp, 5);
    Serial.print(" ki=");
    Serial.print(ki, 5);
    Serial.print(" kd=");
    Serial.println(kd, 5);
    return true;
  }
  return false;
}

static void printTransferFunctions() {
  Serial.println("TF controller C(s)=Kp + Ki/s + Kd*s/(tau_d*s+1)");
  Serial.println("TF plant_model G(s)=K/(T*s+1)*e^(-L*s)");
  Serial.println("TF closed_loop T(s)=C(s)G(s)/(1+C(s)G(s))");
}

static void handleCommand(const String& cmd_raw) {
  String cmd = cmd_raw;
  cmd.trim();
  if (cmd.length() == 0) return;

  if (cmd == "GET") { emitStatus(); return; }
  if (cmd == "ARM") {
    g_mode = MODE_BALANCING;
    g_estop = false;
    g_i_state = 0.0f;
    g_prev_err = 0.0f;
    Serial.println("OK ARM");
    return;
  }
  if (cmd == "DISARM") {
    g_mode = MODE_SAFE;
    g_out = 0.0f;
    applyMotorOutput(0.0f);
    Serial.println("OK DISARM");
    return;
  }
  if (cmd.startsWith("ESTOP ")) {
    int v = cmd.substring(6).toInt();
    g_estop = (v != 0);
    if (g_estop) g_mode = MODE_SAFE;
    Serial.println("OK ESTOP");
    return;
  }
  if (cmd == "CAL ZERO") { Serial.println("OK CAL ZERO"); return; }
  if (cmd == "SAVECFG") { Serial.println("OK SAVECFG"); return; }
  if (cmd == "IDENT") { Serial.println("UPRIGHT_CONTROL_LAB_V1"); return; }
  if (cmd == "CSVHDR") {
    Serial.println("CSV,ms,mode,estop,set,ang,raw,gyro,out,wspd,wpos,encL,encR,pid_i,filter_alpha");
    return;
  }
  if (cmd.startsWith("LOGCSV ")) {
    g_log_csv = (cmd.substring(7).toInt() != 0);
    Serial.println("OK LOGCSV");
    return;
  }
  if (cmd.startsWith("LOGT ")) {
    g_log_t = (cmd.substring(5).toInt() != 0);
    Serial.println("OK LOGT");
    return;
  }
  if (cmd.startsWith("BURSTCSV")) {
    emitCsv();
    Serial.println("OK BURSTCSV");
    return;
  }
  if (cmd == "TF") { printTransferFunctions(); return; }
  if (parsePID(cmd) || parseMotion(cmd) || parseSetpoint(cmd) || parseLimits(cmd) || parseFilter(cmd) || parseKal(cmd) || parseCohenCoon(cmd)) {
    return;
  }
  if (cmd == "HELP") {
    Serial.println("OK HELP GET ARM DISARM ESTOP PID MOTION SETPOINT LIMITS FILTER KAL CC TF CAL ZERO SAVECFG LOGCSV LOGT BURSTCSV CSVHDR IDENT");
    return;
  }
  Serial.print("ERR UNKNOWN ");
  Serial.println(cmd);
}

void setup() {
  Serial.begin(115200);
  delay(120);

  pinMode(Pins::LED, OUTPUT);
  digitalWrite(Pins::LED, LOW);
  pinMode(Pins::ENC_LEFT, INPUT_PULLUP);
  pinMode(Pins::ENC_RIGHT, INPUT_PULLUP);

  attachInterrupt(digitalPinToInterrupt(Pins::ENC_LEFT), isrEncLeft, CHANGE);

  g_prev_port_d = PIND;
  PCICR |= _BV(PCIE2);
  PCMSK2 |= _BV(PCINT20);

  g_last_loop_us = micros();
  Serial.println("UPRIGHT_CONTROL_LAB_BOOT");
}

void loop() {
  while (Serial.available() > 0) {
    String cmd = Serial.readStringUntil('\n');
    handleCommand(cmd);
  }

  uint32_t now_us = micros();
  float dt_s = (now_us - g_last_loop_us) / 1000000.0f;
  g_last_loop_us = now_us;
  if (dt_s <= 0.0f || dt_s > 0.2f) dt_s = 0.01f;

  g_raw = readAccelAngleDegStub();
  g_gyro = readGyroRateDpsStub();
  kalmanUpdate(g_raw, g_gyro, dt_s);
  g_ang = g_kf_angle;
  g_vol_raw = 0.0f;

  long l_now, r_now;
  noInterrupts();
  l_now = g_enc_left;
  r_now = g_enc_right;
  interrupts();

  long dL = l_now - g_prev_enc_l;
  long dR = r_now - g_prev_enc_r;
  g_prev_enc_l = l_now;
  g_prev_enc_r = r_now;

  float dL_signed = dL * g_cmd_sign_l;
  float dR_signed = dR * g_cmd_sign_r;
  g_wpos = 0.5f * (l_now + r_now);
  g_wspd = (0.5f * (dL_signed + dR_signed)) / dt_s;

  if (g_mode == MODE_BALANCING && !g_estop) {
    if (fabs(g_ang) > g_tip_deg) {
      g_estop = true;
      g_mode = MODE_SAFE;
      g_out = 0.0f;
      applyMotorOutput(0.0f);
    } else {
      g_pid_err = g_set - g_ang;
      g_pid_p = g_kp * g_pid_err;

      g_d_unfilt = (g_pid_err - g_prev_err) / dt_s;
      g_d_alpha = alphaFromCutoffHz(g_d_cutoff_hz, dt_s);
      if (!g_d_init) {
        g_d_filt = g_d_unfilt;
        g_d_init = true;
      } else {
        g_d_filt = lowPass(g_d_unfilt, g_d_filt, g_d_alpha);
      }
      g_pid_d = g_kd * g_d_filt;

      bool pushing_sat = g_output_saturated &&
                        ((g_pid_err > 0.0f && g_pid_u_unsat > g_out_max) ||
                         (g_pid_err < 0.0f && g_pid_u_unsat < -g_out_max));
      bool integrate_err = (!g_conditional_i) || (!pushing_sat);
      if (integrate_err) {
        g_i_state += g_pid_err * dt_s;
      }

      g_i_state = clampf(g_i_state, -g_i_max, g_i_max);
      g_pid_i = g_ki * g_i_state;
      g_pid_i = clampf(g_pid_i, -g_i_term_max, g_i_term_max);

      float motion_term = (g_kv * g_wspd) + (g_kx * g_wpos);
      g_pid_u_unsat = g_pid_p + g_pid_i + g_pid_d + motion_term;
      g_pid_u_sat = clampf(g_pid_u_unsat, -g_out_max, g_out_max);
      g_output_saturated = fabs(g_pid_u_unsat - g_pid_u_sat) > 0.001f;

      // Integral feedback path (back-calculation anti-windup).
      g_i_state += g_kaw * (g_pid_u_sat - g_pid_u_unsat) * dt_s;
      g_i_state = clampf(g_i_state, -g_i_max, g_i_max);

      g_out = g_pid_u_sat;
      applyMotorOutput(g_out);
      g_prev_err = g_pid_err;
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

  uint32_t now_ms = millis();
  if (now_ms - g_last_status_ms >= g_status_period_ms) {
    g_last_status_ms = now_ms;
    if (g_log_t) emitStatus();
    if (g_log_csv) emitCsv();
    digitalWrite(Pins::LED, !digitalRead(Pins::LED));
  }
}
