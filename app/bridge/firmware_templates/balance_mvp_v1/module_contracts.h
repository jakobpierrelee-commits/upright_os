#pragma once

#include <Arduino.h>

/*
  Module interface template:
  - init(): one-time setup
  - update(dt): called each control tick
  - healthy(): module self-health
  - failOff(): force safe output state

  Rules:
  1) Optional modules must fail "off" (never unsafe).
  2) Core modules must always compile and run.
*/

struct ModuleHealth {
  bool ok;
  uint16_t fault_code;
};

class ICoreModule {
 public:
  virtual void init() = 0;
  virtual void update(float dt_s) = 0;
  virtual ModuleHealth healthy() const = 0;
  virtual void failOff() = 0;
};

class IOptionalModule {
 public:
  virtual void init() = 0;
  virtual void update(float dt_s) = 0;
  virtual ModuleHealth healthy() const = 0;
  virtual void failOff() = 0;
};

enum FaultCode : uint16_t {
  FAULT_NONE = 0,
  FAULT_SENSOR_INVALID = 10,
  FAULT_LOOP_OVERRUN = 11,
  FAULT_WATCHDOG = 12,
  FAULT_ENCODER_STALE = 13,
  FAULT_MODULE_UNHEALTHY = 20
};

// Minimal runtime state shared across modules.
struct RuntimeState {
  bool estop_latched;
  bool armed;
  float angle_deg;
  float gyro_dps;
  float output_cmd;
  uint32_t loop_overrun_count;
  uint16_t active_fault;
};
