ARDUINO N/*
  Tumbller V2 - Repeatable Balance Controller

  Goals:
  - Deterministic state machine
  - Cascaded control loops (angle + motion damping/hold)
  - Persistent config and calibration
  - Minimal command interface for factory-like bring-up

  Board: Arduino Nano (ATmega328P)
  IMU: MPU6050 (MPU6050_light)
  Driver: TB6612 (AIN1/BIN1/PWMA/PWMB/STBY)
*/

#include <Arduino.h>
#include <Wire.h>
#include <EEPROM.h>
#include <MPU6050_light.h>

namespace Pins {
  const uint8_t BIN1 = 12;
  const uint8_t AIN1 = 7;
  const uint8_t STBY = 8;
  const uint8_t PWMB = 6;
  const uint8_t PWMA = 5;
  const uint8_t ENC_LEFT = 2;
  const uint8_t ENC_RIGHT = 4;
  const uint8_t VOL = A2;
}

enum Mode : uint8_t {
  SAFE_IDLE = 0,
  ARMED = 1,
  BALANCING = 2,
  FAULT = 3,
  CALIBRATING = 4
};

volatile long encLeft = 0;
volatile long encRight = 0;
void isrEncLeft() { encLeft++; }
void isrEncRight() { encRight++; }

MPU6050 mpu(Wire);

struct ConfigV2 {
  uint32_t magic;
  uint8_t version;

  int8_t motorPolarity;
  int8_t imuPolarity;
  char imuAxis;
  uint8_t swapAxes;

  float angleZeroDeg;
  float setpointDeg;

  float kp;
  float ki;
  float kd;
  float kv;
  float kx;

  float outLimit;
  float iLimit;
  float tipDeg;
  uint8_t deadbandPwm;

  float qAngle;
  float qBias;
  float rMeasure;

  uint8_t autoRun;
  uint8_t csvLog;
  uint8_t tLog;
  uint8_t encMode;  // 0=AUTO, 1=LEFT, 2=RIGHT
};

ConfigV2 cfg;

const uint32_t CFG_MAGIC = 0x56324243UL;  // "V2BC"
const uint8_t CFG_VERSION = 2;
const int EEPROM_ADDR = 0;

Mode mode = SAFE_IDLE;
bool estop = true;

// Kalman state
float kfAngle = 0.0f;
float kfBias = 0.0f;
float P00 = 1.0f, P01 = 0.0f, P10 = 0.0f, P11 = 1.0f;

// Loop state
float angleCtrlDeg = 0.0f;
float accelAngleDeg = 0.0f;
float gyroRateDps = 0.0f;
float angleOut = 0.0f;
float motionOut = 0.0f;
float integrator = 0.0f;
float prevAngle = 0.0f;

// Motion loop state
float wheelPos = 0.0f;
float wheelSpeed = 0.0f;
float posRef = 0.0f;
long prevEncL = 0;
long prevEncR = 0;
bool encSeeded = false;
float cmdVel = 0.0f;

// Manual motor test
bool manualMotor = false;
int manualL = 0;
int manualR = 0;

// Timers
uint32_t lastLoopUs = 0;
uint32_t lastTelMs = 0;
const uint32_t LOOP_US = 5000;      // 200 Hz
const uint32_t TEL_MS = 25;         // 20 Hz
const uint32_t STATUS_MS = 100;     // 10 Hz heartbeat for host HUDs
const uint32_t ARM_HOLD_MS = 800;   // upright hold before BALANCING
uint32_t armStartMs = 0;
uint32_t lastStatusMs = 0;

// Burst logger
bool burstPending = false;
bool burstActive = false;
uint16_t burstTarget = 30;
uint16_t burstSent = 0;
uint32_t burstDelayMs = 5000;
uint32_t burstBalStartMs = 0;
uint32_t burstStableStartMs = 0;
const float BURST_BAL_ERR_DEG = 4.0f;
const uint32_t BURST_STABLE_HOLD_MS = 800;

