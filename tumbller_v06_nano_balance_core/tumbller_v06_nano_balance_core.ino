/*
  ELEGOO Tumbller V1.1 / BalanceCarRobot-PCB-v06
  Nano Balance Core (Production Scaffold)

  What this sketch provides:
  - MPU6050 pitch estimation with 2-state Kalman filter (angle + gyro bias)
  - PID balance controller with anti-windup and derivative-on-measurement
  - Safety state machine: SAFE_IDLE, ARMED, BALANCING, FAULT
  - TB6612 motor control with board-specific polarity map
  - Encoder ISR capture on discovered pins:
      Left encoder  -> D2
      Right encoder -> D4
  - UART protocol for ESP32 bridge (web UI / OTA / telemetry)

  Serial settings:
  - 115200 baud
  - Newline line ending

  WARNING:
  - First tests must be done with wheels off ground.
*/

#include <Arduino.h>
#include <Wire.h>
#include <MPU6050_light.h>
#include <EEPROM.h>

// ------------------------------
// Pin mapping for PCB-v06
// ------------------------------
namespace Pins {
  const uint8_t BIN1 = 12;  // Right motor direction
  const uint8_t AIN1 = 7;   // Left motor direction
  const uint8_t STBY = 8;   // TB6612 standby (HIGH = enabled)
  const uint8_t PWMB = 6;   // Right motor PWM
  const uint8_t PWMA = 5;   // Left motor PWM

  const uint8_t ENC_LEFT = 2;   // discovered by probe
  const uint8_t ENC_RIGHT = 4;  // discovered by probe

  const uint8_t MODE = 10;
  const uint8_t VOL = A2;
}

// ------------------------------
// State machine
// ------------------------------
enum ControlState : uint8_t {
  SAFE_IDLE = 0,
  ARMED = 1,
  BALANCING = 2,
  FAULT = 3
};

volatile ControlState state = SAFE_IDLE;
volatile bool estop = true;

// ------------------------------
// Encoder counters
// ------------------------------
volatile long encLeftCount = 0;
volatile long encRightCount = 0;

void isrEncLeft() { encLeftCount++; }
void isrEncRight() { encRightCount++; }

// ------------------------------
// IMU / Kalman
// ------------------------------
MPU6050 mpu(Wire);
float kalmanAngleDeg = 0.0f;
float kalmanBiasDegPerSec = 0.0f;
float P00 = 1.0f, P01 = 0.0f, P10 = 0.0f, P11 = 1.0f;

// Kalman tunables (exposed via UART)
float Q_angle = 0.001f;
float Q_bias = 0.003f;
float R_measure = 0.03f;

// ------------------------------
// PID variables
// ------------------------------
float setpointDeg = 0.0f;
float Kp = 18.0f;
float Ki = 0.0f;
float Kd = 0.8f;

float integrator = 0.0f;
float prevMeasured = 0.0f;
float pidOutput = 0.0f;
float motionOutput = 0.0f;

float outLimit = 255.0f;
float iLimit = 120.0f;
float tipCutoffDeg = 32.0f;
float Kv = 0.0f;  // velocity damping gain (counts/s -> motor cmd)
float Kx = 0.0f;  // position hold gain (counts -> motor cmd)

// ------------------------------
// Timing
// ------------------------------
uint32_t lastLoopUs = 0;
uint32_t lastTelemetryMs = 0;
const uint32_t LOOP_PERIOD_US = 5000;    // 200 Hz
const uint32_t TELEMETRY_MS = 50;        // 20 Hz
const uint32_t ARM_HOLD_MS = 800;        // must remain near upright before balancing
uint32_t armStartMs = 0;

// ------------------------------
// Test metadata / logging
// ------------------------------
bool csvLogEnabled = true;
bool tLogEnabled = true;
bool autoRunEnabled = false;
int8_t motorPolarity = 1;   // +1 normal, -1 inverted
int8_t imuPolarity = 1;     // +1 normal, -1 inverted
char imuAxis = 'Y';         // balance axis: 'X' or 'Y'
bool swapAxes = false;      // false=normal, true=use X as Y and Y as X
float angleZeroDeg = 0.0f;  // upright reference offset
uint32_t testRunId = 0;
float payloadMassG = 0.0f;
float cgHeightMm = 0.0f;
float cgOffsetMm = 0.0f;
int lastLeftCmd = 0;
int lastRightCmd = 0;
bool manualMotorActive = false;
int manualLeftCmd = 0;
int manualRightCmd = 0;
float wheelSpeedCps = 0.0f;
float wheelPosCounts = 0.0f;
float wheelPosRefCounts = 0.0f;
long prevEncLeftForMotion = 0;
long prevEncRightForMotion = 0;
bool motionEncInit = false;
bool burstCsvPending = false;
bool burstCsvActive = false;
uint16_t burstCsvTargetLines = 30;
uint16_t burstCsvSentLines = 0;
uint32_t burstCsvDelayMs = 5000;
uint32_t burstCsvBalStartMs = 0;

