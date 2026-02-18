/*
  ELEGOO Tumbller (BalanceCarRobot-PCB-v06) Nano Hardware Probe

  Purpose:
  - Identify and validate onboard wiring when you cannot visually trace PCB routes.
  - Keep outputs safe by default (motors disabled until explicit command).

  IMPORTANT:
  - Put robot on a stand before motor tests.
  - Open Serial Monitor at 115200 baud, "Newline" line ending.

  Inferred signal mapping from your PCB header labels (verify with tests):
    D13 -> LED13
    D12 -> BIN1
    D11 -> TRIG
    D10 -> MODE
    D9  -> IR
    D8  -> STBY
    D7  -> AIN1
    D6  -> PWMB (PWM)
    D5  -> PWMA (PWM)
    D4  -> M1A encoder
    D3  -> DIN
    D2  -> M2A encoder
    D1  -> TX
    D0  -> RX
    A3  -> ECHO
    A2  -> VOL (battery sense)
    A5/A4 -> I2C SCL/SDA (MPU6050 expected at 0x68)
*/

#include <Arduino.h>
#include <Wire.h>

namespace Pins {
  const uint8_t LED13 = 13;
  const uint8_t BIN1 = 12;
  const uint8_t TRIG = 11;
  const uint8_t MODE = 10;
  const uint8_t IR = 9;
  const uint8_t STBY = 8;
  const uint8_t AIN1 = 7;
  const uint8_t PWMB = 6;
  const uint8_t PWMA = 5;
  const uint8_t M1A = 4;
  const uint8_t DIN = 3;
  const uint8_t M2A = 2;

  const uint8_t VOL = A2;
  const uint8_t ECHO = A3;
}

volatile long m1Count = 0;
volatile long m2Count = 0;

void isrM1() { m1Count++; }
void isrM2() { m2Count++; }

void motorStop() {
  analogWrite(Pins::PWMA, 0);
  analogWrite(Pins::PWMB, 0);
  digitalWrite(Pins::STBY, LOW);
}

void motorDriveSingleDir(int pwmA, int pwmB, bool dirA, bool dirB, uint32_t runMs) {
  pwmA = constrain(pwmA, 0, 255);
  pwmB = constrain(pwmB, 0, 255);
  digitalWrite(Pins::AIN1, dirA ? HIGH : LOW);
  digitalWrite(Pins::BIN1, dirB ? HIGH : LOW);
  digitalWrite(Pins::STBY, HIGH);
  analogWrite(Pins::PWMA, pwmA);
  analogWrite(Pins::PWMB, pwmB);
  delay(runMs);
  motorStop();
}

void printHelp() {
  Serial.println(F("\nCommands:"));
  Serial.println(F("  help               - show this help"));
  Serial.println(F("  map                - print inferred pin map"));
  Serial.println(F("  i2c                - scan I2C bus for devices"));
  Serial.println(F("  sensors            - print VOL/MODE/IR/ECHO state once"));
  Serial.println(F("  monitor            - print sensors + encoder counts every 250ms (10s)"));
  Serial.println(F("  enc_reset          - reset encoder counters"));
  Serial.println(F("  enc_scan [sec]     - edge scan on candidate pins while spinning one wheel"));
  Serial.println(F("  ping               - read ultrasonic distance (TRIG/ECHO)"));
  Serial.println(F("  led                - blink D13 and DIN"));
  Serial.println(F("  motor_test <pwm>   - run short motor pattern, default pwm=80"));
  Serial.println(F("  stop               - immediate motor stop"));
}

void printMap() {
  Serial.println(F("\nInferred PCB-v06 signal map:"));
  Serial.println(F("D13=LED, D12=BIN1, D11=TRIG, D10=MODE, D9=IR, D8=STBY"));
  Serial.println(F("D7=AIN1, D6=PWMB, D5=PWMA, D4=M1A, D3=DIN, D2=M2A"));
  Serial.println(F("A3=ECHO, A2=VOL, A5/A4=I2C SCL/SDA"));
}

void i2cScan() {
  Serial.println(F("I2C scan start..."));
  uint8_t found = 0;
  for (uint8_t addr = 1; addr < 127; addr++) {
    Wire.beginTransmission(addr);
    uint8_t err = Wire.endTransmission();
    if (err == 0) {
      Serial.print(F("  Found 0x"));
      if (addr < 16) Serial.print('0');
      Serial.println(addr, HEX);
      found++;
    }
  }
  if (!found) {
    Serial.println(F("  No I2C devices found."));
  } else {
    Serial.print(F("Total found: "));
    Serial.println(found);
  }
}

