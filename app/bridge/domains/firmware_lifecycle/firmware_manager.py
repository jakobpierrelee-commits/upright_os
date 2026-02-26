"""
Firmware Manager - Compile, upload, and manage firmware lifecycle.

Extracted from server.py to domains/firmware_lifecycle/
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import secrets
import shutil
import subprocess
import threading
import time
import uuid
import zipfile
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from serial_gateway import NanoSerialGateway


def _family_capabilities() -> Dict[str, Dict[str, Any]]:
    return {
        "arduino_avr": {
            "default_telemetry_hz": 200,
            "default_telemetry_mode": "ascii_lowrate",
            "telemetry_modes": ["ascii_lowrate"],
            "imu_protocols": ["i2c"],
            "encoder_protocols": ["quadrature", "hall"],
            "actuator_protocols": ["gpio_pwm", "gpio_dir_pwm"],
            "actuator_classes": ["dual_dc_hbridge_pwm", "dual_dc_hbridge_dir_pwm"],
        },
        "esp32": {
            "default_telemetry_hz": 250,
            "default_telemetry_mode": "binary_highrate",
            "telemetry_modes": ["ascii_lowrate", "binary_highrate"],
            "imu_protocols": ["i2c", "spi"],
            "encoder_protocols": ["quadrature", "hall", "spi"],
            "actuator_protocols": ["gpio_pwm", "gpio_dir_pwm", "can"],
            "actuator_classes": [
                "dual_dc_hbridge_pwm",
                "dual_dc_hbridge_dir_pwm",
                "bldc_foc",
            ],
        },
        "rp2040": {
            "default_telemetry_hz": 250,
            "default_telemetry_mode": "binary_highrate",
            "telemetry_modes": ["ascii_lowrate", "binary_highrate"],
            "imu_protocols": ["i2c", "spi"],
            "encoder_protocols": ["quadrature", "hall", "spi"],
            "actuator_protocols": ["gpio_pwm", "gpio_dir_pwm"],
            "actuator_classes": ["dual_dc_hbridge_pwm", "dual_dc_hbridge_dir_pwm"],
        },
        "teensy": {
            "default_telemetry_hz": 400,
            "default_telemetry_mode": "binary_highrate",
            "telemetry_modes": ["ascii_lowrate", "binary_highrate"],
            "imu_protocols": ["i2c", "spi", "uart"],
            "encoder_protocols": ["quadrature", "hall", "spi"],
            "actuator_protocols": ["gpio_pwm", "gpio_dir_pwm", "can"],
            "actuator_classes": [
                "dual_dc_hbridge_pwm",
                "dual_dc_hbridge_dir_pwm",
                "bldc_foc",
            ],
        },
    }


def _pin_range_for_family(family: str) -> tuple[int, int]:
    fam = str(family or "").strip().lower()
    if fam == "esp32":
        return (0, 39)
    if fam == "rp2040":
        return (0, 29)
    if fam == "teensy":
        return (0, 54)
    return (0, 21)  # arduino_avr default


def _protocol_schema() -> Dict[str, Dict[str, Dict[str, Any]]]:
    return {
        "imu": {
            "i2c": {"required_pins": ["sda", "scl"]},
            "spi": {"required_pins": ["miso", "mosi", "sck", "cs"]},
            "uart": {"required_pins": ["rx", "tx"]},
        },
        "encoders": {
            "quadrature": {
                "required_any_pin_groups": [
                    ["left_a", "left_b"],
                    ["right_a", "right_b"],
                ]
            },
            "hall": {"required_any_pins": ["left_a", "right_a", "pulse"]},
            "spi": {"required_pins": ["miso", "mosi", "sck", "cs"]},
        },
        "actuator": {
            "gpio_pwm": {"required_pins": ["left_pwm", "right_pwm"]},
            "gpio_dir_pwm": {
                "required_pins": ["left_pwm", "right_pwm", "left_dir", "right_dir"]
            },
            "can": {"required_pins": ["can_tx", "can_rx"]},
        },
    }


def _has_valid_pin(pins: Dict[str, Any], key: str) -> bool:
    if key not in pins:
        return False
    try:
        return int(pins[key]) >= 0
    except Exception:
        return False


def _validate_protocol_pins(
    *,
    node_name: str,
    protocol: str,
    pins: Dict[str, Any],
    spec: Dict[str, Any],
    errors: list[str],
) -> None:
    required = [
        str(x).strip() for x in list(spec.get("required_pins") or []) if str(x).strip()
    ]
    for key in required:
        if not _has_valid_pin(pins, key):
            errors.append(
                f"interfaces.{node_name}.protocol_pin_missing:{protocol}.{key}"
            )
    any_pins = [
        str(x).strip()
        for x in list(spec.get("required_any_pins") or [])
        if str(x).strip()
    ]
    if any_pins and not any(_has_valid_pin(pins, k) for k in any_pins):
        errors.append(
            f"interfaces.{node_name}.protocol_pin_missing_any:{protocol}:{'|'.join(any_pins)}"
        )
    any_groups = list(spec.get("required_any_pin_groups") or [])
    if any_groups:
        group_ok = False
        rendered: list[str] = []
        for raw_group in any_groups:
            group = [str(x).strip() for x in list(raw_group or []) if str(x).strip()]
            if not group:
                continue
            rendered.append("&".join(group))
            if all(_has_valid_pin(pins, k) for k in group):
                group_ok = True
        if not group_ok and rendered:
            errors.append(
                f"interfaces.{node_name}.protocol_pin_group_missing:{protocol}:{'|'.join(rendered)}"
            )


def _validate_runtime_manifest_v1(
    manifest: Any, targets: Dict[str, Any]
) -> Dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(manifest, dict):
        return {
            "ok": False,
            "errors": ["manifest_not_object"],
            "warnings": [],
        }

    version = str(manifest.get("version", "")).strip()
    if version != "runtime_manifest_v1":
        errors.append("version_invalid")

    board = manifest.get("board")
    if not isinstance(board, dict):
        errors.append("board_missing")
        board = {}
    interfaces = manifest.get("interfaces")
    if not isinstance(interfaces, dict):
        errors.append("interfaces_missing")
        interfaces = {}

    telemetry_fields = manifest.get("telemetry_fields")
    if not isinstance(telemetry_fields, list):
        errors.append("telemetry_fields_missing")
        telemetry_fields = []
    commands = manifest.get("commands")
    if not isinstance(commands, list):
        errors.append("commands_missing")
        commands = []
    mcu_topology = manifest.get("mcu_topology")
    if mcu_topology is not None and not isinstance(mcu_topology, dict):
        errors.append("mcu_topology_invalid")
        mcu_topology = {}
    telemetry = manifest.get("telemetry")
    if telemetry is not None and not isinstance(telemetry, dict):
        errors.append("telemetry.invalid")
        telemetry = {}

    board_id = str(board.get("id", "")).strip()
    board_family = str(board.get("family", "")).strip()
    board_fqbn = str(board.get("fqbn", "")).strip()
    if not board_id:
        errors.append("board.id_required")
    if not board_family:
        errors.append("board.family_required")
    if not board_fqbn:
        errors.append("board.fqbn_required")

    target_rows = list(targets.get("boards") or []) if isinstance(targets, dict) else []
    target_by_id = {
        str(row.get("id", "")).strip(): row
        for row in target_rows
        if isinstance(row, dict) and str(row.get("id", "")).strip()
    }
    target_board = target_by_id.get(board_id)
    if board_id and target_board is None:
        errors.append(f"board.id_unknown:{board_id}")
    if target_board is not None:
        target_family = str(target_board.get("family", "")).strip()
        if board_family and target_family and board_family != target_family:
            errors.append(
                f"board.family_mismatch:manifest={board_family},registry={target_family}"
            )
        base = str(target_board.get("fqbn_base", "")).strip()
        bootloaders = list(target_board.get("bootloaders") or [])
        valid_fqbns = {base}
        for b in bootloaders:
            if not isinstance(b, dict):
                continue
            valid_fqbns.add(f"{base}{str(b.get('fqbn_suffix', '')).strip()}")
        if board_fqbn and board_fqbn not in valid_fqbns:
            errors.append("board.fqbn_not_allowed_for_board_id")
    family_caps = _family_capabilities().get(
        str((target_board or {}).get("family", "")).strip() or board_family,
        {},
    )
    telemetry_mode = ""
    if isinstance(telemetry, dict):
        telemetry_mode = str(telemetry.get("mode", "")).strip().lower()
    if telemetry_mode:
        if telemetry_mode not in {"ascii_lowrate", "binary_highrate"}:
            errors.append(f"telemetry.mode_invalid:{telemetry_mode}")
        allowed_modes = set(
            str(x).strip().lower()
            for x in list(family_caps.get("telemetry_modes") or [])
            if str(x).strip()
        )
        if allowed_modes and telemetry_mode not in allowed_modes:
            errors.append(
                f"telemetry.mode_not_supported_for_family:{board_family}:{telemetry_mode}"
            )
    else:
        warnings.append("telemetry.mode_missing:assume_ascii_lowrate")

    required_cmds = {"GET", "ARM", "DISARM", "PID", "SETPOINT"}
    cmd_set = {str(c).strip().upper() for c in commands if str(c).strip()}
    missing_cmds = sorted(list(required_cmds - cmd_set))
    for c in missing_cmds:
        errors.append(f"commands.missing:{c}")

    tf = [str(x).strip() for x in telemetry_fields if str(x).strip()]
    tf_set = set(tf)
    for fld in ["mode", "ang", "raw", "out", "fault", "estop"]:
        if fld not in tf_set:
            errors.append(f"telemetry_fields.missing:{fld}")
    if not any(k in tf_set for k in ("gyro", "gyr", "gx")):
        errors.append("telemetry_fields.missing:gyro|gyr|gx")

    imu = interfaces.get("imu")
    enc = interfaces.get("encoders")
    act = interfaces.get("actuator")
    if not isinstance(imu, dict):
        errors.append("interfaces.imu_missing")
        imu = {}
    if not isinstance(enc, dict):
        errors.append("interfaces.encoders_missing")
        enc = {}
    if not isinstance(act, dict):
        errors.append("interfaces.actuator_missing")
        act = {}

    imu_protocol = str(imu.get("protocol", "i2c") or "i2c").strip().lower()
    enc_protocol = (
        str(enc.get("protocol", "quadrature") or "quadrature").strip().lower()
    )
    raw_act_protocol = str(act.get("protocol", "") or "").strip().lower()
    act_type = str(act.get("type", "") or "").strip().lower()
    act_protocol = raw_act_protocol or (
        "gpio_dir_pwm" if "dir_pwm" in act_type else "gpio_pwm"
    )

    protocol_schema = _protocol_schema()
    if imu_protocol not in protocol_schema["imu"]:
        errors.append(f"interfaces.imu.protocol_invalid:{imu_protocol}")
    if enc_protocol not in protocol_schema["encoders"]:
        errors.append(f"interfaces.encoders.protocol_invalid:{enc_protocol}")
    if act_protocol not in protocol_schema["actuator"]:
        errors.append(f"interfaces.actuator.protocol_invalid:{act_protocol}")

    imu_allowed = set(
        str(x).strip().lower() for x in list(family_caps.get("imu_protocols") or [])
    )
    enc_allowed = set(
        str(x).strip().lower() for x in list(family_caps.get("encoder_protocols") or [])
    )
    act_allowed = set(
        str(x).strip().lower()
        for x in list(family_caps.get("actuator_protocols") or [])
    )
    if imu_allowed and imu_protocol and imu_protocol not in imu_allowed:
        errors.append(
            f"interfaces.imu.protocol_not_supported_for_family:{board_family}:{imu_protocol}"
        )
    if enc_allowed and enc_protocol and enc_protocol not in enc_allowed:
        errors.append(
            f"interfaces.encoders.protocol_not_supported_for_family:{board_family}:{enc_protocol}"
        )
    if act_allowed and act_protocol and act_protocol not in act_allowed:
        errors.append(
            f"interfaces.actuator.protocol_not_supported_for_family:{board_family}:{act_protocol}"
        )

    used_pins: Dict[int, str] = {}
    lo, hi = _pin_range_for_family(board_family or "arduino_avr")
    for node_name, node in [("imu", imu), ("encoders", enc), ("actuator", act)]:
        pins = node.get("pins") if isinstance(node, dict) else {}
        if not isinstance(pins, dict):
            errors.append(f"interfaces.{node_name}.pins_missing")
            continue
        for key, raw in pins.items():
            try:
                pin = int(raw)
            except Exception:
                errors.append(f"interfaces.{node_name}.pins.{key}_not_int")
                continue
            if pin < 0:
                continue
            if pin < lo or pin > hi:
                errors.append(
                    f"interfaces.{node_name}.pins.{key}_out_of_range:{pin} (expected {lo}-{hi})"
                )
            prev = used_pins.get(pin)
            if prev:
                errors.append(f"pin_conflict:{pin}:{prev} vs {node_name}.{key}")
            else:
                used_pins[pin] = f"{node_name}.{key}"

    imu_pins = imu.get("pins") if isinstance(imu.get("pins"), dict) else {}
    enc_pins = enc.get("pins") if isinstance(enc.get("pins"), dict) else {}
    act_pins = act.get("pins") if isinstance(act.get("pins"), dict) else {}
    if imu_protocol in protocol_schema["imu"]:
        _validate_protocol_pins(
            node_name="imu",
            protocol=imu_protocol,
            pins=imu_pins,
            spec=protocol_schema["imu"][imu_protocol],
            errors=errors,
        )
    if enc_protocol in protocol_schema["encoders"]:
        _validate_protocol_pins(
            node_name="encoders",
            protocol=enc_protocol,
            pins=enc_pins,
            spec=protocol_schema["encoders"][enc_protocol],
            errors=errors,
        )
    if act_protocol in protocol_schema["actuator"]:
        _validate_protocol_pins(
            node_name="actuator",
            protocol=act_protocol,
            pins=act_pins,
            spec=protocol_schema["actuator"][act_protocol],
            errors=errors,
        )

    if not board_id or not board_family or not board_fqbn:
        warnings.append("board_identity_incomplete")
    if "LIMITS" not in cmd_set:
        warnings.append("commands.optional_missing:LIMITS")
    if "MOTION" not in cmd_set:
        warnings.append("commands.optional_missing:MOTION")

    if isinstance(mcu_topology, dict) and mcu_topology:
        control_mcu = mcu_topology.get("control_mcu")
        if not isinstance(control_mcu, dict):
            errors.append("mcu_topology.control_mcu_missing")
            control_mcu = {}
        control_id = str((control_mcu or {}).get("id", "")).strip()
        control_role = str((control_mcu or {}).get("role", "")).strip().lower()
        if not control_id:
            errors.append("mcu_topology.control_mcu.id_required")
        if control_role and control_role != "control":
            errors.append("mcu_topology.control_mcu.role_invalid")
        control_fqbn = str((control_mcu or {}).get("fqbn", "")).strip()
        if control_fqbn and board_fqbn and control_fqbn != board_fqbn:
            warnings.append("mcu_topology.control_mcu.fqbn_differs_from_board")

        io_mcu = mcu_topology.get("io_mcu")
        if io_mcu is not None and not isinstance(io_mcu, dict):
            errors.append("mcu_topology.io_mcu_invalid")
        if isinstance(io_mcu, dict):
            io_id = str(io_mcu.get("id", "")).strip()
            io_role = str(io_mcu.get("role", "")).strip().lower()
            if not io_id:
                errors.append("mcu_topology.io_mcu.id_required")
            if io_role and io_role != "io":
                errors.append("mcu_topology.io_mcu.role_invalid")
            if control_id and io_id and control_id == io_id:
                errors.append("mcu_topology.io_mcu.id_conflicts_with_control")

        link = mcu_topology.get("link")
        if link is not None and not isinstance(link, dict):
            errors.append("mcu_topology.link_invalid")
        if isinstance(link, dict):
            transport = str(link.get("transport", "")).strip().lower()
            if transport and transport not in {"uart", "spi", "i2c", "can", "none"}:
                errors.append("mcu_topology.link.transport_invalid")

        command_namespaces = mcu_topology.get("command_namespaces")
        if command_namespaces is not None and not isinstance(command_namespaces, dict):
            errors.append("mcu_topology.command_namespaces_invalid")
        if isinstance(command_namespaces, dict):
            rc_ns = str(command_namespaces.get("remote_control", "")).strip()
            if rc_ns and not rc_ns.endswith("_"):
                warnings.append(
                    "mcu_topology.command_namespaces.remote_control_suffix_recommended"
                )

    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }


class FirmwareManager:
    def __init__(self, repo_root: pathlib.Path, default_port: str) -> None:
        self.repo_root = repo_root
        self.default_port = default_port
        self.default_sketch = (
            repo_root / "app" / "bridge" / "firmware_templates" / "profiled_runtime_v1"
        )
        self.default_fqbn = "arduino:avr:nano"
        self.arduino_cli = self._resolve_arduino_cli()
        self._lock = threading.Lock()
        self._running = False
        self._state = "idle"
        self._phase = "none"
        self._started_at: Optional[float] = None
        self._finished_at: Optional[float] = None
        self._returncode: Optional[int] = None
        self._log: list[str] = []
        self._last_cmd: list[str] = []
        self._run_artifacts_dir = self.repo_root / ".runlogs" / "firmware_ops"
        self._last_artifact: Optional[Dict[str, Any]] = None
        self._active_operation: Optional[Dict[str, Any]] = None
        self._last_completed_operation: Optional[Dict[str, Any]] = None
        self._unified_templates_dir = (
            repo_root / "app" / "bridge" / "firmware_templates" / "unified_v1"
        )
        self._generated_root = repo_root / "generated_firmware"

    def _resolve_arduino_cli(self) -> str:
        env_override = os.environ.get("ARDUINO_CLI_BIN", "").strip()
        candidates = [env_override] if env_override else []
        candidates.extend(
            [
                shutil.which("arduino-cli") or "",
                str(pathlib.Path.home() / ".local" / "bin" / "arduino-cli"),
                "/opt/homebrew/bin/arduino-cli",
                "/usr/local/bin/arduino-cli",
            ]
        )
        for c in candidates:
            if not c:
                continue
            p = pathlib.Path(c).expanduser()
            if p.exists() and p.is_file():
                return str(p)
        return "arduino-cli"

    def _set(self, **kwargs: Any) -> None:
        with self._lock:
            for k, v in kwargs.items():
                setattr(self, k, v)

    def _append_log(self, line: str) -> None:
        with self._lock:
            self._log.append(line)
            self._log = self._log[-500:]

    def _status_unlocked(self) -> Dict[str, Any]:
        return {
            "state": self._state,
            "phase": self._phase,
            "running": self._running,
            "started_at": self._started_at,
            "finished_at": self._finished_at,
            "returncode": self._returncode,
            "last_cmd": self._last_cmd,
            "log_tail": self._log[-120:],
            "last_artifact": self._last_artifact,
            "operation": {
                "running": self._running,
                "active": dict(self._active_operation)
                if isinstance(self._active_operation, dict)
                else None,
                "last_completed": (
                    dict(self._last_completed_operation)
                    if isinstance(self._last_completed_operation, dict)
                    else None
                ),
            },
            "defaults": {
                "sketch": str(self.default_sketch),
                "fqbn": self.default_fqbn,
                "port": self.default_port,
            },
        }

    def _begin_operation(
        self,
        *,
        phase: str,
        cmd: list[str],
        idempotency_key: Optional[str],
    ) -> tuple[bool, Dict[str, Any], Optional[str]]:
        with self._lock:
            if self._running:
                active = (
                    self._active_operation
                    if isinstance(self._active_operation, dict)
                    else {}
                )
                active_key = str(active.get("idempotency_key") or "").strip()
                active_phase = str(active.get("phase") or "")
                active_cmd = list(active.get("cmd") or [])
                key = str(idempotency_key or "").strip()
                if (
                    key
                    and active_key
                    and key == active_key
                    and active_phase == phase
                    and active_cmd == list(cmd)
                ):
                    snap = self._status_unlocked()
                    snap["idempotent_reused"] = True
                    return False, snap, str(active.get("op_id") or "")
                raise RuntimeError("operation_in_progress")
            started_at = time.time()
            op_id = f"fwop_{uuid.uuid4().hex[:12]}"
            self._running = True
            self._state = "running"
            self._phase = phase
            self._started_at = started_at
            self._finished_at = None
            self._returncode = None
            self._log = []
            self._last_cmd = list(cmd)
            self._active_operation = {
                "op_id": op_id,
                "phase": phase,
                "cmd": list(cmd),
                "idempotency_key": str(idempotency_key or "").strip(),
                "started_at": started_at,
            }
            return True, self._status_unlocked(), op_id

    def _reconnect_gateway_after_flash(
        self,
        *,
        gateway: NanoSerialGateway,
        local_log: list[str],
        attempts: int = 5,
        ready_timeout_s: float = 3.0,
        settle_s: float = 0.25,
    ) -> tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        n = max(1, int(attempts))
        last_err: Optional[str] = None
        for idx in range(1, n + 1):
            if settle_s > 0:
                time.sleep(min(1.0, settle_s + (idx - 1) * 0.15))
            try:
                gateway.close()
            except Exception:
                pass
            try:
                gateway.connect()
                ready = gateway.wait_ready(timeout=max(0.5, float(ready_timeout_s)))
                return True, ready, None
            except Exception as exc:
                last_err = str(exc)
                line = f"warn: reconnect attempt {idx}/{n} failed: {last_err}"
                local_log.append(line)
                self._append_log(line)
        return False, None, last_err

    @staticmethod
    def _extract_cmd_arg(cmd: list[str], flag: str) -> Optional[str]:
        try:
            idx = cmd.index(flag)
        except ValueError:
            return None
        if idx + 1 >= len(cmd):
            return None
        val = str(cmd[idx + 1] or "").strip()
        return val or None

    @staticmethod
    def _runtime_identity_from_log(log_lines: list[str]) -> Dict[str, Any]:
        mode_re = re.compile(r"\bmode=([A-Za-z0-9_]+)")
        estop_re = re.compile(r"\bestop=([0-9]+)")
        fault_re = re.compile(r"\bfault=([0-9]+)")
        ident_re = re.compile(r"\bident=([A-Za-z0-9_.:-]+)")
        hash_re = re.compile(r"\bhash=([A-Za-z0-9_.:-]+)")
        runtime_re = re.compile(r"\bruntime=([A-Za-z0-9_.:-]+)")
        tune_re = re.compile(r"\btune=([A-Za-z0-9_.:-]+)")
        for raw in reversed(log_lines):
            line = str(raw or "").strip()
            if not line:
                continue
            if "STATUS " in line:
                mode_m = mode_re.search(line)
                estop_m = estop_re.search(line)
                fault_m = fault_re.search(line)
                ident_m = ident_re.search(line)
                hash_m = hash_re.search(line)
                runtime_m = runtime_re.search(line)
                tune_m = tune_re.search(line)
                return {
                    "source": "status_line",
                    "mode": mode_m.group(1) if mode_m else None,
                    "estop": int(estop_m.group(1)) if estop_m else None,
                    "fault": int(fault_m.group(1)) if fault_m else None,
                    "ident": ident_m.group(1) if ident_m else None,
                    "hash": hash_m.group(1) if hash_m else None,
                    "runtime_version": runtime_m.group(1) if runtime_m else None,
                    "tune_version": tune_m.group(1) if tune_m else None,
                }
            m = re.search(r"bridge reconnected:\s*mode=([A-Za-z0-9_]+)", line)
            if m:
                ident_m = ident_re.search(line)
                hash_m = hash_re.search(line)
                runtime_m = runtime_re.search(line)
                tune_m = tune_re.search(line)
                return {
                    "source": "reconnect_line",
                    "mode": m.group(1),
                    "estop": None,
                    "fault": None,
                    "ident": ident_m.group(1) if ident_m else None,
                    "hash": hash_m.group(1) if hash_m else None,
                    "runtime_version": runtime_m.group(1) if runtime_m else None,
                    "tune_version": tune_m.group(1) if tune_m else None,
                }
        return {
            "source": "unavailable",
            "mode": None,
            "estop": None,
            "fault": None,
            "ident": None,
            "hash": None,
            "runtime_version": None,
            "tune_version": None,
        }

    def _snapshot_hardware_fingerprint(
        self, *, cmd: list[str], log_lines: list[str]
    ) -> Dict[str, Any]:
        selected_port = self._extract_cmd_arg(cmd, "-p")
        selected_fqbn = self._extract_cmd_arg(cmd, "--fqbn")
        selected_sketch: Optional[str] = None
        if cmd:
            tail = str(cmd[-1] or "").strip()
            if tail and not tail.startswith("-"):
                selected_sketch = tail
        out: Dict[str, Any] = {
            "captured_at": time.time(),
            "selected_port": selected_port,
            "selected_fqbn": selected_fqbn,
            "selected_sketch": selected_sketch,
            "detected_board": None,
            "runtime_identity": self._runtime_identity_from_log(log_lines),
        }
        if not selected_port:
            return out
        boards = self.list_boards()
        if not bool(boards.get("ok", False)):
            out["board_scan_error"] = str(boards.get("error", "board_scan_failed"))
            return out
        detected_ports = (
            ((boards.get("raw") or {}).get("detected_ports") or [])
            if isinstance(boards, dict)
            else []
        )
        matched: Optional[Dict[str, Any]] = None
        for row in detected_ports:
            if not isinstance(row, dict):
                continue
            port_node = row.get("port") or {}
            if not isinstance(port_node, dict):
                continue
            address = str(port_node.get("address") or "").strip()
            if address != selected_port:
                continue
            props = port_node.get("properties") or {}
            if not isinstance(props, dict):
                props = {}
            boards_node = row.get("matching_boards") or []
            has_board = (
                isinstance(boards_node, list)
                and bool(boards_node)
                and isinstance(boards_node[0], dict)
            )
            board0 = boards_node[0] if has_board else {}
            matched = {
                "address": address,
                "label": port_node.get("label"),
                "protocol": port_node.get("protocol"),
                "board_name": board0.get("name"),
                "fqbn": board0.get("fqbn"),
                "vid": props.get("vid"),
                "pid": props.get("pid"),
                "serial_number": props.get("serialNumber")
                or props.get("serial_number"),
            }
            break
        out["detected_board"] = matched
        return out

    def _record_run_artifact(
        self,
        *,
        phase: str,
        cmd: list[str],
        returncode: int,
        state: str,
        started_at: Optional[float],
        finished_at: Optional[float],
        log_lines: list[str],
        op_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> None:
        try:
            self._run_artifacts_dir.mkdir(parents=True, exist_ok=True)
            ts = float(finished_at or time.time())
            stamp = time.strftime("%Y%m%d_%H%M%S", time.localtime(ts))
            outcome = "pass" if str(state) == "passed" else "fail"
            rid = f"{stamp}_{str(phase or 'run')}_{outcome}"
            meta_path = self._run_artifacts_dir / f"{rid}.json"
            log_path = self._run_artifacts_dir / f"{rid}.log"
            hardware_fingerprint = self._snapshot_hardware_fingerprint(
                cmd=cmd, log_lines=log_lines
            )
            payload = {
                "run_id": rid,
                "phase": str(phase or ""),
                "state": str(state or ""),
                "returncode": int(returncode),
                "started_at": started_at,
                "finished_at": finished_at,
                "duration_s": (
                    max(0.0, float(finished_at) - float(started_at))
                    if (started_at is not None and finished_at is not None)
                    else None
                ),
                "cmd": list(cmd),
                "log_path": str(log_path),
                "line_count": len(log_lines),
                "op_id": str(op_id or ""),
                "idempotency_key": str(idempotency_key or ""),
                "hardware_fingerprint": hardware_fingerprint,
            }
            log_path.write_text(
                "\n".join(log_lines) + ("\n" if log_lines else ""), encoding="utf-8"
            )
            meta_path.write_text(
                json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
            )
            with self._lock:
                self._last_artifact = dict(payload)
        except Exception as exc:
            self._append_log(f"warn: artifact write failed ({exc})")

    def list_run_artifacts(self, *, limit: int = 20) -> Dict[str, Any]:
        n = max(1, min(int(limit), 200))
        root = self._run_artifacts_dir
        if not root.exists():
            return {"ok": True, "artifacts": []}
        nodes: list[pathlib.Path] = sorted(root.glob("*.json"), reverse=True)
        out: list[Dict[str, Any]] = []
        for p in nodes[:n]:
            try:
                node = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(node, dict):
                    out.append(node)
            except Exception:
                continue
        return {"ok": True, "artifacts": out}

    def _run_subprocess(
        self,
        cmd: list[str],
        *,
        phase: str,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        started, snap, op_id = self._begin_operation(
            phase=phase, cmd=cmd, idempotency_key=idempotency_key
        )
        if not started:
            return snap
        started_at = float(snap.get("started_at") or time.time())
        idem_key = str(idempotency_key or "").strip()

        def worker() -> None:
            rc = -1
            local_log: list[str] = []
            try:
                proc = subprocess.Popen(
                    cmd,
                    cwd=str(self.repo_root),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
                assert proc.stdout is not None
                for ln in proc.stdout:
                    line = ln.rstrip()
                    local_log.append(line)
                    self._append_log(line)
                rc = proc.wait()
            except Exception as exc:
                err_line = f"ERROR: {exc}"
                local_log.append(err_line)
                self._append_log(err_line)
            finally:
                finished_at = time.time()
                final_state = "passed" if rc == 0 else "failed"
                self._set(
                    _running=False,
                    _state=final_state,
                    _finished_at=finished_at,
                    _returncode=rc,
                    _active_operation=None,
                    _last_completed_operation={
                        "op_id": str(op_id or ""),
                        "phase": phase,
                        "finished_at": finished_at,
                        "state": final_state,
                        "returncode": rc,
                    },
                )
                self._record_run_artifact(
                    phase=phase,
                    cmd=cmd,
                    returncode=rc,
                    state=final_state,
                    started_at=started_at,
                    finished_at=finished_at,
                    log_lines=local_log,
                    op_id=op_id,
                    idempotency_key=idem_key,
                )

        t = threading.Thread(target=worker, daemon=True)
        t.start()
        return self.status()

    def status(self) -> Dict[str, Any]:
        with self._lock:
            return self._status_unlocked()

    def check(self) -> Dict[str, Any]:
        self.arduino_cli = self._resolve_arduino_cli()
        cmd = [self.arduino_cli, "board", "list", "--format", "json"]
        try:
            version = subprocess.check_output(
                [self.arduino_cli, "version"],
                text=True,
                cwd=str(self.repo_root),
                stderr=subprocess.STDOUT,
            ).strip()
            listing = subprocess.check_output(
                cmd, text=True, cwd=str(self.repo_root), stderr=subprocess.STDOUT
            ).strip()
            parsed = json.loads(listing) if listing else {}
            ports = parsed.get("detected_ports", []) if isinstance(parsed, dict) else []
            return {
                "ok": True,
                "version": version,
                "binary": self.arduino_cli,
                "detected_ports": ports,
                "raw": parsed,
            }
        except Exception as exc:
            return {
                "ok": False,
                "error": str(exc),
                "hint": "Install arduino-cli, then retry check.",
                "install_suggestion": "Use UI button 'Install Arduino CLI' or run: curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh | BINDIR=$HOME/.local/bin sh",
            }

    def compile(
        self,
        *,
        sketch: Optional[str] = None,
        fqbn: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        self.arduino_cli = self._resolve_arduino_cli()
        sketch_path = sketch or str(self.default_sketch)
        board = fqbn or self.default_fqbn
        cmd = [self.arduino_cli, "compile", "--fqbn", board, sketch_path]
        return self._run_subprocess(
            cmd, phase="compile", idempotency_key=idempotency_key
        )

    def upload(
        self,
        *,
        sketch: Optional[str] = None,
        fqbn: Optional[str] = None,
        port: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        self.arduino_cli = self._resolve_arduino_cli()
        sketch_path = sketch or str(self.default_sketch)
        board = fqbn or self.default_fqbn
        upload_port = port or self.default_port
        cmd = [
            self.arduino_cli,
            "upload",
            "-p",
            upload_port,
            "--fqbn",
            board,
            sketch_path,
        ]
        return self._run_subprocess(
            cmd, phase="upload", idempotency_key=idempotency_key
        )

    def upload_guarded(
        self,
        *,
        gateway: NanoSerialGateway,
        sketch: Optional[str] = None,
        fqbn: Optional[str] = None,
        port: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        self.arduino_cli = self._resolve_arduino_cli()
        sketch_path = sketch or str(self.default_sketch)
        board = fqbn or self.default_fqbn
        upload_port = port or self.default_port
        cmd = [
            self.arduino_cli,
            "upload",
            "-p",
            upload_port,
            "--fqbn",
            board,
            sketch_path,
        ]
        upload_policy = self._resolve_upload_strategy(board)

        started, snap, op_id = self._begin_operation(
            phase="upload_guarded", cmd=cmd, idempotency_key=idempotency_key
        )
        if not started:
            return snap
        started_at = float(snap.get("started_at") or time.time())
        idem_key = str(idempotency_key or "").strip()

        def worker() -> None:
            rc = -1
            reconnect_ok = False
            local_log: list[str] = []
            artifact_cmd = list(cmd)
            try:
                s0 = "guarded flash: disarm -> close serial -> upload -> reconnect"
                local_log.append(s0)
                self._append_log(s0)
                try:
                    gateway.command("DISARM", timeout=1.0)
                    s1 = "disarm command sent"
                    local_log.append(s1)
                    self._append_log(s1)
                except Exception as exc:
                    s1e = f"warn: disarm failed ({exc})"
                    local_log.append(s1e)
                    self._append_log(s1e)

                gateway.close()
                s2 = "serial bridge closed for flashing"
                local_log.append(s2)
                self._append_log(s2)

                max_upload_attempts = max(
                    1, int(upload_policy.get("max_attempts", 1) or 1)
                )
                retryable_classes = {
                    str(x).strip()
                    for x in list(upload_policy.get("retryable_classes", []) or [])
                    if str(x).strip()
                }
                retry_backoff_s = max(
                    0.0, float(upload_policy.get("retry_backoff_s", 0.35) or 0.35)
                )
                last_failure_class = "unknown"
                for attempt in range(1, max_upload_attempts + 1):
                    attempt_header = f"upload attempt {attempt}/{max_upload_attempts}"
                    local_log.append(attempt_header)
                    self._append_log(attempt_header)
                    proc = subprocess.Popen(
                        cmd,
                        cwd=str(self.repo_root),
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        bufsize=1,
                    )
                    assert proc.stdout is not None
                    attempt_lines: list[str] = []
                    for ln in proc.stdout:
                        line = ln.rstrip()
                        attempt_lines.append(line)
                        local_log.append(line)
                        self._append_log(line)
                    rc = proc.wait()
                    s3 = f"upload return code={rc}"
                    local_log.append(s3)
                    self._append_log(s3)
                    if rc == 0:
                        artifact_cmd = list(cmd)
                        break
                    failure_class = self._classify_upload_failure(
                        attempt_lines, returncode=rc
                    )
                    last_failure_class = failure_class
                    class_line = (
                        f"upload failure class={failure_class}; retryable="
                        f"{'yes' if failure_class in retryable_classes else 'no'}"
                    )
                    local_log.append(class_line)
                    self._append_log(class_line)
                    if (
                        failure_class in retryable_classes
                        and attempt < max_upload_attempts
                    ):
                        retry_line = f"warn: transient {failure_class} detected; auto-retrying upload"
                        local_log.append(retry_line)
                        self._append_log(retry_line)
                        time.sleep(retry_backoff_s)
                        continue
                    break

                if rc != 0 and last_failure_class == "bootloader_sync":
                    fallback_cmd = self._nano_bootloader_fallback_cmd(cmd)
                    if fallback_cmd is not None:
                        fallback_attempts = 2
                        fb_rc = 1
                        fb_class = "unknown"
                        fb_cmd_last = list(fallback_cmd)
                        for fb_attempt in range(1, fallback_attempts + 1):
                            fallback_port = self._resolve_port_for_retry(upload_port)
                            fb_cmd = self._cmd_with_port(
                                fallback_cmd, fallback_port or upload_port
                            )
                            fb_cmd_last = list(fb_cmd)
                            if fallback_port and fallback_port != upload_port:
                                port_line = f"fallback upload port updated: {upload_port} -> {fallback_port}"
                                local_log.append(port_line)
                                self._append_log(port_line)
                            if fb_attempt > 1:
                                fb_attempt_line = f"fallback upload attempt {fb_attempt}/{fallback_attempts}"
                                local_log.append(fb_attempt_line)
                                self._append_log(fb_attempt_line)
                            fb_hdr = "bootloader fallback: retrying upload with alternate Nano bootloader fqbn"
                            local_log.append(fb_hdr)
                            self._append_log(fb_hdr)
                            proc = subprocess.Popen(
                                fb_cmd,
                                cwd=str(self.repo_root),
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT,
                                text=True,
                                bufsize=1,
                            )
                            assert proc.stdout is not None
                            fb_lines: list[str] = []
                            for ln in proc.stdout:
                                line = ln.rstrip()
                                fb_lines.append(line)
                                local_log.append(line)
                                self._append_log(line)
                            fb_rc = proc.wait()
                            fb_rc_line = f"upload fallback return code={fb_rc}"
                            local_log.append(fb_rc_line)
                            self._append_log(fb_rc_line)
                            if fb_rc == 0:
                                rc = 0
                                artifact_cmd = list(fb_cmd)
                                note = "note: upload succeeded with alternate Nano bootloader; consider switching bootloader selection."
                                local_log.append(note)
                                self._append_log(note)
                                break
                            fb_class = self._classify_upload_failure(
                                fb_lines, returncode=fb_rc
                            )
                            retryable_fb = fb_class in retryable_classes
                            fb_class_line = (
                                f"upload fallback failure class={fb_class}; retryable="
                                f"{'yes' if retryable_fb else 'no'}"
                            )
                            local_log.append(fb_class_line)
                            self._append_log(fb_class_line)
                            if retryable_fb and fb_attempt < fallback_attempts:
                                fb_retry_line = f"warn: transient fallback {fb_class} detected; retrying fallback upload"
                                local_log.append(fb_retry_line)
                                self._append_log(fb_retry_line)
                                time.sleep(retry_backoff_s)
                                continue
                            break
                        if rc != 0:
                            artifact_cmd = list(fb_cmd_last)
            except Exception as exc:
                s4 = f"ERROR: guarded upload failed: {exc}"
                local_log.append(s4)
                self._append_log(s4)
            finally:
                if rc == 0:
                    reconnect_ok, ready, reconnect_err = (
                        self._reconnect_gateway_after_flash(
                            gateway=gateway,
                            local_log=local_log,
                            attempts=max(
                                1,
                                int(
                                    upload_policy.get("reconnect_attempts_success", 6)
                                    or 6
                                ),
                            ),
                            ready_timeout_s=max(
                                0.5,
                                float(
                                    upload_policy.get("reconnect_ready_timeout_s", 3.0)
                                    or 3.0
                                ),
                            ),
                            settle_s=0.2,
                        )
                    )
                    # Some boards/USB stacks need longer post-upload settle time.
                    # Retry once with a wider window before declaring guarded flash failure.
                    if not reconnect_ok:
                        retry_line = "warn: reconnect failed after upload; running extended reconnect sweep"
                        local_log.append(retry_line)
                        self._append_log(retry_line)
                        reconnect_ok, ready, reconnect_err = (
                            self._reconnect_gateway_after_flash(
                                gateway=gateway,
                                local_log=local_log,
                                attempts=max(
                                    8,
                                    int(
                                        upload_policy.get(
                                            "reconnect_attempts_success", 6
                                        )
                                        or 6
                                    ),
                                ),
                                ready_timeout_s=max(
                                    2.0,
                                    float(
                                        upload_policy.get(
                                            "reconnect_ready_timeout_s", 3.0
                                        )
                                        or 3.0
                                    )
                                    * 1.8,
                                ),
                                settle_s=0.45,
                            )
                        )
                    if reconnect_ok and isinstance(ready, dict):
                        mode = str(ready.get("mode", "UNKNOWN") or "UNKNOWN")
                        ident = str(ready.get("ident", "") or "").strip()
                        build_hash_value = str(ready.get("hash", "") or "").strip()
                        runtime_version = str(
                            ready.get("runtime", ready.get("runtime_version", "")) or ""
                        ).strip()
                        tune_version = str(
                            ready.get("tune", ready.get("tune_version", "")) or ""
                        ).strip()
                        parts = [f"bridge reconnected: mode={mode}"]
                        if ident:
                            parts.append(f"ident={ident}")
                        if build_hash_value:
                            parts.append(f"hash={build_hash_value}")
                        if runtime_version:
                            parts.append(f"runtime={runtime_version}")
                        if tune_version:
                            parts.append(f"tune={tune_version}")
                        s5 = " ".join(parts)
                        local_log.append(s5)
                        self._append_log(s5)
                    else:
                        s5e = f"ERROR: reconnect failed: {reconnect_err or 'unknown'}"
                        local_log.append(s5e)
                        self._append_log(s5e)
                else:
                    # Upload already failed (usually bootloader sync/port issue). Reconnect best-effort only.
                    reconnect_ok, _ready, reconnect_err = (
                        self._reconnect_gateway_after_flash(
                            gateway=gateway,
                            local_log=local_log,
                            attempts=3,
                            ready_timeout_s=1.5,
                            settle_s=0.1,
                        )
                    )
                    if reconnect_ok:
                        s6 = "bridge reconnect attempted after failed upload (status validation skipped)"
                        local_log.append(s6)
                        self._append_log(s6)
                    else:
                        s6e = f"warn: bridge reconnect after failed upload: {reconnect_err or 'unknown'}"
                        local_log.append(s6e)
                        self._append_log(s6e)

                final_pass = rc == 0 and reconnect_ok
                final_state = "passed" if final_pass else "failed"
                final_rc = 0 if final_pass else (rc if rc != 0 else -2)
                finished_at = time.time()
                self._set(
                    _running=False,
                    _state=final_state,
                    _finished_at=finished_at,
                    _returncode=final_rc,
                    _active_operation=None,
                    _last_completed_operation={
                        "op_id": str(op_id or ""),
                        "phase": "upload_guarded",
                        "finished_at": finished_at,
                        "state": final_state,
                        "returncode": final_rc,
                    },
                )
                self._record_run_artifact(
                    phase="upload_guarded",
                    cmd=artifact_cmd,
                    returncode=final_rc,
                    state=final_state,
                    started_at=started_at,
                    finished_at=finished_at,
                    log_lines=local_log,
                    op_id=op_id,
                    idempotency_key=idem_key,
                )

        t = threading.Thread(target=worker, daemon=True)
        t.start()
        return self.status()

    def _resolve_upload_strategy(self, fqbn: str) -> Dict[str, Any]:
        targets = self.list_targets()
        board = self._match_target_for_fqbn(fqbn)
        family_id = str(board.get("family", "")).strip()
        families = list(targets.get("families") or [])
        family_row = next(
            (
                row
                for row in families
                if isinstance(row, dict) and str(row.get("id", "")).strip() == family_id
            ),
            {},
        )
        policy: Dict[str, Any] = {}
        if isinstance(family_row, dict) and isinstance(
            family_row.get("upload_strategy"), dict
        ):
            policy.update(dict(family_row.get("upload_strategy") or {}))
        if isinstance(board.get("upload_strategy"), dict):
            policy.update(dict(board.get("upload_strategy") or {}))
        if "max_attempts" not in policy:
            policy["max_attempts"] = 1
        if "retryable_classes" not in policy:
            policy["retryable_classes"] = []
        if "retry_backoff_s" not in policy:
            policy["retry_backoff_s"] = 0.35
        if "reconnect_attempts_success" not in policy:
            policy["reconnect_attempts_success"] = 6
        if "reconnect_ready_timeout_s" not in policy:
            policy["reconnect_ready_timeout_s"] = 3.0
        return policy

    @staticmethod
    def _classify_upload_failure(lines: list[str], *, returncode: int) -> str:
        if returncode == 0:
            return "none"
        blob = "\n".join([str(x) for x in list(lines or [])]).lower()
        if any(
            tok in blob
            for tok in (
                "device or resource busy",
                "resource busy",
                "permission denied",
                "multiple access on port",
            )
        ):
            return "port_busy"
        if any(
            tok in blob
            for tok in (
                "no such file or directory",
                "can't open device",
                "cannot open",
                "unable to open port",
                "serial port not found",
            )
        ):
            return "port_missing"
        if any(
            tok in blob
            for tok in (
                "programmer is out of sync",
                "protocol expects sync byte",
                "not in sync",
            )
        ):
            return "bootloader_sync"
        if any(
            tok in blob
            for tok in (
                "unknown fqbn",
                "platform not installed",
                "core not installed",
            )
        ):
            return "toolchain_config"
        return "unknown"

    @staticmethod
    def _nano_bootloader_fallback_cmd(cmd: list[str]) -> Optional[list[str]]:
        try:
            idx = cmd.index("--fqbn")
        except ValueError:
            return None
        if idx + 1 >= len(cmd):
            return None
        fqbn = str(cmd[idx + 1]).strip()
        if not fqbn.startswith("arduino:avr:nano"):
            return None
        alt = (
            "arduino:avr:nano"
            if fqbn.endswith(":cpu=atmega328old")
            else "arduino:avr:nano:cpu=atmega328old"
        )
        if alt == fqbn:
            return None
        out = list(cmd)
        out[idx + 1] = alt
        return out

    def _resolve_port_for_retry(self, preferred_port: str) -> str:
        selected = str(preferred_port or "").strip()
        deadline = time.time() + 2.5
        while True:
            try:
                boards = self.list_boards()
            except Exception:
                boards = {"ports": [], "recommended_port": ""}
            ports = []
            for row in list(boards.get("ports") or []):
                if not isinstance(row, dict):
                    continue
                addr = str(row.get("address", "")).strip()
                if addr:
                    ports.append(addr)
            if selected and selected in ports:
                return selected
            recommended = str(boards.get("recommended_port", "")).strip()
            if recommended and recommended in ports:
                return recommended
            if ports:
                return ports[0]
            if time.time() >= deadline:
                break
            time.sleep(0.25)
        return selected

    @staticmethod
    def _cmd_with_port(cmd: list[str], port: str) -> list[str]:
        out = list(cmd)
        try:
            idx = out.index("-p")
            if idx + 1 < len(out):
                out[idx + 1] = str(port)
                return out
        except ValueError:
            pass
        return out

    def install_cli(self) -> Dict[str, Any]:
        script = r"""