struct PersistedConfig {
  uint32_t magic;
  uint8_t version;
  int8_t motorPolarity;
  int8_t imuPolarity;
  char imuAxis;
  uint8_t swapAxes;
  uint8_t csvLogEnabled;
  uint8_t tLogEnabled;
  uint8_t autoRunEnabled;
  float angleZeroDeg;
  float setpointDeg;
  float Kp;
  float Ki;
  float Kd;
  float outLimit;
  float iLimit;
  float tipCutoffDeg;
  float Q_angle;
  float Q_bias;
  float R_measure;
  float Kv;
  float Kx;
};

const int EEPROM_CFG_ADDR = 0;
const uint32_t EEPROM_MAGIC = 0x42435452UL;  // "BCTR"
const uint8_t EEPROM_VERSION = 3;

// ------------------------------
// Helpers
// ------------------------------
const __FlashStringHelper* stateName(ControlState s) {
  switch (s) {
    case SAFE_IDLE: return F("SAFE_IDLE");
    case ARMED: return F("ARMED");
    case BALANCING: return F("BALANCING");
    case FAULT: return F("FAULT");
    default: return F("UNKNOWN");
  }
}

void resetControllerCore() {
  integrator = 0.0f;
  prevMeasured = kalmanAngleDeg;
  pidOutput = 0.0f;
  motionOutput = 0.0f;
  wheelSpeedCps = 0.0f;
}

void applyDefaultConfig(bool preserveCalibration = false) {
  int8_t keepMotorPol = motorPolarity;
  int8_t keepImuPol = imuPolarity;
  char keepAxis = imuAxis;
  bool keepSwap = swapAxes;
  float keepZero = angleZeroDeg;
  float keepSetpoint = setpointDeg;

  csvLogEnabled = false;
  tLogEnabled = false;
  autoRunEnabled = false;
  motorPolarity = 1;
  imuPolarity = 1;
  imuAxis = 'Y';
  swapAxes = false;
  angleZeroDeg = 0.0f;
  setpointDeg = 0.0f;
  Kp = 18.0f;
  Ki = 0.0f;
  Kd = 0.8f;
  outLimit = 255.0f;
  iLimit = 120.0f;
  tipCutoffDeg = 32.0f;
  Q_angle = 0.001f;
  Q_bias = 0.003f;
  R_measure = 0.03f;
  Kv = 0.0f;
  Kx = 0.0f;

  if (preserveCalibration) {
    motorPolarity = (keepMotorPol >= 0) ? 1 : -1;
    imuPolarity = (keepImuPol >= 0) ? 1 : -1;
    imuAxis = (keepAxis == 'X') ? 'X' : 'Y';
    swapAxes = keepSwap;
    angleZeroDeg = keepZero;
    setpointDeg = keepSetpoint;
  }
}

void saveConfigToEeprom() {
  PersistedConfig cfg;
  cfg.magic = EEPROM_MAGIC;
  cfg.version = EEPROM_VERSION;
  cfg.motorPolarity = (motorPolarity >= 0) ? 1 : -1;
  cfg.imuPolarity = (imuPolarity >= 0) ? 1 : -1;
  cfg.imuAxis = (imuAxis == 'X') ? 'X' : 'Y';
  cfg.swapAxes = swapAxes ? 1 : 0;
  cfg.csvLogEnabled = csvLogEnabled ? 1 : 0;
  cfg.tLogEnabled = tLogEnabled ? 1 : 0;
  cfg.autoRunEnabled = autoRunEnabled ? 1 : 0;
  cfg.angleZeroDeg = angleZeroDeg;
  cfg.setpointDeg = setpointDeg;
  cfg.Kp = Kp;
  cfg.Ki = Ki;
  cfg.Kd = Kd;
  cfg.outLimit = outLimit;
  cfg.iLimit = iLimit;
  cfg.tipCutoffDeg = tipCutoffDeg;
  cfg.Q_angle = Q_angle;
  cfg.Q_bias = Q_bias;
  cfg.R_measure = R_measure;
  cfg.Kv = Kv;
  cfg.Kx = Kx;
  EEPROM.put(EEPROM_CFG_ADDR, cfg);
}

bool loadConfigFromEeprom() {
  PersistedConfig cfg;
  EEPROM.get(EEPROM_CFG_ADDR, cfg);
  if (cfg.magic != EEPROM_MAGIC || cfg.version != EEPROM_VERSION) return false;

  motorPolarity = (cfg.motorPolarity >= 0) ? 1 : -1;
  imuPolarity = (cfg.imuPolarity >= 0) ? 1 : -1;
  imuAxis = (cfg.imuAxis == 'X') ? 'X' : 'Y';
  swapAxes = (cfg.swapAxes != 0);
  csvLogEnabled = (cfg.csvLogEnabled != 0);
  tLogEnabled = (cfg.tLogEnabled != 0);
  autoRunEnabled = (cfg.autoRunEnabled != 0);
  angleZeroDeg = cfg.angleZeroDeg;
  setpointDeg = cfg.setpointDeg;
  Kp = max(0.0f, cfg.Kp);
  Ki = max(0.0f, cfg.Ki);
  Kd = max(0.0f, cfg.Kd);
  outLimit = constrain(cfg.outLimit, 40.0f, 255.0f);
  iLimit = constrain(cfg.iLimit, 10.0f, 255.0f);
  tipCutoffDeg = constrain(cfg.tipCutoffDeg, 10.0f, 45.0f);
  Q_angle = max(0.000001f, cfg.Q_angle);
  Q_bias = max(0.000001f, cfg.Q_bias);
  R_measure = max(0.0001f, cfg.R_measure);
  Kv = max(0.0f, cfg.Kv);
  Kx = max(0.0f, cfg.Kx);
  return true;
}

