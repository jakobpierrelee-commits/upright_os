#include <Arduino.h>

namespace {
bool g_armed = false;
bool g_estop = true;
uint8_t g_fault = 0;
float g_kp = 20.0f;
float g_ki = 0.0f;
float g_kd = 0.6f;
float g_set = 0.0f;
}

static void print_status() {
  Serial.print("STATUS mode=");
  Serial.print(g_armed ? "BALANCING" : "SAFE_IDLE");
  Serial.print(" estop=");
  Serial.print(g_estop ? 1 : 0);
  Serial.print(" fault=");
  Serial.print(g_fault);
  Serial.print(" ang=0.000 raw=0.000 gyro=0.000 out=0.000");
  Serial.print(" kp=");
  Serial.print(g_kp, 4);
  Serial.print(" ki=");
  Serial.print(g_ki, 4);
  Serial.print(" kd=");
  Serial.print(g_kd, 4);
  Serial.print(" set=");
  Serial.print(g_set, 3);
  Serial.println(" wpos=0.000 wspd=0.000");
}

static String read_line() {
  static String buf;
  while (Serial.available() > 0) {
    char ch = static_cast<char>(Serial.read());
    if (ch == '\r') continue;
    if (ch == '\n') {
      String out = buf;
      buf = "";
      out.trim();
      return out;
    }
    buf += ch;
  }
  return "";
}

static void handle_cmd(const String& cmd) {
  if (cmd == "GET") {
    print_status();
    return;
  }
  if (cmd == "ARM") {
    g_estop = false;
    g_armed = true;
    Serial.println("OK ARM");
    return;
  }
  if (cmd == "DISARM") {
    g_armed = false;
    g_estop = true;
    Serial.println("OK DISARM");
    return;
  }
  if (cmd == "ESTOP 1") {
    g_armed = false;
    g_estop = true;
    Serial.println("OK ESTOP");
    return;
  }
  if (cmd == "ESTOP 0") {
    g_estop = false;
    Serial.println("OK ESTOP");
    return;
  }
  if (cmd.startsWith("PID ")) {
    Serial.println("OK PID");
    return;
  }
  if (cmd.startsWith("SETPOINT ")) {
    Serial.println("OK SETPOINT");
    return;
  }
  if (cmd.startsWith("LIMITS ")) {
    Serial.println("OK LIMITS");
    return;
  }
  if (cmd.startsWith("MOTION ")) {
    Serial.println("OK MOTION");
    return;
  }
  if (cmd == "CAL ZERO") {
    Serial.println("OK CAL ZERO");
    return;
  }
  if (cmd == "SAVECFG") {
    Serial.println("OK SAVECFG");
    return;
  }
  if (cmd == "HELP") {
    Serial.println("CMDS GET ARM DISARM PID SETPOINT LIMITS CAL ZERO SAVECFG MOTION");
    return;
  }
  Serial.println("ERR unknown_command");
}

void setup() {
  Serial.begin(115200);
  while (!Serial && millis() < 1500) {
    delay(5);
  }
  Serial.println("IDENT teensy41_reference_v1");
  print_status();
}

void loop() {
  String cmd = read_line();
  if (cmd.length() > 0) {
    handle_cmd(cmd);
  }
}