set -euo pipefail
if command -v arduino-cli >/dev/null 2>&1; then
  echo "arduino-cli already installed: $(arduino-cli version)"
  exit 0
fi
OS="$(uname -s)"
ARCH="$(uname -m)"
TARGET=""
if [ "$OS" = "Darwin" ] && [ "$ARCH" = "arm64" ]; then
  TARGET="macOS_ARM64"
elif [ "$OS" = "Darwin" ] && [ "$ARCH" = "x86_64" ]; then
  TARGET="macOS_64bit"
elif [ "$OS" = "Linux" ] && [ "$ARCH" = "x86_64" ]; then
  TARGET="Linux_64bit"
elif [ "$OS" = "Linux" ] && [ "$ARCH" = "aarch64" ]; then
  TARGET="Linux_ARM64"
else
  echo "Unsupported platform for auto-install: $OS $ARCH"
  exit 2
fi
VER="$(curl -fsSL https://api.github.com/repos/arduino/arduino-cli/releases/latest | python3 -c 'import sys,json; print(json.load(sys.stdin)["tag_name"].lstrip("v"))')"
URL="https://downloads.arduino.cc/arduino-cli/arduino-cli_${VER}_${TARGET}.tar.gz"
echo "Installing arduino-cli ${VER} for ${TARGET}"
mkdir -p "$HOME/.local/bin"
TMPD="$(mktemp -d)"
trap 'rm -rf "$TMPD"' EXIT
cd "$TMPD"
curl -fL "$URL" -o arduino-cli.tar.gz
tar -xzf arduino-cli.tar.gz
install -m 0755 arduino-cli "$HOME/.local/bin/arduino-cli"
echo "Installed at $HOME/.local/bin/arduino-cli"
"$HOME/.local/bin/arduino-cli" version
"""
        cmd = ["/bin/bash", "-lc", script]
        self.arduino_cli = self._resolve_arduino_cli()
        return self._run_subprocess(cmd, phase="install_cli")

    def _default_sketch_file(self) -> pathlib.Path:
        folder = pathlib.Path(self.default_sketch)
        preferred = folder / f"{folder.name}.ino"
        if preferred.exists() and preferred.is_file():
            try:
                if preferred.stat().st_size > 0:
                    return preferred
            except OSError:
                pass
        non_empty_ino_files = []
        for candidate in sorted(folder.glob("*.ino")):
            if not candidate.is_file():
                continue
            try:
                if candidate.stat().st_size > 0:
                    non_empty_ino_files.append(candidate)
            except OSError:
                continue
        if non_empty_ino_files:
            if preferred.exists() and preferred.is_file():
                logger.warning(
                    f"default sketch preferred file is empty, falling back to non-empty file in {folder}: {preferred}"
                )
            return non_empty_ino_files[0]
        ino_files = sorted(folder.glob("*.ino"))
        if ino_files:
            raise RuntimeError(f"No non-empty .ino file found in {folder}")
        if preferred.exists():
            return preferred
        raise FileNotFoundError(f"No .ino file found in {folder}")

    def read_sketch(self, path: Optional[str] = None) -> Dict[str, Any]:
        target = pathlib.Path(path) if path else self._default_sketch_file()
        if not target.exists() or not target.is_file():
            raise FileNotFoundError(str(target))
        content = target.read_text(encoding="utf-8")
        if not content.strip():
            raise RuntimeError(f"sketch_file_empty:{target}")
        return {"path": str(target), "content": content}

    @staticmethod
    def _write_text_atomic(target: pathlib.Path, content: str) -> int:
        payload = content.encode("utf-8")
        tmp = target.with_name(f".{target.name}.tmp")
        tmp.write_bytes(payload)
        tmp.replace(target)
        written = target.stat().st_size if target.exists() else 0
        if written != len(payload):
            raise RuntimeError("sketch_write_size_mismatch")
        return written

    def _ensure_manifest_after_write(
        self,
        *,
        sketch_folder: str,
        fqbn: str,
        profile: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        try:
            return self.ensure_runtime_manifest(
                sketch=sketch_folder,
                fqbn=fqbn,
                profile=profile if isinstance(profile, dict) else None,
                force_update=False,
            )
        except RuntimeError as exc:
            msg = str(exc)
            if profile is None and msg.startswith("runtime_manifest_invalid:"):
                raise RuntimeError(
                    "profile_required_for_manifest: provide profile.board/profile.hardware/profile.pins when writing sketches to folders without a valid runtime manifest"
                ) from exc
            raise

    def write_sketch(
        self,
        *,
        content: str,
        path: Optional[str] = None,
        profile: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("sketch_content_empty")
        target = pathlib.Path(path) if path else self._default_sketch_file()
        target.parent.mkdir(parents=True, exist_ok=True)
        bytes_written = self._write_text_atomic(target, content)
        manifest = self._ensure_manifest_after_write(
            sketch_folder=str(target.parent),
            fqbn=self.default_fqbn,
            profile=profile,
        )
        return {
            "path": str(target),
            "bytes": bytes_written,
            "runtime_manifest": manifest,
        }

    def write_sketch_with_backup(
        self,
        *,
        content: str,
        path: Optional[str] = None,
        source: str = "assistant",
        profile: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("sketch_content_empty")
        target = pathlib.Path(path) if path else self._default_sketch_file()
        target.parent.mkdir(parents=True, exist_ok=True)
        backup_dir = self.repo_root / "generated_firmware" / "_sketch_backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = int(time.time())
        backup_name = f"{target.name}.{source}.{stamp}.bak"
        backup_path = backup_dir / backup_name
        if target.exists() and target.is_file():
            shutil.copy2(target, backup_path)
        bytes_written = self._write_text_atomic(target, content)
        manifest = self._ensure_manifest_after_write(
            sketch_folder=str(target.parent),
            fqbn=self.default_fqbn,
            profile=profile,
        )
        return {
            "path": str(target),
            "bytes": bytes_written,
            "backup_path": str(backup_path) if backup_path.exists() else None,
            "runtime_manifest": manifest,
        }

    def list_boards(self) -> Dict[str, Any]:
        self.arduino_cli = self._resolve_arduino_cli()
        cmd = [self.arduino_cli, "board", "list", "--format", "json"]
        try:
            raw = subprocess.check_output(
                cmd, text=True, cwd=str(self.repo_root), stderr=subprocess.STDOUT
            ).strip()
            parsed = json.loads(raw) if raw else {}
            detected_ports = (
                parsed.get("detected_ports", []) if isinstance(parsed, dict) else []
            )
            simplified = []
            for p in detected_ports:
                addr = p.get("port", {}).get("address")
                label = p.get("port", {}).get("label")
                protocol = p.get("port", {}).get("protocol")
                props = p.get("port", {}).get("properties", {}) or {}
                boards = p.get("matching_boards", []) or []
                fqbn = boards[0].get("fqbn") if boards else None
                name = boards[0].get("name") if boards else None
                simplified.append(
                    {
                        "address": addr,
                        "label": label,
                        "protocol": protocol,
                        "fqbn": fqbn,
                        "board_name": name,
                        "vid": props.get("vid"),
                        "pid": props.get("pid"),
                        "serial_number": props.get("serialNumber")
                        or props.get("serial_number"),
                    }
                )
            recommended = next((p for p in simplified if p.get("fqbn")), None)
            return {
                "ok": True,
                "ports": simplified,
                "recommended_fqbn": recommended.get("fqbn")
                if recommended
                else self.default_fqbn,
                "recommended_port": recommended.get("address")
                if recommended
                else self.default_port,
                "raw": parsed,
            }
        except Exception as exc:
            return {
                "ok": False,
                "error": str(exc),
                "ports": [],
                "recommended_fqbn": self.default_fqbn,
                "recommended_port": self.default_port,
            }

    def list_targets(self) -> Dict[str, Any]:
        return {
            "ok": True,
            "version": 1,
            "families": [
                {
                    "id": "arduino_avr",
                    "label": "Arduino AVR",
                    "upload_strategy": {
                        "uploader": "arduino_cli_upload",
                        "reset_method": "dtr_autoreset",
                        "max_attempts": 2,
                        "retryable_classes": [
                            "bootloader_sync",
                            "port_busy",
                            "port_missing",
                        ],
                        "retry_backoff_s": 0.35,
                        "reconnect_attempts_success": 6,
                        "reconnect_ready_timeout_s": 3.0,
                    },
                },
                {
                    "id": "esp32",
                    "label": "ESP32",
                    "upload_strategy": {
                        "uploader": "arduino_cli_upload",
                        "reset_method": "manual_boot_en",
                        "max_attempts": 2,
                        "retryable_classes": ["port_busy"],
                        "retry_backoff_s": 0.35,
                        "reconnect_attempts_success": 6,
                        "reconnect_ready_timeout_s": 3.0,
                    },
                },
                {
                    "id": "rp2040",
                    "label": "RP2040",
                    "upload_strategy": {
                        "uploader": "arduino_cli_upload",
                        "reset_method": "manual_bootsel",
                        "max_attempts": 1,
                        "retryable_classes": ["port_busy"],
                        "retry_backoff_s": 0.35,
                        "reconnect_attempts_success": 6,
                        "reconnect_ready_timeout_s": 3.0,
                    },
                },
                {
                    "id": "teensy",
                    "label": "Teensy",
                    "upload_strategy": {
                        "uploader": "arduino_cli_upload",
                        "reset_method": "manual_program_button",
                        "max_attempts": 1,
                        "retryable_classes": ["port_busy"],
                        "retry_backoff_s": 0.35,
                        "reconnect_attempts_success": 6,
                        "reconnect_ready_timeout_s": 3.0,
                    },
                },
            ],
            "boards": [
                {
                    "id": "nano",
                    "family": "arduino_avr",
                    "label": "Arduino Nano",
                    "fqbn_base": "arduino:avr:nano",
                    "default_bootloader": "new",
                    "bootloaders": [
                        {"id": "new", "label": "New", "fqbn_suffix": ""},
                        {
                            "id": "old",
                            "label": "Old (ATmega328P)",
                            "fqbn_suffix": ":cpu=atmega328old",
                        },
                    ],
                    "upload_strategy": {
                        "max_attempts": 2,
                        "retryable_classes": [
                            "bootloader_sync",
                            "port_busy",
                            "port_missing",
                        ],
                    },
                },
                {
                    "id": "uno",
                    "family": "arduino_avr",
                    "label": "Arduino Uno",
                    "fqbn_base": "arduino:avr:uno",
                    "default_bootloader": "default",
                    "bootloaders": [
                        {"id": "default", "label": "Default", "fqbn_suffix": ""}
                    ],
                },
                {
                    "id": "esp32_devkit",
                    "family": "esp32",
                    "label": "ESP32 Dev Module",
                    "fqbn_base": "esp32:esp32:esp32",
                    "default_bootloader": "default",
                    "bootloaders": [
                        {"id": "default", "label": "Default", "fqbn_suffix": ""}
                    ],
                },
                {
                    "id": "rp2040_pico",
                    "family": "rp2040",
                    "label": "Raspberry Pi Pico",
                    "fqbn_base": "rp2040:rp2040:rpipico",
                    "default_bootloader": "default",
                    "bootloaders": [
                        {"id": "default", "label": "Default", "fqbn_suffix": ""}
                    ],
                },
                {
                    "id": "teensy40",
                    "family": "teensy",
                    "label": "Teensy 4.0",
                    "fqbn_base": "teensy:avr:teensy40",
                    "default_bootloader": "default",
                    "bootloaders": [
                        {"id": "default", "label": "Default", "fqbn_suffix": ""}
                    ],
                },
                {
                    "id": "teensy41",
                    "family": "teensy",
                    "label": "Teensy 4.1",
                    "fqbn_base": "teensy:avr:teensy41",
                    "default_bootloader": "default",
                    "bootloaders": [
                        {"id": "default", "label": "Default", "fqbn_suffix": ""}
                    ],
                },
            ],
        }

    def _resolve_sketch_folder(self, sketch: Optional[str] = None) -> pathlib.Path:
        raw = str(sketch or self.default_sketch).strip()
        p = pathlib.Path(raw).expanduser()
        if not p.is_absolute():
            p = (self.repo_root / p).resolve()
        if p.suffix.lower() == ".ino":
            return p.parent
        return p

    def runtime_manifest_path(self, sketch: Optional[str] = None) -> pathlib.Path:
        return self._resolve_sketch_folder(sketch=sketch) / "runtime_manifest_v1.json"

    def read_runtime_manifest(self, sketch: Optional[str] = None) -> Dict[str, Any]:
        path = self.runtime_manifest_path(sketch=sketch)
        if not path.exists() or not path.is_file():
            raise RuntimeError(f"runtime_manifest_missing:{path}")
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise RuntimeError(f"runtime_manifest_invalid_json:{exc}") from exc
        if not isinstance(raw, dict):
            raise RuntimeError("runtime_manifest_not_object")
        return {"path": str(path), "manifest": raw}

    def validate_runtime_manifest(
        self,
        *,
        sketch: Optional[str] = None,
        manifest: Optional[Dict[str, Any]] = None,
        require_exists: bool = True,
    ) -> Dict[str, Any]:
        path = self.runtime_manifest_path(sketch=sketch)
        source = "inline"
        node: Any = manifest
        if node is None:
            source = "file"
            if not path.exists() or not path.is_file():
                return {
                    "ok": False if require_exists else True,
                    "manifest_path": str(path),
                    "source": source,
                    "errors": ["runtime_manifest_missing"] if require_exists else [],
                    "warnings": [],
                    "manifest": None,
                }
            try:
                node = json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:
                return {
                    "ok": False,
                    "manifest_path": str(path),
                    "source": source,
                    "errors": [f"runtime_manifest_invalid_json:{exc}"],
                    "warnings": [],
                    "manifest": None,
                }

        check = _validate_runtime_manifest_v1(node, self.list_targets())
        return {
            "ok": bool(check.get("ok", False)),
            "manifest_path": str(path),
            "source": source,
            "errors": list(check.get("errors") or []),
            "warnings": list(check.get("warnings") or []),
            "manifest": node if isinstance(node, dict) else None,
            "checked_at": time.time(),
        }

    def write_runtime_manifest(
        self,
        *,
        sketch: Optional[str] = None,
        manifest: Dict[str, Any],
        validate: bool = True,
    ) -> Dict[str, Any]:
        if validate:
            check = self.validate_runtime_manifest(
                sketch=sketch, manifest=manifest, require_exists=False
            )
            if not bool(check.get("ok", False)):
                raise RuntimeError(
                    "runtime_manifest_invalid:" + "; ".join(check.get("errors", []))
                )
        path = self.runtime_manifest_path(sketch=sketch)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = dict(manifest)
        payload["updated_at"] = int(time.time())
        payload["version"] = "runtime_manifest_v1"
        text = json.dumps(payload, indent=2, sort_keys=True)
        path.write_text(text + "\n", encoding="utf-8")
        return {"path": str(path), "bytes": len((text + "\n").encode("utf-8"))}

    def _match_target_for_fqbn(self, fqbn: str) -> Dict[str, Any]:
        raw = str(fqbn or "").strip()
        targets = self.list_targets()
        for row in list(targets.get("boards") or []):
            if not isinstance(row, dict):
                continue
            base = str(row.get("fqbn_base", "")).strip()
            if not base:
                continue
            if raw == base or raw.startswith(f"{base}:"):
                out = dict(row)
                out["fqbn"] = raw
                return out
        fallback = next(
            (
                r
                for r in list(targets.get("boards") or [])
                if isinstance(r, dict) and str(r.get("id", "")) == "nano"
            ),
            None,
        )
        if isinstance(fallback, dict):
            out = dict(fallback)
            out["fqbn"] = raw or str(fallback.get("fqbn_base", "arduino:avr:nano"))
            return out
        return {
            "id": "nano",
            "family": "arduino_avr",
            "fqbn_base": "arduino:avr:nano",
            "fqbn": raw or "arduino:avr:nano",
        }

    @staticmethod
    def _int_pin(node: Any, key: str, default: int = -1) -> int:
        if not isinstance(node, dict):
            return int(default)
        try:
            return int(node.get(key, default))
        except Exception:
            return int(default)

    @staticmethod
    def _default_release_meta() -> Dict[str, str]:
        return {
            "runtime_version": "runtime_v1.0.0",
            "tune_version": "tune_v1",
            "version_policy": (
                "Bump runtime_version only for structural/scaffold code changes; "
                "bump tune_version for variable/tuning-only changes."
            ),
        }

    def _load_release_meta(self, *, sketch: Optional[str] = None) -> Dict[str, str]:
        out = dict(self._default_release_meta())
        candidates: list[pathlib.Path] = []
        if isinstance(sketch, str) and sketch.strip():
            candidates.append(
                self._resolve_sketch_folder(sketch=sketch) / "release.json"
            )
        candidates.append(pathlib.Path(self.default_sketch) / "release.json")
        seen: set[str] = set()
        for path in candidates:
            key = str(path.resolve()) if path.exists() else str(path)
            if key in seen:
                continue
            seen.add(key)
            if not path.exists() or not path.is_file():
                continue
            try:
                node = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(node, dict):
                continue
            runtime_version = str(node.get("runtime_version", "")).strip()
            tune_version = str(node.get("tune_version", "")).strip()
            version_policy = str(node.get("version_policy", "")).strip()
            if runtime_version:
                out["runtime_version"] = runtime_version
            if tune_version:
                out["tune_version"] = tune_version
            if version_policy:
                out["version_policy"] = version_policy
            return out
        return out

    def _build_runtime_manifest_from_profile(
        self,
        *,
        fqbn: str,
        profile: Optional[Dict[str, Any]] = None,
        sketch: Optional[str] = None,
    ) -> Dict[str, Any]:
        target = self._match_target_for_fqbn(fqbn)
        pins = profile.get("pins", {}) if isinstance(profile, dict) else {}
        board = profile.get("board", {}) if isinstance(profile, dict) else {}
        hardware = profile.get("hardware", {}) if isinstance(profile, dict) else {}
        profile_probe = profile.get("probe", {}) if isinstance(profile, dict) else {}
        profile_probe_commands = (
            profile_probe.get("commands", []) if isinstance(profile_probe, dict) else []
        )
        release_defaults = self._load_release_meta(sketch=sketch)
        release = profile.get("release", {}) if isinstance(profile, dict) else {}
        runtime_version = str(
            (profile or {}).get("runtime_version")
            or (release.get("runtime_version") if isinstance(release, dict) else "")
            or release_defaults.get("runtime_version", "")
            or "runtime_v1.0.0"
        ).strip()
        tune_version = str(
            (profile or {}).get("tune_version")
            or (release.get("tune_version") if isinstance(release, dict) else "")
            or release_defaults.get("tune_version", "")
            or "tune_v1"
        ).strip()
        version_policy = str(
            (profile or {}).get("version_policy")
            or (release.get("version_policy") if isinstance(release, dict) else "")
            or release_defaults.get("version_policy", "")
            or self._default_release_meta().get("version_policy", "")
        ).strip()
        manifest_commands_base = [
            "GET",
            "ARM",
            "DISARM",
            "PID",
            "SETPOINT",
            "LIMITS",
            "CAL ZERO",
            "SAVECFG",
        ]
        manifest_commands: list[str] = []
        seen_commands: set[str] = set()
        for raw_cmd in [*manifest_commands_base, *list(profile_probe_commands or [])]:
            cmd = str(raw_cmd or "").strip().upper()
            if not cmd or cmd in seen_commands:
                continue
            seen_commands.add(cmd)
            manifest_commands.append(cmd)
        imu_protocol = str(hardware.get("imu_protocol", "i2c") or "i2c").strip().lower()
        encoder_protocol = (
            str(hardware.get("encoder_protocol", "quadrature") or "quadrature")
            .strip()
            .lower()
        )
        actuator_type = str(
            (profile or {})
            .get("hardware", {})
            .get("motor_driver", "dual_dc_hbridge_dir_pwm")
        )
        actuator_protocol = (
            str(
                hardware.get(
                    "actuator_protocol",
                    "gpio_dir_pwm"
                    if "dir_pwm" in actuator_type.lower()
                    else "gpio_pwm",
                )
                or "gpio_pwm"
            )
            .strip()
            .lower()
        )
        family = str(target.get("family", "arduino_avr")).strip() or "arduino_avr"
        family_caps = _family_capabilities().get(family, {})
        profile_firmware = (
            profile.get("firmware", {}) if isinstance(profile, dict) else {}
        )
        telemetry_mode = (
            str(
                (
                    profile_firmware.get("telemetry_mode")
                    if isinstance(profile_firmware, dict)
                    else ""
                )
                or (
                    profile_probe.get("telemetry_mode")
                    if isinstance(profile_probe, dict)
                    else ""
                )
                or family_caps.get("default_telemetry_mode", "ascii_lowrate")
            )
            .strip()
            .lower()
        )
        if telemetry_mode not in {"ascii_lowrate", "binary_highrate"}:
            telemetry_mode = (
                str(family_caps.get("default_telemetry_mode", "ascii_lowrate"))
                .strip()
                .lower()
                or "ascii_lowrate"
            )
        telemetry_status_hz = 10 if telemetry_mode == "ascii_lowrate" else 50
        manifest = {
            "version": "runtime_manifest_v1",
            "board": {
                "id": str(target.get("id", "nano")),
                "family": str(target.get("family", "arduino_avr")),
                "fqbn": str(board.get("fqbn", "")).strip()
                or str(target.get("fqbn", fqbn)),
                "bootloader": str(board.get("bootloader", "")).strip() or "default",
            },
            "interfaces": {
                "imu": {
                    "type": str(
                        (profile or {})
                        .get("hardware", {})
                        .get("imu_type", "imu_generic")
                    ),
                    "protocol": imu_protocol,
                    "pins": {
                        "sda": self._int_pin(pins, "imu_sda", -1),
                        "scl": self._int_pin(pins, "imu_scl", -1),
                        "miso": self._int_pin(pins, "imu_miso", -1),
                        "mosi": self._int_pin(pins, "imu_mosi", -1),
                        "sck": self._int_pin(pins, "imu_sck", -1),
                        "cs": self._int_pin(pins, "imu_cs", -1),
                        "rx": self._int_pin(pins, "imu_rx", -1),
                        "tx": self._int_pin(pins, "imu_tx", -1),
                    },
                },
                "encoders": {
                    "type": "quadrature",
                    "protocol": encoder_protocol,
                    "pins": {
                        "left_a": self._int_pin(pins, "enc_l_a", -1),
                        "left_b": self._int_pin(pins, "enc_l_b", -1),
                        "right_a": self._int_pin(pins, "enc_r_a", -1),
                        "right_b": self._int_pin(pins, "enc_r_b", -1),
                        "pulse": self._int_pin(pins, "enc_pulse", -1),
                        "miso": self._int_pin(pins, "enc_miso", -1),
                        "mosi": self._int_pin(pins, "enc_mosi", -1),
                        "sck": self._int_pin(pins, "enc_sck", -1),
                        "cs": self._int_pin(pins, "enc_cs", -1),
                    },
                },
                "actuator": {
                    "type": actuator_type,
                    "protocol": actuator_protocol,
                    "pins": {
                        "left_pwm": self._int_pin(pins, "motor_l_pwm", -1),
                        "left_dir": self._int_pin(pins, "motor_l_dir", -1),
                        "right_pwm": self._int_pin(pins, "motor_r_pwm", -1),
                        "right_dir": self._int_pin(pins, "motor_r_dir", -1),
                        "can_tx": self._int_pin(pins, "motor_can_tx", -1),
                        "can_rx": self._int_pin(pins, "motor_can_rx", -1),
                    },
                },
            },
            "telemetry_fields": [
                "mode",
                "ident",
                "hash",
                "runtime",
                "tune",
                "ang",
                "raw",
                "gyro",
                "out",
                "fault",
                "estop",
                "kp",
                "ki",
                "kd",
                "set",
                "encL",
                "encR",
            ],
            "commands": [
                *manifest_commands,
            ],
            "telemetry": {
                "mode": telemetry_mode,
                "transport": "serial_ascii"
                if telemetry_mode == "ascii_lowrate"
                else "binary_framed",
                "status_hz": telemetry_status_hz,
            },
            "release": {
                "runtime_version": runtime_version,
                "tune_version": tune_version,
                "version_policy": version_policy,
            },
            "generated_by": "firmware_manager",
            "generated_at": int(time.time()),
        }
        topology = (
            profile.get("mcu_topology")
            if isinstance(profile, dict)
            and isinstance(profile.get("mcu_topology"), dict)
            else None
        )
        if isinstance(topology, dict) and topology:
            manifest["mcu_topology"] = dict(topology)
        return manifest

    def ensure_runtime_manifest(
        self,
        *,
        sketch: Optional[str] = None,
        fqbn: Optional[str] = None,
        profile: Optional[Dict[str, Any]] = None,
        force_update: bool = False,
    ) -> Dict[str, Any]:
        effective_fqbn = str(fqbn or self.default_fqbn).strip() or self.default_fqbn
        current = self.validate_runtime_manifest(
            sketch=sketch, require_exists=not force_update
        )
        if (not force_update) and bool(current.get("ok", False)):
            return {
                "ok": True,
                "action": "kept",
                "manifest_path": str(current.get("manifest_path", "")),
                "validation": current,
            }
        manifest = self._build_runtime_manifest_from_profile(
            fqbn=effective_fqbn, profile=profile, sketch=sketch
        )
        written = self.write_runtime_manifest(
            sketch=sketch, manifest=manifest, validate=True
        )
        post = self.validate_runtime_manifest(sketch=sketch, require_exists=True)
        return {
            "ok": bool(post.get("ok", False)),
            "action": "updated" if force_update else "created",
            "manifest_path": str(written.get("path", "")),
            "validation": post,
        }

    def list_sketch_folders(self) -> Dict[str, Any]:
        roots = [
            self.repo_root / "generated_firmware",
            self.repo_root / "app" / "bridge" / "firmware_templates",
            pathlib.Path(self.default_sketch),
        ]
        skip_dirs = {
            ".git",
            ".venv",
            "node_modules",
            "__pycache__",
            ".pytest_cache",
            "dist",
            "build",
            "output",
        }
        found: set[str] = set()
        for root in roots:
            if root.is_file():
                root = root.parent
            if not root.exists() or not root.is_dir():
                continue
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [d for d in dirnames if d not in skip_dirs]
                has_nonempty_ino = False
                for name in filenames:
                    if not name.endswith(".ino"):
                        continue
                    candidate = pathlib.Path(dirpath) / name
                    try:
                        if candidate.is_file() and candidate.stat().st_size > 0:
                            has_nonempty_ino = True
                            break
                    except OSError:
                        continue
                if has_nonempty_ino:
                    found.add(str(pathlib.Path(dirpath)))
        found.add(str(self.default_sketch))
        folders = sorted(found)
        return {
            "ok": True,
            "folders": folders,
            "default_folder": str(self.default_sketch),
        }

    def pick_sketch_folder(self) -> Dict[str, Any]:
        chosen = ""
        if sys.platform == "darwin":
            scripts = [
                [
                    'tell application "Finder" to activate',
                    'POSIX path of (choose folder with prompt "Select Sketch Folder")',
                ],
                ['POSIX path of (choose folder with prompt "Select Sketch Folder")'],
            ]
            out = ""
            last_error = ""
            for steps in scripts:
                try:
                    cmd = ["osascript"]
                    for step in steps:
                        cmd.extend(["-e", step])
                    out = subprocess.check_output(
                        cmd, text=True, stderr=subprocess.STDOUT
                    ).strip()
                    if out:
                        break
                except subprocess.CalledProcessError as exc:
                    detail = (exc.output or str(exc)).strip()
                    last_error = detail or str(exc)
                    if "User canceled" in last_error:
                        raise RuntimeError("folder_pick_cancelled") from exc
            if not out:
                raise RuntimeError(f"folder_picker_failed:{last_error or 'unknown'}")
            chosen = out
        elif sys.platform.startswith("linux"):
            zenity = shutil.which("zenity")
            if not zenity:
                raise RuntimeError("folder_picker_unavailable:zenity_not_found")
            out = subprocess.check_output(
                [
                    zenity,
                    "--file-selection",
                    "--directory",
                    "--title=Select Sketch Folder",
                ],
                text=True,
                stderr=subprocess.STDOUT,
            ).strip()
            chosen = out
        else:
            raise RuntimeError("folder_picker_unavailable:unsupported_platform")

        path = pathlib.Path(chosen).expanduser().resolve()
        if not path.exists() or not path.is_dir():
            raise RuntimeError(f"invalid_sketch_folder:{path}")
        has_ino = False
        for p in path.iterdir():
            if not p.is_file() or p.suffix.lower() != ".ino":
                continue
            try:
                if p.stat().st_size > 0:
                    has_ino = True
                    break
            except OSError:
                continue
        return {"ok": True, "path": str(path), "has_ino": has_ino}

    def unified_schema(self) -> Dict[str, Any]:
        return {
            "version": "unified.v1",
            "required": {
                "profile": ["label", "board", "hardware", "pins"],
                "board": ["fqbn"],
                "hardware": ["imu_type", "motor_driver"],
                "pins": [
                    "motor_l_pwm",
                    "motor_l_dir",
                    "motor_r_pwm",
                    "motor_r_dir",
                    "imu_sda",
                    "imu_scl",
                    "gate_enable",
                    "led",
                ],
            },
            "optional_hardware": [
                "imu_protocol",
                "encoder_protocol",
                "actuator_protocol",
            ],
            "optional_pins": [
                "enc_l_a",
                "enc_l_b",
                "enc_r_a",
                "enc_r_b",
                "imu_miso",
                "imu_mosi",
                "imu_sck",
                "imu_cs",
                "imu_rx",
                "imu_tx",
                "enc_pulse",
                "enc_miso",
                "enc_mosi",
                "enc_sck",
                "enc_cs",
                "motor_can_tx",
                "motor_can_rx",
            ],
            "notes": [
                "Pin values must be integers. Use -1 for optional pins that are not present.",
                "Board detection can infer FQBN/port, but wiring pins must come from user profile.",
            ],
        }

    @staticmethod
    def _safe_name(raw: str, fallback: str) -> str:
        candidate = re.sub(r"[^a-zA-Z0-9_]+", "_", raw.strip()).strip("_")
        return candidate[:64] if candidate else fallback

    def _validate_unified_profile(
        self, profile: Dict[str, Any]
    ) -> tuple[Dict[str, Any], list[str]]:
        errors: list[str] = []
        if not isinstance(profile, dict):
            return {}, ["profile must be an object"]

        label = str(profile.get("label", "")).strip()
        board = profile.get("board")
        hardware = profile.get("hardware")
        pins = profile.get("pins")
        if not label:
            errors.append("profile.label is required")
        if not isinstance(board, dict):
            errors.append("profile.board must be an object")
            board = {}
        if not isinstance(hardware, dict):
            errors.append("profile.hardware must be an object")
            hardware = {}
        if not isinstance(pins, dict):
            errors.append("profile.pins must be an object")
            pins = {}

        fqbn = str(board.get("fqbn", "")).strip()
        if not fqbn:
            errors.append("profile.board.fqbn is required")
        imu_type = str(hardware.get("imu_type", "")).strip()
        if not imu_type:
            errors.append("profile.hardware.imu_type is required")
        motor_driver = str(hardware.get("motor_driver", "")).strip()
        if not motor_driver:
            errors.append("profile.hardware.motor_driver is required")
        imu_protocol = str(hardware.get("imu_protocol", "i2c") or "i2c").strip().lower()
        encoder_protocol = (
            str(hardware.get("encoder_protocol", "quadrature") or "quadrature")
            .strip()
            .lower()
        )
        actuator_protocol = (
            str(
                hardware.get(
                    "actuator_protocol",
                    "gpio_dir_pwm" if "dir_pwm" in motor_driver.lower() else "gpio_pwm",
                )
                or "gpio_pwm"
            )
            .strip()
            .lower()
        )

        required_pin_keys = [
            "motor_l_pwm",
            "motor_l_dir",
            "motor_r_pwm",
            "motor_r_dir",
            "imu_sda",
            "imu_scl",
            "gate_enable",
            "led",
        ]
        optional_pin_keys = [
            "enc_l_a",
            "enc_l_b",
            "enc_r_a",
            "enc_r_b",
            "imu_miso",
            "imu_mosi",
            "imu_sck",
            "imu_cs",
            "imu_rx",
            "imu_tx",
            "enc_pulse",
            "enc_miso",
            "enc_mosi",
            "enc_sck",
            "enc_cs",
            "motor_can_tx",
            "motor_can_rx",
        ]
        parsed_pins: Dict[str, int] = {}
        for key in required_pin_keys + optional_pin_keys:
            raw = pins.get(key, -1 if key in optional_pin_keys else None)
            if raw is None:
                errors.append(f"profile.pins.{key} is required")
                continue
            try:
                parsed_pins[key] = int(raw)
            except Exception:
                errors.append(f"profile.pins.{key} must be an integer")

        normalized = {
            "label": label,
            "board": {
                "fqbn": fqbn,
                "port": str(board.get("port", "")).strip(),
                "mcu_family": str(board.get("mcu_family", "unknown")).strip()
                or "unknown",
            },
            "hardware": {
                "imu_type": imu_type,
                "motor_driver": motor_driver,
                "imu_protocol": imu_protocol,
                "encoder_protocol": encoder_protocol,
                "actuator_protocol": actuator_protocol,
            },
            "pins": parsed_pins,
            "generated_at": int(time.time()),
            "schema_version": "unified.v1",
        }
        return normalized, errors

    def generate_unified(
        self, *, profile: Dict[str, Any], sketch_name: Optional[str] = None
    ) -> Dict[str, Any]:
        norm, errors = self._validate_unified_profile(profile)
        if errors:
            raise RuntimeError("invalid_unified_profile: " + "; ".join(errors))
        if not self._unified_templates_dir.exists():
            raise RuntimeError(f"template_dir_missing: {self._unified_templates_dir}")

        ts = int(time.time())
        base_name = self._safe_name(
            sketch_name or norm["label"], f"upright_unified_{ts}"
        )
        out_dir = self._generated_root / base_name
        suffix = 1
        while out_dir.exists():
            suffix += 1
            out_dir = self._generated_root / f"{base_name}_{suffix}"
        out_dir.mkdir(parents=True, exist_ok=False)

        tokens = {
            "__SKETCH_NAME__": out_dir.name,
            "__PROFILE_LABEL__": norm["label"],
            "__FQBN__": norm["board"]["fqbn"],
            "__IMU_TYPE__": norm["hardware"]["imu_type"],
            "__MOTOR_DRIVER__": norm["hardware"]["motor_driver"],
            "__PIN_MOTOR_L_PWM__": str(norm["pins"].get("motor_l_pwm", -1)),
            "__PIN_MOTOR_L_DIR__": str(norm["pins"].get("motor_l_dir", -1)),
            "__PIN_MOTOR_R_PWM__": str(norm["pins"].get("motor_r_pwm", -1)),
            "__PIN_MOTOR_R_DIR__": str(norm["pins"].get("motor_r_dir", -1)),
            "__PIN_IMU_SDA__": str(norm["pins"].get("imu_sda", -1)),
            "__PIN_IMU_SCL__": str(norm["pins"].get("imu_scl", -1)),
            "__PIN_GATE_ENABLE__": str(norm["pins"].get("gate_enable", -1)),
            "__PIN_LED__": str(norm["pins"].get("led", -1)),
            "__PIN_ENC_L_A__": str(norm["pins"].get("enc_l_a", -1)),
            "__PIN_ENC_L_B__": str(norm["pins"].get("enc_l_b", -1)),
            "__PIN_ENC_R_A__": str(norm["pins"].get("enc_r_a", -1)),
            "__PIN_ENC_R_B__": str(norm["pins"].get("enc_r_b", -1)),
        }

        rendered_files: list[str] = []
        main_file: Optional[pathlib.Path] = None
        try:
            for tmpl in sorted(self._unified_templates_dir.glob("*.tmpl")):
                text = tmpl.read_text(encoding="utf-8")
                for key, value in tokens.items():
                    text = text.replace(key, value)
                out_name = tmpl.name[:-5]
                if out_name == "main.ino":
                    out_name = f"{out_dir.name}.ino"
                target = out_dir / out_name
                target.write_text(text, encoding="utf-8")
                rendered_files.append(str(target))
                if target.suffix.lower() == ".ino":
                    main_file = target

            if main_file is None or not main_file.exists() or not main_file.is_file():
                raise RuntimeError("generated_main_file_missing")
            if main_file.stat().st_size <= 0:
                raise RuntimeError(f"generated_main_file_empty:{main_file}")

            profile_path = out_dir / "profile.json"
            profile_path.write_text(
                json.dumps(norm, indent=2, sort_keys=True), encoding="utf-8"
            )
            rendered_files.append(str(profile_path))
            manifest_status = self.ensure_runtime_manifest(
                sketch=str(out_dir),
                fqbn=str(norm.get("board", {}).get("fqbn", self.default_fqbn)),
                profile=norm,
                force_update=True,
            )
            manifest_path = str(
                manifest_status.get(
                    "manifest_path", self.runtime_manifest_path(sketch=str(out_dir))
                )
            )
            if manifest_path:
                rendered_files.append(manifest_path)
        except Exception:
            shutil.rmtree(out_dir, ignore_errors=True)
            raise
        archive = shutil.make_archive(
            str(out_dir), "zip", root_dir=str(out_dir.parent), base_dir=out_dir.name
        )
        return {
            "schema_version": "unified.v1",
            "sketch_folder": str(out_dir),
            "main_file": str(main_file or (out_dir / f"{out_dir.name}.ino")),
            "archive": archive,
            "files": rendered_files,
            "profile": norm,
            "runtime_manifest": manifest_status,
        }

    def generate_docs_pack(
        self,
        *,
        profile: Dict[str, Any],
        sketch_name: Optional[str] = None,
        sketch_content: Optional[str] = None,
        sketch_path: Optional[str] = None,
        force_regenerate: bool = False,
    ) -> Dict[str, Any]:
        norm, errors = self._validate_unified_profile(profile)
        if errors:
            raise RuntimeError("invalid_unified_profile: " + "; ".join(errors))

        ts = int(time.time())
        generation_id = f"docs_{int(time.time() * 1000)}_{secrets.token_hex(4)}"
        base_name = self._safe_name(sketch_name or norm["label"], f"upright_docs_{ts}")
        out_dir = self._generated_root / f"{base_name}_docs"
        suffix = 1
        while out_dir.exists():
            suffix += 1
            out_dir = self._generated_root / f"{base_name}_docs_{suffix}"
        out_dir.mkdir(parents=True, exist_ok=False)

        sketch_src = str(sketch_content or "").strip()
        sketch_source_label = "profile_only"
        if not sketch_src and isinstance(sketch_path, str) and sketch_path.strip():
            try:
                sketch_src = pathlib.Path(sketch_path.strip()).read_text(
                    encoding="utf-8"
                )
                sketch_source_label = "profile_plus_sketch_path"
            except Exception:
                sketch_src = ""
        elif sketch_src:
            sketch_source_label = "profile_plus_sketch_inline"

        cmd_keywords = [
            "GET",
            "PID",
            "MOTION",
            "SETPOINT",
            "LIMITS",
            "CAL",
            "SAVECFG",
            "ARM",
            "DISARM",
            "ESTOP",
        ]
        detected_commands: list[str] = []
        detected_states: list[str] = []
        detected_pin_defs: list[str] = []
        has_setup = False
        has_loop = False
        if sketch_src:
            up = sketch_src.upper()
            has_setup = "VOID SETUP(" in up
            has_loop = "VOID LOOP(" in up
            for cmd in cmd_keywords:
                if re.search(rf"\\b{re.escape(cmd)}\\b", up):
                    detected_commands.append(cmd)
            for state in ["SAFE_IDLE", "IDLE", "ARMED", "BALANCING", "ESTOP", "FAULT"]:
                if re.search(rf"\\b{re.escape(state)}\\b", up):
                    detected_states.append(state)
            pin_rx_a = re.findall(
                r"#define\\s+([A-Za-z_][A-Za-z0-9_]*)\\s+(-?\\d+)", sketch_src
            )
            pin_rx_b = re.findall(
                r"const\\s+(?:uint8_t|int|byte|int16_t|int32_t)\\s+([A-Za-z_][A-Za-z0-9_]*)\\s*=\\s*(-?\\d+)",
                sketch_src,
            )
            for name, val in pin_rx_a + pin_rx_b:
                uname = name.upper()
                if (
                    "PIN" in uname
                    or uname.startswith("MOTOR_")
                    or uname.startswith("IMU_")
                    or uname.startswith("ENC_")
                ):
                    detected_pin_defs.append(f"{name}={val}")

        pins = norm.get("pins", {})
        pin_rows = [
            (
                "motor_l_pwm",
                "MOTOR_L_PWM",
                "OUT",
                "Motor Driver",
                "Left motor PWM output",
            ),
            (
                "motor_l_dir",
                "MOTOR_L_DIR",
                "OUT",
                "Motor Driver",
                "Left motor direction",
            ),
            (
                "motor_r_pwm",
                "MOTOR_R_PWM",
                "OUT",
                "Motor Driver",
                "Right motor PWM output",
            ),
            (
                "motor_r_dir",
                "MOTOR_R_DIR",
                "OUT",
                "Motor Driver",
                "Right motor direction",
            ),
            ("imu_sda", "IMU_SDA", "I/O", "IMU", "I2C data"),
            ("imu_scl", "IMU_SCL", "OUT", "IMU", "I2C clock"),
            (
                "gate_enable",
                "GATE_ENABLE",
                "OUT",
                "Safety Gate",
                "Motor driver gate/enable",
            ),
            ("led", "LED", "OUT", "Status", "Status indicator LED"),
            ("enc_l_a", "ENC_L_A", "IN", "Encoder", "Left encoder A (-1 if unused)"),
            ("enc_l_b", "ENC_L_B", "IN", "Encoder", "Left encoder B (-1 if unused)"),
            ("enc_r_a", "ENC_R_A", "IN", "Encoder", "Right encoder A (-1 if unused)"),
            ("enc_r_b", "ENC_R_B", "IN", "Encoder", "Right encoder B (-1 if unused)"),
        ]

        pin_table_lines = [
            "# Pin Assignment Table",
            "",
            "| Pin | Signal | Direction | Component | Notes |",
            "| --- | --- | --- | --- | --- |",
        ]
        for key, signal, direction, component, notes in pin_rows:
            pin_val = pins.get(key, -1)
            pin_table_lines.append(
                f"| {pin_val} | {signal} | {direction} | {component} | {notes} |"
            )
        pin_table_lines.append("")

        command_map_lines = [
            "# Command/API Map",
            "",
            "| Command | Changes | Notes |",
            "| --- | --- | --- |",
            "| `GET` | Reads status snapshot | No state mutation |",
            "| `PID <kp> <ki> <kd>` | PID gains (`kp`,`ki`,`kd`) | Inner loop tuning |",
            "| `MOTION <kv> <kx>` | Motion gains (`kv`,`kx`) | Outer behavior tuning |",
            "| `SETPOINT <deg>` | Balance target angle (`set`) | Degrees |",
            "| `LIMITS <out_max> <tip_deg> <i_max>` | Safety/output constraints | Device-side clamp |",
            "| `CAL ZERO` | Calibration zero offset | Use while stationary upright |",
            "| `SAVECFG` | Persists config | Writes active config to storage |",
            "| `ARM` | Transition toward armed path | Guarded by safety checks |",
            "| `DISARM` | Transition to safe/idle path | Stops balancing loop |",
            "| `ESTOP LATCH` / `ESTOP RESET` | Emergency stop state | Latch blocks motion commands |",
            "",
            f"Source mode: `{sketch_source_label}`.",
            "",
        ]

        if detected_commands:
            command_map_lines.extend(
                [
                    "Detected in sketch:",
                    "",
                    "| Command Token | Evidence |",
                    "| --- | --- |",
                ]
            )
            for token in sorted(set(detected_commands)):
                command_map_lines.append(f"| `{token}` | present in sketch source |")
            command_map_lines.append("")

        command_map_lines.extend(
            [
                "Contract note: STATUS telemetry should include `ang`, `raw`, and `gyro|gyr|gx` for Kalman/compatibility compliance.",
                "",
            ]
        )

        control_flow = """flowchart TB
  S0["Setup"] --> S1["Init serial and sensors"]
  S1 --> S2["Load config"]
  S2 --> S3["Enter SAFE_IDLE"]
  S3 --> L0["Loop tick"]

  L0 --> L1["Read IMU"]
  L1 --> L2["Fuse tilt to ang raw gyro"]
  L2 --> L3["Publish STATUS telemetry"]
  L3 --> L4["Parse serial commands"]
  L4 --> L5["Evaluate mode and guards"]

  L5 --> M0["SAFE_IDLE path motors off"]
  L5 --> M1["BALANCING path compute and drive"]
  L5 --> M2["Fault path latch stop"]

  M0 --> L0
  M1 --> L0
  M2 --> L0
