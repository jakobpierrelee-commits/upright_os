from __future__ import annotations

import re
import threading
import time
from typing import Any, Dict, Optional


class PreArmSafetyGate:
    def __init__(self, *, required: bool = True) -> None:
        self._lock = threading.Lock()
        self._required = bool(required)
        self._passed = False
        self._checked_at: Optional[float] = None
        self._required_reason = "startup_session"
        self._last_report: Dict[str, Any] = {}

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "required": self._required,
                "passed": self._passed,
                "required_reason": self._required_reason,
                "checked_at": self._checked_at,
                "last_report": dict(self._last_report),
            }

    def require(self, reason: str) -> Dict[str, Any]:
        with self._lock:
            self._required = True
            self._passed = False
            self._required_reason = str(reason or "manual")
            self._checked_at = None
            self._last_report = {}
            return {
                "required": self._required,
                "passed": self._passed,
                "required_reason": self._required_reason,
                "checked_at": self._checked_at,
                "last_report": dict(self._last_report),
            }

    def mark_pass(self, report: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            self._required = False
            self._passed = True
            self._required_reason = "passed"
            self._checked_at = time.time()
            self._last_report = dict(report or {})
            return {
                "required": self._required,
                "passed": self._passed,
                "required_reason": self._required_reason,
                "checked_at": self._checked_at,
                "last_report": dict(self._last_report),
            }


def run_prearm_hardware_check(
    gateway: Any,
    control: Any,
    body: Dict[str, Any],
) -> Dict[str, Any]:
    def _parse_kv_line(line: str) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for tok in str(line or "").split():
            if "=" not in tok:
                continue
            k, v = tok.split("=", 1)
            out[str(k).strip().lower()] = str(v).strip()
        return out

    def _from_rpc_report(line: str) -> Dict[str, Any]:
        kv = _parse_kv_line(line)
        bool_keys = {
            "ok",
            "stand",
            "wheel_l",
            "wheel_r",
            "estop_latch",
            "estop_unlatch",
        }
        b: Dict[str, bool] = {}
        for k in bool_keys:
            raw = str(kv.get(k, "")).strip().lower()
            b[k] = raw in {"1", "true", "yes", "ok", "pass"}
        detail = str(kv.get("detail", "")).replace("_", " ").strip()
        d_l = str(kv.get("dl", "0"))
        d_r = str(kv.get("dr", "0"))
        checks = [
            {
                "id": "bot_on_stand",
                "status": "pass" if b["stand"] else "fail",
                "detail": "operator confirmed robot is lifted/on stand"
                if b["stand"]
                else "robot must be lifted/on stand before pre-arm check",
            },
            {
                "id": "wheel_probe_mode",
                "status": "pass",
                "detail": "wheel probe mode=firmware_rpc (PREARM_CHECK)",
            },
            {
                "id": "wheel_left_pulse",
                "status": "pass" if b["wheel_l"] else "fail",
                "detail": f"left wheel probe {'validated' if b['wheel_l'] else 'failed'} (dL={d_l})",
            },
            {
                "id": "wheel_right_pulse",
                "status": "pass" if b["wheel_r"] else "fail",
                "detail": f"right wheel probe {'validated' if b['wheel_r'] else 'failed'} (dR={d_r})",
            },
            {
                "id": "estop_latch",
                "status": "pass" if b["estop_latch"] else "fail",
                "detail": "e-stop latch verified"
                if b["estop_latch"]
                else "e-stop latch not verified",
            },
            {
                "id": "estop_unlatch",
                "status": "pass" if b["estop_unlatch"] else "fail",
                "detail": "e-stop unlatch verified"
                if b["estop_unlatch"]
                else "e-stop unlatch not verified",
            },
        ]
        report: Dict[str, Any] = {
            "phase": "prearm_hardware_safety_rpc_v1",
            "checks": checks,
            "wheel_probe_mode": "firmware_rpc",
            "motor_test_supported": True,
            "rpc_used": True,
            "rpc_line": str(line or ""),
            "ok": bool(b["ok"]),
            "summary": "prearm safety checks passed"
            if b["ok"]
            else "prearm safety checks failed",
            "rpc_detail": detail or str(kv.get("reason", "")).strip(),
        }
        report["control"] = control.snapshot()
        try:
            report["status"] = gateway.get_status()
        except Exception:
            report["status"] = {}
        return report

    def _try_firmware_rpc() -> Optional[Dict[str, Any]]:
        try:
            # Bridge-first strategy: prefer firmware-owned atomic prearm check when available.
            resp = gateway.command(
                "PREARM_CHECK",
                expect_contains="PREARM_CHECK",
                timeout=4.0,
            )
            if not isinstance(resp, dict):
                return None
            lines = [str(x) for x in list(resp.get("lines") or [])]
            matched = str(resp.get("matched", "") or "")
            line = matched
            for ln in reversed(lines):
                if "PREARM_CHECK" in ln:
                    line = ln
                    break
            if not line:
                return None
            u = line.upper()
            if "OK PREARM_CHECK" in u:
                return _from_rpc_report(line)
            if "ERR PREARM_CHECK unsupported" in u:
                return None
            # Firmware responded but failed check; still return structured report when possible.
            if "PREARM_CHECK" in u:
                return _from_rpc_report(
                    line.replace("ERR PREARM_CHECK", "OK PREARM_CHECK ok=0")
                )
            return None
        except Exception as exc:
            msg = str(exc).lower()
            # Unknown/unsupported command -> legacy fallback.
            if (
                "unknown" in msg
                or "unsupported" in msg
                or "timeout waiting for expected response" in msg
            ):
                return None
            return {
                "phase": "prearm_hardware_safety_rpc_v1",
                "checks": [
                    {
                        "id": "prearm_rpc_runtime",
                        "status": "fail",
                        "detail": f"PREARM_CHECK rpc failed: {str(exc)}",
                    }
                ],
                "wheel_probe_mode": "firmware_rpc_failed",
                "motor_test_supported": True,
                "rpc_used": True,
                "ok": False,
                "summary": "prearm safety checks failed",
                "control": control.snapshot(),
                "status": {},
            }

    rpc_report = _try_firmware_rpc()
    if isinstance(rpc_report, dict):
        return rpc_report

    def _as_bool(key: str) -> bool:
        v = body.get(key)
        if isinstance(v, bool):
            return v
        s = str(v or "").strip().lower()
        return s in {"1", "true", "yes", "y", "ok", "pass"}

    def _as_int(key: str, default: int) -> int:
        try:
            return int(body.get(key, default))
        except Exception:
            return int(default)

    report: Dict[str, Any] = {
        "phase": "prearm_hardware_safety_v1",
        "checks": [],
        "summary": "pending",
    }
    checks = report["checks"]

    stand_ok = _as_bool("bot_on_stand_ok")
    checks.append(
        {
            "id": "bot_on_stand",
            "status": "pass" if stand_ok else "fail",
            "detail": (
                "operator confirmed robot is lifted/on stand"
                if stand_ok
                else "robot must be lifted/on stand before pre-arm check"
            ),
        }
    )

    def _help_has_motor_test() -> bool:
        try:
            resp = gateway.command("HELP", timeout=1.4)
            lines = list(resp.get("lines") or [])
            matched = str(resp.get("matched", "") or "")
            blob = " ".join([matched] + [str(x) for x in lines]).upper()
            return "MOTOR_TEST" in blob
        except Exception:
            return False

    def _run_motor_test(
        side: str, pwm: int = 110, duration_ms: int = 160
    ) -> Dict[str, Any]:
        side_u = side.upper()
        resp = gateway.command(
            f"MOTOR_TEST {side_u} {int(pwm)} {int(duration_ms)}",
            timeout=2.8,
        )
        lines = [str(x) for x in list(resp.get("lines") or [])]
        line = str(resp.get("matched", "") or "")
        if lines:
            # Prefer explicit MOTOR_TEST response line when present.
            for ln in reversed(lines):
                if "MOTOR_TEST" in ln:
                    line = ln
                    break
            if not line:
                line = str(lines[-1])
        uline = line.upper()
        if "ERR MOTOR_TEST" in uline:
            raise RuntimeError(line)
        moved_m = re.search(r"\bmoved=(\d+)\b", line)
        dl_m = re.search(r"\bdL=(-?\d+)\b", line)
        dr_m = re.search(r"\bdR=(-?\d+)\b", line)
        moved = (moved_m.group(1) if moved_m else "0") == "1"
        d_l = int(dl_m.group(1)) if dl_m else 0
        d_r = int(dr_m.group(1)) if dr_m else 0
        primary_delta = d_l if side_u == "L" else d_r
        if not moved:
            moved = abs(primary_delta) >= 1
        return {
            "ok": bool(moved),
            "side": side_u,
            "delta_primary": int(primary_delta),
            "delta_left": int(d_l),
            "delta_right": int(d_r),
            "pwm": int(pwm),
            "duration_ms": int(duration_ms),
            "detail": (
                f"firmware MOTOR_TEST pwm={int(pwm)} ms={int(duration_ms)} "
                f"returned dL={d_l} dR={d_r} moved={1 if moved else 0}"
            ),
        }

    def _prepare_motor_test_state() -> Dict[str, Any]:
        notes: list[str] = []
        try:
            gateway.command("DISARM", timeout=2.0)
            notes.append("DISARM ok")
        except Exception as exc:
            notes.append(f"DISARM failed: {exc}")
        try:
            gateway.command("ESTOP 0", timeout=2.0)
            notes.append("ESTOP 0 ok")
        except Exception as exc:
            notes.append(f"ESTOP 0 failed: {exc}")
        try:
            gateway.command("FAULTCLR", timeout=2.0)
            notes.append("FAULTCLR ok")
        except Exception as exc:
            notes.append(f"FAULTCLR failed: {exc}")
        try:
            st = gateway.get_status()
        except Exception:
            st = {}
        # Some runtimes (profiled_runtime_v1) make FAULTCLR end in estop=1,fault=0.
        # If estop is not latched, latch it and clear fault again to satisfy
        # MOTOR_TEST preconditions: estop=1 and fault=0.
        estop = str(st.get("estop", ""))
        fault = str(st.get("fault", ""))
        if estop != "1":
            try:
                gateway.command("ESTOP 1", timeout=2.0)
                notes.append("ESTOP 1 ok")
            except Exception as exc:
                notes.append(f"ESTOP 1 failed: {exc}")
            try:
                gateway.command("FAULTCLR", timeout=2.0)
                notes.append("FAULTCLR(after ESTOP 1) ok")
            except Exception as exc:
                notes.append(f"FAULTCLR(after ESTOP 1) failed: {exc}")
            try:
                st = gateway.get_status()
            except Exception:
                st = {}
            estop = str(st.get("estop", ""))
            fault = str(st.get("fault", ""))
        ready_faults = {"0", "", "none", "NONE"}
        ready = estop == "1" and fault in ready_faults
        detail = f"estop={estop or '?'} fault={fault or '?'}; {'; '.join(notes)}"
        return {"ok": ready, "detail": detail, "status": st}

    def _run_motor_probe_with_retries(side: str) -> Dict[str, Any]:
        base_pwm = max(80, min(160, _as_int("wheel_probe_pwm", 110)))
        base_ms = max(120, min(260, _as_int("wheel_probe_ms", 160)))
        retries = max(1, min(4, _as_int("wheel_probe_retries", 3)))
        scale = [1.0, 1.3, 1.6, 1.9]
        attempts: list[Dict[str, Any]] = []
        for idx in range(retries):
            pwm = min(200, int(round(base_pwm * scale[idx])))
            duration_ms = min(360, int(round(base_ms * (1.0 + 0.25 * idx))))
            probe = _run_motor_test(side, pwm=pwm, duration_ms=duration_ms)
            probe["attempt"] = idx + 1
            attempts.append(probe)
            if bool(probe.get("ok", False)):
                probe["attempts"] = attempts
                return probe
        last = dict(
            attempts[-1] if attempts else {"ok": False, "detail": "no probe attempt"}
        )
        last["ok"] = False
        last["attempts"] = attempts
        return last

    auto_estop_probe = _as_bool("auto_estop_probe")
    estop_latch_ok = _as_bool("estop_latch_ok")
    estop_unlatch_ok = _as_bool("estop_unlatch_ok")

    auto_wheel_probe = _as_bool("auto_wheel_probe")
    left_ok = _as_bool("left_wheel_pulse_ok")
    right_ok = _as_bool("right_wheel_pulse_ok")
    wheel_probe_mode = "manual"
    motor_test_supported = False
    if auto_wheel_probe:
        motor_test_supported = _help_has_motor_test()
        if motor_test_supported:
            wheel_probe_mode = "auto_firmware"
            try:
                prep = _prepare_motor_test_state()
                checks.append(
                    {
                        "id": "wheel_probe_prepare",
                        "status": "pass" if prep.get("ok") else "fail",
                        "detail": str(prep.get("detail", "")),
                    }
                )
                if not bool(prep.get("ok", False)):
                    raise RuntimeError(
                        f"MOTOR_TEST preconditions not met ({str(prep.get('detail', 'unknown'))})"
                    )
                left_probe = _run_motor_probe_with_retries("L")
                right_probe = _run_motor_probe_with_retries("R")
                left_ok = bool(left_probe.get("ok", False))
                right_ok = bool(right_probe.get("ok", False))
                checks.append(
                    {
                        "id": "wheel_probe_mode",
                        "status": "pass",
                        "detail": "wheel probe mode=auto_firmware (MOTOR_TEST)",
                    }
                )
                checks.append(
                    {
                        "id": "wheel_left_probe_evidence",
                        "status": "pass" if left_ok else "fail",
                        "detail": (
                            str(left_probe.get("detail", ""))
                            if left_ok
                            else (
                                f"{str(left_probe.get('detail', ''))}; "
                                f"attempts={len(list(left_probe.get('attempts') or []))}"
                            )
                        ),
                    }
                )
                checks.append(
                    {
                        "id": "wheel_right_probe_evidence",
                        "status": "pass" if right_ok else "fail",
                        "detail": (
                            str(right_probe.get("detail", ""))
                            if right_ok
                            else (
                                f"{str(right_probe.get('detail', ''))}; "
                                f"attempts={len(list(right_probe.get('attempts') or []))}"
                            )
                        ),
                    }
                )
            except Exception as exc:
                wheel_probe_mode = "auto_firmware_failed"
                detail = str(exc)
                if "err motor_test unsafe_state" in detail.lower():
                    detail = (
                        "auto wheel probe failed: firmware rejected MOTOR_TEST (unsafe_state). "
                        "Clear active fault and keep E-Stop latched, then retry."
                    )
                checks.append(
                    {
                        "id": "wheel_probe_runtime",
                        "status": "fail",
                        "detail": detail,
                    }
                )
                left_ok = False
                right_ok = False
        else:
            checks.append(
                {
                    "id": "wheel_probe_mode",
                    "status": "warn",
                    "detail": "MOTOR_TEST not supported by firmware; using manual wheel confirmation",
                }
            )

    report["wheel_probe_mode"] = wheel_probe_mode
    report["motor_test_supported"] = motor_test_supported

    checks.append(
        {
            "id": "wheel_left_pulse",
            "status": "pass" if left_ok else "fail",
            "detail": (
                "left wheel pulse validated"
                if left_ok
                else (
                    "left wheel pulse did not validate"
                    if wheel_probe_mode.startswith("auto")
                    else "left wheel pulse not confirmed"
                )
            ),
        }
    )
    checks.append(
        {
            "id": "wheel_right_pulse",
            "status": "pass" if right_ok else "fail",
            "detail": (
                "right wheel pulse validated"
                if right_ok
                else (
                    "right wheel pulse did not validate"
                    if wheel_probe_mode.startswith("auto")
                    else "right wheel pulse not confirmed"
                )
            ),
        }
    )

    if auto_estop_probe:
        try:
            gateway.command("DISARM", timeout=2.0)
            gateway.command("ESTOP 1", timeout=2.0)
            latched = str(gateway.get_status().get("estop", "0")) == "1"
            gateway.command("ESTOP 0", timeout=2.0)
            cleared = str(gateway.get_status().get("estop", "1")) == "0"
            estop_latch_ok = latched
            estop_unlatch_ok = cleared
        except Exception as exc:
            checks.append(
                {
                    "id": "estop_probe_runtime",
                    "status": "fail",
                    "detail": f"auto e-stop probe failed: {str(exc)}",
                }
            )
            estop_latch_ok = False
            estop_unlatch_ok = False

    checks.append(
        {
            "id": "estop_latch",
            "status": "pass" if estop_latch_ok else "fail",
            "detail": "e-stop latch verified"
            if estop_latch_ok
            else "e-stop latch not verified",
        }
    )
    checks.append(
        {
            "id": "estop_unlatch",
            "status": "pass" if estop_unlatch_ok else "fail",
            "detail": "e-stop unlatch verified"
            if estop_unlatch_ok
            else "e-stop unlatch not verified",
        }
    )

    ok = not any(str(c.get("status")) == "fail" for c in checks if isinstance(c, dict))
    report["ok"] = ok
    report["summary"] = (
        "prearm safety checks passed" if ok else "prearm safety checks failed"
    )
    report["control"] = control.snapshot()
    try:
        report["status"] = gateway.get_status()
    except Exception:
        report["status"] = {}
    return report