// ------------------------------
// Utils
// ------------------------------
const __FlashStringHelper* modeName(Mode m) {
  switch (m) {
    case SAFE_IDLE: return F("SAFE_IDLE");
    case ARMED: return F("ARMED");
    case BALANCING: return F("BALANCING");
    case FAULT: return F("FAULT");
    case CALIBRATING: return F("CALIBRATING");
    default: return F("UNKNOWN");
  }
}

const __FlashStringHelper* encModeName(uint8_t m) {
  switch (m) {
    case 1: return F("LEFT");
    case 2: return F("RIGHT");
    default: return F("AUTO");
  }
}

void cfgDefaults() {
  cfg.magic = CFG_MAGIC;
  cfg.version = CFG_VERSION;
  cfg.motorPolarity = 1;
  cfg.imuPolarity = 1;
  cfg.imuAxis = 'Y';
  cfg.swapAxes = 1;
  cfg.angleZeroDeg = 0.0f;
  cfg.setpointDeg = 0.0f;
  cfg.kp = 31.0f;
  cfg.ki = 0.05f;
  cfg.kd = 1.05f;
  cfg.kv = 0.0f;
  cfg.kx = 0.0f;
  cfg.outLimit = 180.0f;
  cfg.iLimit = 70.0f;
  cfg.tipDeg = 26.0f;
  cfg.deadbandPwm = 0;
  cfg.qAngle = 0.001f;
  cfg.qBias = 0.003f;
  cfg.rMeasure = 0.03f;
  cfg.autoRun = 0;
  cfg.csvLog = 0;
  cfg.tLog = 0;
  cfg.encMode = 0;
}

void cfgSave() { EEPROM.put(EEPROM_ADDR, cfg); }

bool cfgLoad() {
  ConfigV2 tmp;
  EEPROM.get(EEPROM_ADDR, tmp);
  if (tmp.magic != CFG_MAGIC || tmp.version != CFG_VERSION) return false;
  cfg = tmp;
  return true;
}

float readAccelDeg() {
  float x = mpu.getAngleX();
  float y = mpu.getAngleY();
  if (!cfg.swapAxes) return (cfg.imuAxis == 'X') ? x : y;
  return (cfg.imuAxis == 'X') ? y : x;
}

float readGyroDps() {
  float x = mpu.getGyroX();
  float y = mpu.getGyroY();
  if (!cfg.swapAxes) return (cfg.imuAxis == 'X') ? x : y;
  return (cfg.imuAxis == 'X') ? y : x;
}

float kalmanUpdate(float measDeg, float gyroDpsIn, float dt) {
  float rate = gyroDpsIn - kfBias;
  kfAngle += dt * rate;

  P00 += dt * (dt * P11 - P01 - P10 + cfg.qAngle);
  P01 -= dt * P11;
  P10 -= dt * P11;
  P11 += cfg.qBias * dt;

  float y = measDeg - kfAngle;
  float s = P00 + cfg.rMeasure;
  float k0 = P00 / s;
  float k1 = P10 / s;

  kfAngle += k0 * y;
  kfBias += k1 * y;

  float p00 = P00;
  float p01 = P01;
  P00 -= k0 * p00;
  P01 -= k0 * p01;
  P10 -= k1 * p00;
  P11 -= k1 * p01;

  return kfAngle;
}

void resetControllers() {
  integrator = 0.0f;
  angleOut = 0.0f;
  motionOut = 0.0f;
  prevAngle = angleCtrlDeg;
}

void motorStop() {
  analogWrite(Pins::PWMA, 0);
  analogWrite(Pins::PWMB, 0);
  digitalWrite(Pins::STBY, LOW);
}