"""
        if sketch_src:
            control_flow += f"\n%% sketch-evidence: setup_found={str(has_setup).lower()} loop_found={str(has_loop).lower()}\n"

        state_machine = """stateDiagram-v2
  [*] --> SAFE_IDLE
  SAFE_IDLE --> ARMED: ARM with prechecks
  ARMED --> BALANCING: balance enabled
  BALANCING --> SAFE_IDLE: DISARM
  ARMED --> SAFE_IDLE: DISARM
  SAFE_IDLE --> ESTOP: ESTOP_LATCH
  ARMED --> ESTOP: ESTOP_LATCH
  BALANCING --> ESTOP: ESTOP_LATCH or fault
  ESTOP --> SAFE_IDLE: ESTOP_RESET with checks
"""
        if detected_states:
            state_machine += (
                "\n%% detected-states: "
                + ", ".join(sorted(set(detected_states)))
                + "\n"
            )

        hardware_block = f"""graph TB
  MCU["MCU\\n{norm['board'].get('fqbn', 'unknown')}"]
  IMU["IMU\\n{norm['hardware'].get('imu_type', 'unknown')}"]
  MD["Motor Driver\\n{norm['hardware'].get('motor_driver', 'unknown')}"]
  ENC["Wheel Encoders"]
  USB["USB Serial"]
  GATE["Safety Gate"]
  MOT["Drive Motors"]

  MCU --> IMU
  MCU --> MD
  MCU --> ENC
  MCU --> USB
  MCU --> GATE
  MD --> MOT
