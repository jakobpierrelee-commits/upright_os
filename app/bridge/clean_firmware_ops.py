from __future__ import annotations

import os
import time
from typing import Any, Callable, Dict, Optional, Tuple


ToolCallBuilder = Callable[..., Dict[str, Any]]
PrecheckBuilder = Callable[..., Dict[str, Any]]
StatusNormalizer = Callable[[Dict[str, Any]], Dict[str, Any]]
ActionGatesResolver = Callable[..., Dict[str, Any]]


def handle_clean_firmware_compile(
    *,
    firmware: Any,
    sketch: str,
    fqbn: str,
    idempotency_key: Optional[str],
    tool_call_builder: ToolCallBuilder,
) -> Tuple[int, Dict[str, Any]]:
    t0 = int(time.time() * 1000)
    try:
        st = firmware.compile(
            sketch=sketch,
            fqbn=fqbn,
            idempotency_key=idempotency_key,
        )
        return (
            200,
            {
                "ok": True,
                "firmware": st,
                "tool_call": tool_call_builder(
                    name="firmware_compile",
                    arguments={
                        "sketch": sketch,
                        "fqbn": fqbn,
                        "idempotency_key": idempotency_key,
                    },
                    ok=True,
                    data={
                        "state": str(st.get("state", "")),
                        "phase": str(st.get("phase", "")),
                        "returncode": st.get("returncode"),
                        "idempotent_reused": bool(st.get("idempotent_reused", False)),
                    },
                    started_ms=t0,
                ),
            },
        )
    except Exception as exc:
        err = str(exc)
        if err == "operation_in_progress":
            return (
                409,
                {
                    "ok": False,
                    "error": "operation_in_progress",
                    "firmware": firmware.status(),
                    "tool_call": tool_call_builder(
                        name="firmware_compile",
                        arguments={
                            "sketch": sketch,
                            "fqbn": fqbn,
                            "idempotency_key": idempotency_key,
                        },
                        ok=False,
                        error="operation_in_progress",
                        started_ms=t0,
                    ),
                },
            )
        return (
            500,
            {
                "ok": False,
                "error": err,
                "tool_call": tool_call_builder(
                    name="firmware_compile",
                    arguments={
                        "sketch": sketch,
                        "fqbn": fqbn,
                        "idempotency_key": idempotency_key,
                    },
                    ok=False,
                    error=err,
                    started_ms=t0,
                ),
            },
        )


def handle_clean_firmware_upload(
    *,
    firmware: Any,
    gateway: Any,
    prearm_safety: Any,
    sketch: str,
    fqbn: str,
    port: Optional[str],
    idempotency_key: Optional[str],
    tool_call_builder: ToolCallBuilder,
) -> Tuple[int, Dict[str, Any]]:
    t0 = int(time.time() * 1000)
    try:
        st = firmware.upload_guarded(
            gateway=gateway,
            sketch=sketch,
            fqbn=fqbn,
            port=port,
            idempotency_key=idempotency_key,
        )
        prearm_safety.require("firmware_upload_guarded")
        return (
            200,
            {
                "ok": True,
                "firmware": st,
                "tool_call": tool_call_builder(
                    name="firmware_upload_guarded",
                    arguments={
                        "sketch": sketch,
                        "fqbn": fqbn,
                        "port": port,
                        "idempotency_key": idempotency_key,
                    },
                    ok=True,
                    data={
                        "state": str(st.get("state", "")),
                        "phase": str(st.get("phase", "")),
                        "returncode": st.get("returncode"),
                        "idempotent_reused": bool(st.get("idempotent_reused", False)),
                    },
                    started_ms=t0,
                ),
            },
        )
    except Exception as exc:
        err = str(exc)
        if err == "operation_in_progress":
            return (
                409,
                {
                    "ok": False,
                    "error": "operation_in_progress",
                    "firmware": firmware.status(),
                    "tool_call": tool_call_builder(
                        name="firmware_upload_guarded",
                        arguments={
                            "sketch": sketch,
                            "fqbn": fqbn,
                            "port": port,
                            "idempotency_key": idempotency_key,
                        },
                        ok=False,
                        error="operation_in_progress",
                        started_ms=t0,
                    ),
                },
            )
        return (
            500,
            {
                "ok": False,
                "error": err,
                "tool_call": tool_call_builder(
                    name="firmware_upload_guarded",
                    arguments={
                        "sketch": sketch,
                        "fqbn": fqbn,
                        "port": port,
                        "idempotency_key": idempotency_key,
                    },
                    ok=False,
                    error=err,
                    started_ms=t0,
                ),
            },
        )