long readDistanceCm() {
  digitalWrite(Pins::TRIG, LOW);
  delayMicroseconds(3);
  digitalWrite(Pins::TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(Pins::TRIG, LOW);
  unsigned long us = pulseIn(Pins::ECHO, HIGH, 30000UL);
  if (us == 0) return -1;
  return (long)(us * 0.0343f / 2.0f);
}

void printSensorSnapshot() {
  int volRaw = analogRead(Pins::VOL);
  int modeState = digitalRead(Pins::MODE);
  int irState = digitalRead(Pins::IR);
  int echoState = digitalRead(Pins::ECHO);

  Serial.print(F("VOL raw="));
  Serial.print(volRaw);
  Serial.print(F("  MODE="));
  Serial.print(modeState);
  Serial.print(F("  IR="));
  Serial.print(irState);
  Serial.print(F("  ECHO(pin)="));
  Serial.print(echoState);
  Serial.print(F("  M1A_count="));
  Serial.print(m1Count);
  Serial.print(F("  M2A_count="));
  Serial.println(m2Count);
}

void monitorSensors() {
  Serial.println(F("Monitoring for 10s..."));
  unsigned long start = millis();
  while (millis() - start < 10000UL) {
    printSensorSnapshot();
    delay(250);
  }
  Serial.println(F("Monitor done."));
}

void scanEncoderPins(uint8_t durationSec) {
  const uint8_t scanPins[] = {2, 4, 9, 10, A0, A1, A2, A3};
  const char* scanNames[] = {"D2", "D4", "D9", "D10", "A0", "A1", "A2", "A3"};
  const uint8_t n = sizeof(scanPins) / sizeof(scanPins[0]);
  uint8_t lastState[n];
  unsigned long edges[n];

  for (uint8_t i = 0; i < n; i++) {
    pinMode(scanPins[i], INPUT_PULLUP);
    lastState[i] = (uint8_t)digitalRead(scanPins[i]);
    edges[i] = 0;
  }

  Serial.println(F("enc_scan started. Spin only ONE wheel now."));
  unsigned long startMs = millis();
  while (millis() - startMs < (unsigned long)durationSec * 1000UL) {
    for (uint8_t i = 0; i < n; i++) {
      uint8_t s = (uint8_t)digitalRead(scanPins[i]);
      if (s != lastState[i]) {
        edges[i]++;
        lastState[i] = s;
      }
    }
  }

  Serial.println(F("enc_scan edge totals:"));
  for (uint8_t i = 0; i < n; i++) {
    Serial.print(F("  "));
    Serial.print(scanNames[i]);
    Serial.print(F(" -> "));
    Serial.println(edges[i]);
  }
  Serial.println(F("Repeat enc_scan for the other wheel and compare."));
}

void blinkOutputs() {
  Serial.println(F("Blinking D13 + DIN..."));
  for (int i = 0; i < 10; i++) {
    digitalWrite(Pins::LED13, HIGH);
    digitalWrite(Pins::DIN, HIGH);
    delay(100);
    digitalWrite(Pins::LED13, LOW);
    digitalWrite(Pins::DIN, LOW);
    delay(100);
  }
  Serial.println(F("Blink done."));
}

void runMotorPattern(int pwm) {
  Serial.println(F("Motor test start: keep robot lifted."));
  Serial.println(F("Phase 1: both dir HIGH"));
  motorDriveSingleDir(pwm, pwm, true, true, 800);
  delay(300);
  Serial.println(F("Phase 2: both dir LOW"));
  motorDriveSingleDir(pwm, pwm, false, false, 800);
  delay(300);
  Serial.println(F("Phase 3: A only"));
  motorDriveSingleDir(pwm, 0, true, true, 700);
  delay(300);
  Serial.println(F("Phase 4: B only"));
  motorDriveSingleDir(0, pwm, true, true, 700);
  Serial.println(F("Motor test done."));
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
    if (line.length() > 120) line.remove(120);
  }
  return "";
}

void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println(F("\nTumbller v06 Nano Probe boot"));

  pinMode(Pins::LED13, OUTPUT);
  pinMode(Pins::DIN, OUTPUT);
  pinMode(Pins::STBY, OUTPUT);
  pinMode(Pins::AIN1, OUTPUT);
  pinMode(Pins::BIN1, OUTPUT);
  pinMode(Pins::PWMA, OUTPUT);
  pinMode(Pins::PWMB, OUTPUT);
  pinMode(Pins::TRIG, OUTPUT);

  pinMode(Pins::MODE, INPUT_PULLUP);
  pinMode(Pins::IR, INPUT_PULLUP);
  pinMode(Pins::M1A, INPUT_PULLUP);
  pinMode(Pins::M2A, INPUT_PULLUP);
  pinMode(Pins::ECHO, INPUT);
  pinMode(Pins::VOL, INPUT);

  motorStop();

  attachInterrupt(digitalPinToInterrupt(Pins::M1A), isrM1, CHANGE);
  attachInterrupt(digitalPinToInterrupt(Pins::M2A), isrM2, CHANGE);

  Wire.begin();

  printMap();
  printHelp();
}

void loop() {
  String cmd = readLine();
  if (!cmd.length()) return;

  if (cmd == "help") {
    printHelp();
  } else if (cmd == "map") {
    printMap();
  } else if (cmd == "i2c") {
    i2cScan();
  } else if (cmd == "sensors") {
    printSensorSnapshot();
  } else if (cmd == "monitor") {
    monitorSensors();
  } else if (cmd == "enc_reset") {
    noInterrupts();
    m1Count = 0;
    m2Count = 0;
    interrupts();
    Serial.println(F("Encoder counts reset."));
  } else if (cmd.startsWith("enc_scan")) {
    uint8_t seconds = 5;
    int spacePos = cmd.indexOf(' ');
    if (spacePos > 0) {
      int parsed = cmd.substring(spacePos + 1).toInt();
      if (parsed >= 1 && parsed <= 20) seconds = (uint8_t)parsed;
    }
    scanEncoderPins(seconds);
  } else if (cmd == "ping") {
    long cm = readDistanceCm();
    if (cm < 0) Serial.println(F("Ping timeout/no echo."));
    else {
      Serial.print(F("Distance cm="));
      Serial.println(cm);
    }
  } else if (cmd == "led") {
    blinkOutputs();
  } else if (cmd.startsWith("motor_test")) {
    int pwm = 80;
    int spacePos = cmd.indexOf(' ');
    if (spacePos > 0) {
      pwm = cmd.substring(spacePos + 1).toInt();
      if (pwm <= 0) pwm = 80;
    }
    runMotorPattern(pwm);
  } else if (cmd == "stop") {
    motorStop();
    Serial.println(F("Motor stop command executed."));
  } else {
    Serial.println(F("Unknown command. Type: help"));
  }
}