void setMotorSigned(int left, int right) {
  left *= cfg.motorPolarity;
  right *= cfg.motorPolarity;
  left = constrain(left, -255, 255);
  right = constrain(right, -255, 255);

  int lPwm = abs(left);
  int rPwm = abs(right);
  if (lPwm > 0 && lPwm < cfg.deadbandPwm) lPwm = cfg.deadbandPwm;
  if (rPwm > 0 && rPwm < cfg.deadbandPwm) rPwm = cfg.deadbandPwm;

  bool leftBackward = (left > 0);
  bool rightBackward = (right > 0);
  digitalWrite(Pins::AIN1, leftBackward ? HIGH : LOW);
  digitalWrite(Pins::BIN1, rightBackward ? HIGH : LOW);

  if (lPwm == 0 && rPwm == 0) {
    motorStop();
    return;
  }

  digitalWrite(Pins::STBY, HIGH);
  analogWrite(Pins::PWMA, lPwm);
  analogWrite(Pins::PWMB, rPwm);
}

void enterMode(Mode next) {
  if (mode == next) return;
  mode = next;

  if (next == SAFE_IDLE || next == FAULT || next == CALIBRATING) {
    estop = true;
    manualMotor = false;
    resetControllers();
    motorStop();
    encSeeded = false;
  } else if (next == ARMED) {
    estop = false;
    manualMotor = false;
    resetControllers();
    motorStop();
    encSeeded = false;
    armStartMs = millis();
  } else if (next == BALANCING) {
    estop = false;
    manualMotor = false;
    resetControllers();
    noInterrupts();
    prevEncL = encLeft;
    prevEncR = encRight;
    interrupts();
    posRef = 0.5f * (prevEncL + prevEncR);
    encSeeded = true;
    if (burstPending) {
      burstActive = true;
      burstSent = 0;
      burstBalStartMs = 0;
      burstStableStartMs = 0;
      Serial.print(F("BURSTCSV ARMED delay_ms="));
      Serial.print(burstDelayMs);
      Serial.print(F(" lines="));
      Serial.println(burstTarget);
    }
  }

  if (next != BALANCING && burstActive) {
    burstActive = false;
    burstPending = false;
    burstBalStartMs = 0;
    burstStableStartMs = 0;
    Serial.println(F("BURSTCSV CANCELED"));
  }

  Serial.print(F("MODE "));
  Serial.println(modeName(next));
}

// ------------------------------
// Commands
// ------------------------------
String readLine() {
  static String line;
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\r') continue;
    if ((uint8_t)c < 32 || (uint8_t)c > 126) {
      if (c != '\n') continue;
    }
    if (c == '\n') {
      String out = line;
      line = "";
      out.trim();
      return out;
    }
    line += c;
    if (line.length() > 180) line.remove(180);
  }
  return "";
}

bool parse3f(const String& s, float& a, float& b, float& c) {
  int p1 = s.indexOf(' ');
  if (p1 < 0) return false;
  int p2 = s.indexOf(' ', p1 + 1);
  if (p2 < 0) return false;
  int p3 = s.indexOf(' ', p2 + 1);
  if (p3 < 0) return false;
  a = s.substring(p1 + 1, p2).toFloat();
  b = s.substring(p2 + 1, p3).toFloat();
  c = s.substring(p3 + 1).toFloat();
  return true;
}

bool parse2f(const String& s, float& a, float& b) {
  int p1 = s.indexOf(' ');
  if (p1 < 0) return false;
  int p2 = s.indexOf(' ', p1 + 1);
  if (p2 < 0) return false;
  a = s.substring(p1 + 1, p2).toFloat();
  b = s.substring(p2 + 1).toFloat();
  return true;
}

bool parse2i(const String& s, int& a, int& b) {
  int p1 = s.indexOf(' ');
  if (p1 < 0) return false;
  int p2 = s.indexOf(' ', p1 + 1);
  if (p2 < 0) return false;
  a = s.substring(p1 + 1, p2).toInt();
  b = s.substring(p2 + 1).toInt();
  return true;
}