def handle_clean_upload_precheck(
    *,
    precheck_builder: PrecheckBuilder,
    requested_port: str,
    requested_fqbn: str,
    requested_sketch: str,
) -> Tuple[int, Dict[str, Any]]:
    payload = precheck_builder(
        requested_port=requested_port,
        requested_fqbn=requested_fqbn,
        requested_sketch=requested_sketch,
    )
    return 200, payload


def handle_clean_known_good_recovery(
    *,
    gateway: Any,
    firmware: Any,
    control: Any,
    prearm_safety: Any,
    requested_port: str,
    requested_fqbn: str,
    requested_sketch: str,
    precheck_builder: PrecheckBuilder,
    normalize_status: StatusNormalizer,
    resolve_action_gates: ActionGatesResolver,
    tool_call_builder: ToolCallBuilder,
) -> Tuple[int, Dict[str, Any]]:
    t0 = int(time.time() * 1000)
    steps: list[Dict[str, Any]] = []

    try:
        gateway.close()
    except Exception:
        pass
    try:
        gateway.connect()
        ready = gateway.wait_ready(timeout=6.0)
        steps.append(
            {
                "id": "bridge_recover",
                "ok": True,
                "detail": f"bridge recovered: mode={ready.get('mode', 'UNKNOWN')}",
            }
        )
    except Exception as exc:
        steps.append({"id": "bridge_recover", "ok": False, "detail": str(exc)})

    boards = firmware.list_boards()
    detected_ports: list[str] = []
    for row in boards.get("ports") or []:
        if not isinstance(row, dict):
            continue
        addr = str(row.get("address") or "").strip()
        if addr:
            detected_ports.append(addr)
    recommended_port = str(boards.get("recommended_port") or "").strip()
    effective_port = requested_port or recommended_port
    steps.append(
        {
            "id": "detect",
            "ok": bool(boards.get("ok", False)),
            "detail": f"detected_ports={len(detected_ports)} selected_port={effective_port or 'none'}",
        }
    )

    payload = precheck_builder(
        requested_port=effective_port,
        requested_fqbn=requested_fqbn,
        requested_sketch=requested_sketch,
    )
    steps.append(
        {
            "id": "precheck",
            "ok": bool(payload.get("ready", False)),
            "detail": (
                "ready"
                if bool(payload.get("ready", False))
                else ",".join([str(x) for x in list(payload.get("hard_fail_reasons") or [])])
            ),
        }
    )

    h = gateway.health()
    st_raw = dict(h.get("last_status", {}))
    normalized = normalize_status(st_raw)
    st = dict(normalized.get("status", st_raw))
    gates = resolve_action_gates(
        gateway=gateway,
        control=control,
        prearm_gate=prearm_safety,
        status_override=st,
    )
    arm_prepare_ok = bool((gates.get("arm_prepare") or {}).get("ok", False))
    status_ok = bool(h.get("connected", False)) and len(st) > 0
    steps.append(
        {
            "id": "status_validate",
            "ok": status_ok,
            "detail": f"connected={bool(h.get('connected', False))} status_keys={len(st)} arm_prepare_ok={arm_prepare_ok}",
        }
    )

    ok = all(bool(step.get("ok", False)) for step in steps)
    report = {
        "ok": ok,
        "steps": steps,
        "selected_port": effective_port,
        "detected_ports": detected_ports,
        "precheck": payload,
        "status": st,
        "action_gates": gates,
    }
    return (
        200,
        {
            "ok": ok,
            "recovery": report,
            "tool_call": tool_call_builder(
                name="known_good_recovery",
                arguments={
                    "fqbn": requested_fqbn,
                    "port": effective_port,
                    "sketch": requested_sketch,
                },
                ok=ok,
                data={
                    "step_count": len(steps),
                    "passed_steps": sum(1 for step in steps if bool(step.get("ok", False))),
                },
                error="" if ok else "known_good_recovery_failed",
                started_ms=t0,
            ),
        },
    )


