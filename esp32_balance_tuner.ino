/*
  ESP32 Self-Balancing Robot - Wireless PID Tuner (Single-File Sketch)

  Features:
  - Wi-Fi STA + fallback AP mode
  - Async Web Server + WebSocket for low-latency PID updates
  - ArduinoOTA support
  - Real-time telemetry stream: setpoint vs current angle
  - Emergency stop from dashboard
  - Save PID values to NVS Preferences (non-volatile)
  - Export PID values via Serial and Web console

  Required libraries:
  - ESPAsyncWebServer
  - AsyncTCP
  - ArduinoOTA
  - Preferences (built-in for ESP32 core)
  - PID_v1
  - MPU6050_light (or replace IMU section with your own)
*/

#include <WiFi.h>
#include <AsyncTCP.h>
#include <ESPAsyncWebServer.h>
#include <ArduinoOTA.h>
#include <Preferences.h>
#include <Wire.h>
#include <PID_v1.h>
#include <MPU6050_light.h>

// ------------------------------
// Wi-Fi config
// ------------------------------
const char* WIFI_SSID = "YOUR_WIFI_SSID";
const char* WIFI_PASS = "YOUR_WIFI_PASSWORD";

const char* AP_SSID = "BalanceBot-Setup";
const char* AP_PASS = "12345678";

// ------------------------------
// Web server / WebSocket
// ------------------------------
AsyncWebServer server(80);
AsyncWebSocket ws("/ws");

// ------------------------------
// Persistent config
// ------------------------------
Preferences prefs;

// ------------------------------
// Control variables
// ------------------------------
double setpoint = 0.0;      // desired pitch angle (upright)
double currentAngle = 0.0;  // measured pitch angle
double pidOutput = 0.0;     // controller output to motors

double Kp = 18.0;
double Ki = 0.0;
double Kd = 0.8;

PID balancePID(&currentAngle, &pidOutput, &setpoint, Kp, Ki, Kd, DIRECT);

volatile bool emergencyStop = false;

// ------------------------------
// IMU
// ------------------------------
MPU6050 mpu(Wire);
unsigned long lastImuMs = 0;

// 2-state Kalman filter (angle + gyro bias)
double kfAngleDeg = 0.0;
double kfBiasDegPerSec = 0.0;
double kfP00 = 1.0, kfP01 = 0.0, kfP10 = 0.0, kfP11 = 1.0;
double Q_angle = 0.001;
double Q_bias = 0.003;
double R_measure = 0.03;

// ------------------------------
// Loop timing
// ------------------------------
unsigned long lastControlUs = 0;
unsigned long lastTelemetryMs = 0;
const uint32_t CONTROL_PERIOD_US = 5000;  // 200 Hz
const uint32_t TELEMETRY_PERIOD_MS = 50;  // 20 Hz