float readAccelAngleDeg() {
  if (!swapAxes) return (imuAxis == 'X') ? mpu.getAngleX() : mpu.getAngleY();
  return (imuAxis == 'X') ? mpu.getAngleY() : mpu.getAngleX();
}

float readGyroRateDegPerSec() {
  if (!swapAxes) return (imuAxis == 'X') ? mpu.getGyroX() : mpu.getGyroY();
  return (imuAxis == 'X') ? mpu.getGyroY() : mpu.getGyroX();
}

void motorStop() {
  analogWrite(Pins::PWMA, 0);
  analogWrite(Pins::PWMB, 0);
  digitalWrite(Pins::STBY, LOW);
}

void setMotorSigned(int leftCmd, int rightCmd) {
  leftCmd *= motorPolarity;
  rightCmd *= motorPolarity;
  leftCmd = constrain(leftCmd, -255, 255);
  rightCmd = constrain(rightCmd, -255, 255);
  lastLeftCmd = leftCmd;
  lastRightCmd = rightCmd;

  // Board behavior discovered: dir LOW = forward, dir HIGH = backward
  // `motorPolarity` lets us flip this live without reflashing.
  bool leftBackward = (leftCmd > 0);
  bool rightBackward = (rightCmd > 0);

  digitalWrite(Pins::AIN1, leftBackward ? HIGH : LOW);
  digitalWrite(Pins::BIN1, rightBackward ? HIGH : LOW);

  int leftPwm = abs(leftCmd);
  int rightPwm = abs(rightCmd);

  if (leftPwm == 0 && rightPwm == 0) {
    motorStop();
    return;
  }

  digitalWrite(Pins::STBY, HIGH);
  analogWrite(Pins::PWMA, leftPwm);
  analogWrite(Pins::PWMB, rightPwm);
}

float kalmanUpdate(float measuredAngleDeg, float gyroRateDegPerSec, float dtSec) {
  // Predict
  float rate = gyroRateDegPerSec - kalmanBiasDegPerSec;
  kalmanAngleDeg += dtSec * rate;

  P00 += dtSec * (dtSec * P11 - P01 - P10 + Q_angle);
  P01 -= dtSec * P11;
  P10 -= dtSec * P11;
  P11 += Q_bias * dtSec;

  // Update
  float innovation = measuredAngleDeg - kalmanAngleDeg;
  float S = P00 + R_measure;
  float K0 = P00 / S;
  float K1 = P10 / S;

  kalmanAngleDeg += K0 * innovation;
  kalmanBiasDegPerSec += K1 * innovation;

  float P00_temp = P00;
  float P01_temp = P01;
  P00 -= K0 * P00_temp;
  P01 -= K0 * P01_temp;
  P10 -= K1 * P00_temp;
  P11 -= K1 * P01_temp;

  return kalmanAngleDeg;
}

void enterState(ControlState next) {
  if (state == next) return;
  state = next;

  if (next == SAFE_IDLE || next == FAULT) {
    estop = true;
    manualMotorActive = false;
    motorStop();
    resetControllerCore();
    motionEncInit = false;
  } else if (next == ARMED) {
    estop = false;
    manualMotorActive = false;
    motorStop();
    resetControllerCore();
    motionEncInit = false;
    armStartMs = millis();
  } else if (next == BALANCING) {
    estop = false;
    resetControllerCore();
    noInterrupts();
    prevEncLeftForMotion = encLeftCount;
    prevEncRightForMotion = encRightCount;
    interrupts();
    wheelPosRefCounts = 0.5f * (prevEncLeftForMotion + prevEncRightForMotion);
    motionEncInit = true;
    if (burstCsvPending) {
      burstCsvActive = true;
      burstCsvSentLines = 0;
      burstCsvBalStartMs = millis();
      Serial.print(F("BURSTCSV ARMED delay_ms="));
      Serial.print(burstCsvDelayMs);
      Serial.print(F(" lines="));
      Serial.println(burstCsvTargetLines);
    }
  }

  if (next != BALANCING && burstCsvActive) {
    burstCsvActive = false;
    burstCsvPending = false;
    Serial.println(F("BURSTCSV CANCELED (left BALANCING)."));
  }

  Serial.print(F("STATE "));
  Serial.println(stateName(next));
}

void printBootConfig() {
  Serial.println(F("CFG pins: AIN1=D7 BIN1=D12 PWMA=D5 PWMB=D6 STBY=D8"));
  Serial.println(F("CFG encoders: LEFT=D2 RIGHT=D4"));
  Serial.println(F("CFG dir map: LOW=forward HIGH=backward"));
}

