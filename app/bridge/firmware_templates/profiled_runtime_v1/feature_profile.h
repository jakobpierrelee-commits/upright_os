#pragma once

/*
  UpRight.os Profile + Feature Flag Template
  Use one compile profile at a time.
*/

// ------------------------------
// Profile select
// ------------------------------
#define UPRIGHT_PROFILE_TEST_MINIMAL 1
#define UPRIGHT_PROFILE_LAB_FULL 2
#define UPRIGHT_PROFILE_FIELD_HARDENED 3

#ifndef UPRIGHT_PROFILE
#define UPRIGHT_PROFILE UPRIGHT_PROFILE_TEST_MINIMAL
#endif

// ------------------------------
// Core (non-optional safety path)
// ------------------------------
#define FEAT_FIXED_RATE_LOOP 1
#define FEAT_SAFETY_STATE_MACHINE 1
#define FEAT_ESTOP_LATCH 1
#define FEAT_WATCHDOG 1
#define FEAT_SENSOR_PLAUSIBILITY 1
#define FEAT_NO_HEAP_RT_PATH 1

// ------------------------------
// Optional modules (profile-controlled)
// ------------------------------
#if UPRIGHT_PROFILE == UPRIGHT_PROFILE_TEST_MINIMAL
  #define FEAT_ADV_TELEMETRY 0
  #define FEAT_VERBOSE_DIAGNOSTICS 0
  #define FEAT_AUTOTUNE_HELPERS 0
  #define FEAT_COHEN_COON_CMD 0
  #define FEAT_TRANSFER_FN_CMD 0
  #define FEAT_BURST_LOGGING 1
  #define FEAT_EEPROM_CONFIG 0
  #define FEAT_ADAPTIVE_GAINS 0
  // Bench-friendly encoder stale policy for bring-up.
  #define ENCODER_STALE_ARM_GRACE_MS 1800U
  #define ENCODER_STALE_TIMEOUT_MS 700U
  #define ENCODER_STALE_OUT_MIN 85.0f
#elif UPRIGHT_PROFILE == UPRIGHT_PROFILE_LAB_FULL
  #define FEAT_ADV_TELEMETRY 1
  #define FEAT_VERBOSE_DIAGNOSTICS 1
  #define FEAT_AUTOTUNE_HELPERS 1
  #define FEAT_COHEN_COON_CMD 1
  #define FEAT_TRANSFER_FN_CMD 1
  #define FEAT_BURST_LOGGING 1
  #define FEAT_EEPROM_CONFIG 1
  #define FEAT_ADAPTIVE_GAINS 1
  // Slightly relaxed during lab iteration.
  #define ENCODER_STALE_ARM_GRACE_MS 1600U
  #define ENCODER_STALE_TIMEOUT_MS 650U
  #define ENCODER_STALE_OUT_MIN 80.0f
#elif UPRIGHT_PROFILE == UPRIGHT_PROFILE_FIELD_HARDENED
  #define FEAT_ADV_TELEMETRY 1
  #define FEAT_VERBOSE_DIAGNOSTICS 0
  #define FEAT_AUTOTUNE_HELPERS 0
  #define FEAT_COHEN_COON_CMD 0
  #define FEAT_TRANSFER_FN_CMD 0
  #define FEAT_BURST_LOGGING 1
  #define FEAT_EEPROM_CONFIG 1
  #define FEAT_ADAPTIVE_GAINS 0
  // Keep field profile conservative.
  #define ENCODER_STALE_ARM_GRACE_MS 500U
  #define ENCODER_STALE_TIMEOUT_MS 500U
  #define ENCODER_STALE_OUT_MIN 70.0f
#else
  #error "Unknown UPRIGHT_PROFILE value"
#endif

// ------------------------------
// Runtime budgets (determinism)
// ------------------------------
#define LOOP_HZ 200U
#define LOOP_PERIOD_US (1000000UL / LOOP_HZ)
#define STATUS_PERIOD_MS 100U

// Hard budget for control step compute on AVR Nano.
#define MAX_CONTROL_STEP_US 3500U