def resolve_clean_upload_inputs(
    *,
    body: Dict[str, Any],
    default_sketch: str,
    default_fqbn: str,
) -> Dict[str, Optional[str]]:
    sketch = str(body.get("sketch", "")).strip() or default_sketch
    fqbn = str(body.get("fqbn", "")).strip() or default_fqbn
    idempotency_key = str(body.get("idempotency_key", "")).strip() or None
    port = (
        str(body.get("port", "")).strip()
        or str(os.environ.get("UPRIGHT_CLEAN_UPLOAD_PORT", "")).strip()
        or None
    )
    return {
        "sketch": sketch,
        "fqbn": fqbn,
        "idempotency_key": idempotency_key,
        "port": port,
    }


def build_upload_target_runbook(target: Dict[str, Any]) -> Dict[str, Any]:
    """Build upload sequence and recovery runbook for a target board."""
    family = str(target.get("board_family", "")).strip().lower()
    board_id = str(target.get("board_id", "")).strip().lower()
    fqbn = str(target.get("fqbn", "")).strip().lower()

    upload_sequence_steps = [
        {
            "id": "confirm_port",
            "label": "Confirm selected serial port matches the active board.",
            "action_key": "detect_port",
        },
        {
            "id": "compile_first",
            "label": "Compile first.",
            "action_key": "compile",
        },
        {
            "id": "upload_guarded",
            "label": "Run guarded upload.",
            "action_key": "upload",
        },
        {
            "id": "verify_after_upload",
            "label": "Refresh status and verify telemetry is live.",
            "action_key": "refresh_status",
        },
    ]
    family_boot = "Use board-specific boot/reset sequence before retry."
    if family == "arduino_avr":
        if board_id == "nano":
            if "atmega328old" in fqbn:
                family_boot = "Nano (Old bootloader selected): if sync fails, try New bootloader and retry within 2s of reset."
            else:
                family_boot = "Nano (New bootloader selected): if sync fails, try Old bootloader and retry within 2s of reset."
        else:
            family_boot = "AVR board: press reset once and retry upload immediately."
    elif family == "esp32":
        family_boot = "ESP32: hold BOOT, tap EN/RESET once, then retry upload."
    elif family == "rp2040":
        family_boot = "RP2040: hold BOOTSEL while plugging in (or reset to UF2 mode), then retry upload."
    elif family == "teensy":
        family_boot = "Teensy: press Program button once, then retry upload."

    recovery_steps = {
        "firmware_busy": [
            {
                "id": "firmware_busy_refresh",
                "label": "Refresh status and ensure runner is idle.",
                "action_key": "refresh_status",
            },
            {
                "id": "firmware_busy_retry",
                "label": "Retry upload.",
                "action_key": "retry_upload",
            },
        ],
        "upload_port_missing": [
            {
                "id": "port_missing_detect",
                "label": "Run Detect / Re-Detect Port.",
                "action_key": "detect_port",
            },
            {
                "id": "port_missing_select",
                "label": "Select the active serial port.",
                "action_key": "select_port",
            },
            {
                "id": "port_missing_retry",
                "label": "Retry upload.",
                "action_key": "retry_upload",
            },
        ],
        "selected_port_not_detected": [
            {
                "id": "port_not_detected_redetect",
                "label": "Run Re-Detect Port.",
                "action_key": "detect_port",
            },
            {
                "id": "port_not_detected_select",
                "label": "Select the detected board port.",
                "action_key": "select_port",
            },
            {
                "id": "port_not_detected_retry",
                "label": "Retry upload.",
                "action_key": "retry_upload",
            },
        ],
        "bridge_disconnected": [
            {
                "id": "bridge_disconnected_copy",
                "label": "Copy restart command.",
                "action_key": "copy_restart_cmd",
            },
            {
                "id": "bridge_disconnected_check",
                "label": "Run recovery check after restart.",
                "action_key": "check",
            },
            {
                "id": "bridge_disconnected_retry",
                "label": "Retry upload.",
                "action_key": "retry_upload",
            },
        ],
        "runtime_manifest_invalid": [
            {
                "id": "manifest_invalid_check",
                "label": "Run recovery check and read manifest validation errors.",
                "action_key": "check",
            },
            {
                "id": "manifest_invalid_retry",
                "label": "After fixing manifest, retry upload.",
                "action_key": "retry_upload",
            },
        ],
        "bootloader_sync": [
            {
                "id": "bootloader_sync_switch",
                "label": family_boot,
                "action_key": "set_bootloader",
            },
            {
                "id": "bootloader_sync_retry",
                "label": "Retry upload.",
                "action_key": "retry_upload",
            },
        ],
    }
    recovery = {
        k: [str(step.get("label", "")).strip() for step in v if isinstance(step, dict)]
        for k, v in recovery_steps.items()
    }
    return {
        "target": target,
        "upload_sequence": [
            str(step.get("label", "")).strip()
            for step in upload_sequence_steps
            if isinstance(step, dict)
        ],
        "upload_sequence_steps": upload_sequence_steps,
        "recovery": recovery,
        "recovery_steps": recovery_steps,
    }