// ------------------------------
// HTML Dashboard (inline)
// ------------------------------
const char INDEX_HTML[] PROGMEM = R"rawliteral(
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>ESP32 Balance PID Tuner</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    :root{
      --bg:#0b1220;
      --card:#111a2b;
      --text:#e8eefc;
      --muted:#9fb2d9;
      --accent:#31c48d;
      --danger:#ff5f57;
      --line1:#4ea1ff;
      --line2:#ffb020;
    }
    *{box-sizing:border-box}
    body{
      margin:0;
      font-family:ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
      background:radial-gradient(1200px 600px at 70% -20%,#20345f 0%,var(--bg) 55%);
      color:var(--text);
      padding:14px;
    }
    .wrap{max-width:900px;margin:0 auto;display:grid;gap:12px}
    .card{
      background:linear-gradient(180deg,#17243c 0%,var(--card) 100%);
      border:1px solid #2b3f67;
      border-radius:14px;
      padding:14px;
      box-shadow:0 8px 24px rgba(0,0,0,.25);
    }
    h1{margin:0 0 6px 0;font-size:1.1rem}
    .muted{color:var(--muted);font-size:.92rem}
    .grid{display:grid;gap:10px}
    .row{display:grid;grid-template-columns:52px 1fr 72px;align-items:center;gap:10px}
    input[type=range]{width:100%}
    input[type=number]{
      width:100%;padding:7px;border-radius:8px;border:1px solid #3b507d;background:#0f1729;color:var(--text)
    }
    .btns{display:flex;flex-wrap:wrap;gap:8px}
    button{
      border:none;border-radius:10px;padding:10px 12px;font-weight:700;cursor:pointer
    }
    .primary{background:var(--accent);color:#052015}
    .warn{background:#ffc857;color:#332200}
    .danger{background:var(--danger);color:#2d0000}
    .status{display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap}
    .pill{
      border:1px solid #3a4f7a;border-radius:999px;padding:5px 10px;background:#0f1729;color:var(--muted);font-size:.88rem
    }
    #log{
      height:110px;overflow:auto;background:#0f1729;border:1px solid #33486f;border-radius:10px;padding:8px;
      font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;font-size:.85rem;color:#cde0ff;
      white-space:pre-wrap;
    }
    canvas{max-height:280px}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1>ESP32 Balance Robot - PID Tuner</h1>
      <div class="muted">Live tuning over WebSocket. Keep robot supported during first tune.</div>
    </div>

    <div class="card grid">
      <div class="row">
        <label>Kp</label>
        <input id="kp" type="range" min="0" max="80" step="0.1">
        <input id="kpv" type="number" min="0" max="80" step="0.1">
      </div>
      <div class="row">
        <label>Ki</label>
        <input id="ki" type="range" min="0" max="20" step="0.01">
        <input id="kiv" type="number" min="0" max="20" step="0.01">
      </div>
      <div class="row">
        <label>Kd</label>
        <input id="kd" type="range" min="0" max="20" step="0.01">
        <input id="kdv" type="number" min="0" max="20" step="0.01">
      </div>
      <div class="btns">
        <button class="primary" id="saveBtn">Save</button>
        <button class="warn" id="exportBtn">Export</button>
        <button class="danger" id="estopBtn">E-STOP</button>
        <button id="resumeBtn">Resume</button>
      </div>
    </div>

    <div class="card">
      <canvas id="plot"></canvas>
    </div>

    <div class="card status">
      <div class="pill" id="wsState">WS: disconnected</div>
      <div class="pill" id="angleState">Angle: --</div>
      <div class="pill" id="outState">Output: --</div>
      <div class="pill" id="stopState">Motors: --</div>
    </div>

    <div class="card">
      <div class="muted" style="margin-bottom:8px">Console</div>
      <div id="log"></div>
    </div>
  </div>

  <script>
    let ws;
    const maxPts = 120;
    const el = (id)=>document.getElementById(id);
    const logEl = el('log');
    const wsState = el('wsState');
    const angleState = el('angleState');
    const outState = el('outState');
    const stopState = el('stopState');

    const kp = el('kp'), ki = el('ki'), kd = el('kd');
    const kpv = el('kpv'), kiv = el('kiv'), kdv = el('kdv');

    const chart = new Chart(el('plot'), {
      type:'line',
      data:{
        labels:[],
        datasets:[
          {label:'Setpoint', data:[], borderColor:getComputedStyle(document.documentElement).getPropertyValue('--line2').trim(), tension:.2},
          {label:'Angle', data:[], borderColor:getComputedStyle(document.documentElement).getPropertyValue('--line1').trim(), tension:.2}
        ]
      },
      options:{
        animation:false,
        responsive:true,
        maintainAspectRatio:false,
        scales:{x:{display:false}}
      }
    });

    function log(msg){
      const t = new Date().toLocaleTimeString();
      logEl.textContent += `[${t}] ${msg}\n`;
      logEl.scrollTop = logEl.scrollHeight;
    }

    function syncPair(r, n){
      r.addEventListener('input', ()=>{n.value = r.value; sendPID();});
      n.addEventListener('change', ()=>{
        r.value = n.value;
        sendPID();
      });
    }

    function send(obj){
      if(ws && ws.readyState === WebSocket.OPEN){
        ws.send(JSON.stringify(obj));
      }
    }

    function sendPID(){
      send({type:'pid', kp:parseFloat(kp.value), ki:parseFloat(ki.value), kd:parseFloat(kd.value)});
    }

    function connect(){
      ws = new WebSocket(`ws://${location.host}/ws`);
      ws.onopen = ()=>{wsState.textContent='WS: connected'; wsState.style.color='#8fffd2'; log('WebSocket connected'); send({type:'get'});};
      ws.onclose = ()=>{wsState.textContent='WS: disconnected'; wsState.style.color='#ffb3b3'; log('WebSocket disconnected, retrying...'); setTimeout(connect, 1000);};
      ws.onerror = ()=>{log('WebSocket error');};
      ws.onmessage = (ev)=>{
        try{
          const m = JSON.parse(ev.data);
          if(m.type === 'state'){
            kp.value = kpv.value = m.kp.toFixed(3);
            ki.value = kiv.value = m.ki.toFixed(3);
            kd.value = kdv.value = m.kd.toFixed(3);
            stopState.textContent = `Motors: ${m.estop ? 'STOPPED' : 'RUNNING'}`;
          }else if(m.type === 'telemetry'){
            angleState.textContent = `Angle: ${m.angle.toFixed(2)} deg`;
            outState.textContent = `Output: ${m.output.toFixed(1)}`;
            stopState.textContent = `Motors: ${m.estop ? 'STOPPED' : 'RUNNING'}`;
            chart.data.labels.push('');
            chart.data.datasets[0].data.push(m.setpoint);
            chart.data.datasets[1].data.push(m.angle);
            if(chart.data.labels.length > maxPts){
              chart.data.labels.shift();
              chart.data.datasets[0].data.shift();
              chart.data.datasets[1].data.shift();
            }
            chart.update('none');
          }else if(m.type === 'log'){
            log(m.msg);
          }
        }catch(e){
          log(`Parse error: ${ev.data}`);
        }
      };
    }

    syncPair(kp, kpv);
    syncPair(ki, kiv);
    syncPair(kd, kdv);

    el('saveBtn').onclick = ()=>send({type:'save'});
    el('exportBtn').onclick = ()=>send({type:'export'});
    el('estopBtn').onclick = ()=>send({type:'estop', value:true});
    el('resumeBtn').onclick = ()=>send({type:'estop', value:false});

    connect();
  </script>
</body>
</html>
)rawliteral";

// ------------------------------
// Forward declarations
// ------------------------------
void setupWiFi();
void setupOTA();
void setupWeb();
void setupIMU();
void loadPIDFromNVS();
void savePIDToNVS();
void broadcastState();
void broadcastLog(const String& msg);
void broadcastTelemetry();
void handleWsMessage(void* arg, uint8_t* data, size_t len);
void runControlLoop();
void setMotorOutput(double output);
double kalmanUpdate(double measuredAngleDeg, double gyroRateDegPerSec, double dtSec);

// ------------------------------
// Setup
// ------------------------------
void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.println();
  Serial.println("Booting ESP32 Balance PID Tuner...");

  loadPIDFromNVS();

  setupWiFi();
  setupOTA();
  setupWeb();
  setupIMU();

  balancePID.SetTunings(Kp, Ki, Kd);
  balancePID.SetSampleTime(5);       // ms
  balancePID.SetOutputLimits(-255, 255);
  balancePID.SetMode(AUTOMATIC);

  lastControlUs = micros();
  lastTelemetryMs = millis();

  Serial.println("System ready.");
}

// ------------------------------
// Main loop
// ------------------------------
void loop() {
  ArduinoOTA.handle();
  ws.cleanupClients();

  runControlLoop();

  if (millis() - lastTelemetryMs >= TELEMETRY_PERIOD_MS) {
    lastTelemetryMs = millis();
    broadcastTelemetry();
  }
}

// ------------------------------
// Wi-Fi
// ------------------------------
void setupWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.printf("Connecting to Wi-Fi SSID: %s\n", WIFI_SSID);

  uint32_t start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 10000) {
    delay(250);
    Serial.print(".");
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("Wi-Fi connected. IP: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("STA connect failed. Starting AP fallback.");
    WiFi.mode(WIFI_AP);
    bool ok = WiFi.softAP(AP_SSID, AP_PASS);
    if (ok) {
      Serial.print("AP started. IP: ");
      Serial.println(WiFi.softAPIP());
    } else {
      Serial.println("AP start failed.");
    }
  }
}

// ------------------------------
// OTA
// ------------------------------
void setupOTA() {
  ArduinoOTA.setHostname("esp32-balance-bot");
  ArduinoOTA.onStart([]() { Serial.println("OTA Start"); });
  ArduinoOTA.onEnd([]() { Serial.println("OTA End"); });
  ArduinoOTA.onProgress([](unsigned int progress, unsigned int total) {
    Serial.printf("OTA Progress: %u%%\r", (progress * 100U) / total);
  });
  ArduinoOTA.onError([](ota_error_t error) {
    Serial.printf("OTA Error[%u]\n", error);
  });
  ArduinoOTA.begin();
  Serial.println("OTA ready.");
}

// ------------------------------
// Web / WS
// ------------------------------
void setupWeb() {
  ws.onEvent([](AsyncWebSocket* serverObj, AsyncWebSocketClient* client, AwsEventType type, void* arg, uint8_t* data, size_t len) {
    (void)serverObj;
    if (type == WS_EVT_CONNECT) {
      Serial.printf("WS client connected: #%u from %s\n", client->id(), client->remoteIP().toString().c_str());
      broadcastState();
    } else if (type == WS_EVT_DISCONNECT) {
      Serial.printf("WS client disconnected: #%u\n", client->id());
    } else if (type == WS_EVT_DATA) {
      handleWsMessage(arg, data, len);
    }
  });

  server.addHandler(&ws);

  server.on("/", HTTP_GET, [](AsyncWebServerRequest* req) {
    req->send_P(200, "text/html", INDEX_HTML);
  });

  server.on("/health", HTTP_GET, [](AsyncWebServerRequest* req) {
    req->send(200, "application/json", "{\"ok\":true}");
  });

  server.begin();
  Serial.println("Web server started.");
}

// ------------------------------
// IMU
// ------------------------------
void setupIMU() {
  Wire.begin();
  byte status = mpu.begin();
  Serial.print("MPU6050 status: ");
  Serial.println(status);
  if (status != 0) {
    Serial.println("MPU init failed. Verify wiring/power.");
  }
  Serial.println("Keep robot still for gyro calibration...");
  delay(1000);
  mpu.calcOffsets();
  mpu.update();
  kfAngleDeg = mpu.getAngleY();  // adjust axis if your IMU orientation differs
  kfBiasDegPerSec = 0.0;
  kfP00 = 1.0;
  kfP01 = 0.0;
  kfP10 = 0.0;
  kfP11 = 1.0;
  currentAngle = kfAngleDeg;
  Serial.println("IMU calibrated.");
  lastImuMs = millis();
}

// ------------------------------
// PID persistence
// ------------------------------
void loadPIDFromNVS() {
  prefs.begin("pidcfg", true);
  Kp = prefs.getDouble("kp", Kp);
  Ki = prefs.getDouble("ki", Ki);
  Kd = prefs.getDouble("kd", Kd);
  prefs.end();
  Serial.printf("Loaded PID from NVS: Kp=%.4f Ki=%.4f Kd=%.4f\n", Kp, Ki, Kd);
}

void savePIDToNVS() {
  prefs.begin("pidcfg", false);
  prefs.putDouble("kp", Kp);
  prefs.putDouble("ki", Ki);
  prefs.putDouble("kd", Kd);
  prefs.end();
}

// ------------------------------
// WS helpers
// ------------------------------
void broadcastState() {
  String msg = String("{\"type\":\"state\",\"kp\":") + String(Kp, 4) +
               ",\"ki\":" + String(Ki, 4) +
               ",\"kd\":" + String(Kd, 4) +
               ",\"estop\":" + (emergencyStop ? "true" : "false") + "}";
  ws.textAll(msg);
}

void broadcastLog(const String& msg) {
  String escaped = msg;
  escaped.replace("\\", "\\\\");
  escaped.replace("\"", "\\\"");
  String payload = String("{\"type\":\"log\",\"msg\":\"") + escaped + "\"}";
  ws.textAll(payload);
}

void broadcastTelemetry() {
  String msg = String("{\"type\":\"telemetry\",\"setpoint\":") + String(setpoint, 3) +
               ",\"angle\":" + String(currentAngle, 3) +
               ",\"output\":" + String(pidOutput, 2) +
               ",\"estop\":" + (emergencyStop ? "true" : "false") + "}";
  ws.textAll(msg);
}

// Naive JSON parser for known message formats to keep this single-file and lightweight.
static bool extractNumber(const String& src, const String& key, double& out) {
  int keyPos = src.indexOf("\"" + key + "\"");
  if (keyPos < 0) return false;
  int colon = src.indexOf(':', keyPos);
  if (colon < 0) return false;
  int end = src.indexOf(',', colon + 1);
  if (end < 0) end = src.indexOf('}', colon + 1);
  if (end < 0) return false;
  String token = src.substring(colon + 1, end);
  token.trim();
  out = token.toDouble();
  return true;
}

static bool extractBool(const String& src, const String& key, bool& out) {
  int keyPos = src.indexOf("\"" + key + "\"");
  if (keyPos < 0) return false;
  int colon = src.indexOf(':', keyPos);
  if (colon < 0) return false;
  int end = src.indexOf(',', colon + 1);
  if (end < 0) end = src.indexOf('}', colon + 1);
  if (end < 0) return false;
  String token = src.substring(colon + 1, end);
  token.trim();
  token.toLowerCase();
  out = (token == "true" || token == "1");
  return true;
}

static bool hasType(const String& src, const char* typeValue) {
  String pattern = String("\"type\":\"") + typeValue + "\"";
  return src.indexOf(pattern) >= 0;
}

void handleWsMessage(void* arg, uint8_t* data, size_t len) {
  AwsFrameInfo* info = (AwsFrameInfo*)arg;
  if (!info || !info->final || info->index != 0 || info->len != len || info->opcode != WS_TEXT) return;

  String msg;
  msg.reserve(len + 1);
  for (size_t i = 0; i < len; ++i) msg += (char)data[i];

  if (hasType(msg, "pid")) {
    double newKp, newKi, newKd;
    bool ok1 = extractNumber(msg, "kp", newKp);
    bool ok2 = extractNumber(msg, "ki", newKi);
    bool ok3 = extractNumber(msg, "kd", newKd);
    if (ok1 && ok2 && ok3) {
      Kp = newKp;
      Ki = newKi;
      Kd = newKd;
      balancePID.SetTunings(Kp, Ki, Kd);
      String log = String("PID updated: Kp=") + String(Kp, 4) + " Ki=" + String(Ki, 4) + " Kd=" + String(Kd, 4);
      Serial.println(log);
      broadcastLog(log);
      broadcastState();
    }
  } else if (hasType(msg, "save")) {
    savePIDToNVS();
    String log = "PID saved to Preferences (NVS).";
    Serial.println(log);
    broadcastLog(log);
  } else if (hasType(msg, "export")) {
    String out = String("EXPORT PID -> double Kp=") + String(Kp, 4) +
                 "; double Ki=" + String(Ki, 4) +
                 "; double Kd=" + String(Kd, 4) + ";";
    Serial.println(out);
    broadcastLog(out);
  } else if (hasType(msg, "estop")) {
    bool v = true;
    extractBool(msg, "value", v);
    emergencyStop = v;
    if (emergencyStop) {
      setMotorOutput(0);
      String log = "E-STOP activated: motor output forced to 0.";
      Serial.println(log);
      broadcastLog(log);
    } else {
      String log = "E-STOP released.";
      Serial.println(log);
      broadcastLog(log);
    }
    broadcastState();
  } else if (hasType(msg, "get")) {
    broadcastState();
  }
}

// ------------------------------
// Control loop
// ------------------------------
void runControlLoop() {
  uint32_t nowUs = micros();
  if ((uint32_t)(nowUs - lastControlUs) < CONTROL_PERIOD_US) return;
  double dtSec = (nowUs - lastControlUs) / 1000000.0;
  if (dtSec <= 0.0) dtSec = CONTROL_PERIOD_US / 1000000.0;
  lastControlUs = nowUs;

  // IMU update
  mpu.update();
  double accelAngleDeg = mpu.getAngleY();      // adjust axis for your mounting orientation
  double gyroRateDegPerSec = mpu.getGyroY();   // same axis as accelAngleDeg
  currentAngle = kalmanUpdate(accelAngleDeg, gyroRateDegPerSec, dtSec);

  // PID compute
  balancePID.Compute();

  // Safety gate
  if (emergencyStop) {
    setMotorOutput(0);
    return;
  }

  // Basic tip-over cutoff. Tune threshold for your robot.
  if (abs(currentAngle) > 35.0) {
    setMotorOutput(0);
    return;
  }

  setMotorOutput(pidOutput);
}

double kalmanUpdate(double measuredAngleDeg, double gyroRateDegPerSec, double dtSec) {
  double rate = gyroRateDegPerSec - kfBiasDegPerSec;
  kfAngleDeg += dtSec * rate;

  kfP00 += dtSec * (dtSec * kfP11 - kfP01 - kfP10 + Q_angle);
  kfP01 -= dtSec * kfP11;
  kfP10 -= dtSec * kfP11;
  kfP11 += Q_bias * dtSec;

  double innovation = measuredAngleDeg - kfAngleDeg;
  double s = kfP00 + R_measure;
  double k0 = kfP00 / s;
  double k1 = kfP10 / s;

  kfAngleDeg += k0 * innovation;
  kfBiasDegPerSec += k1 * innovation;

  double p00Tmp = kfP00;
  double p01Tmp = kfP01;
  kfP00 -= k0 * p00Tmp;
  kfP01 -= k0 * p01Tmp;
  kfP10 -= k1 * p00Tmp;
  kfP11 -= k1 * p01Tmp;

  return kfAngleDeg;
}

// ------------------------------
// Motor output abstraction
// ------------------------------
void setMotorOutput(double output) {
  // Placeholder:
  // Map PID output [-255..255] to your motor driver signals.
  // For DC motors:
  //   - set direction pins based on sign(output)
  //   - set PWM duty on EN pins using abs(output)
  //
  // For stepper drivers:
  //   - convert output to target step rate and direction
  //   - enforce acceleration limits to reduce jitter
  //
  // Keep this function fast and non-blocking.

  int pwm = (int)constrain(abs(output), 0, 255);
  (void)pwm;
}
