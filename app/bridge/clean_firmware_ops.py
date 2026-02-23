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