void printHelp() {
  Serial.println(F("\nCommands:"));
  Serial.println(F("  HELP"));
  Serial.println(F("  GET"));
  Serial.println(F("  ARM"));
  Serial.println(F("  DISARM"));
  Serial.println(F("  ESTOP 1|0"));
  Serial.println(F("  STATE SAFE|ARM|BAL|FAULT"));
  Serial.println(F("  PID <kp> <ki> <kd>"));
  Serial.println(F("  MOTION <kv> <kx>"));
  Serial.println(F("  KAL <q_angle> <q_bias> <r_measure>"));
  Serial.println(F("  SETPOINT <deg>"));
  Serial.println(F("  LIMITS <outMax> <tipDeg> <iMax>"));
  Serial.println(F("  MOTOR <left -255..255> <right -255..255>"));
  Serial.println(F("  MOTOROFF"));
  Serial.println(F("  MOTORPOL <1|-1>"));
  Serial.println(F("  IMUPOL <1|-1>"));
  Serial.println(F("  AXIS <X|Y>"));
  Serial.println(F("  SWAPAXIS 1|0"));
  Serial.println(F("  ZERO"));
  Serial.println(F("  SAVEZERO"));
  Serial.println(F("  LOADZERO"));
  Serial.println(F("  CLRZERO"));
  Serial.println(F("  SAVECFG"));
  Serial.println(F("  LOADCFG"));
  Serial.println(F("  DEFAULTCFG"));
  Serial.println(F("  AUTORUN 1|0"));
  Serial.println(F("  META <runId> <payload_g> <cg_h_mm> <cg_off_mm>"));
  Serial.println(F("  LOGCSV 1|0"));
  Serial.println(F("  LOGT 1|0"));
  Serial.println(F("  BURSTCSV [delay_ms lines]"));
  Serial.println(F("  CSVHDR"));
  Serial.println(F("  ENC_RESET"));
}

void printCsvHeader() {
  Serial.println(F("CSV,ms,run_id,state,estop,setpoint_deg,angle_kf_deg,angle_acc_deg,gyro_dps,pid_out,motion_out,wheel_spd_cps,wheel_pos_cnt,left_cmd,right_cmd,enc_l,enc_r,vol_raw,kp,ki,kd,kv,kx,q_angle,q_bias,r_measure,payload_g,cg_h_mm,cg_off_mm"));
}

void printStatus() {
  long l, r;
  noInterrupts();
  l = encLeftCount;
  r = encRightCount;
  interrupts();

  Serial.print(F("STATUS state="));
  Serial.print(stateName(state));
  Serial.print(F(" estop="));
  Serial.print(estop ? 1 : 0);
  Serial.print(F(" ang="));
  Serial.print((imuPolarity * kalmanAngleDeg) - angleZeroDeg, 3);
  Serial.print(F(" raw="));
  Serial.print(kalmanAngleDeg, 3);
  Serial.print(F(" bias="));
  Serial.print(kalmanBiasDegPerSec, 3);
  Serial.print(F(" out="));
  Serial.print(pidOutput, 2);
  Serial.print(F(" kp="));
  Serial.print(Kp, 3);
  Serial.print(F(" ki="));
  Serial.print(Ki, 3);
  Serial.print(F(" kd="));
  Serial.print(Kd, 3);
  Serial.print(F(" kv="));
  Serial.print(Kv, 3);
  Serial.print(F(" kx="));
  Serial.print(Kx, 4);
  Serial.print(F(" qA="));
  Serial.print(Q_angle, 5);
  Serial.print(F(" qB="));
  Serial.print(Q_bias, 5);
  Serial.print(F(" rM="));
  Serial.print(R_measure, 5);
  Serial.print(F(" encL="));
  Serial.print(l);
  Serial.print(F(" encR="));
  Serial.print(r);
  Serial.print(F(" volRaw="));
  Serial.print(analogRead(Pins::VOL));
  Serial.print(F(" runId="));
  Serial.print(testRunId);
  Serial.print(F(" payloadG="));
  Serial.print(payloadMassG, 1);
  Serial.print(F(" cgH="));
  Serial.print(cgHeightMm, 1);
  Serial.print(F(" cgOff="));
  Serial.print(cgOffsetMm, 1);
  Serial.print(F(" csv="));
  Serial.print(csvLogEnabled ? 1 : 0);
  Serial.print(F(" tlog="));
  Serial.print(tLogEnabled ? 1 : 0);
  Serial.print(F(" mpol="));
  Serial.print(motorPolarity);
  Serial.print(F(" ipol="));
  Serial.print(imuPolarity);
  Serial.print(F(" axis="));
  Serial.print(imuAxis);
  Serial.print(F(" swap="));
  Serial.print(swapAxes ? 1 : 0);
  Serial.print(F(" zero="));
  Serial.print(angleZeroDeg, 3);
  Serial.print(F(" sp="));
  Serial.print(setpointDeg, 3);
  Serial.print(F(" autorun="));
  Serial.print(autoRunEnabled ? 1 : 0);
  Serial.print(F(" burst="));
  Serial.print(burstCsvPending ? 1 : 0);
  Serial.print(F(" bcnt="));
  Serial.print(burstCsvSentLines);
  Serial.print(F("/"));
  Serial.println(burstCsvTargetLines);
}