void printHelp() {
  Serial.println(F("\nCommands:"));
  Serial.println(F("  HELP GET"));
  Serial.println(F("  ARM DISARM STATE SAFE|ARM|BAL|FAULT"));
  Serial.println(F("  PID <kp> <ki> <kd>"));
  Serial.println(F("  MOTION <kv> <kx>"));
  Serial.println(F("  LIMITS <out tip iMax>"));
  Serial.println(F("  SETPOINT <deg> VEL <counts_per_s>"));
  Serial.println(F("  ENCMODE AUTO|LEFT|RIGHT"));
  Serial.println(F("  AXIS <X|Y> SWAPAXIS 1|0"));
  Serial.println(F("  IMUPOL <1|-1> MOTORPOL <1|-1>"));
  Serial.println(F("  ZERO"));
  Serial.println(F("  SAVECFG LOADCFG DEFAULTCFG"));
  Serial.println(F("  AUTORUN 1|0"));
  Serial.println(F("  MOTOR <l r> MOTOROFF"));
  Serial.println(F("  LOGCSV 1|0 LOGT 1|0 BURSTCSV [delay lines] CSVHDR"));
  Serial.println(F("  CAL ZERO"));
}

void printCsvHeader() {
  Serial.println(F("CSV,ms,mode,estop,setpoint,angle,accel,gyro,pid,motion,wspd,wpos,cmdL,cmdR,encL,encR,vol,kp,ki,kd,kv,kx,qA,qB,rM"));
}

void printStatus() {
  long l, r;
  noInterrupts();
  l = encLeft;
  r = encRight;
  interrupts();
  Serial.print(F("STATUS mode=")); Serial.print(modeName(mode));
  Serial.print(F(" estop=")); Serial.print(estop ? 1 : 0);
  Serial.print(F(" ang=")); Serial.print(angleCtrlDeg, 3);
  Serial.print(F(" raw=")); Serial.print(accelAngleDeg, 3);
  Serial.print(F(" gyro=")); Serial.print(gyroRateDps, 3);
  Serial.print(F(" set=")); Serial.print(cfg.setpointDeg, 3);
  Serial.print(F(" out=")); Serial.print(angleOut + motionOut, 2);
  Serial.print(F(" pid=")); Serial.print(angleOut, 2);
  Serial.print(F(" mot=")); Serial.print(motionOut, 2);
  Serial.print(F(" wspd=")); Serial.print(wheelSpeed, 2);
  Serial.print(F(" wpos=")); Serial.print(wheelPos, 1);
  Serial.print(F(" kp=")); Serial.print(cfg.kp, 3);
  Serial.print(F(" ki=")); Serial.print(cfg.ki, 3);
  Serial.print(F(" kd=")); Serial.print(cfg.kd, 3);
  Serial.print(F(" kv=")); Serial.print(cfg.kv, 4);
  Serial.print(F(" kx=")); Serial.print(cfg.kx, 5);
  Serial.print(F(" axis=")); Serial.print(cfg.imuAxis);
  Serial.print(F(" encmode=")); Serial.print(encModeName(cfg.encMode));
  Serial.print(F(" swap=")); Serial.print(cfg.swapAxes);
  Serial.print(F(" ipol=")); Serial.print(cfg.imuPolarity);
  Serial.print(F(" mpol=")); Serial.print(cfg.motorPolarity);
  Serial.print(F(" zero=")); Serial.print(cfg.angleZeroDeg, 3);
  Serial.print(F(" autorun=")); Serial.print(cfg.autoRun ? 1 : 0);
  Serial.print(F(" encL=")); Serial.print(l);
  Serial.print(F(" encR=")); Serial.print(r);
  Serial.print(F(" volRaw=")); Serial.println(analogRead(Pins::VOL));
}

void runCalZero() {
  enterMode(CALIBRATING);
  Serial.println(F("CAL ZERO: keep robot perfectly upright/still..."));
  const int n = 120;
  float sum = 0.0f;
  for (int i = 0; i < n; i++) {
    mpu.update();
    accelAngleDeg = readAccelDeg();
    gyroRateDps = readGyroDps();
    float a = cfg.imuPolarity * kalmanUpdate(accelAngleDeg, gyroRateDps, 0.005f);
    sum += a;
    delay(5);
  }
  cfg.angleZeroDeg = sum / n;
  cfg.setpointDeg = 0.0f;
  cfgSave();
  Serial.print(F("OK CAL ZERO zero="));
  Serial.println(cfg.angleZeroDeg, 4);
  enterMode(SAFE_IDLE);
}

