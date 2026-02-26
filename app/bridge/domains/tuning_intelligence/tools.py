"""
Tuning Intelligence Tools - AI agent tool implementations for telemetry observation.

Extracted from codex_tools.py for domain organization.
Tools: get_probe_results, query_telemetry, observe_telemetry, read_burst_capture
"""

from __future__ import annotations

import statistics
import time
from typing import Any, Callable, Dict, List, Optional

try:
    from app.bridge.domains.ai_agent.tool_constants import (
        ToolResult,
        T1Errors,
        ObservationLimits,
    )
except ImportError:
    from domains.ai_agent.tool_constants import (  # type: ignore
        ToolResult,
        T1Errors,
        ObservationLimits,
    )


class TelemetryTools:
    """Telemetry observation tool implementations."""

    def __init__(
        self,
        gateway: Any = None,
        db: Any = None,
        host_capture: Any = None,
        probe_funcs: Optional[Dict[str, Callable]] = None,
        active_robot_id: Optional[str] = None,
    ):
        self.gateway = gateway
        self.db = db
        self.host_capture = host_capture
        self.probe_funcs = probe_funcs or {}
        self.active_robot_id = active_robot_id or "default"

    def get_probe_results(self, args: Dict[str, Any]) -> ToolResult:
        """Get probe/validation results."""
        probe_type = args.get("probe_type", "all")
        data: Dict[str, Any] = {}

        if probe_type in ("compat", "all"):
            if "run_compat_probe" in self.probe_funcs:
                try:
                    data["compat"] = self.probe_funcs["run_compat_probe"](self.gateway)
                except Exception as e:
                    data["compat_error"] = str(e)

        if probe_type in ("connect", "all"):
            if "run_connect_probe" in self.probe_funcs:
                try:
                    data["connect"] = self.probe_funcs["run_connect_probe"](
                        self.gateway
                    )
                except Exception as e:
                    data["connect_error"] = str(e)

        if self.gateway:
            try:
                data["status"] = self.gateway.get_status()
                data["health"] = self.gateway.health()
            except Exception as e:
                data["status_error"] = str(e)

        return ToolResult(ok=True, tool="get_probe_results", data=data)

    def query_telemetry(self, args: Dict[str, Any]) -> ToolResult:
        """Query telemetry from database."""
        if not self.db:
            return ToolResult(
                ok=False, tool="query_telemetry", error="Database not configured"
            )

        minutes = args.get("minutes", 5)
        robot_id = args.get("robot_id", self.active_robot_id)
        aggregation = args.get("aggregation", "stats")

        end_ts = time.time()
        start_ts = end_ts - (minutes * 60)

        snapshots = self.db.query_telemetry(
            robot_id=robot_id,
            start_ts=start_ts,
            end_ts=end_ts,
            limit=500,
        )

        if aggregation == "raw":
            data = {
                "count": len(snapshots),
                "samples": [
                    {
                        "ts": s.ts,
                        "ang": s.ang,
                        "raw": s.raw,
                        "out": s.out,
                        "mode": s.mode,
                    }
                    for s in snapshots[:100]
                ],
            }
        elif aggregation == "trend":
            if len(snapshots) >= 2:
                first_half = snapshots[len(snapshots) // 2 :]
                second_half = snapshots[: len(snapshots) // 2]
                avg_ang_first = (
                    sum(s.ang for s in first_half) / len(first_half)
                    if first_half
                    else 0
                )
                avg_ang_second = (
                    sum(s.ang for s in second_half) / len(second_half)
                    if second_half
                    else 0
                )
                data = {
                    "count": len(snapshots),
                    "angle_trend": "increasing"
                    if avg_ang_second > avg_ang_first + 0.1
                    else "decreasing"
                    if avg_ang_second < avg_ang_first - 0.1
                    else "stable",
                    "avg_angle_early": round(avg_ang_first, 3),
                    "avg_angle_recent": round(avg_ang_second, 3),
                }
            else:
                data = {"count": len(snapshots), "angle_trend": "insufficient_data"}
        else:  # stats
            if snapshots:
                angles = [s.ang for s in snapshots]
                outputs = [s.out for s in snapshots]
                data = {
                    "count": len(snapshots),
                    "time_range_minutes": minutes,
                    "angle": {
                        "min": round(min(angles), 3),
                        "max": round(max(angles), 3),
                        "avg": round(sum(angles) / len(angles), 3),
                    },
                    "output": {
                        "min": round(min(outputs), 1),
                        "max": round(max(outputs), 1),
                        "avg": round(sum(outputs) / len(outputs), 1),
                    },
                    "latest_mode": snapshots[0].mode if snapshots else None,
                }
            else:
                data = {"count": 0, "message": "No telemetry data in time range"}

        return ToolResult(ok=True, tool="query_telemetry", data=data)

    def observe_telemetry(self, args: Dict[str, Any]) -> ToolResult:
        """Watch live telemetry for N seconds and compute stability metrics."""
        if not self.gateway:
            return ToolResult(
                ok=False,
                tool="observe_telemetry",
                error=T1Errors.E_SERIAL_DISCONNECTED,
                data={"message": "Serial gateway not configured", "retry_after_s": 5},
            )

        try:
            health = self.gateway.health()
            if not health.get("connected"):
                return ToolResult(
                    ok=False,
                    tool="observe_telemetry",
                    error=T1Errors.E_SERIAL_DISCONNECTED,
                    data={"message": "Serial not connected", "retry_after_s": 5},
                )
        except Exception as e:
            return ToolResult(
                ok=False,
                tool="observe_telemetry",
                error=T1Errors.E_SERIAL_DISCONNECTED,
                data={"message": str(e), "retry_after_s": 5},
            )

        duration_s = min(
            float(args.get("duration_s", 5)), ObservationLimits.MAX_OBSERVE_DURATION_S
        )
        sample_rate_hz = float(
            args.get("sample_rate_hz", ObservationLimits.DEFAULT_SAMPLE_RATE_HZ)
        )
        requested_metrics = args.get(
            "metrics",
            ["angle_variance", "output_saturation_pct", "oscillation_detected"],
        )
        trigger = args.get("trigger", "immediate")

        # Handle trigger modes
        if trigger in ("on_arm", "on_balance"):
            target_mode = "ARMED" if trigger == "on_arm" else "BALANCING"
            trigger_start = time.time()
            while time.time() - trigger_start < ObservationLimits.TRIGGER_TIMEOUT_S:
                try:
                    status = self.gateway.get_status()
                    current_mode = str(status.get("mode", ""))
                    if current_mode == target_mode or (
                        trigger == "on_balance" and current_mode == "BALANCING"
                    ):
                        break
                except Exception:
                    pass
                time.sleep(0.1)
            else:
                return ToolResult(
                    ok=False,
                    tool="observe_telemetry",
                    error=T1Errors.E_TRIGGER_TIMEOUT,
                    data={
                        "message": f"Timeout waiting for {target_mode} mode",
                        "waited_s": ObservationLimits.TRIGGER_TIMEOUT_S,
                    },
                )

        # Collect samples
        samples: List[Dict[str, Any]] = []
        sample_interval = 1.0 / sample_rate_hz
        start_time = time.time()
        last_sample_time = 0.0
        expected_samples = int(duration_s * sample_rate_hz)

        while time.time() - start_time < duration_s:
            now = time.time()
            if now - last_sample_time >= sample_interval:
                try:
                    status = self.gateway.get_status()
                    if status:
                        samples.append(
                            {
                                "ts": now,
                                "ang": float(status.get("ang", 0)),
                                "raw": float(status.get("raw", 0)),
                                "out": float(status.get("out", 0)),
                                "mode": str(status.get("mode", "")),
                                "gyro": float(
                                    status.get(
                                        "gyro", status.get("gyr", status.get("gx", 0))
                                    )
                                ),
                            }
                        )
                        last_sample_time = now
                except Exception:
                    pass
            time.sleep(0.01)

        if not samples:
            return ToolResult(
                ok=False,
                tool="observe_telemetry",
                error=T1Errors.E_WS_NO_SAMPLES,
                data={"message": "No samples collected", "duration_s": duration_s},
            )

        metrics = self._compute_observation_metrics(samples, requested_metrics)
        partial = len(samples) < expected_samples * 0.8

        result_data = {
            "samples_collected": len(samples),
            "samples_expected": expected_samples,
            "duration_actual_s": round(time.time() - start_time, 2),
            "duration_requested_s": duration_s,
            "sample_rate_actual_hz": round(len(samples) / (time.time() - start_time), 1)
            if samples
            else 0,
            "metrics": metrics,
        }

        if partial:
            result_data["partial"] = True
            result_data["error_code"] = T1Errors.E_WS_DISCONNECT

        return ToolResult(ok=True, tool="observe_telemetry", data=result_data)

    def _compute_observation_metrics(
        self, samples: List[Dict[str, Any]], requested: List[str]
    ) -> Dict[str, Any]:
        """Compute requested metrics from collected samples."""
        metrics: Dict[str, Any] = {}

        if not samples:
            return metrics

        angles = [s["ang"] for s in samples]
        outputs = [s["out"] for s in samples]

        metrics["sample_count"] = len(samples)

        if "angle_variance" in requested or "all" in requested:
            metrics["angle_variance"] = (
                round(statistics.variance(angles), 4) if len(angles) > 1 else 0.0
            )

        if "angle_mean" in requested or "all" in requested:
            metrics["angle_mean"] = round(statistics.mean(angles), 4)

        if "angle_peak" in requested or "all" in requested:
            metrics["angle_peak"] = round(max(abs(a) for a in angles), 4)

        if "angle_std" in requested or "all" in requested:
            metrics["angle_std"] = (
                round(statistics.stdev(angles), 4) if len(angles) > 1 else 0.0
            )

        if "output_mean" in requested or "all" in requested:
            metrics["output_mean"] = round(statistics.mean(outputs), 2)

        if "output_saturation_pct" in requested or "all" in requested:
            saturated = sum(1 for o in outputs if abs(o) > 242)
            metrics["output_saturation_pct"] = round(100 * saturated / len(outputs), 1)

        if "oscillation_detected" in requested or "all" in requested:
            metrics["oscillation_detected"] = self._detect_oscillation(angles)

        if "settling_time_ms" in requested or "all" in requested:
            metrics["settling_time_ms"] = self._compute_settling_time(samples)

        return metrics

    def _detect_oscillation(self, angles: List[float], threshold: float = 0.5) -> bool:
        """Detect oscillation via zero-crossing analysis."""
        if len(angles) < 10:
            return False

        mean_ang = statistics.mean(angles)
        deviations = [a - mean_ang for a in angles]

        sign_changes = 0
        for i in range(1, len(deviations)):
            if deviations[i] * deviations[i - 1] < 0:
                sign_changes += 1

        return sign_changes > len(angles) * 0.2

    def _compute_settling_time(
        self, samples: List[Dict[str, Any]], threshold: float = 1.0
    ) -> Optional[int]:
        """Compute time until angle variance drops below threshold."""
        if len(samples) < 10:
            return None

        window_size = 5
        for i in range(window_size, len(samples)):
            window = [s["ang"] for s in samples[i - window_size : i]]
            if statistics.variance(window) < threshold:
                elapsed_ms = int((samples[i]["ts"] - samples[0]["ts"]) * 1000)
                return elapsed_ms

        return None
