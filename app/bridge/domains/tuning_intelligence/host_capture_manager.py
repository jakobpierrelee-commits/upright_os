"""
Host Capture Manager - Telemetry capture and event detection for tuning runs.

Extracted from server.py to domains/tuning_intelligence/
"""

from __future__ import annotations

import collections
import json
import math
import pathlib
import threading
import time
from typing import Any, Dict, Optional


class HostCaptureManager:
    def __init__(self, repo_root: pathlib.Path) -> None:
        self.out_dir = repo_root / "tests" / "results"
        self._lock = threading.Lock()
        self._state = "idle"
        self._delay_ms = 0
        self._freq_hz = 8.0
        self._target_lines = 0
        self._rows = 0
        self._armed_mono: Optional[float] = None
        self._last_row_mono: Optional[float] = None
        self._started_at: Optional[float] = None
        self._finished_at: Optional[float] = None
        self._last_error: Optional[str] = None
        self._latest_run: Optional[str] = None
        self._latest_summary: Optional[Dict[str, Any]] = None
        self._current_path: Optional[pathlib.Path] = None
        self._fh: Optional[Any] = None
        # compat/nano capture path:
        # Host-side trigger/diagnosis intentionally lives outside firmware control loops
        # so higher-capability MCU telemetry paths can replace it additively later.
        self._ring: collections.deque[Dict[str, Any]] = collections.deque(maxlen=280)
        self._trigger_enabled = True
        self._prebuffer_lines = 24
        self._trigger_angle_deg = 8.0
        self._trigger_out_frac = 0.90
        self._trigger_runaway = 0.65
        self._post_trigger_lines = 20
        self._trigger_latched = False
        self._capture_reason = "delay"
        self._capture_stale_timeout_s = 2.5
        self._capture_started_host_ts: Optional[float] = None
        self._fault_count_start = 0
        self._fault_count_end = 0
        self._max_abs_ang = 0.0
        self._max_abs_gyro = 0.0
        self._max_abs_out = 0.0
        self._max_runaway = 0.0
        self._saturation_hits = 0
        self._drift_bias_sum = 0.0
        self._drift_bias_n = 0
        self._fall_detected = False
        self._runaway_detected = False
        self._incoherent_event = False
        self._fall_streak = 0
        self._runaway_streak = 0
        self._runaway_wpos_prev = 0.0
        self._runaway_wpos_prev_sign = 0
        self._operator_outcome = ""
        self._operator_assisted = False
        self._operator_notes = ""
        self._run_intent = "unassisted_tuning"
        self._changed_params: list[str] = []

    @staticmethod
    def _header() -> str:
        return (
            "host_ts,mode,estop,fault,fault_count,ang,raw,gyro,set,out,pid,mot,wspd,wpos,"
            "wposRaw,wposRawU,wdelta,wdeltaTick,runaway,kp,ki,kd,kv,kx,encL,encR,volRaw,"
            "outL,outR,engage_ramp,fault_ang,fault_out,fault_runaway,fault_wpos"
        )

    def _close_file_unlocked(self) -> None:
        if self._fh is not None:
            try:
                self._fh.flush()
                self._fh.close()
            except Exception:
                pass
        self._fh = None

    def _finish_unlocked(self, next_state: str) -> None:
        self._state = next_state
        self._finished_at = time.time()
        self._armed_mono = None
        self._close_file_unlocked()
        if self._current_path is not None:
            self._latest_run = str(self._current_path)
            self._write_summary_unlocked()
        self._current_path = None

    def status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "state": self._state,
                "delay_ms": self._delay_ms,
                "freq_hz": self._freq_hz,
                "target_lines": self._target_lines,
                "rows": self._rows,
                "started_at": self._started_at,
                "finished_at": self._finished_at,
                "latest_run": self._latest_run,
                "latest_summary": self._latest_summary,
                "last_error": self._last_error,
                "trigger_enabled": self._trigger_enabled,
                "prebuffer_lines": self._prebuffer_lines,
                "trigger_angle_deg": self._trigger_angle_deg,
                "trigger_out_frac": self._trigger_out_frac,
                "trigger_runaway": self._trigger_runaway,
                "post_trigger_lines": self._post_trigger_lines,
                "capture_stale_timeout_s": self._capture_stale_timeout_s,
                "operator_outcome": self._operator_outcome,
                "operator_assisted": self._operator_assisted,
                "operator_notes": self._operator_notes,
                "run_intent": self._run_intent,
                "changed_params": list(self._changed_params),
            }

    @staticmethod
    def _f(status: Dict[str, Any], key: str, default: float = 0.0) -> float:
        try:
            return float(status.get(key, default))
        except Exception:
            return float(default)

    @staticmethod
    def _i(status: Dict[str, Any], key: str, default: int = 0) -> int:
        try:
            return int(float(status.get(key, default)))
        except Exception:
            return int(default)

    @classmethod
    def _to_row(cls, status: Dict[str, Any], host_ts: float) -> Dict[str, Any]:
        return {
            "host_ts": host_ts,
            "mode": str(status.get("mode", "")),
            "estop": str(status.get("estop", "")),
            "ang": cls._f(status, "ang"),
            "raw": cls._f(status, "raw"),
            "gyro": cls._f(status, "gyro"),
            "set": cls._f(status, "set"),
            "out": cls._f(status, "out"),
            "pid": str(status.get("pid", "")),
            "mot": cls._f(status, "mot"),
            "wspd": cls._f(status, "wspd"),
            "wpos": cls._f(status, "wpos"),
            "wpos_raw": cls._f(status, "wposRaw", cls._f(status, "wpos_raw")),
            "wpos_raw_u": cls._f(
                status,
                "wposRawU",
                cls._f(
                    status,
                    "wpos_raw_u",
                    cls._f(status, "wposRaw", cls._f(status, "wpos_raw")),
                ),
            ),
            "wdelta": cls._f(status, "wdelta"),
            "wdelta_tick": cls._f(
                status,
                "wdeltaTick",
                cls._f(status, "wdelta_tick", cls._f(status, "wdelta")),
            ),
            "kp": cls._f(status, "kp"),
            "ki": cls._f(status, "ki"),
            "kd": cls._f(status, "kd"),
            "kv": cls._f(status, "kv"),
            "kx": cls._f(status, "kx"),
            "encL": cls._i(status, "encL"),
            "encR": cls._i(status, "encR"),
            "volRaw": cls._f(status, "volRaw"),
            "runaway": cls._f(status, "runaway"),
            "out_l": cls._f(status, "outL", cls._f(status, "out_l")),
            "out_r": cls._f(status, "outR", cls._f(status, "out_r")),
            "engage_ramp": cls._f(status, "engage_ramp"),
            "fault_ang": cls._f(status, "fault_ang"),
            "fault_out": cls._f(status, "fault_out"),
            "fault_runaway": cls._f(status, "fault_runaway"),
            "fault_wpos": cls._f(status, "fault_wpos"),
            "out_max": cls._f(status, "outMax", cls._f(status, "out_max", 0.0)),
            "fault": cls._i(status, "fault"),
            "fault_count": cls._i(status, "fault_count"),
        }

    @staticmethod
    def _row_csv(row: Dict[str, Any]) -> str:
        return ",".join(
            [
                f"{float(row.get('host_ts', 0.0)):.6f}",
                str(row.get("mode", "")),
                str(row.get("estop", "")),
                str(row.get("fault", "")),
                str(row.get("fault_count", "")),
                str(row.get("ang", "")),
                str(row.get("raw", "")),
                str(row.get("gyro", "")),
                str(row.get("set", "")),
                str(row.get("out", "")),
                str(row.get("pid", "")),
                str(row.get("mot", "")),
                str(row.get("wspd", "")),
                str(row.get("wpos", "")),
                str(row.get("wpos_raw", "")),
                str(row.get("wpos_raw_u", "")),
                str(row.get("wdelta", "")),
                str(row.get("wdelta_tick", "")),
                str(row.get("runaway", "")),
                str(row.get("kp", "")),
                str(row.get("ki", "")),
                str(row.get("kd", "")),
                str(row.get("kv", "")),
                str(row.get("kx", "")),
                str(row.get("encL", "")),
                str(row.get("encR", "")),
                str(row.get("volRaw", "")),
                str(row.get("out_l", "")),
                str(row.get("out_r", "")),
                str(row.get("engage_ramp", "")),
                str(row.get("fault_ang", "")),
                str(row.get("fault_out", "")),
                str(row.get("fault_runaway", "")),
                str(row.get("fault_wpos", "")),
            ]
        )

    @staticmethod
    def _classify_summary(summary: Dict[str, Any]) -> str:
        if bool(summary.get("invalid_window", False)):
            return "invalid_window_low_signal"
        if bool(summary.get("bad_data_incoherent_event", False)):
            return "bad_data_incoherent_event"
        if int(summary.get("fault_count_delta", 0)) > 0:
            return "tip_event"
        if bool(summary.get("runaway_detected", False)):
            return "runaway_event"
        sat = float(summary.get("output_saturation_pct", 0.0))
        runaway = float(summary.get("max_runaway", 0.0))
        drift = float(summary.get("drift_bias_mean", 0.0))
        max_ang = float(summary.get("max_abs_ang_deg", 0.0))
        if sat >= 45.0 and runaway >= 0.7:
            return "saturation_runaway"
        if max_ang >= 6.0 and abs(drift) >= 25.0:
            return "drift_bias"
        if sat >= 25.0:
            return "underdamped"
        return "stable_or_low_signal"

    def _write_summary_unlocked(self) -> None:
        if self._latest_run is None:
            return
        duration_s = 0.0
        if self._capture_started_host_ts is not None and self._rows > 0:
            duration_s = max(0.0, time.time() - self._capture_started_host_ts)
        sat_pct = 0.0
        if self._rows > 0:
            sat_pct = max(
                0.0,
                min(100.0, 100.0 * float(self._saturation_hits) / float(self._rows)),
            )
        drift_bias = 0.0
        if self._drift_bias_n > 0:
            drift_bias = self._drift_bias_sum / float(self._drift_bias_n)
        fault_delta = max(0, int(self._fault_count_end) - int(self._fault_count_start))
        coherence_channels = 0
        if fault_delta > 0:
            coherence_channels += 1
        if self._max_abs_ang >= 8.0:
            coherence_channels += 1
        if self._max_abs_gyro >= 20.0:
            coherence_channels += 1
        if self._max_abs_out >= 20.0:
            coherence_channels += 1
        if self._max_runaway >= 0.10:
            coherence_channels += 1
        if abs(drift_bias) >= 15.0:
            coherence_channels += 1
        data_coherence_ok = coherence_channels >= 2
        event_detected = bool(self._fall_detected or self._runaway_detected)
        invalid_window = (
            not event_detected
            and self._max_abs_ang < 5.0
            and self._max_abs_out < 20.0
            and self._max_runaway < 0.10
        )
        bad_data_incoherent_event = bool(event_detected and not data_coherence_ok)
        operator_assisted = bool(self._operator_assisted)
        run_invalid_reasons: list[str] = []
        if bool(invalid_window):
            run_invalid_reasons.append("invalid_window")
        if bool(bad_data_incoherent_event):
            run_invalid_reasons.append("bad_data_incoherent_event")
        if str(self._run_intent or "unassisted_tuning") != "unassisted_tuning":
            run_invalid_reasons.append("non_tuning_intent")
        if operator_assisted:
            run_invalid_reasons.append("operator_assisted")
        if len(self._changed_params) > 1:
            run_invalid_reasons.append("multi_parameter_change")
        if int(self._rows) < 24:
            run_invalid_reasons.append("too_few_rows")
        run_valid_for_tuning = len(run_invalid_reasons) == 0
        summary: Dict[str, Any] = {
            "capture_reason": self._capture_reason,
            "rows": int(self._rows),
            "duration_s": round(duration_s, 3),
            "max_abs_ang_deg": round(self._max_abs_ang, 3),
            "max_abs_gyro_dps": round(self._max_abs_gyro, 3),
            "max_abs_out": round(self._max_abs_out, 3),
            "max_runaway": round(self._max_runaway, 3),
            "output_saturation_pct": round(sat_pct, 3),
            "drift_bias_mean": round(drift_bias, 3),
            "fault_count_delta": fault_delta,
            "fall_detected": bool(self._fall_detected or fault_delta > 0),
            "runaway_detected": bool(self._runaway_detected),
            "event_detected": bool(event_detected),
            "data_coherence_ok": bool(data_coherence_ok),
            "coherence_channels": int(coherence_channels),
            "invalid_window": bool(invalid_window),
            "bad_data_incoherent_event": bool(bad_data_incoherent_event),
            "operator_outcome": str(self._operator_outcome or ""),
            "operator_assisted": operator_assisted,
            "operator_notes": str(self._operator_notes or ""),
            "run_intent": str(self._run_intent or "unassisted_tuning"),
            "changed_params": list(self._changed_params),
            "run_valid_for_tuning": bool(run_valid_for_tuning),
            "run_invalid_reasons": run_invalid_reasons,
            "event_contract_version": "v1",
            "diagnosis": "",
        }
        summary["diagnosis"] = self._classify_summary(summary)
        self._latest_summary = summary
        try:
            p = pathlib.Path(self._latest_run)
            meta_path = p.with_suffix(".summary.json")
            meta_path.write_text(
                json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
            )
        except Exception:
            pass

    def _reset_metrics_unlocked(self) -> None:
        self._capture_started_host_ts = None
        self._fault_count_start = 0
        self._fault_count_end = 0
        self._max_abs_ang = 0.0
        self._max_abs_gyro = 0.0
        self._max_abs_out = 0.0
        self._max_runaway = 0.0
        self._saturation_hits = 0
        self._drift_bias_sum = 0.0
        self._drift_bias_n = 0
        self._fall_detected = False
        self._runaway_detected = False
        self._incoherent_event = False
        self._fall_streak = 0
        self._runaway_streak = 0
        self._runaway_wpos_prev = 0.0
        self._runaway_wpos_prev_sign = 0
        self._operator_outcome = ""
        self._operator_assisted = False
        self._operator_notes = ""
        self._run_intent = "unassisted_tuning"
        self._changed_params = []

    def label_latest_run(
        self,
        *,
        outcome: str = "",
        assisted: bool = False,
        notes: str = "",
        run_intent: str = "",
        changed_params: Optional[list[str]] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            self._operator_outcome = str(outcome or "").strip()
            self._operator_assisted = bool(assisted)
            self._operator_notes = str(notes or "").strip()
            if str(run_intent or "").strip():
                self._run_intent = str(run_intent).strip()
            if changed_params is not None:
                self._changed_params = [
                    str(x).strip() for x in list(changed_params) if str(x).strip()
                ][:4]
            if self._latest_run:
                self._write_summary_unlocked()
            return {
                "state": self._state,
                "delay_ms": self._delay_ms,
                "freq_hz": self._freq_hz,
                "target_lines": self._target_lines,
                "rows": self._rows,
                "started_at": self._started_at,
                "finished_at": self._finished_at,
                "latest_run": self._latest_run,
                "latest_summary": self._latest_summary,
                "last_error": self._last_error,
                "trigger_enabled": self._trigger_enabled,
                "prebuffer_lines": self._prebuffer_lines,
                "trigger_angle_deg": self._trigger_angle_deg,
                "trigger_out_frac": self._trigger_out_frac,
                "trigger_runaway": self._trigger_runaway,
                "post_trigger_lines": self._post_trigger_lines,
                "capture_stale_timeout_s": self._capture_stale_timeout_s,
                "operator_outcome": self._operator_outcome,
                "operator_assisted": self._operator_assisted,
                "operator_notes": self._operator_notes,
                "run_intent": self._run_intent,
                "changed_params": list(self._changed_params),
            }

    def _ingest_metrics_unlocked(self, row: Dict[str, Any]) -> None:
        ang = abs(float(row.get("ang", 0.0)))
        gyro = abs(float(row.get("gyro", 0.0)))
        out = abs(float(row.get("out", 0.0)))
        runaway = max(0.0, float(row.get("runaway", 0.0)))
        self._max_abs_ang = max(self._max_abs_ang, ang)
        self._max_abs_gyro = max(self._max_abs_gyro, gyro)
        self._max_abs_out = max(self._max_abs_out, out)
        self._max_runaway = max(self._max_runaway, runaway)
        out_max = abs(float(row.get("out_max", 0.0)))
        if out_max > 1e-3 and out >= (out_max * self._trigger_out_frac):
            self._saturation_hits += 1
        self._drift_bias_sum += float(
            row.get("wpos_raw_u", row.get("wpos_raw", row.get("wpos", 0.0)))
        )
        self._drift_bias_n += 1
        fault = int(row.get("fault", 0))
        self._fault_count_end = int(row.get("fault_count", self._fault_count_end))

        # Event contract v1:
        # - fall: fault latched OR sustained high angle
        # - runaway: sustained high output + monotonic wheel-position growth
        sample_s = 1.0 / max(1.0, float(self._freq_hz))
        fall_need = max(2, int(math.ceil(0.10 / sample_s)))
        runaway_need = max(3, int(math.ceil(0.25 / sample_s)))
        fall_angle_deg = 25.0

        if fault > 0 or ang >= fall_angle_deg:
            self._fall_streak += 1
        else:
            self._fall_streak = 0
        if self._fall_streak >= fall_need:
            self._fall_detected = True

        wpos = float(row.get("wpos_raw_u", row.get("wpos_raw", row.get("wpos", 0.0))))
        wsign = 1 if wpos > 0.0 else (-1 if wpos < 0.0 else 0)
        prev_abs = abs(self._runaway_wpos_prev)
        curr_abs = abs(wpos)
        monotonic = (
            self._runaway_wpos_prev_sign != 0
            and wsign == self._runaway_wpos_prev_sign
            and curr_abs >= (prev_abs + 0.2)
        )
        out_ref = out_max if out_max > 1.0 else 120.0
        out_hi = out >= (0.50 * out_ref)
        runaway_step = out_hi and monotonic and curr_abs >= 4.0
        if runaway_step:
            self._runaway_streak += 1
        else:
            self._runaway_streak = 0
        if self._runaway_streak >= runaway_need:
            self._runaway_detected = True
        self._runaway_wpos_prev = wpos
        self._runaway_wpos_prev_sign = wsign

    def _trigger_hit_unlocked(self, row: Dict[str, Any]) -> bool:
        if not self._trigger_enabled:
            return False
        ang = abs(float(row.get("ang", 0.0)))
        out = abs(float(row.get("out", 0.0)))
        out_max = abs(float(row.get("out_max", 0.0)))
        runaway = max(0.0, float(row.get("runaway", 0.0)))
        fault = int(row.get("fault", 0))
        by_ang = ang >= self._trigger_angle_deg
        by_out = out_max > 1e-3 and out >= (out_max * self._trigger_out_frac)
        by_runaway = runaway >= self._trigger_runaway
        by_fault = fault > 0
        return bool(by_ang or by_out or by_runaway or by_fault)

    def arm(
        self,
        *,
        delay_ms: int,
        lines: int,
        freq_hz: float = 8.0,
        trigger_enabled: bool = True,
        prebuffer_lines: int = 24,
        trigger_angle_deg: float = 8.0,
        trigger_out_frac: float = 0.90,
        trigger_runaway: float = 0.65,
        post_trigger_lines: int = 20,
        operator_outcome: str = "",
        operator_assisted: bool = False,
        operator_notes: str = "",
        run_intent: str = "unassisted_tuning",
        changed_params: Optional[list[str]] = None,
    ) -> Dict[str, Any]:
        d = max(0, min(int(delay_ms), 60_000))
        n = max(1, min(int(lines), 3_000))
        hz = max(1.0, min(float(freq_hz), 100.0))
        with self._lock:
            self._close_file_unlocked()
            self._state = "armed"
            self._delay_ms = d
            self._freq_hz = hz
            self._target_lines = n
            self._rows = 0
            # Queue now; delay timer starts only after BALANCING is reached.
            self._armed_mono = None
            self._last_row_mono = None
            self._started_at = None
            self._finished_at = None
            self._last_error = None
            self._current_path = None
            self._trigger_enabled = bool(trigger_enabled)
            self._prebuffer_lines = max(6, min(int(prebuffer_lines), 120))
            self._trigger_angle_deg = max(2.0, min(float(trigger_angle_deg), 25.0))
            self._trigger_out_frac = max(0.25, min(float(trigger_out_frac), 1.0))
            self._trigger_runaway = max(0.03, min(float(trigger_runaway), 2.0))
            self._post_trigger_lines = max(5, min(int(post_trigger_lines), 250))
            self._trigger_latched = False
            self._capture_reason = "delay"
            self._latest_summary = None
            self._reset_metrics_unlocked()
            self._operator_outcome = str(operator_outcome or "").strip()
            self._operator_assisted = bool(operator_assisted)
            self._operator_notes = str(operator_notes or "").strip()
            self._run_intent = (
                str(run_intent or "unassisted_tuning").strip() or "unassisted_tuning"
            )
            self._changed_params = [
                str(x).strip() for x in list(changed_params or []) if str(x).strip()
            ][:4]
            return {
                "state": self._state,
                "delay_ms": self._delay_ms,
                "freq_hz": self._freq_hz,
                "target_lines": self._target_lines,
                "rows": self._rows,
                "started_at": self._started_at,
                "finished_at": self._finished_at,
                "latest_run": self._latest_run,
                "latest_summary": self._latest_summary,
                "last_error": self._last_error,
                "trigger_enabled": self._trigger_enabled,
                "prebuffer_lines": self._prebuffer_lines,
                "trigger_angle_deg": self._trigger_angle_deg,
                "trigger_out_frac": self._trigger_out_frac,
                "trigger_runaway": self._trigger_runaway,
                "post_trigger_lines": self._post_trigger_lines,
                "capture_stale_timeout_s": self._capture_stale_timeout_s,
                "operator_outcome": self._operator_outcome,
                "operator_assisted": self._operator_assisted,
                "operator_notes": self._operator_notes,
                "run_intent": self._run_intent,
                "changed_params": list(self._changed_params),
            }

    def _start_capture_unlocked(self, reason: str = "delay") -> None:
        ts = int(time.time())
        self.out_dir.mkdir(parents=True, exist_ok=True)
        path = self.out_dir / f"host_run_{ts}.csv"
        self._fh = path.open("w", encoding="utf-8")
        self._fh.write(self._header() + "\n")
        pre_rows = list(self._ring)[-self._prebuffer_lines :]
        for row in pre_rows:
            self._fh.write(self._row_csv(row) + "\n")
        self._rows = len(pre_rows)
        self._fh.flush()
        self._current_path = path
        self._started_at = time.time()
        self._last_row_mono = None
        self._capture_reason = reason
        self._capture_started_host_ts = time.time()
        self._fault_count_start = (
            int(pre_rows[-1].get("fault_count", 0)) if pre_rows else 0
        )
        self._fault_count_end = self._fault_count_start
        self._max_abs_ang = 0.0
        self._max_abs_gyro = 0.0
        self._max_abs_out = 0.0
        self._max_runaway = 0.0
        self._saturation_hits = 0
        self._drift_bias_sum = 0.0
        self._drift_bias_n = 0
        for row in pre_rows:
            self._ingest_metrics_unlocked(row)
        self._state = "capturing"

    def ingest(self, status: Dict[str, Any]) -> None:
        if not status:
            return
        row = self._to_row(status, host_ts=time.time())
        with self._lock:
            self._ring.append(row)
            if self._state not in {"armed", "capturing"}:
                return
            mode = str(status.get("mode", ""))
            estop = str(status.get("estop", "1"))
            if mode != "BALANCING" or estop == "1":
                if self._state == "capturing" and self._last_row_mono is not None:
                    timeout_s = max(0.6, float(self._capture_stale_timeout_s))
                    if (time.monotonic() - self._last_row_mono) >= timeout_s:
                        self._finish_unlocked("done")
                # Require continuous BALANCING window for queued-delay logic.
                if self._state == "armed":
                    self._armed_mono = None
                return
            if self._state == "armed":
                if self._armed_mono is None:
                    self._armed_mono = time.monotonic()
                elapsed_ms = (time.monotonic() - self._armed_mono) * 1000.0
                if self._trigger_hit_unlocked(row):
                    self._trigger_latched = True
                    self._capture_reason = "event_trigger"
                    self._target_lines = min(
                        3000,
                        max(
                            self._target_lines,
                            self._prebuffer_lines + self._post_trigger_lines,
                        ),
                    )
                if elapsed_ms < float(self._delay_ms) and not self._trigger_latched:
                    return
                try:
                    self._start_capture_unlocked(reason=self._capture_reason)
                except Exception as exc:
                    self._last_error = str(exc)
                    self._finish_unlocked("failed")
                    return
            if self._state != "capturing" or self._fh is None:
                return
            period_s = 1.0 / max(self._freq_hz, 1.0)
            now_mono = time.monotonic()
            if (
                self._last_row_mono is not None
                and (now_mono - self._last_row_mono) < period_s
            ):
                return
            self._fh.write(self._row_csv(row) + "\n")
            self._rows += 1
            self._last_row_mono = now_mono
            self._ingest_metrics_unlocked(row)
            if self._rows >= self._target_lines:
                self._finish_unlocked("done")