void handleCommand(const String& cmd) {
  if (!cmd.length()) return;
  if (cmd == "HELP") {
    printHelp();
  } else if (cmd == "GET") {
    printStatus();
  } else if (cmd == "ARM") {
    enterMode(ARMED);
  } else if (cmd == "DISARM") {
    enterMode(SAFE_IDLE);
  } else if (cmd.startsWith("STATE ")) {
    String s = cmd.substring(6);
    if (s == "SAFE") enterMode(SAFE_IDLE);
    else if (s == "ARM") enterMode(ARMED);
    else if (s == "BAL") enterMode(BALANCING);
    else if (s == "FAULT") enterMode(FAULT);
  } else if (cmd.startsWith("PID ")) {
    float a, b, c;
    if (parse3f(cmd, a, b, c)) {
      cfg.kp = max(0.0f, a);
      cfg.ki = max(0.0f, b);
      cfg.kd = max(0.0f, c);
      Serial.println(F("OK PID"));
    }
  } else if (cmd.startsWith("MOTION ")) {
    float a, b;
    if (parse2f(cmd, a, b)) {
      cfg.kv = max(0.0f, a);
      cfg.kx = max(0.0f, b);
      Serial.println(F("OK MOTION"));
    }
  } else if (cmd.startsWith("LIMITS ")) {
    float a, b, c;
    if (parse3f(cmd, a, b, c)) {
      cfg.outLimit = constrain(a, 40.0f, 255.0f);
      cfg.tipDeg = constrain(b, 10.0f, 45.0f);
      cfg.iLimit = constrain(c, 10.0f, 255.0f);
      Serial.println(F("OK LIMITS"));
    }
  } else if (cmd.startsWith("SETPOINT ")) {
    cfg.setpointDeg = cmd.substring(9).toFloat();
    Serial.print(F("OK SETPOINT "));
    Serial.println(cfg.setpointDeg, 3);
  } else if (cmd.startsWith("ENCMODE ")) {
    String s = cmd.substring(8);
    s.toUpperCase();
    if (s == "AUTO") cfg.encMode = 0;
    else if (s == "LEFT") cfg.encMode = 1;
    else if (s == "RIGHT") cfg.encMode = 2;
    else {
      Serial.println(F("ERR ENCMODE use AUTO|LEFT|RIGHT"));
      return;
    }
    cfgSave();
    Serial.print(F("OK ENCMODE "));
    Serial.println(encModeName(cfg.encMode));
  } else if (cmd.startsWith("VEL ")) {
    cmdVel = cmd.substring(4).toFloat();
    Serial.print(F("OK VEL "));
    Serial.println(cmdVel, 2);
  } else if (cmd.startsWith("AXIS ")) {
    String ax = cmd.substring(5);
    ax.toUpperCase();
    if (ax == "X" || ax == "Y") {
      cfg.imuAxis = ax.charAt(0);
      Serial.println(F("OK AXIS"));
    }
  } else if (cmd.startsWith("SWAPAXIS ")) {
    cfg.swapAxes = (cmd.substring(9).toInt() != 0);
    Serial.println(F("OK SWAPAXIS"));
  } else if (cmd.startsWith("IMUPOL ")) {
    cfg.imuPolarity = (cmd.substring(7).toInt() >= 0) ? 1 : -1;
    Serial.println(F("OK IMUPOL"));
  } else if (cmd.startsWith("MOTORPOL ")) {
    cfg.motorPolarity = (cmd.substring(9).toInt() >= 0) ? 1 : -1;
    Serial.println(F("OK MOTORPOL"));
  } else if (cmd == "ZERO") {
    cfg.angleZeroDeg = cfg.imuPolarity * kfAngle;
    Serial.print(F("OK ZERO "));
    Serial.println(cfg.angleZeroDeg, 4);
  } else if (cmd == "SAVECFG") {
    cfgSave();
    Serial.println(F("OK SAVECFG"));
  } else if (cmd == "LOADCFG") {
    if (cfgLoad()) Serial.println(F("OK LOADCFG"));
    else Serial.println(F("ERR LOADCFG none"));
  } else if (cmd == "DEFAULTCFG") {
    float keepZero = cfg.angleZeroDeg;
    int8_t keepMpol = cfg.motorPolarity;
    int8_t keepIpol = cfg.imuPolarity;
    char keepAxis = cfg.imuAxis;
    uint8_t keepSwap = cfg.swapAxes;
    cfgDefaults();
    cfg.angleZeroDeg = keepZero;
    cfg.motorPolarity = keepMpol;
    cfg.imuPolarity = keepIpol;
    cfg.imuAxis = keepAxis;
    cfg.swapAxes = keepSwap;
    cfgSave();
    Serial.println(F("OK DEFAULTCFG"));
  } else if (cmd.startsWith("AUTORUN ")) {
    cfg.autoRun = (cmd.substring(8).toInt() != 0);
    cfgSave();
    Serial.print(F("OK AUTORUN "));
    Serial.println(cfg.autoRun ? 1 : 0);
  } else if (cmd.startsWith("MOTOR ")) {
    int l, r;
    if (parse2i(cmd, l, r)) {
      if (mode == SAFE_IDLE || mode == ARMED) {
        manualL = l;
        manualR = r;
        manualMotor = true;
        setMotorSigned(manualL, manualR);
        Serial.println(F("OK MOTOR"));
      } else {
        Serial.println(F("ERR MOTOR only SAFE/ARM"));
      }
    }
  } else if (cmd == "MOTOROFF") {
    manualMotor = false;
    setMotorSigned(0, 0);
    Serial.println(F("OK MOTOROFF"));
  } else if (cmd.startsWith("LOGCSV ")) {
    cfg.csvLog = (cmd.substring(7).toInt() != 0);
    Serial.print(F("OK LOGCSV "));
    Serial.println(cfg.csvLog ? 1 : 0);
  } else if (cmd.startsWith("LOGT ")) {
    cfg.tLog = (cmd.substring(5).toInt() != 0);
    Serial.print(F("OK LOGT "));
    Serial.println(cfg.tLog ? 1 : 0);
  } else if (cmd.startsWith("BURSTCSV")) {
    uint32_t d = 5000;
    uint16_t n = 30;
    int p1 = cmd.indexOf(' ');
    if (p1 > 0) {
      int p2 = cmd.indexOf(' ', p1 + 1);
      if (p2 > p1) {
        d = (uint32_t)max(0, cmd.substring(p1 + 1, p2).toInt());
        n = (uint16_t)constrain(cmd.substring(p2 + 1).toInt(), 1, 500);
      }
    }
    burstDelayMs = d;
    burstTarget = n;
    burstSent = 0;
    burstPending = true;
    burstActive = (mode == BALANCING);
    burstBalStartMs = 0;
    burstStableStartMs = 0;
    Serial.println(F("OK BURSTCSV"));
  } else if (cmd == "CSVHDR") {
    printCsvHeader();
  } else if (cmd == "CAL ZERO") {
    runCalZero();
  } else {
    Serial.println(F("ERR UNKNOWN"));
  }
}