def build_upload_precheck_payload(
    *,
    gateway: Any,
    firmware: Any,
    requested_port: str,
    requested_fqbn: str,
    requested_sketch: str,
    target_meta_fn: Any,
) -> Dict[str, Any]:
    """Build upload precheck payload with port detection and manifest validation."""
    effective_port = (
        requested_port or str(os.environ.get("UPRIGHT_CLEAN_UPLOAD_PORT", "")).strip()
    )
    firmware_st = firmware.status()
    boards = firmware.list_boards()
    detected_ports: list[str] = []
    for row in boards.get("ports") or []:
        if not isinstance(row, dict):
            continue
        addr = str(row.get("address") or "").strip()
        if addr:
            detected_ports.append(addr)
    detected_set = set(detected_ports)
    health = gateway.health()

    reasons: list[str] = []
    if bool(firmware_st.get("running", False)):
        reasons.append("firmware_busy")
    if not effective_port:
        reasons.append("upload_port_missing")
    if (
        effective_port
        and bool(boards.get("ok", False))
        and len(detected_set) > 0
        and effective_port not in detected_set
    ):
        reasons.append("selected_port_not_detected")
    if not bool(health.get("connected", False)):
        reasons.append("bridge_disconnected")
    manifest_gate = firmware.validate_runtime_manifest(
        sketch=requested_sketch,
        require_exists=True,
    )
    if not bool(manifest_gate.get("ok", False)):
        reasons.append("runtime_manifest_invalid")
    runbook = build_upload_target_runbook(
        target_meta_fn(fqbn=requested_fqbn, firmware=firmware)
    )
    hard_fail_reasons = [
        r
        for r in reasons
        if r
        in (
            "firmware_busy",
            "upload_port_missing",
            "selected_port_not_detected",
            "runtime_manifest_invalid",
        )
    ]
    return {
        "ok": True,
        "ready": len(hard_fail_reasons) == 0,
        "error": "upload_precheck_failed" if hard_fail_reasons else "",
        "reasons": reasons,
        "hard_fail_reasons": hard_fail_reasons,
        "port": effective_port,
        "sketch": requested_sketch,
        "detected_ports": detected_ports,
        "boards_ok": bool(boards.get("ok", False)),
        "bridge_connected": bool(health.get("connected", False)),
        "manifest_validation": manifest_gate,
        "target_runbook": runbook,
    }