"""

        pin_mapping = f"""graph TB
  MCU["MCU pin map"]

  subgraph MTR["Motor group"]
    PM["L_PWM={pins.get('motor_l_pwm', -1)}\\nL_DIR={pins.get('motor_l_dir', -1)}\\nR_PWM={pins.get('motor_r_pwm', -1)}\\nR_DIR={pins.get('motor_r_dir', -1)}"]
    MD["Motor driver pins"]
    PM --> MD
  end

  subgraph IMUG["IMU group"]
    PI["SDA={pins.get('imu_sda', -1)}\\nSCL={pins.get('imu_scl', -1)}"]
    ISIG["IMU bus pins"]
    PI --> ISIG
  end

  subgraph AUX["Aux group"]
    PG["GATE={pins.get('gate_enable', -1)}\\nLED={pins.get('led', -1)}"]
    PE["L_A={pins.get('enc_l_a', -1)}\\nL_B={pins.get('enc_l_b', -1)}\\nR_A={pins.get('enc_r_a', -1)}\\nR_B={pins.get('enc_r_b', -1)}"]
  end

  MCU --> PM
  MCU --> PI
  MCU --> PG
  MCU --> PE
"""

        files_map = {
            "control_flow.mmd": control_flow,
            "state_machine.mmd": state_machine,
            "hardware_block.mmd": hardware_block,
            "pin_mapping.mmd": pin_mapping,
            "pin_assignment.md": "\n".join(pin_table_lines),
            "command_api_map.md": "\n".join(command_map_lines),
            "source_report.md": "\n".join(
                [
                    "# Source Report",
                    "",
                    f"- generation_id: `{generation_id}`",
                    f"- force_regenerate: `{str(force_regenerate).lower()}`",
                    f"- mode: `{sketch_source_label}`",
                    f"- sketch_path: `{sketch_path or ''}`",
                    f"- setup_found: `{str(has_setup).lower()}`",
                    f"- loop_found: `{str(has_loop).lower()}`",
                    f"- detected_states: `{', '.join(sorted(set(detected_states))) if detected_states else 'none'}`",
                    f"- detected_commands: `{', '.join(sorted(set(detected_commands))) if detected_commands else 'none'}`",
                    f"- detected_pin_defs: `{', '.join(sorted(set(detected_pin_defs))[:20]) if detected_pin_defs else 'none'}`",
                    "",
                ]
            ),
        }

        rendered_files: list[str] = []
        for name, content in files_map.items():
            target = out_dir / name
            target.write_text(content, encoding="utf-8")
            rendered_files.append(str(target))

        profile_path = out_dir / "profile.json"
        profile_path.write_text(
            json.dumps(norm, indent=2, sort_keys=True), encoding="utf-8"
        )
        rendered_files.append(str(profile_path))
        archive = shutil.make_archive(
            str(out_dir), "zip", root_dir=str(out_dir.parent), base_dir=out_dir.name
        )

        return {
            "schema_version": "firmware_docs.v1",
            "generation_id": generation_id,
            "generated_at": int(time.time()),
            "docs_folder": str(out_dir),
            "archive": archive,
            "files": rendered_files,
            "artifacts": files_map,
            "profile": norm,
        }