// ------------------------------
// Setup / Loop
// ------------------------------
void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.println(F("\nTumbller V2 boot"));

  cfgDefaults();
  bool loaded = cfgLoad();
  if (loaded) Serial.println(F("CFG loaded"));
  else Serial.println(F("CFG defaults"));

  pinMode(Pins::AIN1, OUTPUT);
  pinMode(Pins::BIN1, OUTPUT);
  pinMode(Pins::STBY, OUTPUT);
  pinMode(Pins::PWMA, OUTPUT);
  pinMode(Pins::PWMB, OUTPUT);
  pinMode(Pins::VOL, INPUT);
  pinMode(Pins::ENC_LEFT, INPUT_PULLUP);
  pinMode(Pins::ENC_RIGHT, INPUT_PULLUP);

  attachInterrupt(digitalPinToInterrupt(Pins::ENC_LEFT), isrEncLeft, CHANGE);
  attachInterrupt(digitalPinToInterrupt(Pins::ENC_RIGHT), isrEncRight, CHANGE);

  motorStop();

  Wire.begin();
  byte imu = mpu.begin();
  Serial.print(F("MPU status="));
  Serial.println(imu);
  if (imu != 0) {
    enterMode(FAULT);
  } else {
    Serial.println(F("Calibrating gyro... keep still"));
    delay(800);
    mpu.calcOffsets();
    mpu.update();
    kfAngle = readAccelDeg();
    prevAngle = kfAngle;
    enterMode(SAFE_IDLE);
    if (cfg.autoRun) {
      Serial.println(F("AUTORUN -> ARM"));
      enterMode(ARMED);
    }
  }

  printHelp();
  printCsvHeader();
  lastLoopUs = micros();
  lastTelMs = millis();
  lastStatusMs = millis();
  printStatus();
}