def summarize_sketch_artifact_issues(tool_calls: Any) -> str:
    """Validate successful sketch tool outputs still point to non-empty on-disk files."""
    import pathlib

    if not isinstance(tool_calls, list):
        return ""
    lines: list[str] = []
    for tc in tool_calls:
        if not isinstance(tc, dict):
            continue
        tool = str(tc.get("tool", "")).strip()
        result = tc.get("result", {})
        ok = bool(result.get("ok")) if isinstance(result, dict) else False
        if not ok:
            continue
        data = result.get("data", {}) if isinstance(result, dict) else {}
        if not isinstance(data, dict):
            continue

        if tool == "generate_sketch":
            path = str(data.get("main_file", "")).strip()
            if not path:
                lines.append(
                    "- generate_sketch failed post-check: missing main_file in tool result."
                )
                continue
            p = pathlib.Path(path)
            if not p.exists() or not p.is_file():
                lines.append(
                    f"- generate_sketch failed post-check: main_file not found ({path})."
                )
                continue
            try:
                if p.stat().st_size <= 0:
                    lines.append(
                        f"- generate_sketch failed post-check: main_file is empty ({path})."
                    )
            except OSError:
                lines.append(
                    f"- generate_sketch failed post-check: unable to read main_file size ({path})."
                )

        if tool == "edit_sketch_value":
            path = str(data.get("file", "")).strip()
            if not path:
                continue
            p = pathlib.Path(path)
            if not p.exists() or not p.is_file():
                lines.append(
                    f"- edit_sketch_value failed post-check: edited file not found ({path})."
                )
                continue
            try:
                if p.stat().st_size <= 0:
                    lines.append(
                        f"- edit_sketch_value failed post-check: edited file is empty ({path})."
                    )
            except OSError:
                lines.append(
                    f"- edit_sketch_value failed post-check: unable to read edited file size ({path})."
                )

    if not lines:
        return ""
    return "\n".join(lines[:3])


def summarize_tool_failures(tool_calls: Any) -> str:
    """Return a concise deterministic failure summary from tool call results."""
    if not isinstance(tool_calls, list):
        return ""
    lines: list[str] = []
    for tc in tool_calls:
        if not isinstance(tc, dict):
            continue
        tool = str(tc.get("tool", "")).strip() or "unknown_tool"
        result = tc.get("result", {})
        ok = bool(result.get("ok")) if isinstance(result, dict) else False
        if ok:
            continue
        err = ""
        if isinstance(result, dict):
            err = str(result.get("error") or "").strip()
        if not err:
            err = "tool_failed_without_error_detail"

        if tool == "generate_sketch" and "invalid_unified_profile" in err:
            details = err.split("invalid_unified_profile:", 1)[-1].strip()
            lines.append(
                f"generate_sketch failed: missing/invalid profile fields ({details})."
            )
        else:
            lines.append(f"{tool} failed: {err}.")

    if not lines:
        return ""
    return "\n".join(f"- {line}" for line in lines[:3])


def clean_upload_target_meta(
    *, fqbn: str, firmware: Any, board_id_fn: Any, family_fn: Any
) -> Dict[str, Any]:
    """Build upload target metadata for a given FQBN."""
    targets = firmware.list_targets()
    board_id = board_id_fn(fqbn, targets) or "unknown"
    family = family_fn(fqbn, targets) or "unknown"
    board_label = board_id
    for row in list(targets.get("boards") or []):
        if not isinstance(row, dict):
            continue
        if str(row.get("id", "")).strip() != board_id:
            continue
        board_label = str(row.get("label", "")).strip() or board_id
        break
    return {
        "fqbn": str(fqbn).strip(),
        "board_id": board_id,
        "board_family": family,
        "board_label": board_label,
    }


def clean_default_sketch_path(repo_root: Any, firmware: Any) -> str:
    """Get the default sketch path for clean firmware operations."""
    import os
    env_override = str(os.environ.get("UPRIGHT_CLEAN_SKETCH", "")).strip()
    if env_override:
        return env_override
    return str(
        repo_root / "app" / "bridge" / "firmware_templates" / "profiled_runtime_v1"
    )


def clean_default_fqbn() -> str:
    """Get the default FQBN for clean firmware operations."""
    import os
    return str(
        os.environ.get(
            "UPRIGHT_CLEAN_COMPILE_FQBN", "arduino:avr:nano:cpu=atmega328old"
        )
    )