String readLine() {
  static String line;
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      String out = line;
      line = "";
      out.trim();
      return out;
    }
    line += c;
    if (line.length() > 160) line.remove(160);
  }
  return "";
}

bool parse3Floats(const String& s, float& a, float& b, float& c) {
  int p1 = s.indexOf(' ');
  if (p1 < 0) return false;
  int p2 = s.indexOf(' ', p1 + 1);
  if (p2 < 0) return false;
  int p3 = s.indexOf(' ', p2 + 1);
  if (p3 < 0) return false;
  String sa = s.substring(p1 + 1, p2);
  String sb = s.substring(p2 + 1, p3);
  String sc = s.substring(p3 + 1);
  a = sa.toFloat();
  b = sb.toFloat();
  c = sc.toFloat();
  return true;
}

bool parse2Ints(const String& s, int& a, int& b) {
  int p1 = s.indexOf(' ');
  if (p1 < 0) return false;
  int p2 = s.indexOf(' ', p1 + 1);
  if (p2 < 0) return false;
  a = s.substring(p1 + 1, p2).toInt();
  b = s.substring(p2 + 1).toInt();
  return true;
}

bool parse2Floats(const String& s, float& a, float& b) {
  int p1 = s.indexOf(' ');
  if (p1 < 0) return false;
  int p2 = s.indexOf(' ', p1 + 1);
  if (p2 < 0) return false;
  a = s.substring(p1 + 1, p2).toFloat();
  b = s.substring(p2 + 1).toFloat();
  return true;
}

bool parse1Int3Floats(const String& s, int& id, float& a, float& b, float& c) {
  int p1 = s.indexOf(' ');
  if (p1 < 0) return false;
  int p2 = s.indexOf(' ', p1 + 1);
  if (p2 < 0) return false;
  int p3 = s.indexOf(' ', p2 + 1);
  if (p3 < 0) return false;
  int p4 = s.indexOf(' ', p3 + 1);
  if (p4 < 0) return false;
  id = s.substring(p1 + 1, p2).toInt();
  a = s.substring(p2 + 1, p3).toFloat();
  b = s.substring(p3 + 1, p4).toFloat();
  c = s.substring(p4 + 1).toFloat();
  return true;
}