void loop() {
  String cmd = readLine();
  if (cmd.length()) handleCommand(cmd);

  uint32_t nowUs = micros();
  if ((uint32_t)(nowUs - lastLoopUs) < LOOP_US) return;

  float dt = (nowUs - lastLoopUs) * 1e-6f;
  lastLoopUs = nowUs;

  mpu.update();
  accelAngleDeg = readAccelDeg();
  gyroRateDps = readGyroDps();
  float raw = cfg.imuPolarity * kalmanUpdate(accelAngleDeg, gyroRateDps, dt);
  angleCtrlDeg = raw - cfg.angleZeroDeg;

  long l, r;
  noInterrupts();
  l = encLeft;
  r = encRight;
  interrupts();

  if (!encSeeded) {
    prevEncL = l;
    prevEncR = r;
    encSeeded = true;
  }
  long dL = l - prevEncL;
  long dR = r - prevEncR;
  prevEncL = l;
  prevEncR = r;
  if (cfg.encMode == 1) {
    wheelPos = (float)l;
    wheelSpeed = ((float)dL) / dt;
  } else if (cfg.encMode == 2) {
    wheelPos = (float)r;
    wheelSpeed = ((float)dR) / dt;
  } else {
    // AUTO: use both when available, otherwise fallback to active channel.
    bool lActive = (abs(dL) > 0);
    bool rActive = (abs(dR) > 0);
    if (lActive && !rActive) {
      wheelPos = (float)l;
      wheelSpeed = ((float)dL) / dt;
    } else if (!lActive && rActive) {
      wheelPos = (float)r;
      wheelSpeed = ((float)dR) / dt;
    } else {
      wheelPos = 0.5f * (l + r);
      wheelSpeed = (0.5f * (dL + dR)) / dt;
    }
  }

  if (fabs(angleCtrlDeg) > cfg.tipDeg) {
    if (mode == BALANCING || mode == ARMED) enterMode(FAULT);
  }

  if (mode == ARMED) {
    if (fabs(angleCtrlDeg) < 6.0f) {
      if (millis() - armStartMs >= ARM_HOLD_MS) enterMode(BALANCING);
    } else {
      armStartMs = millis();
    }
  }

  if ((mode == SAFE_IDLE || mode == ARMED) && manualMotor) {
    setMotorSigned(manualL, manualR);
  } else if (mode == BALANCING && !estop) {
    float err = cfg.setpointDeg - angleCtrlDeg;
    integrator += cfg.ki * err * dt;
    integrator = constrain(integrator, -cfg.iLimit, cfg.iLimit);
    float deriv = -(angleCtrlDeg - prevAngle) / dt;
    prevAngle = angleCtrlDeg;

    angleOut = cfg.kp * err + integrator + cfg.kd * deriv;
    float posErr = posRef - wheelPos;
    motionOut = (-cfg.kv * (wheelSpeed - cmdVel)) + (cfg.kx * posErr);
    float u = constrain(angleOut + motionOut, -cfg.outLimit, cfg.outLimit);
    setMotorSigned((int)u, (int)u);
  } else {
    manualMotor = false;
    motionOut = 0.0f;
    angleOut = 0.0f;
    setMotorSigned(0, 0);
  }

  if (millis() - lastTelMs >= TEL_MS) {
    lastTelMs = millis();

    if (cfg.tLog) {
      Serial.print(F("T "));
      Serial.print((int)mode); Serial.print(' ');
      Serial.print(estop ? 1 : 0); Serial.print(' ');
      Serial.print(cfg.setpointDeg, 3); Serial.print(' ');
      Serial.print(angleCtrlDeg, 3); Serial.print(' ');
      Serial.print(angleOut + motionOut, 2); Serial.print(' ');
      Serial.print(wheelSpeed, 2); Serial.print(' ');
      Serial.print(wheelPos, 1); Serial.print(' ');
      Serial.println(analogRead(Pins::VOL));
    }

    bool emitBurst = false;
    if (burstActive) {
      if (burstBalStartMs == 0) {
        float balErr = fabs(cfg.setpointDeg - angleCtrlDeg);
        if (balErr <= BURST_BAL_ERR_DEG) {
          if (burstStableStartMs == 0) burstStableStartMs = millis();
          if ((millis() - burstStableStartMs) >= BURST_STABLE_HOLD_MS) {
            burstBalStartMs = millis();
            Serial.print(F("BURSTCSV STABLE delay_ms="));
            Serial.println(burstDelayMs);
          }
        } else {
          burstStableStartMs = 0;
        }
      } else if ((millis() - burstBalStartMs) >= burstDelayMs && burstSent < burstTarget) {
          emitBurst = true;
          burstSent++;
          if (burstSent >= burstTarget) {
            burstActive = false;
            burstPending = false;
            burstBalStartMs = 0;
            burstStableStartMs = 0;
            Serial.println(F("BURSTCSV DONE"));
          }
        }
      }

    if (cfg.csvLog || emitBurst) {
      Serial.print(F("CSV,"));
      Serial.print(millis()); Serial.print(',');
      Serial.print((int)mode); Serial.print(',');
      Serial.print(estop ? 1 : 0); Serial.print(',');
      Serial.print(cfg.setpointDeg, 3); Serial.print(',');
      Serial.print(angleCtrlDeg, 3); Serial.print(',');
      Serial.print(accelAngleDeg, 3); Serial.print(',');
      Serial.print(gyroRateDps, 3); Serial.print(',');
      Serial.print(angleOut + motionOut, 2); Serial.print(',');
      Serial.print(motionOut, 2); Serial.print(',');
      Serial.print(wheelSpeed, 2); Serial.print(',');
      Serial.print(wheelPos, 1); Serial.print(',');
      Serial.print(manualMotor ? manualL : (int)(angleOut + motionOut)); Serial.print(',');
      Serial.print(manualMotor ? manualR : (int)(angleOut + motionOut)); Serial.print(',');
      Serial.print(l); Serial.print(',');
      Serial.print(r); Serial.print(',');
      Serial.print(analogRead(Pins::VOL)); Serial.print(',');
      Serial.print(cfg.kp, 3); Serial.print(',');
      Serial.print(cfg.ki, 3); Serial.print(',');
      Serial.print(cfg.kd, 3); Serial.print(',');
      Serial.print(cfg.kv, 4); Serial.print(',');
      Serial.print(cfg.kx, 5); Serial.print(',');
      Serial.print(cfg.qAngle, 5); Serial.print(',');
      Serial.print(cfg.qBias, 5); Serial.print(',');
      Serial.println(cfg.rMeasure, 5);
    }

    if ((millis() - lastStatusMs) >= STATUS_MS) {
      lastStatusMs = millis();
      printStatus();
    }
  }
}
