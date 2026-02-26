# Balance Variable Manifest (Nano Compat)

Scope: `app/bridge/firmware_templates/balance_mvp_v1/balance_mvp_v1.ino`

Purpose: prevent variable oversight during tuning by making all balance-relevant variables explicit.

## 1) Control Law

`g_cfg.kp`, `g_cfg.ki`, `g_cfg.kd`, `g_cfg.set_deg`, `g_cfg.out_max`, `g_cfg.i_max`, `g_cfg.i_term_max`, `g_cfg.d_cutoff_hz`, `g_conditional_i`, `g_pid_err`, `g_pid_p`, `g_pid_i`, `g_pid_d`, `g_pid_u_unsat`, `g_pid_u_sat`, `g_i_state`, `g_prev_err`, `g_output_saturated`, `g_d_alpha`, `g_d_unfilt`, `g_d_filt`, `g_d_init`

## 2) Motion/Recenter Terms

`g_motion_kv`, `g_motion_kx`, `g_wspd_counts`, `g_wpos_target_counts`, `g_wpos_unclamped_counts`, `g_wpos_raw_counts`, `g_wdelta_counts`, `g_wdelta_tick_counts`, `MOTION_ANGLE_GATE_DEG`, `MOTION_TERM_MAX_DEG`

## 3) Output Shaping/Authority

`OUT_SLEW_PER_S`, `ARM_ENGAGE_RAMP_MS`, `g_out`, `g_state.output_cmd`, `g_out_left_cmd`, `g_out_right_cmd`, `g_cfg.motor_polarity`

## 4) Safety/Fault Gating

`g_cfg.tip_deg`, `g_state.armed`, `g_state.estop_latched`, `g_state.active_fault`, `g_fault_count`, `g_last_fault_note`, `g_runaway_score`, `g_fault_ang_snapshot`, `g_fault_out_snapshot`, `g_fault_runaway_snapshot`, `g_fault_wpos_snapshot`

## 5) Estimator/Sensor Fusion

`g_cfg.q_angle`, `g_cfg.q_bias`, `g_cfg.r_measure`, `g_cfg.angle_zero_deg`, `g_kf_angle`, `g_kf_bias`, `g_kf_P00`, `g_kf_P01`, `g_kf_P10`, `g_kf_P11`, `g_state.angle_deg`, `g_state.gyro_dps`, `g_raw`, `g_cfg.imu_polarity`, `g_cfg.imu_axis`, `g_cfg.swap_axes`, `g_imu_ok`, `g_imu_cal_loaded`

## 6) Autozero/Adaptive Setpoint

`g_autozero_enabled`, `g_autozero_trim_deg`, `g_set_eff_deg`, `g_autozero_fast_active`, `g_autozero_holdoff_until_ms`, `g_autozero_prev_out_sign`, `AUTOZERO_TRIM_MAX_DEG`, `AUTOZERO_STEP_MAX_DEG_PER_S`, `AUTOZERO_ANGLE_GATE_DEG`, `AUTOZERO_GYRO_GATE_DPS`, `AUTOZERO_OUT_FRAC_GATE`, `AUTOZERO_ERR_DEADBAND_DEG`, `AUTOZERO_ARM_HOLDOFF_MS`, `AUTOZERO_REVERSAL_HOLDOFF_MS`, `AUTOZERO_OUT_SIGN_DEADBAND`, `AUTOZERO_WSPD_GATE_COUNTS`, `AUTOZERO_FAST_WINDOW_MS`, `AUTOZERO_FAST_STEP_MAX_DEG_PER_S`, `AUTOZERO_FAST_ANGLE_GATE_DEG`, `AUTOZERO_FAST_GYRO_GATE_DPS`, `AUTOZERO_FAST_OUT_FRAC_GATE`

## 7) Encoder/Wheel State

`g_enc_l`, `g_enc_r`, `g_prev_enc_l`, `g_prev_enc_r`, `g_prev_port_d`, `g_last_moving_enc_ms`

## 8) Timing/Realtime

`DT_S`, `LOOP_PERIOD_US` (macro), `g_next_tick_us`, `g_last_tick_us`, `g_last_period_us`, `g_last_step_us`, `g_loop_missed`, `g_loop_overrun_consecutive`, `g_min_period_us`, `g_max_period_us`, `g_jitter_us`

## 9) Command Runtime State

`g_autorun_pending`, `g_autorun_due_ms`, `AUTORUN_DELAY_MAX_MS`, `AUTORUN_BOOT_DELAY_MS`, `g_state.heartbeat_ms`, `g_cmd_buf`, `g_cmd_len`

## 10) Hardware/IO Inputs

`g_vol_raw`, `Pins::ENC_LEFT`, `Pins::ENC_RIGHT`, `Pins::PWMA`, `Pins::PWMB`, `Pins::AIN1`, `Pins::BIN1`, `Pins::STBY`, `Pins::VOL`

---

## Tuning Classification

- Runtime-tunable now (no reflash):
  - `PID <kp> <ki> <kd>`
  - `SETPOINT <deg>`
  - `LIMITS <out_max> <tip_deg> [i_max] [i_term_max]`
  - `MOTION <kv> <kx>`
  - `SLEW <out_slew_per_s>`
  - `RAMP <arm_engage_ramp_ms>`
  - `MOTIONCFG <motion_angle_gate_deg> <motion_term_max_deg>`
  - `DCFG <d_cutoff_hz> <kaw>`
  - `AUTOZERO <0|1>`
  - `AZCFG <step_max> <angle_gate> <gyro_gate> <out_frac_gate> <arm_holdoff_ms> <reversal_holdoff_ms> <out_sign_deadband> <wspd_gate_counts>`
  - `AZFAST <window_ms> <fast_step_max> <fast_angle_gate> <fast_gyro_gate> <fast_out_frac_gate>`
  - `AZLIMS <trim_max_deg> <err_deadband_deg>`
- Runtime actions (state/safety, no reflash): `ARM`, `DISARM`, `ESTOP`, `FAULTCLR`, `AUTORUN`, `PREARM_CHECK`, `CAL ZERO`, `GET`
- EEPROM-backed persistence:
  - `SAVECFG` / `LOADCFG` / `DEFAULTCFG`
  - runtime config (`g_cfg`) + motion config + runtime tune values
- Compile-time only: loop period/timing macros, feature flags, pin map, low-level estimator implementation details, safety grace-window constants

---

Operational process reference:
- For tuning sequence, backtracking policy, and per-run workflow use:
  - `docs/TUNING_AGENT_GROUND_RULES_V1.md`
  - `docs/TUNING_STAGE_TRACKER_TEMPLATE.md`