void handleCommand(const String& cmd) {
  if (cmd == "HELP") {
    printHelp();
  } else if (cmd == "GET") {
    printStatus();
  } else if (cmd == "ARM") {
    enterState(ARMED);
  } else if (cmd == "DISARM") {
    enterState(SAFE_IDLE);
  } else if (cmd.startsWith("ESTOP ")) {
    int v = cmd.substring(6).toInt();
    estop = (v != 0);
    if (estop) {
      enterState(FAULT);
    } else if (state == FAULT || state == SAFE_IDLE) {
      enterState(ARMED);
    }
  } else if (cmd.startsWith("STATE ")) {
    String s = cmd.substring(6);
    if (s == "SAFE") enterState(SAFE_IDLE);
    else if (s == "ARM") enterState(ARMED);
    else if (s == "BAL") enterState(BALANCING);
    else if (s == "FAULT") enterState(FAULT);
  } else if (cmd.startsWith("PID ")) {
    float a, b, c;
    if (parse3Floats(cmd, a, b, c)) {
      Kp = max(0.0f, a);
      Ki = max(0.0f, b);
      Kd = max(0.0f, c);
      resetControllerCore();
      Serial.print(F("OK PID "));
      Serial.print(Kp, 4); Serial.print(' ');
      Serial.print(Ki, 4); Serial.print(' ');
      Serial.println(Kd, 4);
    }
  } else if (cmd.startsWith("MOTION ")) {
    float a, b;
    if (parse2Floats(cmd, a, b)) {
      Kv = max(0.0f, a);
      Kx = max(0.0f, b);
      saveConfigToEeprom();
      Serial.print(F("OK MOTION "));
      Serial.print(Kv, 4); Serial.print(' ');
      Serial.println(Kx, 4);
    } else {
      Serial.println(F("ERR MOTION format"));
    }
  } else if (cmd.startsWith("KAL ")) {
    float a, b, c;
    if (parse3Floats(cmd, a, b, c)) {
      Q_angle = max(0.000001f, a);
      Q_bias = max(0.000001f, b);
      R_measure = max(0.0001f, c);
      Serial.print(F("OK KAL "));
      Serial.print(Q_angle, 6); Serial.print(' ');
      Serial.print(Q_bias, 6); Serial.print(' ');
      Serial.println(R_measure, 6);
    }
  } else if (cmd.startsWith("SETPOINT ")) {
    setpointDeg = cmd.substring(9).toFloat();
    saveConfigToEeprom();
    Serial.print(F("OK SETPOINT "));
    Serial.println(setpointDeg, 3);
  } else if (cmd.startsWith("LIMITS ")) {
    float a, b, c;
    if (parse3Floats(cmd, a, b, c)) {
      outLimit = constrain(a, 40.0f, 255.0f);
      tipCutoffDeg = constrain(b, 10.0f, 45.0f);
      iLimit = constrain(c, 10.0f, 255.0f);
      Serial.println(F("OK LIMITS"));
    }
  } else if (cmd.startsWith("MOTOR ")) {
    int l, r;
    if (parse2Ints(cmd, l, r)) {
      if (state == SAFE_IDLE || state == ARMED) {
        manualLeftCmd = l;
        manualRightCmd = r;
        manualMotorActive = true;
        setMotorSigned(manualLeftCmd, manualRightCmd);
        Serial.println(F("OK MOTOR"));
      } else {
        Serial.println(F("ERR MOTOR only SAFE/ARM"));
      }
    }
  } else if (cmd == "MOTOROFF") {
    manualMotorActive = false;
    setMotorSigned(0, 0);
    Serial.println(F("OK MOTOROFF"));
  } else if (cmd.startsWith("MOTORPOL ")) {
    int v = cmd.substring(9).toInt();
    motorPolarity = (v >= 0) ? 1 : -1;
    saveConfigToEeprom();
    Serial.print(F("OK MOTORPOL "));
    Serial.println(motorPolarity);
  } else if (cmd.startsWith("IMUPOL ")) {
    int v = cmd.substring(7).toInt();
    imuPolarity = (v >= 0) ? 1 : -1;
    saveConfigToEeprom();
    Serial.print(F("OK IMUPOL "));
    Serial.println(imuPolarity);
  } else if (cmd.startsWith("AXIS ")) {
    String ax = cmd.substring(5);
    ax.toUpperCase();
    if (ax == "X" || ax == "Y") {
      imuAxis = ax.charAt(0);
      // Re-seed Kalman angle to avoid transient jump when changing axis.
      mpu.update();
      kalmanAngleDeg = readAccelAngleDeg();
      prevMeasured = kalmanAngleDeg;
      integrator = 0.0f;
      saveConfigToEeprom();
      Serial.print(F("OK AXIS "));
      Serial.println(imuAxis);
    } else {
      Serial.println(F("ERR AXIS use X or Y"));
    }
  } else if (cmd.startsWith("SWAPAXIS ")) {
    int v = cmd.substring(9).toInt();
    swapAxes = (v != 0);
    mpu.update();
    kalmanAngleDeg = readAccelAngleDeg();
    prevMeasured = kalmanAngleDeg;
    integrator = 0.0f;
    saveConfigToEeprom();
    Serial.print(F("OK SWAPAXIS "));
    Serial.println(swapAxes ? 1 : 0);
  } else if (cmd == "ZERO") {
    angleZeroDeg = imuPolarity * kalmanAngleDeg;
    saveConfigToEeprom();
    Serial.print(F("OK ZERO "));
    Serial.println(angleZeroDeg, 4);
  } else if (cmd == "SAVEZERO") {
    saveConfigToEeprom();
    Serial.print(F("OK SAVEZERO "));
    Serial.println(angleZeroDeg, 4);
  } else if (cmd == "LOADZERO") {
    if (loadConfigFromEeprom()) {
      Serial.print(F("OK LOADZERO "));
      Serial.println(angleZeroDeg, 4);
    } else {
      Serial.println(F("ERR LOADZERO none"));
    }
  } else if (cmd == "CLRZERO") {
    angleZeroDeg = 0.0f;
    saveConfigToEeprom();
    Serial.println(F("OK CLRZERO"));
  } else if (cmd == "SAVECFG") {
    saveConfigToEeprom();
    Serial.println(F("OK SAVECFG"));
  } else if (cmd == "LOADCFG") {
    if (loadConfigFromEeprom()) {
      mpu.update();
      kalmanAngleDeg = readAccelAngleDeg();
      prevMeasured = kalmanAngleDeg;
      integrator = 0.0f;
      Serial.println(F("OK LOADCFG"));
    } else {
      Serial.println(F("ERR LOADCFG none"));
    }
  } else if (cmd == "DEFAULTCFG") {
    applyDefaultConfig(true);
    mpu.update();
    kalmanAngleDeg = readAccelAngleDeg();
    prevMeasured = kalmanAngleDeg;
    integrator = 0.0f;
    saveConfigToEeprom();
    Serial.println(F("OK DEFAULTCFG"));
  } else if (cmd.startsWith("AUTORUN ")) {
    int v = cmd.substring(8).toInt();
    autoRunEnabled = (v != 0);
    saveConfigToEeprom();
    Serial.print(F("OK AUTORUN "));
    Serial.println(autoRunEnabled ? 1 : 0);
  } else if (cmd.startsWith("META ")) {
    int id = 0;
    float m = 0.0f, h = 0.0f, o = 0.0f;
    if (parse1Int3Floats(cmd, id, m, h, o)) {
      testRunId = (uint32_t)max(0, id);
      payloadMassG = m;
      cgHeightMm = h;
      cgOffsetMm = o;
      Serial.print(F("OK META "));
      Serial.print(testRunId);
      Serial.print(' ');
      Serial.print(payloadMassG, 2);
      Serial.print(' ');
      Serial.print(cgHeightMm, 2);
      Serial.print(' ');
      Serial.println(cgOffsetMm, 2);
    } else {
      Serial.println(F("ERR META format"));
    }
  } else if (cmd.startsWith("LOGCSV ")) {
    int v = cmd.substring(7).toInt();
    csvLogEnabled = (v != 0);
    Serial.print(F("OK LOGCSV "));
    Serial.println(csvLogEnabled ? 1 : 0);
  } else if (cmd.startsWith("LOGT ")) {
    int v = cmd.substring(5).toInt();
    tLogEnabled = (v != 0);
    Serial.print(F("OK LOGT "));
    Serial.println(tLogEnabled ? 1 : 0);
  } else if (cmd.startsWith("BURSTCSV")) {
    uint32_t delayMs = 5000;
    uint16_t lines = 30;
    int p1 = cmd.indexOf(' ');
    if (p1 > 0) {
      int p2 = cmd.indexOf(' ', p1 + 1);
      if (p2 > p1) {
        delayMs = (uint32_t)max(0, cmd.substring(p1 + 1, p2).toInt());
        lines = (uint16_t)constrain(cmd.substring(p2 + 1).toInt(), 1, 500);
      }
    }
    burstCsvDelayMs = delayMs;
    burstCsvTargetLines = lines;
    burstCsvSentLines = 0;
    burstCsvPending = true;
    burstCsvActive = (state == BALANCING);
    burstCsvBalStartMs = burstCsvActive ? millis() : 0;
    Serial.print(F("OK BURSTCSV delay_ms="));
    Serial.print(burstCsvDelayMs);
    Serial.print(F(" lines="));
    Serial.println(burstCsvTargetLines);
  } else if (cmd == "CSVHDR") {
    printCsvHeader();
  } else if (cmd == "ENC_RESET") {
    noInterrupts();
    encLeftCount = 0;
    encRightCount = 0;
    interrupts();
    Serial.println(F("OK ENC_RESET"));
  } else if (cmd.length() > 0) {
    Serial.println(F("ERR UNKNOWN"));
  }
}

