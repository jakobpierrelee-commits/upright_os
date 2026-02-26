"""
Simulation Tools - AI agent tool implementations for PID simulation and suggestions.

Extracted from codex_tools.py for domain organization.
Tools: simulate_pid_response, suggest_next_step
"""

from __future__ import annotations

import logging
import math
from typing import Any, Callable, Dict, List, Optional

try:
    from app.bridge.domains.ai_agent.tool_constants import (
        ToolResult,
        T3Errors,
        FACTORY_DEFAULTS,
        ROBOT_DEFAULTS,
        TUNING_THRESHOLDS,
    )
except ImportError:
    from domains.ai_agent.tool_constants import (  # type: ignore
        ToolResult,
        T3Errors,
        FACTORY_DEFAULTS,
        ROBOT_DEFAULTS,
        TUNING_THRESHOLDS,
    )

logger = logging.getLogger(__name__)


class SimulationTools:
    """PID simulation and suggestion tool implementations."""

    def __init__(
        self,
        gateway: Any = None,
        db: Any = None,
        rag: Any = None,
        observe_telemetry_fn: Optional[Callable] = None,
    ):
        self.gateway = gateway
        self.db = db
        self.rag = rag
        self._observe_telemetry = observe_telemetry_fn

    def simulate_pid_response(self, args: Dict[str, Any]) -> ToolResult:
        """Simulate PID step response using linearized inverted pendulum model."""
        proposed_pid = args.get("proposed_pid", {})
        step_size_deg = float(args.get("step_size_deg", 5))
        duration_s = float(args.get("duration_s", 3))
        compare_to_current = args.get("compare_to_current", True)

        try:
            kp = float(proposed_pid.get("Kp", 0))
            ki = float(proposed_pid.get("Ki", 0))
            kd = float(proposed_pid.get("Kd", 0))
            if kp <= 0:
                return ToolResult(
                    ok=False,
                    tool="simulate_pid_response",
                    error=T3Errors.E_SIMULATION_INVALID_PARAMS,
                    data={"message": "Kp must be positive"},
                )
        except (TypeError, ValueError) as e:
            return ToolResult(
                ok=False,
                tool="simulate_pid_response",
                error=T3Errors.E_SIMULATION_INVALID_PARAMS,
                data={"message": f"Invalid PID values: {e}"},
            )

        proposed_result = self._simulate_step_response(
            kp, ki, kd, step_size_deg, duration_s
        )

        current_result = None
        comparison = None

        if compare_to_current and self.gateway:
            try:
                status = self.gateway.get_status()
                current_kp = float(status.get("kp", FACTORY_DEFAULTS["kp"]))
                current_ki = float(status.get("ki", FACTORY_DEFAULTS["ki"]))
                current_kd = float(status.get("kd", FACTORY_DEFAULTS["kd"]))
                current_result = self._simulate_step_response(
                    current_kp, current_ki, current_kd, step_size_deg, duration_s
                )
                current_result["pid"] = {
                    "Kp": current_kp,
                    "Ki": current_ki,
                    "Kd": current_kd,
                }
                comparison = self._compare_pid_simulations(
                    proposed_result, current_result
                )
            except Exception:
                pass

        proposed_result["pid"] = {"Kp": kp, "Ki": ki, "Kd": kd}

        data: Dict[str, Any] = {
            "proposed": proposed_result,
            "model_assumptions": f"Inverted pendulum, {ROBOT_DEFAULTS['mass_kg']*1000:.0f}g mass, {ROBOT_DEFAULTS['height_m']*100:.0f}cm height, {ROBOT_DEFAULTS['loop_period_ms']}ms loop",
        }

        if current_result:
            data["current"] = current_result
        if comparison:
            data["comparison"] = comparison

        return ToolResult(ok=True, tool="simulate_pid_response", data=data)

    def _simulate_step_response(
        self, kp: float, ki: float, kd: float, step_deg: float, duration_s: float
    ) -> Dict[str, Any]:
        """Simulate step response using simplified inverted pendulum dynamics."""
        g = ROBOT_DEFAULTS["gravity"]
        L = ROBOT_DEFAULTS["height_m"]

        if kp > 0:
            zeta = kd / (2 * math.sqrt(kp)) if kp > 0 else 0
            omega_cl = math.sqrt(kp) * 0.5
        else:
            zeta = 0
            omega_cl = math.sqrt(g / L)

        stability = "stable"
        oscillation_risk = "low"

        if zeta < 0.1:
            stability = "marginally_stable"
            oscillation_risk = "high"
        elif zeta < 0.4:
            oscillation_risk = "medium"
        elif zeta > 2.0:
            stability = "overdamped"

        if zeta > 0 and omega_cl > 0:
            settling_time_s = 4 / (zeta * omega_cl)
            settling_time_ms = min(settling_time_s * 1000, duration_s * 1000)
        else:
            settling_time_ms = duration_s * 1000

        if 0 < zeta < 1:
            overshoot_pct = 100 * math.exp(-math.pi * zeta / math.sqrt(1 - zeta**2))
        else:
            overshoot_pct = 0

        if ki > 0:
            steady_state_error_deg = 0.0
        else:
            steady_state_error_deg = step_deg / (1 + kp * 0.1)

        return {
            "settling_time_ms": round(settling_time_ms, 0),
            "overshoot_pct": round(overshoot_pct, 1),
            "steady_state_error_deg": round(steady_state_error_deg, 2),
            "stability": stability,
            "oscillation_risk": oscillation_risk,
            "damping_ratio": round(zeta, 2),
        }

    def _compare_pid_simulations(
        self, proposed: Dict[str, Any], current: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Compare two PID simulation results."""
        prop_settling = proposed.get("settling_time_ms", 0)
        curr_settling = current.get("settling_time_ms", 0)

        if curr_settling > 0:
            settling_delta = (
                f"{(prop_settling - curr_settling) / curr_settling * 100:+.0f}%"
            )
        else:
            settling_delta = "N/A"

        prop_overshoot = proposed.get("overshoot_pct", 0)
        curr_overshoot = current.get("overshoot_pct", 0)
        overshoot_delta = f"{prop_overshoot - curr_overshoot:+.1f}%"

        recommendations: List[str] = []

        if prop_settling < curr_settling * 0.8:
            recommendations.append("Faster settling")
        elif prop_settling > curr_settling * 1.2:
            recommendations.append("Slower settling")

        if prop_overshoot > curr_overshoot + 10:
            recommendations.append("More overshoot—consider increasing Kd")
        elif prop_overshoot < curr_overshoot - 5:
            recommendations.append("Less overshoot")

        if (
            proposed.get("oscillation_risk") == "high"
            and current.get("oscillation_risk") != "high"
        ):
            recommendations.append("Higher oscillation risk—increase Kd")

        recommendation = (
            "; ".join(recommendations)
            if recommendations
            else "Similar performance to current PID"
        )

        return {
            "settling_time_delta": settling_delta,
            "overshoot_delta": overshoot_delta,
            "recommendation": recommendation,
        }

    def suggest_next_step(self, args: Dict[str, Any]) -> ToolResult:
        """Analyze current tuning state and suggest next actions."""
        context = args.get("context", "")
        include_rationale = args.get("include_rationale", True)
        max_suggestions = min(int(args.get("max_suggestions", 3)), 5)

        current_state: Dict[str, Any] = {}
        current_pid: Dict[str, float] = {}

        if self.gateway and self._observe_telemetry:
            try:
                status = self.gateway.get_status()
                current_pid = {
                    "kp": float(status.get("kp", 18)),
                    "ki": float(status.get("ki", 0.1)),
                    "kd": float(status.get("kd", 0.6)),
                }

                obs_result = self._observe_telemetry(
                    {"duration_s": 2, "metrics": ["all"]}
                )
                if obs_result.ok:
                    metrics = obs_result.data.get("metrics", {})
                    current_state = {
                        "angle_variance": metrics.get("angle_variance", 0),
                        "oscillation_detected": metrics.get(
                            "oscillation_detected", False
                        ),
                        "oscillation_freq_hz": metrics.get("oscillation_freq_hz"),
                        "output_saturation_pct": metrics.get(
                            "output_saturation_pct", 0
                        ),
                        "mode": obs_result.data.get("latest_sample", {}).get(
                            "mode", "UNKNOWN"
                        ),
                    }
            except Exception as e:
                logger.warning(f"Could not gather telemetry for suggestions: {e}")

        if not current_state:
            return ToolResult(
                ok=False,
                tool="suggest_next_step",
                error=T3Errors.E_SUGGESTION_NO_DATA,
                data={"message": "Could not gather current telemetry state"},
            )

        suggestions = self._generate_tuning_suggestions(
            current_state, current_pid, context, include_rationale
        )
        suggestions = suggestions[:max_suggestions]

        data_sources = ["current_telemetry"]
        if self.db:
            data_sources.append("checkpoint_history")
        if self.rag:
            data_sources.append("knowledge_base")

        return ToolResult(
            ok=True,
            tool="suggest_next_step",
            data={
                "current_state": current_state,
                "current_pid": current_pid,
                "suggestions": suggestions,
                "data_sources": data_sources,
            },
        )

    def _generate_tuning_suggestions(
        self,
        state: Dict[str, Any],
        pid: Dict[str, float],
        context: str,
        include_rationale: bool,
    ) -> List[Dict[str, Any]]:
        """Generate ranked tuning suggestions based on current state."""
        suggestions: List[Dict[str, Any]] = []
        kp = pid.get("kp", 18)
        ki = pid.get("ki", 0.1)
        kd = pid.get("kd", 0.6)

        variance = state.get("angle_variance", 0)
        osc_detected = state.get("oscillation_detected", False)
        osc_freq = state.get("oscillation_freq_hz")
        saturation = state.get("output_saturation_pct", 0)

        # Rule 1: High-frequency oscillation → reduce Kd
        if (
            osc_detected
            and osc_freq
            and osc_freq > TUNING_THRESHOLDS["oscillation_freq_high_hz"]
        ):
            new_kd = round(kd * 0.8, 2)
            suggestions.append(
                {
                    "rank": len(suggestions) + 1,
                    "action": f"Reduce Kd by 20% (high-freq oscillation at {osc_freq:.1f}Hz)",
                    "command": f"PID {kp} {ki} {new_kd}",
                    "confidence": 0.85,
                    "rationale": f"Oscillation at {osc_freq:.1f}Hz is characteristic of derivative kick."
                    if include_rationale
                    else None,
                    "expected_outcome": "Oscillation should decrease within 2-3 seconds",
                }
            )

        # Rule 2: Low-frequency oscillation → reduce Ki
        if (
            osc_detected
            and osc_freq
            and osc_freq < TUNING_THRESHOLDS["oscillation_freq_low_hz"]
        ):
            new_ki = round(ki * 0.5, 3)
            suggestions.append(
                {
                    "rank": len(suggestions) + 1,
                    "action": f"Reduce Ki by 50% (low-freq oscillation at {osc_freq:.1f}Hz)",
                    "command": f"PID {kp} {new_ki} {kd}",
                    "confidence": 0.75,
                    "rationale": "Low-frequency oscillation suggests integral windup."
                    if include_rationale
                    else None,
                    "expected_outcome": "Slower but more stable recovery",
                }
            )

        # Rule 3: High output saturation → reduce Kp
        if saturation > TUNING_THRESHOLDS["saturation_critical_pct"]:
            new_kp = round(kp * 0.85, 1)
            suggestions.append(
                {
                    "rank": len(suggestions) + 1,
                    "action": f"Reduce Kp by 15% (output saturation at {saturation:.0f}%)",
                    "command": f"PID {new_kp} {ki} {kd}",
                    "confidence": 0.80,
                    "rationale": f"Output saturation at {saturation:.0f}% indicates gain is too high."
                    if include_rationale
                    else None,
                    "expected_outcome": "Reduced saturation, more control headroom",
                }
            )

        # Rule 4: High variance without oscillation → increase Kp
        if (
            variance > TUNING_THRESHOLDS["angle_variance_acceptable"]
            and not osc_detected
        ):
            new_kp = round(kp * 1.15, 1)
            suggestions.append(
                {
                    "rank": len(suggestions) + 1,
                    "action": f"Increase Kp by 15% (high variance {variance:.1f}°)",
                    "command": f"PID {new_kp} {ki} {kd}",
                    "confidence": 0.70,
                    "rationale": f"Angle variance of {variance:.1f}° suggests insufficient proportional gain."
                    if include_rationale
                    else None,
                    "expected_outcome": "Tighter angle control, faster correction",
                }
            )

        # Rule 5: Oscillation detected but no freq data → increase Kd
        if osc_detected and not osc_freq:
            new_kd = round(kd * 1.2, 2)
            suggestions.append(
                {
                    "rank": len(suggestions) + 1,
                    "action": "Increase Kd by 20% (dampen oscillation)",
                    "command": f"PID {kp} {ki} {new_kd}",
                    "confidence": 0.60,
                    "rationale": "Oscillation detected. Increasing derivative gain adds damping."
                    if include_rationale
                    else None,
                    "expected_outcome": "Reduced oscillation amplitude",
                }
            )

        # Rule 6: Good state → suggest checkpoint
        if (
            variance < TUNING_THRESHOLDS["angle_variance_good"]
            and not osc_detected
            and saturation < TUNING_THRESHOLDS["saturation_warning_pct"]
        ):
            suggestions.append(
                {
                    "rank": len(suggestions) + 1,
                    "action": "Save checkpoint (current tuning looks good)",
                    "command": None,
                    "confidence": 0.90,
                    "rationale": f"Variance {variance:.1f}°, no oscillation—this is a good tuning point."
                    if include_rationale
                    else None,
                    "expected_outcome": "Preserve this configuration for future reference",
                }
            )

        # Rule 7: Fallback—try small Kp adjustment
        if len(suggestions) < 2:
            new_kp = round(kp * 1.1, 1)
            suggestions.append(
                {
                    "rank": len(suggestions) + 1,
                    "action": "Try 10% Kp increase (exploratory)",
                    "command": f"PID {new_kp} {ki} {kd}",
                    "confidence": 0.50,
                    "rationale": "No clear issue detected. Small Kp increase may improve responsiveness."
                    if include_rationale
                    else None,
                    "expected_outcome": "Slightly faster response",
                }
            )

        suggestions.sort(key=lambda x: x.get("confidence", 0), reverse=True)
        for i, s in enumerate(suggestions):
            s["rank"] = i + 1

        return suggestions