void setup() {
  Serial.begin(115200);
  delay(250);
  Serial.println(F("\nTumbller Nano Balance Core boot"));

  applyDefaultConfig();
  bool cfgLoaded = loadConfigFromEeprom();

  pinMode(Pins::AIN1, OUTPUT);
  pinMode(Pins::BIN1, OUTPUT);
  pinMode(Pins::STBY, OUTPUT);
  pinMode(Pins::PWMA, OUTPUT);
  pinMode(Pins::PWMB, OUTPUT);
  pinMode(Pins::MODE, INPUT_PULLUP);
  pinMode(Pins::VOL, INPUT);

  pinMode(Pins::ENC_LEFT, INPUT_PULLUP);
  pinMode(Pins::ENC_RIGHT, INPUT_PULLUP);

  attachInterrupt(digitalPinToInterrupt(Pins::ENC_LEFT), isrEncLeft, CHANGE);
  attachInterrupt(digitalPinToInterrupt(Pins::ENC_RIGHT), isrEncRight, CHANGE);

  motorStop();

  Wire.begin();
  byte imuStatus = mpu.begin();
  Serial.print(F("MPU status="));
  Serial.println(imuStatus);
  if (imuStatus != 0) {
    Serial.println(F("FAULT: MPU init failed"));
    enterState(FAULT);
  } else {
    Serial.println(F("Calibrating gyro offsets. Keep still..."));
    delay(800);
    mpu.calcOffsets();
    mpu.update();
    kalmanAngleDeg = readAccelAngleDeg();
    prevMeasured = kalmanAngleDeg;
    if (cfgLoaded) {
      Serial.println(F("Loaded CFG from EEPROM."));
    } else {
      Serial.println(F("No saved CFG in EEPROM (using defaults)."));
    }
    Serial.println(F("IMU ready"));
    enterState(SAFE_IDLE);
    if (autoRunEnabled) {
      Serial.println(F("AUTORUN enabled -> ARM"));
      enterState(ARMED);
    }
  }

  printBootConfig();
  printHelp();
  printCsvHeader();

  lastLoopUs = micros();
  lastTelemetryMs = millis();
}

void loop() {
  String cmd = readLine();
  if (cmd.length()) handleCommand(cmd);

  uint32_t nowUs = micros();
  if ((uint32_t)(nowUs - lastLoopUs) < LOOP_PERIOD_US) return;

  float dt = (nowUs - lastLoopUs) * 1e-6f;
  lastLoopUs = nowUs;

  mpu.update();
  float accelAngleDeg = readAccelAngleDeg();
  float gyroRateDegPerSec = readGyroRateDegPerSec();
  float rawAngleDeg = imuPolarity * kalmanUpdate(accelAngleDeg, gyroRateDegPerSec, dt);
  float angleDeg = rawAngleDeg - angleZeroDeg;

  long lNow, rNow;
  noInterrupts();
  lNow = encLeftCount;
  rNow = encRightCount;
  interrupts();

  if (!motionEncInit) {
    prevEncLeftForMotion = lNow;
    prevEncRightForMotion = rNow;
    motionEncInit = true;
  }

  long dL = lNow - prevEncLeftForMotion;
  long dR = rNow - prevEncRightForMotion;
  prevEncLeftForMotion = lNow;
  prevEncRightForMotion = rNow;

  wheelPosCounts = 0.5f * (lNow + rNow);
  wheelSpeedCps = (0.5f * (dL + dR)) / dt;

  if (abs(angleDeg) > tipCutoffDeg) {
    if (state == BALANCING || state == ARMED) {
      Serial.println(F("FAULT tip cutoff"));
      enterState(FAULT);
    }
  }

  if (state == ARMED) {
    if (abs(angleDeg) < 6.0f) {
      if (millis() - armStartMs >= ARM_HOLD_MS) {
        enterState(BALANCING);
      }
    } else {
      armStartMs = millis();
    }
  }

  if ((state == SAFE_IDLE || state == ARMED) && manualMotorActive) {
    setMotorSigned(manualLeftCmd, manualRightCmd);
  } else if (state == BALANCING && !estop) {
    float error = setpointDeg - angleDeg;

    // Integrator with clamp anti-windup
    integrator += Ki * error * dt;
    integrator = constrain(integrator, -iLimit, iLimit);

    // Derivative on measurement to reduce kick
    float derivative = -(angleDeg - prevMeasured) / dt;
    prevMeasured = angleDeg;

    float posError = wheelPosRefCounts - wheelPosCounts;
    motionOutput = (-Kv * wheelSpeedCps) + (Kx * posError);
    float u = Kp * error + integrator + Kd * derivative + motionOutput;
    pidOutput = constrain(u, -outLimit, outLimit);

    int motor = (int)pidOutput;
    setMotorSigned(motor, motor);
  } else {
    manualMotorActive = false;
    motionOutput = 0.0f;
    setMotorSigned(0, 0);
  }

  if (millis() - lastTelemetryMs >= TELEMETRY_MS) {
    lastTelemetryMs = millis();

    long l = lNow;
    long r = rNow;

    if (tLogEnabled) {
      // Compact machine-readable line for ESP32 parser
      Serial.print(F("T "));
      Serial.print((int)state); Serial.print(' ');
      Serial.print(estop ? 1 : 0); Serial.print(' ');
      Serial.print(setpointDeg, 3); Serial.print(' ');
      Serial.print(angleDeg, 3); Serial.print(' ');
      Serial.print(pidOutput, 2); Serial.print(' ');
      Serial.print(motionOutput, 2); Serial.print(' ');
      Serial.print(wheelSpeedCps, 2); Serial.print(' ');
      Serial.print(wheelPosCounts, 1); Serial.print(' ');
      Serial.print(Kp, 3); Serial.print(' ');
      Serial.print(Ki, 3); Serial.print(' ');
      Serial.print(Kd, 3); Serial.print(' ');
      Serial.print(Kv, 3); Serial.print(' ');
      Serial.print(Kx, 4); Serial.print(' ');
      Serial.print(Q_angle, 5); Serial.print(' ');
      Serial.print(Q_bias, 5); Serial.print(' ');
      Serial.print(R_measure, 5); Serial.print(' ');
      Serial.print(l); Serial.print(' ');
      Serial.print(r); Serial.print(' ');
      Serial.println(analogRead(Pins::VOL));
    }

    bool emitBurstCsv = false;
    if (burstCsvActive) {
      if ((millis() - burstCsvBalStartMs) >= burstCsvDelayMs && burstCsvSentLines < burstCsvTargetLines) {
        emitBurstCsv = true;
        burstCsvSentLines++;
        if (burstCsvSentLines >= burstCsvTargetLines) {
          burstCsvActive = false;
          burstCsvPending = false;
          Serial.println(F("BURSTCSV DONE"));
        }
      }
    }

    if (csvLogEnabled || emitBurstCsv) {
      Serial.print(F("CSV,"));
      Serial.print(millis()); Serial.print(',');
      Serial.print(testRunId); Serial.print(',');
      Serial.print((int)state); Serial.print(',');
      Serial.print(estop ? 1 : 0); Serial.print(',');
      Serial.print(setpointDeg, 3); Serial.print(',');
      Serial.print(angleDeg, 3); Serial.print(',');
      Serial.print(accelAngleDeg, 3); Serial.print(',');
      Serial.print(gyroRateDegPerSec, 3); Serial.print(',');
      Serial.print(pidOutput, 2); Serial.print(',');
      Serial.print(motionOutput, 2); Serial.print(',');
      Serial.print(wheelSpeedCps, 2); Serial.print(',');
      Serial.print(wheelPosCounts, 1); Serial.print(',');
      Serial.print(lastLeftCmd); Serial.print(',');
      Serial.print(lastRightCmd); Serial.print(',');
      Serial.print(l); Serial.print(',');
      Serial.print(r); Serial.print(',');
      Serial.print(analogRead(Pins::VOL)); Serial.print(',');
      Serial.print(Kp, 3); Serial.print(',');
      Serial.print(Ki, 3); Serial.print(',');
      Serial.print(Kd, 3); Serial.print(',');
      Serial.print(Kv, 3); Serial.print(',');
      Serial.print(Kx, 4); Serial.print(',');
      Serial.print(Q_angle, 5); Serial.print(',');
      Serial.print(Q_bias, 5); Serial.print(',');
      Serial.print(R_measure, 5); Serial.print(',');
      Serial.print(payloadMassG, 2); Serial.print(',');
      Serial.print(cgHeightMm, 2); Serial.print(',');
      Serial.println(cgOffsetMm, 2);
    }
  }
}
