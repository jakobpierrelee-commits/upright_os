#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import collections
import hashlib
import json
import logging
import os
import pathlib
import re
import signal
import subprocess
import secrets
import sys
import threading
import time
import traceback
import faulthandler

logger = logging.getLogger(__name__)
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse

try:
    import websockets
except Exception:
    websockets = None

try:
    import certifi
except Exception:
    certifi = None

try:
    from serial.tools import list_ports
except Exception:
    list_ports = None

try:
    from app.bridge.serial_gateway import NanoSerialGateway
except ImportError:
    from serial_gateway import NanoSerialGateway
try:
    from app.bridge.domains.tuning_intelligence.host_capture_manager import (
        HostCaptureManager,
    )
except ImportError:
    from domains.tuning_intelligence.host_capture_manager import HostCaptureManager  # type: ignore
try:
    from app.bridge.domains.ai_agent.ai_manager import AIManager
except ImportError:
    from domains.ai_agent.ai_manager import AIManager  # type: ignore
try:
    from app.bridge.domains.firmware_lifecycle.firmware_manager import FirmwareManager
except ImportError:
    from domains.firmware_lifecycle.firmware_manager import FirmwareManager  # type: ignore
try:
    from app.bridge.domains.session_traceability.mission_memory import (
        MissionMemoryStore,
    )
except ImportError:
    from domains.session_traceability.mission_memory import MissionMemoryStore  # type: ignore
try:
    from app.bridge.domains.session_traceability.design_memory import DesignMemoryStore
except ImportError:
    from domains.session_traceability.design_memory import DesignMemoryStore  # type: ignore
try:
    from app.bridge.domains.hardware_profile.hardware_context import (
        HardwareContextStore,
    )
except ImportError:
    from domains.hardware_profile.hardware_context import HardwareContextStore  # type: ignore
try:
    from app.bridge.domains.session_traceability.setup_attempt_history import (
        SetupAttemptHistoryStore,
    )
except ImportError:
    from domains.session_traceability.setup_attempt_history import (
        SetupAttemptHistoryStore,
    )  # type: ignore
try:
    from app.bridge.domains.session_traceability.config_history_manager import (
        ConfigHistoryManager,
    )
except ImportError:
    from domains.session_traceability.config_history_manager import ConfigHistoryManager  # type: ignore
try:
    from app.bridge.domains.session_traceability.ai_profile_manager import (
        AIProfileManager,
    )
except ImportError:
    from domains.session_traceability.ai_profile_manager import AIProfileManager  # type: ignore
try:
    from app.bridge.domains.session_traceability.assistant_knowledge import (
        AssistantKnowledgeManager,
    )
except ImportError:
    from domains.session_traceability.assistant_knowledge import (
        AssistantKnowledgeManager,
    )  # type: ignore
try:
    from app.bridge.domains.session_traceability.agent_mission_manager import (
        AgentMissionManager,
    )
except ImportError:
    from domains.session_traceability.agent_mission_manager import AgentMissionManager  # type: ignore
try:
    from app.bridge.domains.control_runtime.bridge_control_state import (
        BridgeControlState,
    )
except ImportError:
    from domains.control_runtime.bridge_control_state import BridgeControlState  # type: ignore
try:
    from app.bridge.domains.control_runtime.telemetry_hub import TelemetryHub
except ImportError:
    from domains.control_runtime.telemetry_hub import TelemetryHub  # type: ignore
try:
    from app.bridge.domains.tuning_intelligence.commissioning_manager import (
        CommissioningManager,
    )
except ImportError:
    from domains.tuning_intelligence.commissioning_manager import CommissioningManager  # type: ignore
try:
    from app.bridge.domains.hardware_profile.robot_profiles_manager import (
        RobotProfilesManager,
    )
except ImportError:
    from domains.hardware_profile.robot_profiles_manager import RobotProfilesManager  # type: ignore
try:
    from app.bridge.domains.session_traceability.auth_manager import AuthManager
except ImportError:
    from domains.session_traceability.auth_manager import AuthManager  # type: ignore
try:
    from app.bridge.domains.safety_prearm.tuning_preflight import TuningPreflightStore
except ImportError:
    from domains.safety_prearm.tuning_preflight import TuningPreflightStore  # type: ignore
try:
    from app.bridge.provider_router import ProviderRouter
except ImportError:
    from provider_router import ProviderRouter
try:
    from app.bridge.arm_safety import (
        PreArmSafetyGate,
        run_prearm_hardware_check as _run_prearm_hardware_check_impl,
    )
except ImportError:
    from arm_safety import (  # type: ignore
        PreArmSafetyGate,
        run_prearm_hardware_check as _run_prearm_hardware_check_impl,
    )
try:
    from app.bridge.clean_firmware_ops import (
        handle_clean_firmware_compile,
        handle_clean_firmware_upload,
        handle_clean_known_good_recovery,
        handle_clean_upload_precheck,
        resolve_clean_upload_inputs,
    )
except ImportError:
    from clean_firmware_ops import (  # type: ignore
        handle_clean_firmware_compile,
        handle_clean_firmware_upload,
        handle_clean_known_good_recovery,
        handle_clean_upload_precheck,
        resolve_clean_upload_inputs,
    )
try:
    from app.bridge.clean_contracts import (
        validate_clean_preflight_response,
        validate_firmware_targets_response,
        validate_prearm_precheck_response,
    )
except ImportError:
    from clean_contracts import (  # type: ignore
        validate_clean_preflight_response,
        validate_firmware_targets_response,
        validate_prearm_precheck_response,
    )
try:
    from app.bridge.clean_preflight import (
        resolve_manifest_gates,
        run_clean_preflight,
    )
except ImportError:
    from clean_preflight import (  # type: ignore
        resolve_manifest_gates,
        run_clean_preflight,
    )
try:
    from app.bridge.clean_codex_chat import (
        run_clean_chat,
        run_clean_chat_stream,
    )
except ImportError:
    from clean_codex_chat import (  # type: ignore
        run_clean_chat,
        run_clean_chat_stream,
    )
try:
    from app.bridge.clean_route_helpers import (
        build_clean_agent_context,
        build_clean_system_prompt,
        clean_tool_call,
        run_clean_auto_tools,
    )
except ImportError:
    from clean_route_helpers import (  # type: ignore
        build_clean_agent_context,
        build_clean_system_prompt,
        clean_tool_call,
        run_clean_auto_tools,
    )
try:
    from app.bridge.clean_auth_helpers import (
        codex_cli_login_status,
        sanitize_agent_attachments,
    )
except ImportError:
    from clean_auth_helpers import (  # type: ignore
        codex_cli_login_status,
        sanitize_agent_attachments,
    )
try:
    from app.bridge.clean_legacy_gate import (
        legacy_execution_block_payload,
        legacy_execution_enabled,
    )
except ImportError:
    from clean_legacy_gate import (  # type: ignore
        legacy_execution_block_payload,
        legacy_execution_enabled,
    )
try:
    from app.bridge.clean_threads import (
        handle_clean_thread_new,
        handle_clean_thread_select,
        handle_clean_threads_get,
    )
except ImportError:
    from clean_threads import (  # type: ignore
        handle_clean_thread_new,
        handle_clean_thread_select,
        handle_clean_threads_get,
    )
try:
    from app.bridge.clean_status import (
        build_agent_status_payload,
        build_health_payload,
        build_clean_status_payload,
        build_status_payload,
    )
except ImportError:
    from clean_status import (  # type: ignore
        build_agent_status_payload,
        build_clean_status_payload,
    )
try:
    from app.bridge.clean_profiles import (
        build_profiles_hardware_payload,
        build_profiles_payload,
        build_runtime_manifest_compat_payload,
    )
except ImportError:
    from clean_profiles import (  # type: ignore
        build_profiles_hardware_payload,
        build_profiles_payload,
        build_runtime_manifest_compat_payload,
    )
try:
    from app.bridge.clean_firmware import (
        build_firmware_artifacts_payload,
        build_firmware_sketch_folders_payload,
        build_firmware_status_payload,
        build_runtime_manifest_validate_payload,
    )
except ImportError:
    from clean_firmware import (  # type: ignore
        build_firmware_artifacts_payload,
        build_firmware_sketch_folders_payload,
        build_firmware_status_payload,
        build_runtime_manifest_validate_payload,
    )
try:
    from app.bridge.clean_safety import (
        build_arm_precheck_payload,
        build_status_control_payload,
    )
except ImportError:
    from clean_safety import (  # type: ignore
        build_arm_precheck_payload,
    )
try:
    from app.bridge.clean_tuning import (
        build_burst_status_payload,
        build_commissioning_artifacts_payload,
        build_commissioning_run_payload,
        build_commissioning_status_payload,
        build_lines_payload,
        build_tuning_preflight_payload,
        build_tuning_recommend_payload,
        build_tuning_result_payload,
    )
except ImportError:
    from clean_tuning import (  # type: ignore
        build_burst_status_payload,
        build_commissioning_artifacts_payload,
        build_commissioning_status_payload,
        build_lines_payload,
        build_tuning_result_payload,
    )
try:
    from app.bridge.clean_probe import (
        build_compat_probe_payload,
        build_design_memory_best_payload,
        build_design_memory_payload,
        build_probe_payload,
        build_tooling_traces_payload,
        build_tuning_capabilities_payload,
    )
except ImportError:
    from clean_probe import (  # type: ignore
        build_compat_probe_payload,
        build_design_memory_best_payload,
        build_design_memory_payload,
        build_probe_payload,
        build_tooling_traces_payload,
    )
try:
    from app.bridge.routes_tuning import (
        handle_tuning_preflight,
        handle_tuning_recommend,
    )
except ImportError:
    from routes_tuning import (  # type: ignore
        handle_tuning_preflight,
        handle_tuning_recommend,
    )
try:
    from app.bridge.routes_burst import (
        handle_burst_arm,
        handle_burst_label,
    )
except ImportError:
    from routes_burst import (  # type: ignore
        handle_burst_arm,
        handle_burst_label,
    )
try:
    from app.bridge.routes_tooling import (
        handle_param_sweep,
        handle_surrogate_simulate,
        handle_trace_replay,
    )
except ImportError:
    from routes_tooling import (  # type: ignore
        handle_param_sweep,
        handle_surrogate_simulate,
        handle_trace_replay,
    )
try:
    from app.bridge.routes_commissioning import (
        handle_commissioning_run,
        handle_commissioning_step,
    )
except ImportError:
    from routes_commissioning import (  # type: ignore
        handle_commissioning_run,
        handle_commissioning_step,
    )
try:
    from app.bridge.routes_firmware import (
        handle_firmware_artifacts_get,
        handle_firmware_boards_get,
        handle_firmware_check_post,
        handle_firmware_compile,
        handle_firmware_generate_docs_pack,
        handle_firmware_generate_unified,
        handle_firmware_install_cli,
        handle_firmware_runtime_manifest_compat_get,
        handle_firmware_runtime_manifest_validate_get,
        handle_firmware_sketch_folders_get,
        handle_firmware_sketch_folder_pick,
        handle_firmware_sketch_get,
        handle_firmware_sketch_write,
        handle_firmware_status_get,
        handle_firmware_targets_get,
        handle_firmware_unified_schema_get,
        handle_firmware_upload,
        handle_firmware_upload_guarded,
    )
except ImportError:
    from routes_firmware import (  # type: ignore
        handle_firmware_artifacts_get,
        handle_firmware_boards_get,
        handle_firmware_check_post,
        handle_firmware_compile,
        handle_firmware_generate_docs_pack,
        handle_firmware_generate_unified,
        handle_firmware_install_cli,
        handle_firmware_runtime_manifest_compat_get,
        handle_firmware_runtime_manifest_validate_get,
        handle_firmware_sketch_folders_get,
        handle_firmware_sketch_folder_pick,
        handle_firmware_sketch_get,
        handle_firmware_sketch_write,
        handle_firmware_status_get,
        handle_firmware_targets_get,
        handle_firmware_unified_schema_get,
        handle_firmware_upload,
        handle_firmware_upload_guarded,
    )
try:
    from app.bridge.routes_profiles import (
        handle_profiles_activate,
        handle_profiles_delete,
        handle_profiles_hardware,
        handle_profiles_list,
        handle_profiles_save,
        handle_profiles_validate,
    )
except ImportError:
    from routes_profiles import (  # type: ignore
        handle_profiles_activate,
        handle_profiles_delete,
        handle_profiles_hardware,
        handle_profiles_list,
        handle_profiles_save,
        handle_profiles_validate,
    )
try:
    from app.bridge.routes_arm import (
        handle_arm,
        handle_arm_confirm,
        handle_arm_prepare,
        handle_command,
        handle_disarm,
        handle_estop_latch,
        handle_estop_reset,
    )
except ImportError:
    from routes_arm import (  # type: ignore
        handle_arm,
        handle_arm_confirm,
        handle_arm_prepare,
        handle_command,
        handle_disarm,
        handle_estop_latch,
        handle_estop_reset,
    )
try:
    from app.bridge.routes_calibration import (
        handle_cal_zero,
        handle_defaultcfg,
        handle_imu_calibrate,
        handle_imu_info,
        handle_imu_load,
        handle_imu_save,
        handle_loadcfg,
        handle_savecfg,
    )
except ImportError:
    from routes_calibration import (  # type: ignore
        handle_cal_zero,
        handle_defaultcfg,
        handle_imu_calibrate,
        handle_imu_info,
        handle_imu_load,
        handle_imu_save,
        handle_loadcfg,
        handle_savecfg,
    )
try:
    from app.bridge.routes_health import (
        handle_health,
        handle_status,
    )
except ImportError:
    from routes_health import (  # type: ignore
        handle_health,
        handle_status,
    )
try:
    from app.bridge.clean_ai import (
        build_agent_chat_reply_payload,
        build_agent_status_payload,
        build_agent_thread_state_payload,
        build_ai_chat_response_payload,
        build_ai_knowledge_payload,
        build_ai_profiles_payload,
        build_ai_status_payload,
        build_ai_thread_payload,
        build_ai_threads_payload,
        build_ai_threads_status_payload,
        build_auth_openai_status_payload,
        build_auth_session_payload,
        build_auth_user_payload,
        build_chat_with_tools_payload,
        build_disambiguation_reply_payload,
        build_openai_config_payload,
        build_rag_index_payload,
        build_session_heartbeat_payload,
    )
except ImportError:
    from clean_ai import (  # type: ignore
        build_agent_chat_reply_payload,
        build_agent_status_payload,
        build_agent_thread_state_payload,
        build_ai_chat_response_payload,
        build_ai_knowledge_payload,
        build_ai_profiles_payload,
        build_ai_status_payload,
        build_ai_thread_payload,
        build_ai_threads_status_payload,
        build_auth_openai_status_payload,
        build_auth_session_payload,
        build_auth_user_payload,
        build_chat_with_tools_payload,
        build_disambiguation_reply_payload,
        build_openai_config_payload,
        build_rag_index_payload,
        build_session_heartbeat_payload,
    )
try:
    from app.bridge.clean_serial import (
        build_diag_serial_payload,
        build_result_status_control_payload,
        build_telemetry_adapters_payload,
        build_unified_schema_payload,
    )
except ImportError:
    from clean_serial import (  # type: ignore
        build_diag_serial_payload,
        build_telemetry_adapters_payload,
        build_unified_schema_payload,
    )
try:
    from app.bridge.clean_misc import (
        build_action_payload,
        build_active_profiles_payload,
        build_agent_state_payload,
        build_attempt_history_payload,
        build_attachment_payload,
        build_boards_payload,
        build_burst_label_payload,
        build_capabilities_payload,
        build_command_result_payload,
        build_control_payload,
        build_design_payload,
        build_docs_pack_payload,
        build_firmware_check_payload,
        build_firmware_cmd_status_payload,
        build_firmware_result_payload,
        build_overwatch_payload,
        build_picked_payload,
        build_port_released_payload,
        build_profiles_list_payload,
        build_replay_payload,
        build_reset_payload,
        build_result_control_payload,
        build_result_payload,
        build_revert_control_payload,
        build_saved_profiles_payload,
        build_sketch_payload,
        build_sketch_write_payload,
        build_setup_check_payload,
        build_snapshots_payload,
        build_stats_payload,
        build_sweep_payload,
        build_targets_payload,
        build_tool_metrics_payload,
        build_unified_payload,
        build_upload_confirm_success_payload,
        build_surrogate_simulate_payload,
        build_validation_payload,
    )
except ImportError:
    from clean_misc import (  # type: ignore
        build_action_payload,
        build_agent_state_payload,
        build_attempt_history_payload,
        build_attachment_payload,
        build_boards_payload,
        build_capabilities_payload,
        build_design_payload,
        build_firmware_check_payload,
        build_overwatch_payload,
        build_port_released_payload,
        build_reset_payload,
        build_result_payload,
        build_revert_control_payload,
        build_sketch_payload,
        build_setup_check_payload,
        build_snapshots_payload,
        build_stats_payload,
        build_targets_payload,
        build_tool_metrics_payload,
        build_upload_confirm_success_payload,
    )
try:
    from app.bridge.clean_request_parsers import (
        parse_clean_chat_request,
        parse_clean_preflight_request,
    )
except ImportError:
    from clean_request_parsers import (  # type: ignore
        parse_clean_chat_request,
        parse_clean_preflight_request,
    )
try:
    from app.bridge.clean_sse import apply_sse_headers, make_sse_emitter
except ImportError:
    from clean_sse import apply_sse_headers, make_sse_emitter  # type: ignore

try:
    from app.bridge.codex_agent import CodexAgent, create_codex_agent
    from app.bridge.codex_db import get_codex_db
    from app.bridge.codex_rag import get_codex_rag
    from app.bridge.trace_replay import replay_file
    from app.bridge.param_sweep import (
        parse_range_spec,
        SweepConfig,
        ParameterSweepRunner,
    )
    from app.bridge.surrogate_sim import simulate_from_logs
    from app.bridge.tuning_policy import evaluate_tuning_plan
except ImportError:
    try:
        from codex_agent import CodexAgent, create_codex_agent
        from codex_db import get_codex_db
        from codex_rag import get_codex_rag
        from trace_replay import replay_file
        from param_sweep import parse_range_spec, SweepConfig, ParameterSweepRunner
        from surrogate_sim import simulate_from_logs
        from tuning_policy import evaluate_tuning_plan
    except ImportError:
        CodexAgent = None  # type: ignore
        create_codex_agent = None  # type: ignore
        get_codex_db = None  # type: ignore
        get_codex_rag = None  # type: ignore
        replay_file = None  # type: ignore
        parse_range_spec = None  # type: ignore
        SweepConfig = None  # type: ignore
        ParameterSweepRunner = None  # type: ignore
        simulate_from_logs = None  # type: ignore
        evaluate_tuning_plan = None  # type: ignore


# BridgeControlState moved to domain module
# CommissioningManager moved to domain module
# SetupAttemptHistoryStore moved to domain module
def _safe_float(v: Any) -> Optional[float]:
    try:
        return float(v)
    except Exception:
        return None


def _first_float(status: Dict[str, Any], *keys: str) -> Optional[float]:
    for k in keys:
        if k in status:
            out = _safe_float(status.get(k))
            if out is not None:
                return out
    return None


def _extract_apply_json(answer: str) -> Optional[Dict[str, Any]]:
    marker = "UPRIGHT_APPLY_JSON:"
    idx = answer.find(marker)
    if idx < 0:
        return None
    tail = answer[idx + len(marker) :].lstrip()
    if not tail.startswith("{"):
        return None
    dec = json.JSONDecoder()
    try:
        obj, _ = dec.raw_decode(tail)
    except Exception:
        return None
    if isinstance(obj, dict):
        return obj
    return None


def _sanitize_apply_plan(raw: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    pid = raw.get("pid")
    if isinstance(pid, dict):
        kp = _safe_float(pid.get("kp"))
        ki = _safe_float(pid.get("ki"))
        kd = _safe_float(pid.get("kd"))
        partial: Dict[str, float] = {}
        if kp is not None:
            partial["kp"] = kp
        if ki is not None:
            partial["ki"] = ki
        if kd is not None:
            partial["kd"] = kd
        if partial:
            out["pid"] = partial
    motion = raw.get("motion")
    if isinstance(motion, dict):
        kv = _safe_float(motion.get("kv"))
        kx = _safe_float(motion.get("kx"))
        partial_m: Dict[str, float] = {}
        if kv is not None:
            partial_m["kv"] = kv
        if kx is not None:
            partial_m["kx"] = kx
        if partial_m:
            out["motion"] = partial_m
    setpoint = raw.get("setpoint")
    if isinstance(setpoint, dict):
        deg = _safe_float(setpoint.get("deg"))
        if deg is not None:
            out["setpoint"] = {"deg": deg}
    else:
        deg = _safe_float(setpoint)
        if deg is not None:
            out["setpoint"] = {"deg": deg}
    limits = raw.get("limits")
    if isinstance(limits, dict):
        out_max = _safe_float(limits.get("out_max"))
        tip_deg = _safe_float(limits.get("tip_deg"))
        i_max = _safe_float(limits.get("i_max"))
        partial_l: Dict[str, float] = {}
        if out_max is not None:
            partial_l["out_max"] = out_max
        if tip_deg is not None:
            partial_l["tip_deg"] = tip_deg
        if i_max is not None:
            partial_l["i_max"] = i_max
        if partial_l:
            out["limits"] = partial_l
    unified = raw.get("unified")
    if isinstance(unified, dict):
        profile = unified.get("profile")
        sketch_name = unified.get("sketch_name")
        if isinstance(profile, dict):
            part_u: Dict[str, Any] = {"profile": profile}
            if isinstance(sketch_name, str) and sketch_name.strip():
                part_u["sketch_name"] = sketch_name.strip()
            out["unified"] = part_u
    sketch = raw.get("sketch")
    if isinstance(sketch, dict):
        content = sketch.get("content")
        path = sketch.get("path")
        if isinstance(content, str) and content.strip():
            part_s: Dict[str, Any] = {"content": content}
            if isinstance(path, str) and path.strip():
                part_s["path"] = path.strip()
            out["sketch"] = part_s
    return out


def _strip_apply_json_block(answer: str) -> str:
    marker = "UPRIGHT_APPLY_JSON:"
    idx = answer.find(marker)
    if idx < 0:
        return answer.strip()
    head = answer[:idx].rstrip()
    tail = answer[idx + len(marker) :].lstrip()
    if tail.startswith("{"):
        dec = json.JSONDecoder()
        try:
            _, end_idx = dec.raw_decode(tail)
            tail = tail[end_idx:].lstrip()
        except Exception:
            pass
    merged = f"{head}\n{tail}".strip() if head and tail else (head or tail).strip()
    return merged


def _format_apply_note(apply_result: Dict[str, Any]) -> str:
    if not bool(apply_result.get("ok", False)):
        return f"Apply failed: {str(apply_result.get('error', 'unknown_error'))}"
    applied = apply_result.get("applied", [])
    if not isinstance(applied, list):
        applied = []
    sections = ", ".join(str(x) for x in applied) if applied else "none"
    changed = apply_result.get("changed", {})
    kd_note = ""
    if isinstance(changed, dict):
        pid = changed.get("pid")
        if isinstance(pid, dict):
            before = pid.get("before") if isinstance(pid.get("before"), dict) else {}
            target = pid.get("target") if isinstance(pid.get("target"), dict) else {}
            bkd = before.get("kd")
            tkd = target.get("kd")
            if bkd is not None and tkd is not None:
                kd_note = f" KD {float(bkd):.3f} -> {float(tkd):.3f}."
    sid = str(apply_result.get("snapshot_id", "")).strip()
    extras = apply_result.get("artifacts", {})
    extra_note = ""
    if isinstance(extras, dict):
        sketch_path = extras.get("sketch_path")
        unified_folder = extras.get("unified_folder")
        if isinstance(unified_folder, str) and unified_folder:
            extra_note += f" Unified scaffold: {unified_folder}."
        if isinstance(sketch_path, str) and sketch_path:
            extra_note += f" Sketch updated: {sketch_path}."
    if sid:
        return f"Applied now: {sections}.{kd_note}{extra_note} Revert point saved ({sid}).".strip()
    return f"Applied now: {sections}.{kd_note}{extra_note}".strip()


def _safe_upload_filename(name: str) -> str:
    raw = str(name or "").strip()
    if not raw:
        return f"upload_{int(time.time())}.bin"
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "_", pathlib.Path(raw).name).strip("._")
    if not cleaned:
        cleaned = f"upload_{int(time.time())}.bin"
    return cleaned[:120]


def _attachment_kind(mime: str, name: str) -> str:
    m = str(mime or "").strip().lower()
    n = str(name or "").strip().lower()
    if m.startswith("image/"):
        return "image"
    if "csv" in m or n.endswith(".csv"):
        return "csv"
    if (
        m.startswith("text/")
        or "json" in m
        or "yaml" in m
        or "toml" in m
        or n.endswith((".txt", ".md", ".json", ".yaml", ".yml", ".toml", ".log"))
    ):
        return "text"
    return "binary"


def _agent_upload_from_body(
    repo_root: pathlib.Path, body: Dict[str, Any]
) -> Dict[str, Any]:
    name = _safe_upload_filename(str(body.get("name", "")))
    mime = (
        str(body.get("mime", "application/octet-stream")).strip()
        or "application/octet-stream"
    )
    payload_b64 = str(body.get("content_base64", "")).strip()
    if not payload_b64:
        raise RuntimeError("missing_content_base64")
    try:
        raw = base64.b64decode(payload_b64, validate=True)
    except Exception as exc:
        raise RuntimeError(f"invalid_base64:{exc}") from exc
    if not raw:
        raise RuntimeError("empty_file")
    if len(raw) > (5 * 1024 * 1024):
        raise RuntimeError("file_too_large_max_5mb")

    up_dir = repo_root / "app" / "bridge" / "agent_uploads"
    up_dir.mkdir(parents=True, exist_ok=True)
    stamp = int(time.time())
    token = secrets.token_hex(4)
    final_name = f"{stamp}_{token}_{name}"
    target = up_dir / final_name
    target.write_bytes(raw)

    kind = _attachment_kind(mime, name)
    text_excerpt = ""
    if kind in {"text", "csv"}:
        try:
            text_excerpt = raw.decode("utf-8", errors="replace")[:16000]
        except Exception:
            text_excerpt = ""

    return {
        "id": f"att_{stamp}_{token}",
        "name": name,
        "mime": mime,
        "kind": kind,
        "size": len(raw),
        "path": str(target),
        "text_excerpt": text_excerpt,
    }


def _sanitize_agent_attachments(raw: Any) -> list[Dict[str, Any]]:
    return sanitize_agent_attachments(
        raw=raw,
        safe_upload_filename_fn=_safe_upload_filename,
        attachment_kind_fn=_attachment_kind,
    )


# ConfigHistoryManager moved to domain module
def _apply_tuning_plan(
    gateway: NanoSerialGateway,
    config_history: ConfigHistoryManager,
    plan: Dict[str, Any],
    *,
    source: str,
) -> Dict[str, Any]:
    status_before = gateway.get_status()
    curr_kp = _first_float(status_before, "kp")
    curr_ki = _first_float(status_before, "ki")
    curr_kd = _first_float(status_before, "kd")
    curr_kv = _first_float(status_before, "kv")
    curr_kx = _first_float(status_before, "kx")
    curr_set = _first_float(status_before, "set")
    curr_out_max = _first_float(status_before, "outMax", "out_max")
    curr_tip_deg = _first_float(status_before, "tipDeg", "tip_deg")
    curr_i_max = _first_float(status_before, "iMax", "i_max")
    snap = config_history.save_snapshot(
        source=source, status_before=status_before, note="auto-pre-apply"
    )
    actions: list[str] = []
    changed: Dict[str, Any] = {}
    if "pid" in plan:
        p = plan["pid"]
        kp = _safe_float(p.get("kp")) if isinstance(p, dict) else None
        ki = _safe_float(p.get("ki")) if isinstance(p, dict) else None
        kd = _safe_float(p.get("kd")) if isinstance(p, dict) else None
        if kp is None:
            kp = curr_kp
        if ki is None:
            ki = curr_ki
        if kd is None:
            kd = curr_kd
        if kp is None or ki is None or kd is None:
            raise RuntimeError("apply_pid_missing_current_values")
        gateway.command(f"PID {kp} {ki} {kd}", expect_contains="OK PID", timeout=2.0)
        actions.append("pid")
        changed["pid"] = {
            "before": {"kp": curr_kp, "ki": curr_ki, "kd": curr_kd},
            "target": {"kp": kp, "ki": ki, "kd": kd},
        }
    if "motion" in plan:
        m = plan["motion"]
        kv = _safe_float(m.get("kv")) if isinstance(m, dict) else None
        kx = _safe_float(m.get("kx")) if isinstance(m, dict) else None
        if kv is None:
            kv = curr_kv
        if kx is None:
            kx = curr_kx
        if kv is None or kx is None:
            raise RuntimeError("apply_motion_missing_current_values")
        gateway.command(f"MOTION {kv} {kx}", expect_contains="OK MOTION", timeout=2.0)
        actions.append("motion")
        changed["motion"] = {
            "before": {"kv": curr_kv, "kx": curr_kx},
            "target": {"kv": kv, "kx": kx},
        }
    if "setpoint" in plan:
        s = plan["setpoint"]
        deg = _safe_float(s.get("deg")) if isinstance(s, dict) else None
        if deg is None:
            deg = curr_set
        if deg is None:
            raise RuntimeError("apply_setpoint_missing_current_value")
        gateway.command(f"SETPOINT {deg}", expect_contains="OK SETPOINT", timeout=2.0)
        actions.append("setpoint")
        changed["setpoint"] = {"before": {"deg": curr_set}, "target": {"deg": deg}}
    if "limits" in plan:
        l = plan["limits"]
        out_max = _safe_float(l.get("out_max")) if isinstance(l, dict) else None
        tip_deg = _safe_float(l.get("tip_deg")) if isinstance(l, dict) else None
        i_max = _safe_float(l.get("i_max")) if isinstance(l, dict) else None
        if out_max is None:
            out_max = curr_out_max
        if tip_deg is None:
            tip_deg = curr_tip_deg
        if i_max is None:
            i_max = curr_i_max
        if out_max is None or tip_deg is None or i_max is None:
            raise RuntimeError("apply_limits_missing_current_values")
        gateway.command(
            f"LIMITS {out_max} {tip_deg} {i_max}",
            expect_contains="OK LIMITS",
            timeout=2.0,
        )
        actions.append("limits")
        changed["limits"] = {
            "before": {
                "out_max": curr_out_max,
                "tip_deg": curr_tip_deg,
                "i_max": curr_i_max,
            },
            "target": {"out_max": out_max, "tip_deg": tip_deg, "i_max": i_max},
        }
    return {
        "ok": True,
        "snapshot_id": snap["snapshot_id"],
        "applied": actions,
        "changed": changed,
        "status": gateway.get_status(),
    }


def _apply_assistant_plan(
    gateway: NanoSerialGateway,
    config_history: ConfigHistoryManager,
    firmware: FirmwareManager,
    plan: Dict[str, Any],
    *,
    source: str,
) -> Dict[str, Any]:
    tuning_keys = {"pid", "motion", "setpoint", "limits"}
    tuning_plan = {k: plan[k] for k in tuning_keys if k in plan}
    applied: list[str] = []
    changed: Dict[str, Any] = {}
    artifacts: Dict[str, Any] = {}
    snapshot_id: Optional[str] = None
    status_after: Optional[Dict[str, Any]] = None

    if tuning_plan:
        t = _apply_tuning_plan(gateway, config_history, tuning_plan, source=source)
        if not bool(t.get("ok", False)):
            return t
        applied.extend(
            list(t.get("applied", [])) if isinstance(t.get("applied"), list) else []
        )
        if isinstance(t.get("changed"), dict):
            changed.update(t["changed"])
        sid = t.get("snapshot_id")
        if isinstance(sid, str) and sid:
            snapshot_id = sid
        if isinstance(t.get("status"), dict):
            status_after = t.get("status")

    unified = plan.get("unified")
    if isinstance(unified, dict):
        profile = unified.get("profile")
        if not isinstance(profile, dict):
            raise RuntimeError("apply_unified_profile_missing")
        sketch_name = unified.get("sketch_name")
        out = firmware.generate_unified(
            profile=profile,
            sketch_name=str(sketch_name) if isinstance(sketch_name, str) else None,
        )
        applied.append("unified")
        artifacts["unified_folder"] = out.get("sketch_folder")
        artifacts["unified_archive"] = out.get("archive")
        artifacts["unified_main_file"] = out.get("main_file")

    sketch = plan.get("sketch")
    if isinstance(sketch, dict):
        content = sketch.get("content")
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("apply_sketch_content_missing")
        path = sketch.get("path")
        profile = sketch.get("profile")
        out = firmware.write_sketch_with_backup(
            content=content,
            path=str(path) if isinstance(path, str) and path.strip() else None,
            source="assistant",
            profile=profile if isinstance(profile, dict) else None,
        )
        applied.append("sketch")
        artifacts["sketch_path"] = out.get("path")
        artifacts["sketch_backup"] = out.get("backup_path")
        artifacts["sketch_bytes"] = out.get("bytes")

    if not status_after:
        try:
            status_after = gateway.get_status()
        except Exception:
            status_after = None
    return {
        "ok": True,
        "snapshot_id": snapshot_id,
        "applied": applied,
        "changed": changed,
        "artifacts": artifacts,
        "status": status_after,
    }


def _revert_snapshot(
    gateway: NanoSerialGateway,
    config_history: ConfigHistoryManager,
    *,
    snapshot_id: Optional[str] = None,
) -> Dict[str, Any]:
    snap = config_history.get_snapshot(snapshot_id=snapshot_id)
    if not snap:
        raise RuntimeError("snapshot_not_found")
    vals = snap.get("values", {})
    pid = vals.get("pid", {}) if isinstance(vals, dict) else {}
    motion = vals.get("motion", {}) if isinstance(vals, dict) else {}
    setpoint = vals.get("setpoint", {}) if isinstance(vals, dict) else {}
    limits = vals.get("limits", {}) if isinstance(vals, dict) else {}
    actions: list[str] = []
    if all(_safe_float(pid.get(k)) is not None for k in ("kp", "ki", "kd")):
        gateway.command(
            f"PID {float(pid['kp'])} {float(pid['ki'])} {float(pid['kd'])}",
            expect_contains="OK PID",
            timeout=2.0,
        )
        actions.append("pid")
    if all(_safe_float(motion.get(k)) is not None for k in ("kv", "kx")):
        gateway.command(
            f"MOTION {float(motion['kv'])} {float(motion['kx'])}",
            expect_contains="OK MOTION",
            timeout=2.0,
        )
        actions.append("motion")
    if _safe_float(setpoint.get("deg")) is not None:
        gateway.command(
            f"SETPOINT {float(setpoint['deg'])}",
            expect_contains="OK SETPOINT",
            timeout=2.0,
        )
        actions.append("setpoint")
    if all(
        _safe_float(limits.get(k)) is not None for k in ("out_max", "tip_deg", "i_max")
    ):
        gateway.command(
            f"LIMITS {float(limits['out_max'])} {float(limits['tip_deg'])} {float(limits['i_max'])}",
            expect_contains="OK LIMITS",
            timeout=2.0,
        )
        actions.append("limits")
    return {
        "ok": True,
        "snapshot_id": snap.get("snapshot_id"),
        "reverted": actions,
        "status": gateway.get_status(),
    }


def _read_csv_tail(path: pathlib.Path, max_tail: int = 80) -> Dict[str, Any]:
    total_lines = 0
    header = ""
    tail: "collections.deque[str]" = collections.deque(maxlen=max(1, max_tail))
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for idx, line in enumerate(f):
            txt = line.rstrip("\n")
            if idx == 0:
                header = txt
            else:
                tail.append(txt)
            total_lines += 1
    return {
        "path": str(path),
        "line_count": total_lines,
        "header": header,
        "tail_rows": list(tail),
    }


# HostCaptureManager moved to domains/tuning_intelligence/host_capture_manager.py


def _commissioning_ai_context(commissioning: CommissioningManager) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "status": commissioning.status(),
        "artifacts": commissioning.artifacts(),
    }

    latest_metrics = out["artifacts"].get("latest_metrics")
    if isinstance(latest_metrics, str) and latest_metrics:
        p = pathlib.Path(latest_metrics)
        try:
            out["latest_metrics_json"] = json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:
            out["latest_metrics_error"] = str(exc)

    latest_run = out["artifacts"].get("latest_run")
    if isinstance(latest_run, str) and latest_run:
        p = pathlib.Path(latest_run)
        try:
            out["latest_run_csv"] = _read_csv_tail(p, max_tail=80)
        except Exception as exc:
            out["latest_run_error"] = str(exc)

    return out


def _host_capture_ai_context(host_capture: HostCaptureManager) -> Dict[str, Any]:
    out: Dict[str, Any] = {"status": host_capture.status()}
    latest = out["status"].get("latest_run")
    if isinstance(latest, str) and latest:
        p = pathlib.Path(latest)
        if p.exists():
            try:
                out["latest_run_csv"] = _read_csv_tail(p, max_tail=80)
            except Exception as exc:
                out["latest_run_error"] = str(exc)
    return out


def _assistant_capabilities_context(*, allow_apply: bool) -> Dict[str, Any]:
    return {
        "can_read": [
            "cached_status",
            "control_state",
            "serial_health",
            "burst_status",
            "host_capture_latest_csv_tail",
            "commissioning_artifacts",
            "assistant_knowledge_pack",
            "config_snapshots",
        ],
        "can_apply_now": bool(allow_apply),
        "can_write": [
            "pid",
            "motion",
            "setpoint",
            "limits",
            "generate_unified_firmware_scaffold",
            "write_sketch_with_backup",
        ]
        if allow_apply
        else [],
        "confirm_first_for": [
            "arm/disarm",
            "cal_zero",
            "firmware_upload_or_flash",
            "power_state_changes",
        ],
    }


# AIProfileManager moved to domain module
# AssistantKnowledgeManager moved to domain module
# AgentMissionManager moved to domain module
_codexrules_cache: Dict[str, Any] = {"content": None, "mtime": 0.0}


def _load_codexrules(repo_root: pathlib.Path) -> str:
    """
    Load .codexrules from repo root if it exists.
    Caches content and reloads only if file modified.
    """
    global _codexrules_cache
    rules_path = repo_root / ".codexrules"
    if not rules_path.exists():
        return ""
    try:
        mtime = rules_path.stat().st_mtime
        if (
            _codexrules_cache["mtime"] == mtime
            and _codexrules_cache["content"] is not None
        ):
            return str(_codexrules_cache["content"])
        content = rules_path.read_text(encoding="utf-8").strip()
        _codexrules_cache = {"content": content, "mtime": mtime}
        logger.info(f"Loaded .codexrules ({len(content)} chars)")
        return content
    except Exception as e:
        logger.warning(f"Failed to load .codexrules: {e}")
        return ""


def _resolve_system_prompt(
    profile: Dict[str, Any],
    *,
    allow_apply: bool,
    repo_root: Optional[pathlib.Path] = None,
) -> str:
    """
    Build system prompt for Codex agent.

    Priority (later overrides earlier):
    1. .codexrules file (project-level rules, like .windsurfrules)
    2. Profile instructions (per-robot customization)
    3. Action policy block (apply permissions)
    """
    # Load project-level rules from .codexrules
    codexrules = ""
    if repo_root:
        codexrules = _load_codexrules(repo_root)

    # Fallback base prompt if no .codexrules exists
    if not codexrules:
        codexrules = (
            "You are Codex for UpRight.os, a robotics tuning copilot. "
            "Be concise, practical, and decisive. Never claim actions already executed unless tool output confirms it. "
            "Use plain English and short bullet points. Never output raw JSON to the user. "
            "Default behavior: if user asks for a concrete non-high-risk change, execute it now instead of asking repeated confirmations. "
            "Ask for confirmation only for high-risk actions: arm/disarm, cal-zero, firmware upload/flash, or power-state changes. "
            "Do not include routine precheck lists unless user asks for a checklist or action is high-risk. "
        )

    # Profile-specific instructions (per-robot customization)
    custom = str(profile.get("instructions", "") or "").strip()

    # Action policy block
    policy = profile.get("policy", {})
    policy_allow = (
        bool(policy.get("allow_auto_apply", True)) if isinstance(policy, dict) else True
    )
    can_apply = allow_apply and policy_allow
    if can_apply:
        action_block = (
            "If user asks to apply/modify now, include exactly one machine-readable line: "
            'UPRIGHT_APPLY_JSON:{"pid":{"kp":..,"ki":..,"kd":..},"motion":{"kv":..,"kx":..},'
            '"setpoint":{"deg":..},"limits":{"out_max":..,"tip_deg":..,"i_max":..},'
            '"unified":{"profile":{...},"sketch_name":"..."},'
            '"sketch":{"path":"/optional/path.ino","content":"...full file content..."}} '
            "using only keys you want changed. "
            "Use unified/sketch only when user explicitly asks to generate or edit firmware files. "
            "Then explain the result in plain English."
        )
    else:
        action_block = (
            "Do not request direct hardware actions; provide recommendations only."
        )

    response_contract = (
        "Response contract: "
        "1) Execute first for concrete requests unless the action is high-risk. "
        "2) Keep responses concise and directly actionable; expand only on request. "
        "3) Ask clarifying questions only when required parameters are missing for execution. "
        "4) Persist and reuse mission facts explicitly provided by user in prior turns (branch, target, guardrail, priority, board/IMU) until user changes them. "
        "Treat current_test_board_imu as test hardware, not automatically preferred production hardware; when discussing hardware architecture, provide alternatives with tradeoffs for voltage, motor size, performance, and planned features. "
        "Hardware recommendation policy: always adapt to the specific build and parts currently in use; do not assume fixed hardware across users. "
        "Default ranking objective: reliability > capability > control performance > safety > cost > dev speed. "
        "Prefer in-stock parts, but recommend a non-stock option when it is materially better and explain why. "
        "Limit options: if one option is clearly/calculably superior, present the winner first and keep alternatives minimal. "
        "Before proposing new parts, ask for key part/context clarifications if missing (motor voltage/current, driver, battery, constraints). "
        "Ask once early whether upgrade recommendations are desired, then keep hardware limitations visible during tuning without repeatedly asking for permission. "
        "Remember: assistant scope is broad (controls, math, EE, firmware/C++, diagnostics, physics), not only parts recommendation. "
        "5) For sketch generation/editing, avoid template lock-in: design to user requirements and explicitly state when template scaffolding was reused. "
        "6) Do not claim environment limitations unless a tool or endpoint in this turn failed with that exact limitation. "
        "7) Do not repeat generic caution clauses on routine generation/edit failures; include cautions only when user asks for safety checklist or action is high-risk. "
        "8) Avoid rigid 'reply exactly ...' wording unless the user explicitly requests strict parser-friendly output. "
        "Project facts: v1 telemetry readiness requires mode,ang,raw,out,kp,ki,kd,set plus one gyro alias (gyro|gyr|gx). "
        "All production sketches must implement FAULTCLR for Tune-page Clear Fault compatibility. "
        "v2 anti-drift readiness fields are gyro_bias, vel_meas, outer_loop_enabled. "
        "For this project, 'secure bridge link' means authenticated bridge API access with health check + valid bearer token + stable thread_id continuity."
    )

    return "\n\n".join(
        x for x in [codexrules, custom, action_block, response_contract] if x
    ).strip()


def _agent_mode_system_prompt(mode: str) -> str:
    base = (
        "You are the UpRight.os build-and-robot agent. "
        "Be concise, evidence-driven, and execution-first. "
        "Never claim execution unless present in provided tool/status evidence. "
        "Do not claim sandbox/read-only/environment limits unless a tool call in this turn failed with that exact error. "
        "Response format contract: always use markdown with these sections in order: "
        "## Summary, ## Findings, ## Evidence, ## Actions. "
        "Under Findings, use short bullets only. "
        "Under Evidence, include file references as inline code with optional :line. "
        "Under Actions, include numbered steps with concrete commands when possible. "
        "Avoid dense paragraphs longer than 3 lines. "
        "Do not emit raw citation tokens like [cite], □cite□, or JSON blobs."
    )
    if mode == "app_dev":
        return (
            f"{base} "
            "Primary mission: app and bridge development. "
            "Prioritize code changes, tests, compile/typecheck status, and concrete next edits. "
            "When giving suggestions, tie them to files, commands, and expected verification output. "
            "Use execute_shell proactively to inspect, build, test, and verify changes in this repository."
        )
    if mode == "ops_debug":
        return (
            f"{base} "
            "Primary mission: incident triage and ops troubleshooting. "
            "Prioritize root-cause from telemetry/logs, smallest safe recovery action, and verification checks."
        )
    return (
        f"{base} "
        "Primary mission: robot bring-up, firmware/test loops, tuning, and safe controls. "
        "Prioritize command/status contract, safety gates, and next best experiment."
    )


def _agent_model_allowed(model: str) -> bool:
    m = str(model or "").strip().lower()
    if not m:
        return False
    # Hard gate: agent runtime must use Codex-class models only.
    # This intentionally rejects non-Codex defaults.
    return "codex" in m


def _agent_mode_default_model(mode: str) -> str:
    mode_norm = str(mode or "").strip().lower()
    if mode_norm in {"app_dev", "robot_dev", "ops_debug"}:
        return "gpt-5-codex"
    return "gpt-5-codex"


def _agent_resolve_model(mode: str, resolved_model: str, *, prefer_codex: bool) -> str:
    candidate = str(resolved_model or "").strip()
    if prefer_codex:
        if _agent_model_allowed(candidate):
            return candidate
        return _agent_mode_default_model(mode)
    if candidate:
        return candidate
    return _agent_mode_default_model(mode)


def _agent_choose_executor(
    *,
    mode: str,
    enable_tools: bool,
    has_api_key: bool,
    codex_logged_in: bool,
    codex_agent_available: bool,
) -> Dict[str, Any]:
    mode_norm = str(mode or "").strip().lower()
    wants_tools = bool(enable_tools)
    policy = (
        os.environ.get("UPRIGHT_AGENT_EXECUTOR_POLICY", "codex_cli_only")
        .strip()
        .lower()
    )
    can_tools = bool(wants_tools and has_api_key and codex_agent_available)
    if can_tools:
        return {
            "executor": "openai_tools",
            "degraded": False,
            "degraded_reason": "",
            "can_execute": True,
        }

    if codex_logged_in:
        return {
            "executor": "codex_cli_exec",
            "degraded": wants_tools,
            "degraded_reason": (
                "tool_execution_unavailable_no_api_key" if wants_tools else ""
            ),
            "can_execute": True,
        }

    # Optional fallback policy; default is codex_cli_only to avoid runtime flapping
    # between providers and to keep behavior aligned with local Codex login UX.
    if has_api_key and policy in {"allow_openai_chat_fallback", "legacy"}:
        return {
            "executor": "openai_chat",
            "degraded": wants_tools,
            "degraded_reason": "tool_execution_unavailable_agent_backend"
            if wants_tools
            else "",
            "can_execute": True,
        }

    # Hard block App Dev when neither tool-capable key nor codex login exists.
    if mode_norm == "app_dev":
        return {
            "executor": "blocked",
            "degraded": True,
            "degraded_reason": "app_dev_requires_codex_login_or_api_key",
            "can_execute": False,
        }
    return {
        "executor": "blocked",
        "degraded": True,
        "degraded_reason": "codex_login_required",
        "can_execute": False,
    }


def _install_runtime_diagnostics() -> None:
    # Emit signal/uncaught-thread diagnostics to stderr so launcher logs show
    # why the bridge exited unexpectedly.
    try:
        faulthandler.enable(all_threads=True)
    except Exception:
        pass

    def _signal_handler(signum: int, frame: Any) -> None:
        try:
            signame = signal.Signals(signum).name
        except Exception:
            signame = str(signum)
        print(
            f"bridge terminating via signal: {signame} ({signum})",
            file=sys.stderr,
            flush=True,
        )
        if signum == signal.SIGINT:
            signal.default_int_handler(signum, frame)
        raise SystemExit(128 + int(signum))

    for sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
        try:
            signal.signal(sig, _signal_handler)
        except Exception:
            continue

    def _thread_excepthook(args: threading.ExceptHookArgs) -> None:
        print(
            f"uncaught thread exception in {getattr(args, 'thread', None)}:"
            f" {getattr(args, 'exc_type', None)}",
            file=sys.stderr,
            flush=True,
        )
        try:
            traceback.print_exception(args.exc_type, args.exc_value, args.exc_traceback)
        except Exception:
            pass

    try:
        threading.excepthook = _thread_excepthook
    except Exception:
        pass


def _codex_cli_login_status() -> Dict[str, Any]:
    return codex_cli_login_status()


def _legacy_execution_guard(path: str) -> Optional[Dict[str, Any]]:
    if legacy_execution_enabled():
        return None
    return legacy_execution_block_payload(path)


def _extract_mission_facts(history: List[Dict[str, Any]]) -> Dict[str, str]:
    """
    Extract durable mission facts from user turns.

    Supports explicit seeded forms such as:
      - "Store these mission facts exactly: branch=..., target=..., guardrail=..., priority=..."
      - "Store this extra fact: preferred robot board is Arduino Nano + MPU6050."
    """
    facts: Dict[str, str] = {}
    for item in history:
        if str(item.get("role", "")).strip().lower() != "user":
            continue
        txt = str(item.get("text", "")).strip()
        if not txt:
            continue
        low = txt.lower()

        if "store these mission facts exactly:" in low:
            _, tail = txt.split(":", 1)
            for part in tail.split(","):
                if "=" not in part:
                    continue
                k, v = part.split("=", 1)
                key = k.strip().lower()
                val = v.strip()
                if key in {"branch", "target", "guardrail", "priority"} and val:
                    facts[key] = val

        if "store this extra fact:" in low:
            _, tail = txt.split(":", 1)
            val = tail.strip().rstrip(".")
            if val:
                if (
                    ("for testing" in low)
                    or ("test board" in low)
                    or ("current board" in low)
                ):
                    facts["current_test_board_imu"] = val
                elif ("preferred" in low) or ("production" in low):
                    facts["preferred_board_imu"] = val
                else:
                    facts["board_imu"] = val

        # Runtime correction cues outside explicit "store ..." format.
        if ("preferred board is not" in low) or (
            "not preferred" in low and "board" in low
        ):
            facts["board_selection_policy"] = (
                "current board may be test-only; recommend alternatives by requirements."
            )
        if ("for testing" in low) and ("board" in low):
            facts["hardware_recommendation_mode"] = "proactive"

        if "rank hardware on" in low:
            facts["hardware_priority_order"] = (
                "reliability>capability>control_performance>safety>cost>dev_speed"
            )
        if "prefer parts in stock" in low:
            facts["prefer_in_stock"] = "true"
            facts["allow_better_non_stock"] = "true"
        if "no major constraints" in low:
            facts["constraints_mode"] = "exploratory"
        if "must at least ask for clarifications on parts" in low:
            facts["require_parts_clarification_before_new_reco"] = "true"
        if "ask at the beginning" in low and "better parts" in low:
            facts["hardware_upgrade_optin_once"] = "true"
        if (
            "not merely a parts reccomender" in low
            or "not merely a parts recommender" in low
        ):
            facts["assistant_role_scope"] = "full_stack_controls_mechatronics"

        if "when i say ide" in low or "by ide i mean" in low:
            if "in-app" in low or "in app" in low or "cli" in low:
                facts["ide_term_meaning"] = "in_app_cli"
            elif "arduino ide" in low or "external ide" in low or "external" in low:
                facts["ide_term_meaning"] = "external_ide"
        if "i meant cli" in low or "i mean cli" in low:
            facts["ide_term_meaning"] = "in_app_cli"
        if "i meant arduino ide" in low or "i mean arduino ide" in low:
            facts["ide_term_meaning"] = "external_ide"

        # Future features that should influence board/architecture choices.
        feature_terms = [
            ("latency", "latency"),
            ("processing speed", "processing_speed"),
            ("memory", "memory"),
            ("storage", "storage"),
            ("wireless connectivity", "wireless_connectivity"),
            ("on board logging", "onboard_logging"),
            ("ota updates", "ota_updates"),
            ("edge ai", "edge_ai"),
            ("steering", "steering"),
        ]
        found_features: list[str] = []
        for term, token in feature_terms:
            if term in low:
                found_features.append(token)
        if found_features:
            facts["future_feature_priorities"] = ",".join(found_features)

    return facts


def _first_sentence(text: str) -> str:
    s = " ".join(text.strip().split())
    if not s:
        return ""
    m = re.search(r"[.!?]", s)
    if not m:
        return s
    return s[: m.end()].strip()


def _truncate_words(text: str, limit: int) -> str:
    words = re.findall(r"\S+", text)
    if len(words) <= limit:
        return text
    return " ".join(words[:limit]).strip()


def _is_high_risk_user_request(user_msg: str) -> bool:
    low = user_msg.lower()
    risk_terms = (
        "flash",
        "upload",
        "guarded flash",
        "arm",
        "disarm",
        "estop",
        "e-stop",
        "cal-zero",
        "calibrate",
        "motor on",
        "enable motors",
        "power on",
    )
    return any(term in low for term in risk_terms)


def _strip_repetitive_caution_lines(user_msg: str, reply: str) -> str:
    if _is_high_risk_user_request(user_msg):
        return reply
    lines = reply.splitlines()
    out: list[str] = []
    for line in lines:
        low = line.strip().lower()
        if low.startswith("cautions:") or low.startswith("caution:"):
            continue
        out.append(line)
    # Collapse excessive blank lines introduced by removals.
    cleaned = "\n".join(out)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned


def _soften_forced_reply_exact(reply: str) -> str:
    # Keep guidance but remove rigid "reply exactly" phrasing that reads robotic.
    cleaned = re.sub(
        r"\(\s*reply exactly:\s*([^)]+)\)",
        r"(reply with: \1)",
        reply,
        flags=re.IGNORECASE,
    )
    return cleaned


def _normalize_reply_for_prompt(user_msg: str, reply: str) -> str:
    """
    Deterministic formatting normalizer for strict user prompt modes.
    Applies only when user explicitly requests a strict output form.
    """
    q = user_msg.lower()
    out = reply.strip()
    if not out:
        return out

    if "reply only: stored" in q:
        return "STORED."

    if "yes or no" in q or "answer only with yes or no" in q:
        up = out.upper()
        if "YES" in up:
            return "YES"
        if "NO" in up:
            return "NO"
        return "NO"

    if "one sentence" in q or "answer exactly" in q:
        one = _first_sentence(out)
        if not one:
            return out
        return _truncate_words(one, 30)

    out = _strip_repetitive_caution_lines(user_msg, out)
    # Preserve strict "reply exactly" when user explicitly asked for strict/exact output.
    if "reply exactly" not in q and "answer exactly" not in q:
        out = _soften_forced_reply_exact(out)

    return out


def _clean_default_sketch_path(
    repo_root: pathlib.Path, firmware: "FirmwareManager"
) -> str:
    env_override = str(os.environ.get("UPRIGHT_CLEAN_SKETCH", "")).strip()
    if env_override:
        return env_override
    # Clean lane must not inherit legacy firmware defaults from FirmwareManager.
    return str(
        repo_root / "app" / "bridge" / "firmware_templates" / "profiled_runtime_v1"
    )


def _clean_default_fqbn() -> str:
    return str(
        os.environ.get(
            "UPRIGHT_CLEAN_COMPILE_FQBN", "arduino:avr:nano:cpu=atmega328old"
        )
    )


def _clean_upload_target_meta(
    *, fqbn: str, firmware: "FirmwareManager"
) -> Dict[str, Any]:
    targets = firmware.list_targets()
    board_id = _board_id_for_fqbn(fqbn, targets) or "unknown"
    family = _family_for_fqbn(fqbn, targets) or "unknown"
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


def _clean_upload_target_runbook(target: Dict[str, Any]) -> Dict[str, Any]:
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


def _clean_upload_precheck_payload(
    *,
    gateway: NanoSerialGateway,
    firmware: FirmwareManager,
    requested_port: str,
    requested_fqbn: str,
    requested_sketch: str,
) -> Dict[str, Any]:
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
        # Informational for upload flows; guarded upload can still attempt recovery.
        reasons.append("bridge_disconnected")
    manifest_gate = firmware.validate_runtime_manifest(
        sketch=requested_sketch,
        require_exists=True,
    )
    if not bool(manifest_gate.get("ok", False)):
        reasons.append("runtime_manifest_invalid")
    runbook = _clean_upload_target_runbook(
        _clean_upload_target_meta(fqbn=requested_fqbn, firmware=firmware)
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


def _summarize_tool_failures(tool_calls: Any) -> str:
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


def _summarize_sketch_artifact_issues(tool_calls: Any) -> str:
    """Validate successful sketch tool outputs still point to non-empty on-disk files."""
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


def _needs_ide_disambiguation(
    user_msg: str, mission_facts: Optional[Dict[str, str]]
) -> bool:
    low = user_msg.lower()
    if "ide" not in low:
        return False
    facts = mission_facts or {}
    if str(facts.get("ide_term_meaning", "")).strip():
        return False
    asked = str(facts.get("ide_disambiguation_asked", "")).strip().lower()
    if asked in {"1", "true", "yes"}:
        return False
    return True


def _ide_disambiguation_reply() -> str:
    return (
        "Quick clarifier before I proceed: when you say IDE, do you mean "
        "the external Arduino IDE, or the in-app CLI workbench in UpRight.os?"
    )


def _hardware_context_board_label(hardware_context: Any) -> str:
    if not isinstance(hardware_context, dict):
        return "unknown board"
    board = hardware_context.get("board")
    if not isinstance(board, dict):
        return "unknown board"
    resolved = board.get("resolved_profile")
    if isinstance(resolved, dict):
        label = str(resolved.get("label", "")).strip()
        model = str(resolved.get("id", "")).strip()
        if label:
            return label
        if model:
            return model
    selected = str(board.get("selected_fqbn", "")).strip()
    return selected or "unknown board"


def _format_hardware_context_notice(hardware_context: Any, update_info: Any) -> str:
    if not isinstance(update_info, dict):
        return ""
    if not bool(update_info.get("accepted")):
        return ""
    if not bool(update_info.get("changed")):
        return ""
    board_label = _hardware_context_board_label(hardware_context)
    changed_keys = update_info.get("changed_keys")
    changed_txt = ""
    if isinstance(changed_keys, list):
        clean_keys = [str(k).strip() for k in changed_keys if str(k).strip()]
        if clean_keys:
            changed_txt = ", ".join(clean_keys[:5])
    if bool(update_info.get("initial")):
        return f"Hardware context synced: {board_label}. I will use this as the active build baseline."
    if changed_txt:
        return f"Hardware context updated ({board_label}). Changed fields: {changed_txt}. I will adapt guidance to the new parts map."
    return f"Hardware context updated ({board_label}). I will adapt guidance to the new parts map."


def _pin_range_for_family(family: str) -> tuple[int, int]:
    fam = str(family or "").strip().lower()
    if fam == "esp32":
        return (0, 39)
    if fam == "rp2040":
        return (0, 29)
    if fam == "teensy":
        return (0, 54)
    return (0, 21)  # arduino_avr default


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


def _manifest_required_field_present(token: str, available: set[str]) -> bool:
    raw = str(token or "").strip()
    if not raw:
        return False
    options = [part.strip() for part in raw.split("|") if part.strip()]
    if not options:
        return False
    return any(opt in available for opt in options)


def _family_for_fqbn(fqbn: str, targets: Dict[str, Any]) -> str:
    raw = str(fqbn or "").strip()
    for row in list(targets.get("boards") or []):
        if not isinstance(row, dict):
            continue
        base = str(row.get("fqbn_base", "")).strip()
        if not base:
            continue
        if raw == base or raw.startswith(f"{base}:"):
            return str(row.get("family", "")).strip()
    return ""


def _board_id_for_fqbn(fqbn: str, targets: Dict[str, Any]) -> str:
    raw = str(fqbn or "").strip()
    for row in list(targets.get("boards") or []):
        if not isinstance(row, dict):
            continue
        base = str(row.get("fqbn_base", "")).strip()
        if not base:
            continue
        if raw == base or raw.startswith(f"{base}:"):
            return str(row.get("id", "")).strip()
    return ""


def _runtime_manifest_profile_compatibility(
    *,
    manifest_validation: Dict[str, Any],
    active_profile: Optional[Dict[str, Any]],
    targets: Dict[str, Any],
) -> Dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    checks: Dict[str, Any] = {}

    if not bool(manifest_validation.get("ok", False)):
        errors.append("runtime_manifest_invalid")
        return {"ok": False, "errors": errors, "warnings": warnings, "checks": checks}

    manifest = manifest_validation.get("manifest")
    if not isinstance(manifest, dict):
        errors.append("runtime_manifest_missing")
        return {"ok": False, "errors": errors, "warnings": warnings, "checks": checks}

    if not isinstance(active_profile, dict):
        warnings.append("active_profile_missing")
        return {"ok": True, "errors": errors, "warnings": warnings, "checks": checks}

    profile_board = (
        active_profile.get("board")
        if isinstance(active_profile.get("board"), dict)
        else {}
    )
    profile_probe = (
        active_profile.get("probe")
        if isinstance(active_profile.get("probe"), dict)
        else {}
    )
    profile_compat = (
        profile_probe.get("compat")
        if isinstance(profile_probe.get("compat"), dict)
        else {}
    )

    manifest_board = (
        manifest.get("board") if isinstance(manifest.get("board"), dict) else {}
    )
    manifest_interfaces = (
        manifest.get("interfaces")
        if isinstance(manifest.get("interfaces"), dict)
        else {}
    )
    manifest_commands = {
        str(x).strip().upper()
        for x in list(manifest.get("commands") or [])
        if str(x).strip()
    }
    manifest_fields = {
        str(x).strip()
        for x in list(manifest.get("telemetry_fields") or [])
        if str(x).strip()
    }

    profile_fqbn = str(profile_board.get("fqbn", "")).strip()
    manifest_fqbn = str(manifest_board.get("fqbn", "")).strip()
    profile_board_id = _board_id_for_fqbn(profile_fqbn, targets) if profile_fqbn else ""
    manifest_board_id = (
        _board_id_for_fqbn(manifest_fqbn, targets) if manifest_fqbn else ""
    )
    strict_fqbn_mismatch = (
        profile_fqbn and manifest_fqbn and profile_fqbn != manifest_fqbn
    )
    if strict_fqbn_mismatch:
        # Bootloader/FQBN suffix differences are acceptable if they still resolve to same board id.
        if not (
            profile_board_id
            and manifest_board_id
            and profile_board_id == manifest_board_id
        ):
            errors.append("board_fqbn_mismatch")
    checks["board_fqbn"] = {
        "profile": profile_fqbn,
        "manifest": manifest_fqbn,
        "ok": "board_fqbn_mismatch" not in errors,
        "profile_board_id": profile_board_id,
        "manifest_board_id": manifest_board_id,
    }

    profile_family = _family_for_fqbn(profile_fqbn, targets) if profile_fqbn else ""
    manifest_family = str(manifest_board.get("family", "")).strip()
    if profile_family and manifest_family and profile_family != manifest_family:
        errors.append("board_family_mismatch")
    checks["board_family"] = {
        "profile": profile_family or "",
        "manifest": manifest_family or "",
        "ok": not (
            profile_family and manifest_family and profile_family != manifest_family
        ),
    }

    telemetry_node = (
        manifest.get("telemetry") if isinstance(manifest.get("telemetry"), dict) else {}
    )
    manifest_telemetry_mode = str(telemetry_node.get("mode", "")).strip().lower()
    profile_firmware = (
        active_profile.get("firmware")
        if isinstance(active_profile.get("firmware"), dict)
        else {}
    )
    profile_telemetry_mode = (
        str(
            profile_firmware.get("telemetry_mode")
            or profile_probe.get("telemetry_mode")
            or ""
        )
        .strip()
        .lower()
    )
    expected_family = profile_family or manifest_family or "arduino_avr"
    family_caps = _family_capabilities().get(expected_family, {})
    expected_mode = (
        profile_telemetry_mode
        or str(family_caps.get("default_telemetry_mode", "ascii_lowrate"))
        .strip()
        .lower()
    )
    if (
        manifest_telemetry_mode
        and expected_mode
        and manifest_telemetry_mode != expected_mode
    ):
        errors.append(
            "telemetry_mode_mismatch:"
            + f"profile={expected_mode},manifest={manifest_telemetry_mode}"
        )
    if not manifest_telemetry_mode:
        warnings.append("telemetry_mode_missing")
    checks["telemetry_mode"] = {
        "profile": expected_mode,
        "manifest": manifest_telemetry_mode,
        "ok": not any(str(e).startswith("telemetry_mode_mismatch:") for e in errors),
    }

    profile_commands = [
        str(x).strip().upper()
        for x in list(profile_probe.get("commands") or [])
        if str(x).strip()
    ]
    core_required_commands = ["GET", "ARM", "DISARM", "PID", "SETPOINT"]
    missing_core = [
        cmd for cmd in core_required_commands if cmd not in manifest_commands
    ]
    if missing_core:
        errors.append("commands_mismatch:" + ",".join(missing_core[:8]))
    optional_missing = [
        cmd
        for cmd in profile_commands
        if cmd not in manifest_commands and cmd not in core_required_commands
    ]
    if optional_missing:
        warnings.append("commands_optional_missing:" + ",".join(optional_missing[:8]))
    checks["commands"] = {
        "required_core": core_required_commands,
        "profile_observed": profile_commands,
        "missing_core": missing_core,
        "missing_optional": optional_missing,
        "ok": len(missing_core) == 0,
    }

    required_fields = [
        str(x).strip()
        for x in list(profile_compat.get("required_fields") or [])
        if str(x).strip()
    ]
    if not required_fields:
        required_fields = ["mode", "ang", "raw", "gyro|gyr|gx", "out", "set"]
    missing_fields = [
        token
        for token in required_fields
        if not _manifest_required_field_present(token, manifest_fields)
    ]
    if missing_fields:
        errors.append("telemetry_mismatch:" + ",".join(missing_fields[:8]))
    checks["telemetry_fields"] = {
        "required": required_fields,
        "missing": missing_fields,
        "ok": len(missing_fields) == 0,
    }

    manifest_imu_protocol = (
        str(
            (
                (
                    manifest_interfaces.get("imu")
                    if isinstance(manifest_interfaces.get("imu"), dict)
                    else {}
                )
                or {}
            ).get("protocol", "")
        )
        .strip()
        .lower()
    )
    manifest_encoder_protocol = (
        str(
            (
                (
                    manifest_interfaces.get("encoders")
                    if isinstance(manifest_interfaces.get("encoders"), dict)
                    else {}
                )
                or {}
            ).get("protocol", "")
        )
        .strip()
        .lower()
    )
    manifest_actuator_protocol = (
        str(
            (
                (
                    manifest_interfaces.get("actuator")
                    if isinstance(manifest_interfaces.get("actuator"), dict)
                    else {}
                )
                or {}
            ).get("protocol", "")
        )
        .strip()
        .lower()
    )

    profile_parts = (
        active_profile.get("parts")
        if isinstance(active_profile.get("parts"), dict)
        else {}
    )
    profile_pinmap = (
        active_profile.get("pinmap")
        if isinstance(active_profile.get("pinmap"), dict)
        else {}
    )
    profile_imu_bus = (
        profile_pinmap.get("imu_bus")
        if isinstance(profile_pinmap.get("imu_bus"), dict)
        else {}
    )
    profile_enc_map = (
        profile_pinmap.get("encoders")
        if isinstance(profile_pinmap.get("encoders"), dict)
        else {}
    )
    profile_motor_map = (
        profile_pinmap.get("motor")
        if isinstance(profile_pinmap.get("motor"), dict)
        else {}
    )
    profile_imu = (
        profile_parts.get("imu") if isinstance(profile_parts.get("imu"), dict) else {}
    )
    profile_enc = (
        profile_parts.get("encoders")
        if isinstance(profile_parts.get("encoders"), dict)
        else {}
    )
    profile_act = (
        profile_parts.get("motor_driver")
        if isinstance(profile_parts.get("motor_driver"), dict)
        else {}
    )

    profile_imu_protocol = (
        str(
            profile_imu_bus.get("protocol")
            or profile_imu_bus.get("type")
            or profile_imu.get("protocol")
            or ""
        )
        .strip()
        .lower()
    )
    profile_encoder_protocol = (
        str(profile_enc_map.get("protocol") or profile_enc.get("protocol") or "")
        .strip()
        .lower()
    )
    profile_actuator_protocol = (
        str(profile_motor_map.get("protocol") or profile_act.get("protocol") or "")
        .strip()
        .lower()
    )

    protocol_mismatches: list[str] = []
    if (
        profile_imu_protocol
        and manifest_imu_protocol
        and profile_imu_protocol != manifest_imu_protocol
    ):
        protocol_mismatches.append(
            f"imu:{profile_imu_protocol}->{manifest_imu_protocol}"
        )
    if (
        profile_encoder_protocol
        and manifest_encoder_protocol
        and profile_encoder_protocol != manifest_encoder_protocol
    ):
        protocol_mismatches.append(
            f"encoders:{profile_encoder_protocol}->{manifest_encoder_protocol}"
        )
    if (
        profile_actuator_protocol
        and manifest_actuator_protocol
        and profile_actuator_protocol != manifest_actuator_protocol
    ):
        protocol_mismatches.append(
            f"actuator:{profile_actuator_protocol}->{manifest_actuator_protocol}"
        )
    if protocol_mismatches:
        warnings.append("protocol_mismatch:" + ",".join(protocol_mismatches))
    checks["protocols"] = {
        "profile": {
            "imu": profile_imu_protocol,
            "encoders": profile_encoder_protocol,
            "actuator": profile_actuator_protocol,
        },
        "manifest": {
            "imu": manifest_imu_protocol,
            "encoders": manifest_encoder_protocol,
            "actuator": manifest_actuator_protocol,
        },
        "mismatches": protocol_mismatches,
        "ok": len(protocol_mismatches) == 0,
    }

    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "checks": checks,
    }


def _build_hardware_registry(targets: Dict[str, Any]) -> Dict[str, Any]:
    family_capabilities = _family_capabilities()
    protocol_schema = _protocol_schema()
    telemetry_core_fields = [
        "mode",
        "ang",
        "raw",
        "gyro|gyr|gx",
        "out",
        "fault",
        "estop",
    ]
    board_rows = []
    for row in list(targets.get("boards") or []):
        if not isinstance(row, dict):
            continue
        family = str(row.get("family", "")).strip() or "unknown"
        caps = family_capabilities.get(family, {})
        board_rows.append(
            {
                "id": str(row.get("id", "")).strip(),
                "label": str(row.get("label", "")).strip(),
                "family": family,
                "fqbn_base": str(row.get("fqbn_base", "")).strip(),
                "default_bootloader": str(row.get("default_bootloader", "")).strip(),
                "bootloaders": list(row.get("bootloaders") or []),
                "capabilities": {
                    "default_telemetry_hz": int(caps.get("default_telemetry_hz", 200)),
                    "default_telemetry_mode": str(
                        caps.get("default_telemetry_mode", "ascii_lowrate")
                    ),
                    "telemetry_modes": list(
                        caps.get("telemetry_modes") or ["ascii_lowrate"]
                    ),
                    "imu_protocols": list(caps.get("imu_protocols") or []),
                    "encoder_protocols": list(caps.get("encoder_protocols") or []),
                    "actuator_protocols": list(caps.get("actuator_protocols") or []),
                    "actuator_classes": list(caps.get("actuator_classes") or []),
                },
                "required_runtime_fields": list(telemetry_core_fields),
            }
        )

    return {
        "ok": True,
        "version": 1,
        "families": list(targets.get("families") or []),
        "boards": board_rows,
        "sensors": [
            {
                "id": "imu_mpu6050",
                "label": "MPU6050 IMU",
                "class": "imu",
                "supported_protocols": ["i2c"],
                "required_signals": ["accel", "gyro"],
                "typical_output_fields": ["ang", "raw", "gyro"],
            },
            {
                "id": "imu_bno085",
                "label": "BNO085/BNO080 IMU",
                "class": "imu",
                "supported_protocols": ["i2c", "uart", "spi"],
                "required_signals": ["quat|euler", "gyro"],
                "typical_output_fields": ["ang", "gyro"],
            },
            {
                "id": "enc_quadrature",
                "label": "Quadrature Encoder",
                "class": "encoder",
                "supported_protocols": ["quadrature"],
                "required_signals": ["A", "B"],
                "typical_output_fields": ["encL", "encR", "wpos", "wspd"],
            },
            {
                "id": "enc_hall",
                "label": "Hall Encoder",
                "class": "encoder",
                "supported_protocols": ["hall"],
                "required_signals": ["pulse"],
                "typical_output_fields": ["encL", "encR", "wpos", "wspd"],
            },
            {
                "id": "enc_spi_abs",
                "label": "SPI Absolute Encoder",
                "class": "encoder",
                "supported_protocols": ["spi"],
                "required_signals": ["angle"],
                "typical_output_fields": ["wpos", "wspd"],
            },
        ],
        "actuators": [
            {
                "id": "dual_dc_hbridge_pwm",
                "label": "Dual DC H-Bridge (PWM)",
                "class": "motor_driver",
                "required_channels": ["left_pwm", "right_pwm"],
            },
            {
                "id": "dual_dc_hbridge_dir_pwm",
                "label": "Dual DC H-Bridge (DIR+PWM)",
                "class": "motor_driver",
                "required_channels": ["left_dir", "left_pwm", "right_dir", "right_pwm"],
            },
            {
                "id": "bldc_foc",
                "label": "BLDC FOC Driver",
                "class": "motor_driver",
                "required_channels": ["left_phase", "right_phase"],
            },
        ],
        "profile_schema": {
            "required_profile_fields": [
                "profile_id",
                "label",
                "board",
                "parts",
                "pinmap",
            ],
            "required_board_fields": ["fqbn", "port"],
            "required_parts_fields": ["imu", "encoders", "motor_driver"],
            "required_pinmap_fields": ["imu_bus", "motor", "encoders"],
            "required_runtime_commands": ["GET", "ARM", "DISARM", "PID", "SETPOINT"],
            "required_runtime_telemetry": list(telemetry_core_fields),
            "optional_profile_fields": ["mcu_topology", "firmware.telemetry_mode"],
            "mcu_topology_schema": {
                "required_when_present": ["control_mcu"],
                "control_mcu_required_fields": ["id"],
                "io_mcu_required_fields_when_present": ["id"],
                "optional_fields": ["io_mcu", "link", "command_namespaces"],
                "recommended_remote_control_namespace_suffix": "_",
            },
        },
        "protocol_schema": protocol_schema,
        "templates": [
            {
                "id": "nano_balancer_v1",
                "label": "Nano Balancer Baseline",
                "board_family": "arduino_avr",
                "sensor_ids": ["imu_mpu6050", "enc_quadrature"],
                "actuator_ids": ["dual_dc_hbridge_dir_pwm"],
            },
            {
                "id": "teensy_balancer_v1",
                "label": "Teensy Performance Balancer",
                "board_family": "teensy",
                "sensor_ids": ["imu_bno085", "enc_spi_abs"],
                "actuator_ids": ["bldc_foc"],
                "reference_firmware_template": "app/bridge/firmware_templates/teensy41_reference_v1/teensy41_reference_v1.ino",
                "reference_runtime_manifest": "app/bridge/firmware_templates/teensy41_reference_v1/runtime_manifest_v1.json",
            },
            {
                "id": "esp32_balancer_v1",
                "label": "ESP32 Balancer",
                "board_family": "esp32",
                "sensor_ids": ["imu_mpu6050", "enc_quadrature"],
                "actuator_ids": ["dual_dc_hbridge_pwm"],
            },
        ],
    }


# RobotProfilesManager moved to domain module
# TelemetryHub moved to domain module
def _json(handler: BaseHTTPRequestHandler, code: int, body: Dict[str, Any]) -> None:
    payload = json.dumps(body).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(payload)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header(
        "Access-Control-Allow-Headers", "Content-Type, Authorization, X-Session-Token"
    )
    handler.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
    handler.end_headers()
    handler.wfile.write(payload)


def _read_json(handler: BaseHTTPRequestHandler) -> Dict[str, Any]:
    n = int(handler.headers.get("Content-Length", "0"))
    if n <= 0:
        return {}
    raw = handler.rfile.read(n)
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


def _extract_auth_token(
    handler: BaseHTTPRequestHandler, body: Optional[Dict[str, Any]] = None
) -> Optional[str]:
    auth_header = handler.headers.get("Authorization", "").strip()
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip() or None
    x_token = handler.headers.get("X-Session-Token", "").strip()
    if x_token:
        return x_token
    if body:
        tok = str(body.get("session_token", "")).strip()
        if tok:
            return tok
    return None


# AuthManager moved to domain module
def _normalize_cmd(cmd: str) -> str:
    return " ".join(cmd.strip().split()).upper()


def _blocked_while_latched(cmd: str) -> bool:
    c = _normalize_cmd(cmd)
    safe_prefixes = ("GET", "DISARM", "HELP", "LOGCSV", "LOGT")
    return not c.startswith(safe_prefixes)


def _classify_imu_command_result(
    res: Dict[str, Any], *, cmd_name: str
) -> Dict[str, Any]:
    lines = list(res.get("lines", [])) if isinstance(res, dict) else []
    matched = str(res.get("matched", "")) if isinstance(res, dict) else ""
    candidates: list[str] = []
    if matched:
        candidates.append(matched)
    candidates.extend(reversed(lines))
    imu_line = ""
    for ln in candidates:
        txt = str(ln or "").strip()
        if "IMU" in txt.upper():
            imu_line = txt
            break
    if not imu_line:
        return {
            "ok": False,
            "error": f"imu_{cmd_name.lower()}_no_response",
            "detail": "",
        }

    up = imu_line.upper()
    if up.startswith("OK IMU_"):
        return {"ok": True, "error": "", "detail": imu_line}
    if "ERR UNKNOWN" in up and "IMU" in up:
        return {
            "ok": False,
            "error": "imu_command_unsupported:flash_runtime_with_imu_calibration_support",
            "detail": imu_line,
        }
    if "EEPROM_UNAVAILABLE" in up:
        return {
            "ok": False,
            "error": "imu_eeprom_unavailable",
            "detail": imu_line,
        }
    if "IMU_NOT_READY" in up:
        return {"ok": False, "error": "imu_not_ready", "detail": imu_line}
    return {
        "ok": False,
        "error": f"imu_{cmd_name.lower()}_failed",
        "detail": imu_line,
    }


TUNING_BAL_BOUNDS = {
    "kp": 1.0,
    "ki": 0.05,
    "kd": 0.2,
    "kv": 0.05,
    "kx": 0.002,
    "setpoint": 0.5,
    "out_max": 20.0,
    "i_max": 20.0,
}

TUNING_PREFLIGHT_DELTA = {
    "pid": {"kp": 0.8, "ki": 0.03, "kd": 0.12},
    "motion": {"kv": 0.03, "kx": 0.001},
    "setpoint": {"deg": 0.35},
    "limits": {"out_max": 8.0, "tip_deg": 2.0, "i_max": 8.0},
}

HUD_CANONICAL_FIELDS = ("mode", "ang", "raw", "gyro", "out", "fault", "estop")

RUNTIME_TELEMETRY_ADAPTERS: Dict[str, Dict[str, Any]] = {
    "generic_v1": {
        "label": "Generic Runtime Adapter",
        "signature_keys": [],
        "aliases": {
            "mode": ["mode", "state", "run_mode", "fsm_state"],
            "ang": ["ang", "angle", "pitch", "theta", "tilt", "angle_deg"],
            "raw": ["raw", "accel_angle", "pitch_raw", "theta_raw", "accel_tilt"],
            "gyro": ["gyro", "gyr", "gx", "gyro_rate", "gyro_z", "omega", "wz"],
            "out": ["out", "motor_out", "pwm", "pwm_out", "u_cmd", "torque_cmd"],
            "fault": ["fault", "fault_code", "err", "error", "overrun"],
            "estop": ["estop", "e_stop", "estop_latched", "kill", "estop_state"],
        },
    },
    "arduino_balance_v1": {
        "label": "Arduino Balance Adapter",
        "signature_keys": ["ang", "raw", "out"],
        "aliases": {},
    },
    "teensy_balance_v1": {
        "label": "Teensy Balance Adapter",
        "signature_keys": ["angle", "gyro_rate", "motor_out"],
        "aliases": {
            "ang": ["angle", "angle_deg", "pitch"],
            "raw": ["accel_angle", "pitch_raw"],
            "gyro": ["gyro_rate", "gyro_z", "omega"],
            "out": ["motor_out", "u_cmd"],
            "mode": ["state", "run_mode"],
            "fault": ["fault_code", "fault"],
            "estop": ["estop_latched", "estop"],
        },
    },
    "esp32_balance_v1": {
        "label": "ESP32 Balance Adapter",
        "signature_keys": ["theta", "omega", "u_cmd"],
        "aliases": {
            "ang": ["theta", "angle", "pitch"],
            "raw": ["theta_raw", "accel_angle"],
            "gyro": ["omega", "gyro_z", "gyro"],
            "out": ["u_cmd", "motor_out", "pwm_out"],
            "mode": ["state", "mode"],
            "fault": ["fault", "error"],
            "estop": ["kill", "estop"],
        },
    },
    "rp2040_balance_v1": {
        "label": "RP2040 Balance Adapter",
        "signature_keys": ["pitch", "gyro_z", "pwm_out"],
        "aliases": {
            "ang": ["pitch", "angle"],
            "raw": ["pitch_raw", "raw"],
            "gyro": ["gyro_z", "gyr", "gyro"],
            "out": ["pwm_out", "motor_out"],
            "mode": ["fsm_state", "mode"],
            "fault": ["fault", "overrun"],
            "estop": ["estop_state", "estop"],
        },
    },
}


def _choose_runtime_adapter(status: Dict[str, Any]) -> str:
    if not isinstance(status, dict) or not status:
        return "generic_v1"
    best_id = "generic_v1"
    best_score = -1
    for adapter_id, node in RUNTIME_TELEMETRY_ADAPTERS.items():
        if adapter_id == "generic_v1":
            continue
        signatures = [str(k) for k in list(node.get("signature_keys") or []) if str(k)]
        if not signatures:
            continue
        score = sum(1 for key in signatures if key in status)
        if score > best_score:
            best_score = score
            best_id = adapter_id
    if best_score <= 0:
        return "generic_v1"
    return best_id


def _normalize_status_for_hud(
    status: Dict[str, Any], *, adapter_hint: Optional[str] = None
) -> Dict[str, Any]:
    if not isinstance(status, dict):
        return {
            "status": {},
            "adapter": {
                "id": "generic_v1",
                "label": RUNTIME_TELEMETRY_ADAPTERS["generic_v1"]["label"],
                "mapped_fields": {},
                "missing_canonical_fields": list(HUD_CANONICAL_FIELDS),
                "source_keys": [],
            },
        }

    raw = dict(status)
    adapter_id = (
        adapter_hint
        if adapter_hint in RUNTIME_TELEMETRY_ADAPTERS
        else _choose_runtime_adapter(raw)
    )
    adapter = RUNTIME_TELEMETRY_ADAPTERS.get(
        adapter_id, RUNTIME_TELEMETRY_ADAPTERS["generic_v1"]
    )
    generic_aliases = dict(RUNTIME_TELEMETRY_ADAPTERS["generic_v1"].get("aliases", {}))
    adapter_aliases = dict(adapter.get("aliases", {}))

    normalized = dict(raw)
    mapped_fields: Dict[str, str] = {}
    missing: list[str] = []
    for field in HUD_CANONICAL_FIELDS:
        if field in normalized:
            continue
        search_order = list(adapter_aliases.get(field, [])) + list(
            generic_aliases.get(field, [])
        )
        seen: set[str] = set()
        for alias in search_order:
            key = str(alias).strip()
            if not key or key in seen:
                continue
            seen.add(key)
            if key in raw:
                normalized[field] = raw[key]
                mapped_fields[field] = key
                break
        if field not in normalized:
            missing.append(field)

    return {
        "status": normalized,
        "adapter": {
            "id": adapter_id,
            "label": str(adapter.get("label", adapter_id)),
            "mapped_fields": mapped_fields,
            "missing_canonical_fields": missing,
            "source_keys": sorted([str(k) for k in raw.keys()]),
        },
    }


def _status_float(status: Dict[str, Any], *keys: str, default: float = 0.0) -> float:
    for key in keys:
        if key in status:
            try:
                return float(status[key])
            except Exception:
                continue
    return default


def _require_tuning_range(name: str, value: float, lo: float, hi: float) -> None:
    if not (lo <= value <= hi):
        raise RuntimeError(f"invalid_tuning_value:{name}:{value}")


def _guard_pid_apply(
    status_before: Dict[str, Any], kp: float, ki: float, kd: float
) -> None:
    _require_tuning_range("kp", kp, 0.0, 400.0)
    _require_tuning_range("ki", ki, 0.0, 5.0)
    _require_tuning_range("kd", kd, 0.0, 50.0)
    if str(status_before.get("mode", "")) == "BALANCING":
        curr_kp = _status_float(status_before, "kp", default=31.0)
        curr_ki = _status_float(status_before, "ki", default=0.05)
        curr_kd = _status_float(status_before, "kd", default=1.05)
        if (
            abs(kp - curr_kp) > TUNING_BAL_BOUNDS["kp"]
            or abs(ki - curr_ki) > TUNING_BAL_BOUNDS["ki"]
            or abs(kd - curr_kd) > TUNING_BAL_BOUNDS["kd"]
        ):
            raise RuntimeError("tuning_delta_too_large_while_balancing")


def _guard_motion_apply(status_before: Dict[str, Any], kv: float, kx: float) -> None:
    _require_tuning_range("kv", kv, -5.0, 5.0)
    _require_tuning_range("kx", kx, -1.0, 1.0)
    if str(status_before.get("mode", "")) == "BALANCING":
        curr_kv = _status_float(status_before, "kv", default=0.0)
        curr_kx = _status_float(status_before, "kx", default=0.0)
        if (
            abs(kv - curr_kv) > TUNING_BAL_BOUNDS["kv"]
            or abs(kx - curr_kx) > TUNING_BAL_BOUNDS["kx"]
        ):
            raise RuntimeError("tuning_delta_too_large_while_balancing")


def _guard_setpoint_apply(status_before: Dict[str, Any], deg: float) -> None:
    _require_tuning_range("setpoint", deg, -30.0, 30.0)
    if str(status_before.get("mode", "")) == "BALANCING":
        curr_set = _status_float(status_before, "set", default=0.0)
        if abs(deg - curr_set) > TUNING_BAL_BOUNDS["setpoint"]:
            raise RuntimeError("tuning_delta_too_large_while_balancing")


def _guard_limits_apply(
    status_before: Dict[str, Any], out_max: float, tip_deg: float, i_max: float
) -> None:
    _require_tuning_range("out_max", out_max, 1.0, 255.0)
    _require_tuning_range("tip_deg", tip_deg, 1.0, 85.0)
    _require_tuning_range("i_max", i_max, 0.0, 400.0)
    if str(status_before.get("mode", "")) == "BALANCING":
        curr_out = _status_float(status_before, "outMax", "out_max", default=180.0)
        curr_i = _status_float(status_before, "iMax", "i_max", default=70.0)
        if (
            abs(out_max - curr_out) > TUNING_BAL_BOUNDS["out_max"]
            or abs(i_max - curr_i) > TUNING_BAL_BOUNDS["i_max"]
        ):
            raise RuntimeError("tuning_delta_too_large_while_balancing")


def _detect_tuning_capabilities(
    status: Dict[str, Any], supported_commands: list[str], help_lines: list[str]
) -> Dict[str, Any]:
    cmds = set(supported_commands or [])
    blob = "\n".join(help_lines or []).upper()
    has_lpf_cmd = any(tok in blob for tok in ("LPF", "LOWPASS", "FILTER", "CUTOFF"))
    has_condint_cmd = any(
        tok in blob
        for tok in ("CONDINT", "ANTIWINDUP", "ANTI-WINDUP", "INTEGRATOR MODE")
    )

    capabilities = {
        "pid": {"runtime_apply_supported": "PID" in cmds, "source": "help"},
        "motion": {"runtime_apply_supported": "MOTION" in cmds, "source": "help"},
        "setpoint": {"runtime_apply_supported": "SETPOINT" in cmds, "source": "help"},
        "limits": {"runtime_apply_supported": "LIMITS" in cmds, "source": "help"},
        "lowpass_cutoff_hz": {
            "runtime_apply_supported": has_lpf_cmd,
            "source": "help",
            "command_candidates": ["LPF", "LOWPASS", "FILTER"],
        },
        "conditional_integration": {
            "runtime_apply_supported": has_condint_cmd,
            "source": "help",
            "command_candidates": ["CONDINT", "ANTIWINDUP"],
        },
    }
    capabilities["status_keys"] = sorted(
        [
            k
            for k in status.keys()
            if k in {"kp", "ki", "kd", "kv", "kx", "set", "outMax", "iMax", "tipDeg"}
        ]
    )
    return capabilities


def _validate_tuning_recommendation_contract(rec: Dict[str, Any]) -> list[str]:
    errs: list[str] = []
    if not isinstance(rec, dict):
        return ["recommendation_not_object"]
    required = {
        "ok",
        "score_pct",
        "readiness",
        "recommendations",
        "procedure",
        "variables_available",
    }
    missing = sorted(required - set(rec.keys()))
    if missing:
        errs.append(f"missing:{','.join(missing)}")
    if not isinstance(rec.get("recommendations", []), list):
        errs.append("recommendations_not_list")
    if not isinstance(rec.get("procedure", []), list):
        errs.append("procedure_not_list")
    if not isinstance(rec.get("variables_available", {}), dict):
        errs.append("variables_available_not_object")
    try:
        score = int(rec.get("score_pct", 0))
        if score < 0 or score > 100:
            errs.append("score_out_of_range")
    except Exception:
        errs.append("score_not_int")
    if rec.get("readiness") not in {"good", "watch", "risky"}:
        errs.append("readiness_invalid")
    return errs


def _evaluate_tuning_recommendation_quality(
    *,
    recommendation: Dict[str, Any],
    telemetry: Dict[str, Any],
    trace_paths: list[pathlib.Path],
    replay_reports: list[Dict[str, Any]],
    surrogate_report: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    telemetry_map = telemetry if isinstance(telemetry, dict) else {}
    rec_map = recommendation if isinstance(recommendation, dict) else {}
    replay_rows = replay_reports if isinstance(replay_reports, list) else []
    trace_rows = trace_paths if isinstance(trace_paths, list) else []
    surrogate_map = surrogate_report if isinstance(surrogate_report, dict) else {}

    dims: Dict[str, Dict[str, Any]] = {
        "completeness": {"ok": True, "reasons": []},
        "confidence": {"ok": True, "reasons": []},
        "actionability": {"ok": True, "reasons": []},
    }

    def add_reason(dim: str, reason: str) -> None:
        node = dims.get(dim)
        if not isinstance(node, dict):
            return
        bucket = node.get("reasons")
        if not isinstance(bucket, list):
            bucket = []
            node["reasons"] = bucket
        if reason not in bucket:
            bucket.append(reason)
        node["ok"] = False

    # Completeness: require core telemetry keys and at least one replay trace.
    required_telemetry = [
        "angle_variance",
        "output_saturation_pct",
        "oscillation_detected",
        "oscillation_freq_hz",
    ]
    missing_telemetry = [k for k in required_telemetry if k not in telemetry_map]
    if missing_telemetry:
        add_reason(
            "completeness",
            "telemetry_fields_missing:" + ",".join(missing_telemetry[:8]),
        )
    if not trace_rows:
        add_reason("completeness", "evidence_missing_trace_paths")

    # Confidence: ensure recommendation score and evidence quality are sufficient.
    try:
        rec_score = int(rec_map.get("score_pct", 0))
    except Exception:
        rec_score = 0
    if rec_score < 60:
        add_reason("confidence", "recommendation_score_low")

    replay_fail_count = sum(
        1
        for rep in replay_rows
        if not bool(
            ((rep.get("result") or {}) if isinstance(rep, dict) else {}).get(
                "pass", False
            )
        )
    )
    if replay_fail_count > 0:
        add_reason("confidence", f"replay_failures:{replay_fail_count}")

    if surrogate_map:
        if bool(surrogate_map.get("ok", False)):
            sim = (
                surrogate_map.get("simulation")
                if isinstance(surrogate_map.get("simulation"), dict)
                else {}
            )
            sim_metrics = (
                sim.get("metrics") if isinstance(sim.get("metrics"), dict) else {}
            )
            if bool(sim_metrics.get("faceplant", False)):
                add_reason("confidence", "surrogate_faceplant_risk")
            model = (
                surrogate_map.get("model")
                if isinstance(surrogate_map.get("model"), dict)
                else {}
            )
            try:
                model_conf = float(model.get("confidence", 0.0) or 0.0)
            except Exception:
                model_conf = 0.0
            if model_conf < 0.35:
                add_reason("confidence", "surrogate_confidence_low")
        else:
            if trace_rows:
                add_reason("confidence", "surrogate_unavailable")

    # Actionability: recommendation and procedure should be directly executable.
    rec_items = rec_map.get("recommendations")
    if not isinstance(rec_items, list) or not rec_items:
        add_reason("actionability", "recommendations_missing")
    else:
        actionable_count = 0
        for row in rec_items:
            if not isinstance(row, dict):
                continue
            action = str(row.get("action", "")).strip()
            rationale = str(row.get("rationale", "")).strip()
            if action and rationale:
                actionable_count += 1
        if actionable_count == 0:
            add_reason("actionability", "recommendations_not_actionable")

    procedure = rec_map.get("procedure")
    if not isinstance(procedure, list) or len(procedure) < 3:
        add_reason("actionability", "procedure_incomplete")

    variables = rec_map.get("variables_available")
    if not isinstance(variables, dict) or not variables:
        add_reason("actionability", "variables_available_missing")

    reasons: list[str] = []
    for dim in ("completeness", "confidence", "actionability"):
        node = dims.get(dim) or {}
        for reason in list(node.get("reasons") or []):
            s = str(reason).strip()
            if s and s not in reasons:
                reasons.append(s)

    gate_ok = len(reasons) == 0
    return {
        "gate_ok": gate_ok,
        "reasons": reasons,
        "dimensions": dims,
        "evidence": {
            "trace_count": len(trace_rows),
            "replay_count": len(replay_rows),
            "replay_fail_count": replay_fail_count,
            "surrogate_ok": bool(surrogate_map.get("ok", False))
            if surrogate_map
            else False,
            "recommendation_score_pct": rec_score,
        },
    }


def _build_tuning_apply_signature(family: str, target: Dict[str, Any]) -> str:
    canonical = json.dumps(
        {"family": family, "target": target},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# TuningPreflightStore moved to domain module
def _requires_preflight(
    *,
    family: str,
    status_before: Dict[str, Any],
    current: Dict[str, float],
    target: Dict[str, float],
) -> bool:
    mode = str(status_before.get("mode", ""))
    if mode in {"ARMED", "BALANCING"}:
        return True

    if family == "pid":
        d = TUNING_PREFLIGHT_DELTA["pid"]
        return (
            abs(target["kp"] - current["kp"]) > d["kp"]
            or abs(target["ki"] - current["ki"]) > d["ki"]
            or abs(target["kd"] - current["kd"]) > d["kd"]
        )
    if family == "motion":
        d = TUNING_PREFLIGHT_DELTA["motion"]
        return (
            abs(target["kv"] - current["kv"]) > d["kv"]
            or abs(target["kx"] - current["kx"]) > d["kx"]
        )
    if family == "setpoint":
        return (
            abs(target["deg"] - current["deg"])
            > TUNING_PREFLIGHT_DELTA["setpoint"]["deg"]
        )
    if family == "limits":
        d = TUNING_PREFLIGHT_DELTA["limits"]
        return (
            abs(target["out_max"] - current["out_max"]) > d["out_max"]
            or abs(target["tip_deg"] - current["tip_deg"]) > d["tip_deg"]
            or abs(target["i_max"] - current["i_max"]) > d["i_max"]
        )
    return False


def _enforce_preflight_if_needed(
    *,
    preflight_store: TuningPreflightStore,
    body: Dict[str, Any],
    family: str,
    status_before: Dict[str, Any],
    current: Dict[str, float],
    target: Dict[str, float],
) -> Optional[str]:
    if not _requires_preflight(
        family=family, status_before=status_before, current=current, target=target
    ):
        return None
    preflight_id = str(body.get("preflight_id", "")).strip()
    if not preflight_id:
        raise RuntimeError("preflight_required")
    signature = _build_tuning_apply_signature(family, target)
    preflight_store.validate(preflight_id, signature)
    return preflight_id


# ============================================================================
# Telemetry Contract v2 Readiness
# ============================================================================

# v1 required fields (unchanged)
V1_REQUIRED_FIELDS = ("mode", "ang", "raw", "out", "kp", "ki", "kd", "set")
V1_GYRO_ALIASES = ("gyro", "gyr", "gx")

# v2 readiness fields (backward-compatible gate)
V2_READINESS_FIELDS = ("gyro_bias", "vel_meas", "outer_loop_enabled")

# v2 factory telemetry fields (strict factory standard)
V2_FACTORY_FIELDS = (
    "gyro_bias",
    "accel_level_offset",
    "upright_trim",
    "vel_meas",
    "vel_target",
    "outer_loop_enabled",
    "target_angle_from_velocity",
    "motor_l_trim",
    "motor_r_trim",
    "drift_diag_state",
)
# Backward-compatible alias used by tests/docs from earlier revision.
V2_OPTIONAL_FIELDS = V2_FACTORY_FIELDS


def detect_contract_readiness(status: Dict[str, Any]) -> Dict[str, Any]:
    """
    Detect telemetry contract version and v2 readiness.

    Returns dict with:
        - contract_version_detected: "v1" or "v2"
        - v1_ok: bool
        - v2_ready: bool
        - phase1_ready: bool (core calibration + v1 telemetry)
        - phase2_ready: bool (advanced anti-drift/v2 telemetry)
        - phase1_missing_fields: list of missing Phase 1 fields
        - phase1_present_fields: list of present Phase 1 fields
        - phase2_missing_fields: list of missing Phase 2 fields
        - phase2_present_fields: list of present Phase 2 fields
        - v2_missing_fields: list of missing v2 readiness fields
        - v2_present_fields: list of v2 optional fields that are present
        - readiness_checks: list of {check, status, detail}
    """
    if not status:
        return {
            "contract_version_detected": "unknown",
            "v1_ok": False,
            "v2_ready": False,
            "phase1_ready": False,
            "phase2_ready": False,
            "calibration_flow": "phase1_phase2",
            "phase1_missing_fields": list(V1_REQUIRED_FIELDS) + ["gyro|gyr|gx"],
            "phase1_present_fields": [],
            "phase2_missing_fields": list(V2_READINESS_FIELDS),
            "phase2_present_fields": [],
            "v2_missing_fields": list(V2_READINESS_FIELDS),
            "v2_factory_ready": False,
            "v2_factory_missing_fields": list(V2_FACTORY_FIELDS),
            "v2_present_fields": [],
            "readiness_checks": [
                {
                    "check": "telemetry_available",
                    "status": "fail",
                    "detail": "No telemetry data",
                }
            ],
        }

    checks: list[Dict[str, Any]] = []

    # v1 check
    v1_missing = [f for f in V1_REQUIRED_FIELDS if f not in status]
    has_gyro = any(alias in status for alias in V1_GYRO_ALIASES)
    if not has_gyro:
        v1_missing.append("gyro|gyr|gx")
    v1_ok = len(v1_missing) == 0
    phase1_present = [f for f in V1_REQUIRED_FIELDS if f in status]
    phase1_present.extend([alias for alias in V1_GYRO_ALIASES if alias in status])

    checks.append(
        {
            "check": "v1_required_fields",
            "status": "pass" if v1_ok else "fail",
            "detail": f"Missing: {v1_missing}"
            if v1_missing
            else "All v1 fields present",
        }
    )

    # v2 readiness check
    v2_missing = [f for f in V2_READINESS_FIELDS if f not in status]
    if not has_gyro and "gyro|gyr|gx" not in v2_missing:
        # Keep backward-compatible diagnostics: missing gyro alias should surface
        # in readiness output even though it is part of v1 base contract.
        v2_missing.append("gyro|gyr|gx")
    v2_ready = len(v2_missing) == 0
    v2_factory_missing = [f for f in V2_FACTORY_FIELDS if f not in status]
    v2_factory_ready = len(v2_factory_missing) == 0

    checks.append(
        {
            "check": "v2_readiness_fields",
            "status": "pass" if v2_ready else "warn",
            "detail": f"Missing: {v2_missing}"
            if v2_missing
            else "All v2 readiness fields present",
        }
    )

    # v2 optional fields present
    v2_present = [f for f in V2_FACTORY_FIELDS if f in status]

    checks.append(
        {
            "check": "v2_optional_fields",
            "status": "pass" if v2_present else "warn",
            "detail": f"Present: {v2_present}"
            if v2_present
            else "No v2 optional fields present",
        }
    )

    checks.append(
        {
            "check": "v2_factory_fields",
            "status": "pass" if v2_factory_ready else "warn",
            "detail": f"Missing: {v2_factory_missing}"
            if v2_factory_missing
            else "All factory v2 fields present",
        }
    )

    # Calibration readiness
    has_gyro_bias = "gyro_bias" in status
    has_accel_offset = "accel_level_offset" in status
    has_upright_trim = "upright_trim" in status
    calibration_ready = has_gyro_bias and has_accel_offset

    checks.append(
        {
            "check": "calibration_data",
            "status": "pass" if calibration_ready else "warn",
            "detail": "Gyro bias and accel offset calibrated"
            if calibration_ready
            else "Calibration not complete",
        }
    )

    # Outer loop readiness
    has_velocity = "vel_meas" in status
    outer_enabled = status.get("outer_loop_enabled", False)

    checks.append(
        {
            "check": "outer_loop_ready",
            "status": "pass" if (has_velocity and outer_enabled) else "warn",
            "detail": "Velocity feedback and outer loop active"
            if (has_velocity and outer_enabled)
            else "Outer loop not active or no velocity data",
        }
    )

    checks.append(
        {
            "check": "phase1_core_ready",
            "status": "pass" if v1_ok else "fail",
            "detail": "Phase 1 core readiness satisfied"
            if v1_ok
            else "Phase 1 incomplete: core telemetry/calibration missing",
        }
    )
    checks.append(
        {
            "check": "phase2_advanced_ready",
            "status": "pass" if v2_ready else "warn",
            "detail": "Phase 2 advanced readiness satisfied"
            if v2_ready
            else "Phase 2 incomplete: advanced anti-drift fields missing",
        }
    )

    return {
        "contract_version_detected": "v2" if v2_ready else "v1",
        "v1_ok": v1_ok,
        "v2_ready": v2_ready,
        "phase1_ready": v1_ok,
        "phase2_ready": v2_ready,
        "calibration_flow": "phase1_phase2",
        "phase1_missing_fields": v1_missing,
        "phase1_present_fields": phase1_present,
        "phase2_missing_fields": v2_missing,
        "phase2_present_fields": v2_present,
        "v2_missing_fields": v2_missing,
        "v2_factory_ready": v2_factory_ready,
        "v2_factory_missing_fields": v2_factory_missing,
        "v2_present_fields": v2_present,
        "readiness_checks": checks,
    }


def _compute_action_gates(
    *,
    connected: bool,
    status: Dict[str, Any],
    control_snapshot: Dict[str, Any],
    session_fresh: bool,
    prearm_safety: Optional[Dict[str, Any]] = None,
) -> Dict[str, Dict[str, Any]]:
    status_map = status if isinstance(status, dict) else {}
    control_map = control_snapshot if isinstance(control_snapshot, dict) else {}
    mode = str(status_map.get("mode", "")).upper()
    estop = bool(control_map.get("estop_latched", False))
    arm_prepared = bool(control_map.get("arm_prepared", False))
    readiness = detect_contract_readiness(status_map)
    phase1_ready = bool(readiness.get("phase1_ready", readiness.get("v1_ok", False)))
    phase2_ready = bool(readiness.get("phase2_ready", readiness.get("v2_ready", False)))
    prearm = prearm_safety if isinstance(prearm_safety, dict) else {}
    prearm_required = bool(prearm.get("required", False))
    prearm_passed = bool(prearm.get("passed", False))

    def gate(reasons: list[str]) -> Dict[str, Any]:
        return {"ok": len(reasons) == 0, "reasons": reasons}

    gates: Dict[str, Dict[str, Any]] = {}

    arm_prepare_reasons: list[str] = []
    if not connected:
        arm_prepare_reasons.append("serial_disconnected")
    if not session_fresh:
        arm_prepare_reasons.append("session_stale")
    if estop:
        arm_prepare_reasons.append("estop_latched")
    if not phase1_ready:
        arm_prepare_reasons.append("telemetry_contract_incomplete")
    if mode in {"ARMED", "BALANCING"}:
        arm_prepare_reasons.append("already_armed")
    if prearm_required and not prearm_passed:
        arm_prepare_reasons.append("prearm_safety_check_required")
    gates["arm_prepare"] = gate(arm_prepare_reasons)

    arm_confirm_reasons: list[str] = []
    if not connected:
        arm_confirm_reasons.append("serial_disconnected")
    if not session_fresh:
        arm_confirm_reasons.append("session_stale")
    if estop:
        arm_confirm_reasons.append("estop_latched")
    if not arm_prepared:
        arm_confirm_reasons.append("arm_not_prepared")
    if mode in {"ARMED", "BALANCING"}:
        arm_confirm_reasons.append("already_armed")
    if prearm_required and not prearm_passed:
        arm_confirm_reasons.append("prearm_safety_check_required")
    gates["arm_confirm"] = gate(arm_confirm_reasons)

    arm_reasons: list[str] = []
    if not connected:
        arm_reasons.append("serial_disconnected")
    if not session_fresh:
        arm_reasons.append("session_stale")
    if estop:
        arm_reasons.append("estop_latched")
    if mode in {"ARMED", "BALANCING"}:
        arm_reasons.append("already_armed")
    if prearm_required and not prearm_passed:
        arm_reasons.append("prearm_safety_check_required")
    gates["arm"] = gate(arm_reasons)

    disarm_reasons: list[str] = []
    if not connected:
        disarm_reasons.append("serial_disconnected")
    gates["disarm"] = gate(disarm_reasons)

    cal_zero_reasons: list[str] = []
    if not connected:
        cal_zero_reasons.append("serial_disconnected")
    if estop:
        cal_zero_reasons.append("estop_latched")
    if mode == "BALANCING":
        cal_zero_reasons.append("disarm_required")
    gates["cal_zero"] = gate(cal_zero_reasons)

    burst_arm_reasons: list[str] = []
    if not connected:
        burst_arm_reasons.append("serial_disconnected")
    if estop:
        burst_arm_reasons.append("estop_latched")
    gates["burst_arm"] = gate(burst_arm_reasons)

    tune_reasons: list[str] = []
    if not connected:
        tune_reasons.append("serial_disconnected")
    if estop:
        tune_reasons.append("estop_latched")
    if not phase1_ready:
        tune_reasons.append("telemetry_contract_incomplete")
    gates["pid"] = gate(list(tune_reasons))
    motion_reasons = list(tune_reasons)
    if not phase2_ready:
        motion_reasons.append("phase2_required_for_motion")
    gates["motion"] = gate(motion_reasons)
    gates["setpoint"] = gate(list(tune_reasons))
    gates["limits"] = gate(list(tune_reasons))
    gates["prearm_safety"] = {
        "ok": (not prearm_required) or prearm_passed,
        "reasons": []
        if ((not prearm_required) or prearm_passed)
        else ["prearm_safety_check_required"],
    }

    return gates


_compat_policy_cache: Dict[str, Any] = {"content": None, "mtime": 0.0}


def _default_compat_policy() -> Dict[str, Any]:
    return {
        "version": "1.0",
        "default_profile": "baseline_v1",
        "required_fields": [
            "mode",
            "ang",
            "raw",
            "gyro|gyr|gx",
            "out",
            "kp",
            "ki",
            "kd",
            "set",
        ],
        "profiles": {
            "lean_v1": {
                "required_commands": [
                    "GET",
                    "HELP",
                    "ARM",
                    "DISARM",
                    "ESTOP",
                    "FAULTCLR",
                    "PID",
                    "SETPOINT",
                    "LIMITS",
                    "CAL ZERO",
                    "SAVECFG",
                ],
                "optional_commands": ["IDENT", "LOGT", "LOGCSV", "BURSTCSV", "CSVHDR"],
                "warn_only_missing_commands": [],
            },
            "baseline_v1": {
                "required_commands": [
                    "GET",
                    "ARM",
                    "DISARM",
                    "PID",
                    "SETPOINT",
                    "LIMITS",
                    "CAL ZERO",
                    "SAVECFG",
                    "FAULTCLR",
                ],
                "optional_commands": [
                    "IDENT",
                    "MOTION",
                    "FILTER",
                    "KAL",
                    "LOGT",
                    "LOGCSV",
                    "BURSTCSV",
                    "CSVHDR",
                    "IMU CAL",
                    "IMU LOAD",
                    "IMU SAVE",
                    "IMU INFO",
                ],
                "warn_only_missing_commands": ["MOTION"],
            },
            "profiled_runtime_v1": {
                "required_commands": [
                    "GET",
                    "ARM",
                    "DISARM",
                    "PID",
                    "SETPOINT",
                    "LIMITS",
                    "CAL ZERO",
                    "SAVECFG",
                    "FAULTCLR",
                ],
                "optional_commands": [
                    "IDENT",
                    "MOTION",
                    "FILTER",
                    "KAL",
                    "LOGT",
                    "LOGCSV",
                    "BURSTCSV",
                    "CSVHDR",
                    "LOADCFG",
                    "DEFAULTCFG",
                    "IMU CAL",
                    "IMU LOAD",
                    "IMU SAVE",
                    "IMU INFO",
                ],
                "warn_only_missing_commands": ["MOTION"],
            },
            "control_lab_v1": {
                "required_commands": [
                    "GET",
                    "ARM",
                    "DISARM",
                    "PID",
                    "SETPOINT",
                    "LIMITS",
                    "MOTION",
                    "FILTER",
                    "KAL",
                    "CAL ZERO",
                    "SAVECFG",
                    "FAULTCLR",
                ],
                "optional_commands": [
                    "IDENT",
                    "LOGT",
                    "LOGCSV",
                    "BURSTCSV",
                    "CSVHDR",
                    "CC",
                    "TF",
                    "IMU CAL",
                    "IMU LOAD",
                    "IMU SAVE",
                    "IMU INFO",
                ],
                "warn_only_missing_commands": [],
            },
        },
    }


def _load_compat_policy() -> Dict[str, Any]:
    global _compat_policy_cache
    repo_root = pathlib.Path(__file__).resolve().parents[2]
    policy_path = repo_root / "docs" / "contracts" / "compat_policy_v1.json"
    default = _default_compat_policy()
    if not policy_path.exists():
        return default
    try:
        mtime = policy_path.stat().st_mtime
        if (
            _compat_policy_cache["content"] is not None
            and _compat_policy_cache["mtime"] == mtime
        ):
            return dict(_compat_policy_cache["content"])
        raw = json.loads(policy_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return default
        merged = dict(default)
        merged.update(raw)
        profiles = raw.get("profiles")
        if isinstance(profiles, dict) and profiles:
            merged["profiles"] = profiles
        _compat_policy_cache = {"content": merged, "mtime": mtime}
        return dict(merged)
    except Exception:
        return default


def _status_has_required_fields(
    status: Dict[str, Any], required_fields: list[str]
) -> list[str]:
    missing: list[str] = []
    for field in required_fields:
        if "|" in field:
            aliases = [token.strip() for token in field.split("|") if token.strip()]
            if not any(alias in status for alias in aliases):
                missing.append(field)
            continue
        if field not in status:
            missing.append(field)
    return missing


def _resolve_compat_profile(
    *,
    firmware_id: Optional[str],
    status: Dict[str, Any],
    help_blob: str,
    policy: Dict[str, Any],
) -> str:
    fid = str(firmware_id or "").upper()
    if "CONTROL_LAB" in fid:
        return "control_lab_v1"
    if "PROFILED_RUNTIME" in fid:
        return "profiled_runtime_v1"
    if "MVP_BASELINE" in fid:
        return "baseline_v1"
    if all(token in help_blob for token in ("MOTION", "FILTER", "KAL", "CC", "TF")):
        return "control_lab_v1"
    if "FAULTCLR" in help_blob:
        return "profiled_runtime_v1"
    default_profile = str(policy.get("default_profile", "baseline_v1"))
    if (
        isinstance(policy.get("profiles"), dict)
        and default_profile in policy["profiles"]
    ):
        return default_profile
    return "baseline_v1"


def _resolve_action_gates(
    gateway: NanoSerialGateway,
    control: BridgeControlState,
    prearm_gate: Optional[PreArmSafetyGate] = None,
    *,
    status_override: Optional[Dict[str, Any]] = None,
) -> Dict[str, Dict[str, Any]]:
    health = gateway.health()
    connected = bool(health.get("connected", False))
    status_src_raw = (
        status_override
        if isinstance(status_override, dict)
        else dict(health.get("last_status", {}))
    )
    status_src = _normalize_status_for_hud(status_src_raw).get("status", status_src_raw)
    control_snapshot = control.snapshot()
    return _compute_action_gates(
        connected=connected,
        status=status_src,
        control_snapshot=control_snapshot,
        session_fresh=control.session_fresh(),
        prearm_safety=(prearm_gate.snapshot() if prearm_gate is not None else None),
    )


def _require_action_allowed(
    action: str,
    gateway: NanoSerialGateway,
    control: BridgeControlState,
    prearm_gate: Optional[PreArmSafetyGate] = None,
    *,
    status_override: Optional[Dict[str, Any]] = None,
) -> Dict[str, Dict[str, Any]]:
    gates = _resolve_action_gates(
        gateway,
        control,
        prearm_gate=prearm_gate,
        status_override=status_override,
    )
    node = gates.get(action, {"ok": True, "reasons": []})
    if not bool(node.get("ok", False)):
        reasons = ",".join([str(r) for r in list(node.get("reasons", [])) if str(r)])
        raise RuntimeError(f"action_blocked:{action}:{reasons}")
    return gates


def _run_prearm_hardware_check(
    gateway: NanoSerialGateway,
    control: BridgeControlState,
    body: Dict[str, Any],
) -> Dict[str, Any]:
    return _run_prearm_hardware_check_impl(gateway, control, body)


def run_compat_probe(
    gateway: NanoSerialGateway, *, profile_override: Optional[str] = None
) -> Dict[str, Any]:
    policy = _load_compat_policy()
    required_fields_policy = list(
        policy.get("required_fields", _default_compat_policy()["required_fields"])
    )
    profiles = (
        policy.get("profiles", {}) if isinstance(policy.get("profiles"), dict) else {}
    )
    report: Dict[str, Any] = {
        "ok": False,
        "policy_version": str(policy.get("version", "1.0")),
        "profile": "unknown",
        "firmware_id": None,
        "required_fields": required_fields_policy,
        "required_commands": [],
        "optional_commands": [],
        "missing_fields": [],
        "supported_commands": [],
        "missing_commands": [],
        "blocking_missing_commands": [],
        "warnings": [],
    }

    # 1) Firmware identity probe (best-effort fallback chain)
    firmware_id = None
    for ident_cmd in ("GET_ID", "ID", "WHOAMI", "IDENT"):
        try:
            resp = gateway.command(ident_cmd, timeout=1.0)
            lines = [ln for ln in resp.get("lines", []) if ln]
            if any("ERR UNKNOWN" in ln for ln in lines):
                continue
            if lines:
                firmware_id = lines[-1]
                break
        except Exception:
            continue
    report["firmware_id"] = firmware_id

    # 2) Required status schema check
    status_raw = gateway.get_status()
    norm = _normalize_status_for_hud(status_raw)
    status = dict(norm.get("status", status_raw))
    report["status"] = status
    report["status_raw"] = status_raw
    report["telemetry_adapter"] = dict(norm.get("adapter", {}))
    missing_fields = _status_has_required_fields(status, required_fields_policy)
    report["missing_fields"] = missing_fields

    # 3) Command support probe from HELP output (safe, read-only)
    help_lines: list[str] = []
    try:
        h = gateway.command("HELP", timeout=1.5)
        help_lines = h.get("lines", [])
    except Exception as exc:
        report["warnings"].append(f"help_probe_failed:{exc}")

    help_blob = "\n".join(help_lines).upper()
    requested_profile = str(profile_override or "").strip()
    if requested_profile and requested_profile in profiles:
        selected_profile = requested_profile
    else:
        selected_profile = _resolve_compat_profile(
            firmware_id=firmware_id,
            status=status,
            help_blob=help_blob,
            policy=policy,
        )
    report["profile"] = selected_profile
    profile_policy = (
        profiles.get(selected_profile, {}) if isinstance(profiles, dict) else {}
    )
    required_commands = list(profile_policy.get("required_commands", []))
    optional_commands = list(profile_policy.get("optional_commands", []))
    warn_only_missing = set(profile_policy.get("warn_only_missing_commands", []))
    command_expect = list(dict.fromkeys(required_commands + optional_commands))
    report["required_commands"] = required_commands
    report["optional_commands"] = optional_commands
    supported = []
    missing = []
    for c in command_expect:
        if c in help_blob:
            supported.append(c)
        else:
            missing.append(c)

    # If HELP output is unusable (e.g., generic "OK"), do not fail compat on
    # command discovery; fall back to schema-based validation.
    if len(supported) == 0:
        report["warnings"].append("help_probe_unusable_command_catalog")
        missing = []

    report["supported_commands"] = supported
    report["missing_commands"] = missing
    blocking_missing = [
        c for c in missing if c in required_commands and c not in warn_only_missing
    ]
    report["blocking_missing_commands"] = blocking_missing
    optional_missing = [
        c for c in missing if c in optional_commands or c in warn_only_missing
    ]
    if optional_missing:
        report["warnings"].append(
            f"optional_commands_missing:{','.join(optional_missing)}"
        )
    report["tuning_capabilities"] = _detect_tuning_capabilities(
        status, supported, help_lines
    )

    report["ok"] = len(missing_fields) == 0 and len(blocking_missing) == 0
    if missing_fields:
        report["warnings"].append("status schema mismatch")
    if firmware_id is None:
        report["warnings"].append("no explicit firmware identity command detected")

    # v2 readiness (additive, non-breaking)
    v2_readiness = detect_contract_readiness(status)
    report["contract_version_detected"] = v2_readiness["contract_version_detected"]
    report["v1_ok"] = v2_readiness["v1_ok"]
    report["v2_ready"] = v2_readiness["v2_ready"]
    report["phase1_ready"] = v2_readiness.get("phase1_ready", report["v1_ok"])
    report["phase2_ready"] = v2_readiness.get("phase2_ready", report["v2_ready"])
    report["calibration_flow"] = v2_readiness.get("calibration_flow", "phase1_phase2")
    report["phase1_missing_fields"] = v2_readiness.get("phase1_missing_fields", [])
    report["phase1_present_fields"] = v2_readiness.get("phase1_present_fields", [])
    report["phase2_missing_fields"] = v2_readiness.get(
        "phase2_missing_fields", v2_readiness["v2_missing_fields"]
    )
    report["phase2_present_fields"] = v2_readiness.get(
        "phase2_present_fields", v2_readiness["v2_present_fields"]
    )
    report["v2_missing_fields"] = v2_readiness["v2_missing_fields"]
    report["v2_factory_ready"] = v2_readiness["v2_factory_ready"]
    report["v2_factory_missing_fields"] = v2_readiness["v2_factory_missing_fields"]
    report["v2_present_fields"] = v2_readiness["v2_present_fields"]
    report["readiness_checks"] = v2_readiness["readiness_checks"]

    return report


def _get_port_meta(port: str) -> Dict[str, Any]:
    meta: Dict[str, Any] = {
        "device": port,
        "description": None,
        "manufacturer": None,
        "product": None,
        "serial_number": None,
        "vid": None,
        "pid": None,
        "hwid": None,
    }
    if list_ports is None:
        return meta

    try:
        for p in list_ports.comports():
            if p.device != port:
                continue
            meta.update(
                {
                    "description": p.description,
                    "manufacturer": p.manufacturer,
                    "product": p.product,
                    "serial_number": p.serial_number,
                    "vid": p.vid,
                    "pid": p.pid,
                    "hwid": p.hwid,
                }
            )
            break
    except Exception:
        return meta
    return meta


def _guess_mcu(port_meta: Dict[str, Any]) -> str:
    blob = " ".join(
        str(port_meta.get(k, "") or "")
        for k in ("description", "manufacturer", "product", "hwid")
    ).upper()

    if "CH340" in blob or "CH341" in blob or "WCH" in blob:
        return "ATmega328P-class Nano via CH340 USB-UART"
    if "CP210" in blob:
        return "ESP-class MCU via CP210x USB bridge"
    if "FT232" in blob or "FTDI" in blob:
        return "MCU with FTDI USB-UART bridge"
    if "16U2" in blob or "ATMEGA16U2" in blob:
        return "ATmega-class Arduino USB interface (16U2)"
    if "CDC" in blob or "USB SERIAL" in blob:
        return "Generic USB CDC serial MCU"
    return "Unknown (serial bridge not fingerprinted)"


def run_connect_probe(gateway: NanoSerialGateway) -> Dict[str, Any]:
    health = gateway.health()
    connected = bool(health.get("connected", False))
    port = str(health.get("port", ""))
    baud = int(health.get("baud", 0) or 0)

    report: Dict[str, Any] = {
        "ok": False,
        "connected": connected,
        "port": port,
        "baud": baud,
        "port_meta": _get_port_meta(port),
        "mcu_guess": "unknown",
        "firmware_profile": "unknown",
        "confidence_pct": 0,
        "status_schema_ok": False,
        "status_error": None,
        "components": {
            "imu": False,
            "motor_driver": False,
            "encoder_feedback": False,
            "voltage_telemetry": False,
            "wheel_model": False,
            "persistent_calibration": False,
        },
        "commands": [],
        "missing_commands": [],
        "warnings": [],
        "next_questions": [
            "Which wheel+gearbox+motor set are you using on this bot build?",
            "Which motor driver board/chip is wired (for example TB6612, L298N)?",
            "Do encoders exist on both wheels, or only one side?",
            "Is external motor power currently connected and enabled?",
        ],
    }
    report["mcu_guess"] = _guess_mcu(report["port_meta"])

    if not connected:
        report["warnings"].append("bridge not connected to serial target")
        return report

    compat: Dict[str, Any]
    try:
        compat = run_compat_probe(gateway)
    except Exception as exc:
        compat = {
            "ok": False,
            "error": str(exc),
            "missing_fields": [],
            "missing_commands": [],
        }
        report["warnings"].append(f"compat probe failed: {exc}")

    status = compat.get("status") if isinstance(compat, dict) else None
    status_raw = compat.get("status_raw") if isinstance(compat, dict) else None
    adapter_meta = compat.get("telemetry_adapter") if isinstance(compat, dict) else None
    if not status:
        try:
            status_raw = gateway.get_status()
            norm = _normalize_status_for_hud(status_raw)
            status = dict(norm.get("status", status_raw))
            adapter_meta = dict(norm.get("adapter", {}))
        except Exception as exc:
            report["status_error"] = str(exc)
            status = {}
            status_raw = {}
            adapter_meta = {}

    report["compat"] = compat
    report["status"] = status
    report["status_raw"] = status_raw
    report["telemetry_adapter"] = dict(adapter_meta or {})
    report["firmware_profile"] = str(compat.get("profile", "unknown"))
    report["commands"] = list(compat.get("supported_commands", []))
    report["missing_commands"] = list(compat.get("missing_commands", []))
    report["tuning_capabilities"] = dict(compat.get("tuning_capabilities", {}))

    required_fields = ("mode", "ang", "raw", "out", "kp", "ki", "kd", "set")
    has_gyro = any(k in status for k in ("gyro", "gyr", "gx"))
    report["status_schema_ok"] = all(f in status for f in required_fields) and has_gyro
    report["components"]["imu"] = "ang" in status and "raw" in status and has_gyro
    report["components"]["motor_driver"] = "out" in status
    report["components"]["encoder_feedback"] = "encL" in status or "encR" in status
    report["components"]["voltage_telemetry"] = "volRaw" in status
    report["components"]["wheel_model"] = "wspd" in status and "wpos" in status
    cmds = set(report["commands"])
    report["components"]["persistent_calibration"] = (
        "CAL ZERO" in cmds and "SAVECFG" in cmds
    )

    score = 0.0
    score += 0.2 if connected else 0.0
    score += 0.2 if report["status_schema_ok"] else 0.0
    score += 0.2 if report["firmware_profile"] != "unknown" else 0.0
    score += 0.2 if len(report["missing_commands"]) <= 2 else 0.0
    component_hits = sum(1 for v in report["components"].values() if v)
    score += 0.2 * (component_hits / max(1, len(report["components"])))
    report["confidence_pct"] = int(round(100 * min(1.0, score)))

    report["ok"] = report["status_schema_ok"] and report["confidence_pct"] >= 60
    if not report["status_schema_ok"]:
        report["warnings"].append("status schema mismatch")
    if not has_gyro:
        report["warnings"].append(
            "kalman telemetry missing gyro rate field (expected one of: gyro/gyr/gx)"
        )
    if report["missing_commands"]:
        report["warnings"].append(
            "some expected commands were not found in HELP output"
        )

    # v2 readiness (additive, non-breaking)
    v2_readiness = detect_contract_readiness(status)
    report["contract_version_detected"] = v2_readiness["contract_version_detected"]
    report["v1_ok"] = v2_readiness["v1_ok"]
    report["v2_ready"] = v2_readiness["v2_ready"]
    report["phase1_ready"] = v2_readiness.get("phase1_ready", report["v1_ok"])
    report["phase2_ready"] = v2_readiness.get("phase2_ready", report["v2_ready"])
    report["calibration_flow"] = v2_readiness.get("calibration_flow", "phase1_phase2")
    report["phase1_missing_fields"] = v2_readiness.get("phase1_missing_fields", [])
    report["phase1_present_fields"] = v2_readiness.get("phase1_present_fields", [])
    report["phase2_missing_fields"] = v2_readiness.get(
        "phase2_missing_fields", v2_readiness["v2_missing_fields"]
    )
    report["phase2_present_fields"] = v2_readiness.get(
        "phase2_present_fields", v2_readiness["v2_present_fields"]
    )
    report["v2_missing_fields"] = v2_readiness["v2_missing_fields"]
    report["v2_factory_ready"] = v2_readiness["v2_factory_ready"]
    report["v2_factory_missing_fields"] = v2_readiness["v2_factory_missing_fields"]
    report["v2_present_fields"] = v2_readiness["v2_present_fields"]
    report["readiness_checks"] = v2_readiness["readiness_checks"]

    # Recommended next action for Phase 2 readiness.
    phase2_recommended_action: Optional[str] = None
    if not v2_readiness["phase1_ready"]:
        phase2_recommended_action = "Run Calibration Phase 1 (core sensor zero + baseline checks) before arming."
    elif not v2_readiness["v2_ready"]:
        missing = v2_readiness["v2_missing_fields"]
        if "gyro_bias" in missing:
            phase2_recommended_action = "Run Calibration Phase 2 to establish gyro bias and advanced anti-drift telemetry."
        elif "vel_meas" in missing:
            phase2_recommended_action = (
                "Complete Calibration Phase 2: enable velocity feedback telemetry."
            )
        elif "outer_loop_enabled" in missing:
            phase2_recommended_action = "Complete Calibration Phase 2: enable outer velocity loop for anti-drift."
        else:
            phase2_recommended_action = (
                "Complete Calibration Phase 2 for advanced anti-drift capabilities."
            )
    report["phase2_recommended_action"] = phase2_recommended_action
    # Backward-compatible alias retained for migration window.
    report["v2_recommended_action"] = phase2_recommended_action

    return report


def run_setup_compat_test(gateway: NanoSerialGateway) -> Dict[str, Any]:
    compat = run_compat_probe(gateway)
    missing_fields = list(
        compat.get("missing_fields", []) if isinstance(compat, dict) else []
    )
    missing_commands = list(
        compat.get("missing_commands", []) if isinstance(compat, dict) else []
    )
    blocking_missing_commands = list(
        compat.get("blocking_missing_commands", []) if isinstance(compat, dict) else []
    )
    optional_commands = {"MOTION"}
    hard_missing_commands = (
        blocking_missing_commands
        if blocking_missing_commands
        else [c for c in missing_commands if c not in optional_commands]
    )
    warnings = list(compat.get("warnings", []) if isinstance(compat, dict) else [])
    blocking_issues: list[str] = []
    if missing_fields:
        blocking_issues.append(f"missing_fields:{','.join(missing_fields)}")
    if hard_missing_commands:
        blocking_issues.append(f"missing_commands:{','.join(hard_missing_commands)}")
    if bool(compat.get("ok", False)) and not hard_missing_commands:
        status = (
            "warn"
            if (
                warnings
                or (len(missing_commands) > 0 and len(hard_missing_commands) == 0)
            )
            else "pass"
        )
    else:
        status = "fail"
    if gateway.health().get("connected", False) is False:
        status = "unavailable"
        if "serial_disconnected" not in blocking_issues:
            blocking_issues.append("serial_disconnected")
    prompts: list[str] = []
    if missing_fields:
        prompts.append(
            "Summarize missing telemetry fields and provide exact sketch additions needed to satisfy compat."
        )
    if hard_missing_commands:
        prompts.append(
            "List missing commands and generate minimal command handler updates for compat pass."
        )
    elif missing_commands:
        prompts.append(
            "Optional commands are missing. Confirm whether MOTION should be implemented for this profile."
        )
    if not prompts:
        prompts.append("Compat passed. Recommend next smoke-check sequence.")
    return {
        "status": status,
        "blocking_issues": blocking_issues,
        "warnings": warnings,
        "recommended_fix_prompts": prompts,
        "compat": compat,
        "tested_at": time.time(),
    }


def run_setup_smoke_check(
    gateway: NanoSerialGateway, control: BridgeControlState
) -> Dict[str, Any]:
    health = gateway.health()
    connected = bool(health.get("connected", False))
    status = health.get("last_status", {})
    feed_hz = _safe_float(status.get("hz"))
    angle = _safe_float(status.get("ang"))
    mode = str(status.get("mode", "UNKNOWN")).upper()
    estop = bool(control.snapshot().get("estop_latched", False))

    checks: list[Dict[str, Any]] = []
    checks.append(
        {
            "id": "serial_connected",
            "status": "pass" if connected else "fail",
            "detail": "serial connected" if connected else "serial disconnected",
        }
    )
    checks.append(
        {
            "id": "estop_clear",
            "status": "pass" if not estop else "fail",
            "detail": "e-stop clear" if not estop else "e-stop latched",
        }
    )
    checks.append(
        {
            "id": "telemetry_mode_known",
            "status": "pass" if mode not in {"", "UNKNOWN"} else "warn",
            "detail": f"mode={mode or 'UNKNOWN'}",
        }
    )
    checks.append(
        {
            "id": "telemetry_feed",
            "status": "pass" if (feed_hz is not None and feed_hz >= 5.0) else "warn",
            "detail": f"feed_hz={feed_hz if feed_hz is not None else 'n/a'}",
        }
    )
    checks.append(
        {
            "id": "angle_streaming",
            "status": "pass" if angle is not None else "warn",
            "detail": f"angle={angle if angle is not None else 'n/a'}",
        }
    )

    fail_count = sum(1 for c in checks if c["status"] == "fail")
    warn_count = sum(1 for c in checks if c["status"] == "warn")
    if not connected:
        overall = "unavailable"
    elif fail_count > 0:
        overall = "fail"
    elif warn_count > 0:
        overall = "warn"
    else:
        overall = "pass"
    failing = [c["id"] for c in checks if c["status"] in {"fail", "warn"}]
    return {
        "status": overall,
        "checks": checks,
        "failure_summary": ", ".join(failing) if failing else "",
        "tested_at": time.time(),
    }


def run_setup_overwatch_check(
    gateway: NanoSerialGateway, firmware: FirmwareManager
) -> Dict[str, Any]:
    report = build_overwatch_report(
        gateway=gateway, firmware=firmware, compat=None, connect=None
    )
    overall = str(report.get("overall", "warn")).lower()
    status = overall if overall in {"pass", "warn", "fail"} else "warn"
    return {
        "status": status,
        "overwatch": report,
        "tested_at": time.time(),
    }


def _latest_docs_folder(generated_root: pathlib.Path) -> Optional[pathlib.Path]:
    try:
        candidates = [p for p in generated_root.glob("*_docs*") if p.is_dir()]
    except Exception:
        return None
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _validate_docs_artifacts(docs_dir: pathlib.Path) -> Dict[str, Any]:
    required = [
        "control_flow.mmd",
        "state_machine.mmd",
        "hardware_block.mmd",
        "pin_mapping.mmd",
        "pin_assignment.md",
        "command_api_map.md",
        "source_report.md",
    ]
    missing: list[str] = []
    invalid: list[str] = []
    for name in required:
        path = docs_dir / name
        if not path.exists() or not path.is_file():
            missing.append(name)
            continue
        try:
            txt = path.read_text(encoding="utf-8").strip()
        except Exception:
            invalid.append(name)
            continue
        if not txt:
            invalid.append(name)
            continue
        if name.endswith(".mmd"):
            first = txt.splitlines()[0].strip().lower()
            if not (
                first.startswith("flowchart")
                or first.startswith("graph")
                or first.startswith("statediagram-v2")
                or first.startswith("classdiagram")
            ):
                invalid.append(name)
    ok = not missing and not invalid
    return {"ok": ok, "missing": missing, "invalid": invalid, "required": required}


def build_overwatch_report(
    *,
    gateway: NanoSerialGateway,
    firmware: FirmwareManager,
    compat: Optional[Dict[str, Any]] = None,
    connect: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    checks: list[Dict[str, Any]] = []
    actions: list[str] = []

    def add_check(
        check_id: str, label: str, status: str, detail: str, evidence: str = ""
    ) -> None:
        checks.append(
            {
                "id": check_id,
                "label": label,
                "status": status,
                "detail": detail,
                "evidence": evidence,
            }
        )
        if status != "pass":
            actions.append(f"{label}: {detail}")

    health = gateway.health()
    connected = bool(health.get("connected", False))
    add_check(
        "serial_connected",
        "Serial Link",
        "pass" if connected else "fail",
        "Bridge has active serial session"
        if connected
        else "Bridge is not connected to serial device",
        f"port={health.get('port', '')}",
    )

    status = dict(health.get("last_status", {}))
    readiness = detect_contract_readiness(status)
    v1_ok = bool(readiness.get("v1_ok", False))
    v2_ready = bool(readiness.get("v2_ready", False))
    add_check(
        "telemetry_contract_v1",
        "Telemetry Contract",
        "pass" if v1_ok else "fail",
        "Required telemetry fields present"
        if v1_ok
        else "Required telemetry fields missing",
        f"version={readiness.get('contract_version_detected', 'unknown')}",
    )
    add_check(
        "antidrift_v2_ready",
        "Anti-Drift Readiness",
        "pass" if v2_ready else ("warn" if v1_ok else "fail"),
        "v2 anti-drift fields present"
        if v2_ready
        else "v2 anti-drift fields incomplete",
        f"missing={','.join(readiness.get('v2_missing_fields', [])) or 'none'}",
    )

    compat_report = compat if isinstance(compat, dict) else {}
    missing_commands = (
        list(compat_report.get("missing_commands", []))
        if isinstance(compat_report.get("missing_commands", []), list)
        else []
    )
    optional_commands = {"MOTION"}
    hard_missing_commands = [c for c in missing_commands if c not in optional_commands]
    only_optional_missing = bool(missing_commands) and not hard_missing_commands
    command_status = (
        "pass"
        if not missing_commands
        else ("warn" if only_optional_missing else "fail")
    )
    command_detail = (
        "Required command set detected"
        if not missing_commands
        else (
            "Optional commands missing"
            if only_optional_missing
            else "Missing required commands"
        )
    )
    add_check(
        "command_contract",
        "Command Contract",
        command_status,
        command_detail,
        ",".join(missing_commands) if missing_commands else "none",
    )

    fw_status = firmware.status()
    default_sketch = pathlib.Path(str(fw_status.get("defaults", {}).get("sketch", "")))
    sketch_path = default_sketch
    if sketch_path.exists() and sketch_path.is_dir():
        preferred = sketch_path / f"{sketch_path.name}.ino"
        if preferred.exists() and preferred.is_file():
            sketch_path = preferred
        else:
            fallback = sorted(sketch_path.glob("*.ino"))
            if fallback:
                sketch_path = fallback[0]
    sketch_exists = sketch_path.exists() and sketch_path.is_file()
    sketch_mtime = sketch_path.stat().st_mtime if sketch_exists else None
    add_check(
        "sketch_present",
        "Sketch Presence",
        "pass" if sketch_exists else "fail",
        "Active sketch file found" if sketch_exists else "No active sketch file found",
        str(sketch_path),
    )

    docs_dir = _latest_docs_folder(firmware._generated_root)
    docs_exists = docs_dir is not None and docs_dir.exists()
    docs_check = (
        _validate_docs_artifacts(docs_dir)
        if docs_exists and docs_dir is not None
        else {"ok": False, "missing": [], "invalid": [], "required": []}
    )
    docs_mtime = (
        docs_dir.stat().st_mtime if docs_exists and docs_dir is not None else None
    )
    docs_fresh = bool(
        sketch_mtime is not None
        and docs_mtime is not None
        and docs_mtime >= sketch_mtime
    )
    docs_ok = bool(docs_exists and docs_check.get("ok", False) and docs_fresh)
    docs_status = "pass" if docs_ok else ("warn" if not docs_exists else "fail")
    docs_detail = (
        "Docs pack is synced to sketch"
        if docs_ok
        else (
            "Docs pack not generated yet"
            if not docs_exists
            else "Docs pack missing, invalid, or stale vs sketch"
        )
    )
    docs_evidence = f"docs={str(docs_dir) if docs_dir else 'none'}; fresh={str(docs_fresh).lower()}; missing={','.join(docs_check.get('missing', [])) or 'none'}; invalid={','.join(docs_check.get('invalid', [])) or 'none'}"
    add_check("docs_sync", "Docs Integrity", docs_status, docs_detail, docs_evidence)

    gyro_present = any(k in status for k in ("gyro", "gyr", "gx"))
    hud_ok = ("ang" in status) and ("raw" in status) and gyro_present
    add_check(
        "hud_sensor_contract",
        "HUD Sensor Contract",
        "pass" if hud_ok else "fail",
        "HUD sensor fields available"
        if hud_ok
        else "HUD fields missing (need ang/raw/gyro alias)",
        f"fields={','.join(sorted(status.keys())[:12])}",
    )

    setpoint = _first_float(status, "set")
    filtered_angle = _first_float(status, "ang")
    raw_angle = _first_float(status, "raw")
    pid_err = _first_float(status, "pid_err", "err")
    out_sat = _first_float(status, "pid_u_sat", "out")
    out_unsat = _first_float(status, "pid_u_unsat", "pid_u", "u")
    if pid_err is None and setpoint is not None and filtered_angle is not None:
        pid_err = setpoint - filtered_angle

    signal_chain_ok = (
        setpoint is not None
        and filtered_angle is not None
        and pid_err is not None
        and out_sat is not None
    )
    add_check(
        "control_signal_chain",
        "Signal/Error/Output Chain",
        "pass" if signal_chain_ok else "warn",
        "Signal, error, and output telemetry present"
        if signal_chain_ok
        else "Missing one or more of set/ang/pid_err/out telemetry fields",
        f"set={setpoint if setpoint is not None else 'n/a'}; ang={filtered_angle if filtered_angle is not None else 'n/a'}; err={pid_err if pid_err is not None else 'n/a'}; out={out_sat if out_sat is not None else 'n/a'}",
    )

    innovation = _first_float(status, "kal_innov", "innovation")
    if innovation is None and raw_angle is not None and filtered_angle is not None:
        innovation = raw_angle - filtered_angle
    if innovation is not None:
        innovation_abs = abs(float(innovation))
        innovation_status = (
            "pass"
            if innovation_abs <= 5.0
            else ("warn" if innovation_abs <= 12.0 else "fail")
        )
        innovation_detail = (
            "Estimator innovation is nominal"
            if innovation_status == "pass"
            else (
                "Estimator innovation elevated; verify calibration/filter tuning"
                if innovation_status == "warn"
                else "Estimator innovation high; check sensor alignment/calibration"
            )
        )
        add_check(
            "kalman_innovation",
            "Kalman Innovation",
            innovation_status,
            innovation_detail,
            f"innovation_deg={innovation:.3f}",
        )
    else:
        add_check(
            "kalman_innovation",
            "Kalman Innovation",
            "warn",
            "Innovation telemetry not available (derive raw-ang or emit kal_innov)",
            "innovation_deg=n/a",
        )

    if out_unsat is not None and out_sat is not None:
        sat_delta = abs(out_unsat - out_sat)
        sat_status = (
            "pass" if sat_delta < 0.5 else ("warn" if sat_delta < 5.0 else "fail")
        )
        add_check(
            "output_clamp_visibility",
            "Output Clamp Visibility",
            sat_status,
            "Saturation metadata available"
            if sat_status == "pass"
            else (
                "Clamp activity present (expected during aggressive maneuvers)"
                if sat_status == "warn"
                else "Heavy clamp activity; revisit limits/gains"
            ),
            f"u_unsat={out_unsat:.3f}; u_sat={out_sat:.3f}",
        )

    loop_hz = _first_float(status, "loop_hz", "loopHz", "hz")
    if loop_hz is None:
        period_us = _first_float(status, "period_us", "loop_period_us")
        if period_us is not None and period_us > 0.0:
            loop_hz = 1000000.0 / period_us
    loop_status = (
        "pass"
        if (loop_hz is not None and loop_hz >= 45.0)
        else ("warn" if (loop_hz is not None and loop_hz >= 20.0) else "fail")
    )
    add_check(
        "loop_rate",
        "Loop Feed Quality",
        loop_status,
        "Loop rate optimal"
        if loop_status == "pass"
        else (
            "Loop rate sufficient but not optimal"
            if loop_status == "warn"
            else "Loop rate too low"
        ),
        f"loop_hz={loop_hz if loop_hz is not None else 'n/a'}",
    )

    pass_count = sum(1 for c in checks if c["status"] == "pass")
    warn_count = sum(1 for c in checks if c["status"] == "warn")
    fail_count = sum(1 for c in checks if c["status"] == "fail")
    denom = max(1, len(checks))
    score_pct = int(round(((pass_count + 0.5 * warn_count) / denom) * 100))
    all_green = fail_count == 0 and warn_count == 0
    overall = "pass" if all_green else ("warn" if fail_count == 0 else "fail")

    connect_report = connect if isinstance(connect, dict) else {}
    return {
        "ok": all_green,
        "overall": overall,
        "score_pct": score_pct,
        "generated_at": time.time(),
        "checks": checks,
        "counts": {
            "pass": pass_count,
            "warn": warn_count,
            "fail": fail_count,
            "total": len(checks),
        },
        "actions": actions[:8],
        "contract_version_detected": readiness.get(
            "contract_version_detected", "unknown"
        ),
        "connect_confidence_pct": int(connect_report.get("confidence_pct", 0) or 0)
        if connect_report
        else 0,
        "docs": {
            "latest_folder": str(docs_dir) if docs_dir else None,
            "exists": docs_exists,
            "fresh": docs_fresh,
            "check": docs_check,
            "sketch_path": str(sketch_path),
        },
    }


def build_handler(
    gateway: NanoSerialGateway,
    control: BridgeControlState,
    commissioning: CommissioningManager,
    host_capture: HostCaptureManager,
    firmware: FirmwareManager,
    ai: AIManager,
    ai_profiles: AIProfileManager,
    knowledge: AssistantKnowledgeManager,
    agent_mission: AgentMissionManager,
    provider_router: ProviderRouter,
    auth: AuthManager,
    mission_memory: MissionMemoryStore,
    profiles: RobotProfilesManager,
    config_history: ConfigHistoryManager,
    telemetry_port: int,
    codex_agent: Optional[Any] = None,
    hardware_context_store: Optional[HardwareContextStore] = None,
    setup_attempt_history_store: Optional[SetupAttemptHistoryStore] = None,
    prearm_safety_gate: Optional[PreArmSafetyGate] = None,
):
    repo_root = firmware.repo_root
    hw_context_store = hardware_context_store or HardwareContextStore(repo_root)
    setup_attempt_history = setup_attempt_history_store or SetupAttemptHistoryStore(
        repo_root
    )
    design_memory = DesignMemoryStore(repo_root)
    prearm_safety = prearm_safety_gate or PreArmSafetyGate(required=True)
    tuning_preflight = TuningPreflightStore(ttl_s=900.0, max_entries=256)
    probe_cache_lock = threading.Lock()
    probe_cache: Dict[str, Dict[str, Any]] = {
        "compat": {"ts": 0.0, "report": None},
        "connect": {"ts": 0.0, "report": None},
        "overwatch": {"ts": 0.0, "report": None},
    }

    def cached_probe(kind: str) -> Optional[Dict[str, Any]]:
        with probe_cache_lock:
            node = probe_cache.get(kind, {})
            ts = float(node.get("ts", 0.0) or 0.0)
            report = node.get("report")
        ttl_s = 4.0 if kind == "compat" else 2.0
        if report is not None and (time.monotonic() - ts) <= ttl_s:
            return report
        return None

    def store_probe(kind: str, report: Dict[str, Any]) -> None:
        with probe_cache_lock:
            probe_cache[kind] = {"ts": time.monotonic(), "report": report}

    def _current_sketch_hash() -> str:
        sketch_path = pathlib.Path(
            str((firmware.status().get("defaults", {}) or {}).get("sketch", ""))
        )
        if sketch_path.exists() and sketch_path.is_dir():
            preferred = sketch_path / f"{sketch_path.name}.ino"
            if preferred.exists() and preferred.is_file():
                sketch_path = preferred
            else:
                fallback = sorted(sketch_path.glob("*.ino"))
                if fallback:
                    sketch_path = fallback[0]
        if not sketch_path.exists() or not sketch_path.is_file():
            return ""
        try:
            raw = sketch_path.read_bytes()
        except Exception:
            return ""
        return hashlib.sha256(raw).hexdigest()[:16]

    def _current_runtime_identity() -> Dict[str, str]:
        st = dict(gateway.health().get("last_status", {}))
        return {
            "runtime_version": str(
                st.get("runtime", st.get("runtime_version", "")) or ""
            ).strip(),
            "tune_version": str(
                st.get("tune", st.get("tune_version", "")) or ""
            ).strip(),
            "ident": str(st.get("ident", "") or "").strip(),
            "hash": str(st.get("hash", "") or "").strip(),
            "mode": str(st.get("mode", "") or "").strip(),
            "estop": str(st.get("estop", "") or "").strip(),
            "fault": str(st.get("fault", "") or "").strip(),
        }

    def _design_evidence_snapshot() -> Dict[str, Any]:
        fw_status = firmware.status()
        fw_state = (
            str(
                (fw_status.get("state", "") if isinstance(fw_status, dict) else "")
                or ""
            )
            .strip()
            .lower()
        )
        fw_phase = (
            str(
                (fw_status.get("phase", "") if isinstance(fw_status, dict) else "")
                or ""
            )
            .strip()
            .lower()
        )
        fw_rc = (
            fw_status.get("returncode", None) if isinstance(fw_status, dict) else None
        )
        fw_tail = (
            list(fw_status.get("log_tail", [])[-20:])
            if isinstance(fw_status, dict)
            else []
        )
        health = gateway.health()
        status = dict(health.get("last_status", {}))
        prearm = prearm_safety.snapshot()
        recent_attempts = setup_attempt_history.list_recent(limit=8)
        preflight_ok = any(
            (
                isinstance(row, dict)
                and str(row.get("test_type", "")).strip().lower() == "preflight"
                and str(row.get("status", "")).strip().lower() == "pass"
            )
            for row in recent_attempts
        )
        latest_overwatch_score_pct: Optional[float] = None
        for row in recent_attempts:
            if not isinstance(row, dict):
                continue
            if str(row.get("test_type", "")).strip().lower() != "overwatch":
                continue
            result = row.get("result")
            if not isinstance(result, dict):
                continue
            ow = result.get("overwatch")
            if isinstance(ow, dict):
                try:
                    latest_overwatch_score_pct = float(ow.get("score_pct"))
                except Exception:
                    latest_overwatch_score_pct = None
            if latest_overwatch_score_pct is not None:
                break
        mode = str(status.get("mode", "") or "").strip().upper()
        fault = str(status.get("fault", "") or "").strip()
        checks = {
            "upload_ok": bool(
                fw_rc == 0 or "upload_guarded_pass" in fw_state or "upload" in fw_phase
            ),
            "reconnect_ok": any(
                "bridge reconnected" in str(line).lower() for line in fw_tail
            )
            or bool(health.get("connected", False)),
            "preflight_ok": bool(preflight_ok),
            "prearm_ok": bool(prearm.get("passed", False)),
            "telemetry_feed_ok": bool(status),
            "no_fault": fault in {"", "0"},
            "safe_mode_ok": mode in {"SAFE_IDLE", "IDLE", "BALANCING", "BALANCE"},
        }
        return {
            "checks": checks,
            "sources": {
                "firmware": {
                    "state": fw_state,
                    "phase": fw_phase,
                    "returncode": fw_rc,
                },
                "bridge_connected": bool(health.get("connected", False)),
                "status_snapshot": dict(status),
                "status_mode": mode,
                "status_fault": fault,
                "prearm_passed": bool(prearm.get("passed", False)),
                "recent_preflight_ok": bool(preflight_ok),
                "overwatch_score_pct": latest_overwatch_score_pct,
            },
        }

    def _report_design_observation(
        *,
        session_key: str,
        success: bool,
        source: str,
        note: str,
        profile_id: str = "",
        profile_label: str = "",
        sketch_revision: str = "",
        sketch_hash: str = "",
        test_type: str = "",
    ) -> Dict[str, Any]:
        fw_status = firmware.status()
        fw_defaults = (
            (fw_status.get("defaults", {}) or {}) if isinstance(fw_status, dict) else {}
        )
        runtime = _current_runtime_identity()
        observation = {
            "runtime_version": runtime.get("runtime_version", ""),
            "tune_version": runtime.get("tune_version", ""),
            "ident": runtime.get("ident", ""),
            "hash": runtime.get("hash", ""),
            "profile_id": str(profile_id or "").strip(),
            "profile_label": str(profile_label or "").strip(),
            "sketch_revision": str(sketch_revision or "").strip(),
            "sketch_hash": str(sketch_hash or "").strip() or _current_sketch_hash(),
            "test_type": str(test_type or "").strip(),
            "fqbn": str(fw_defaults.get("fqbn", "") or "").strip(),
            "port": str(fw_defaults.get("port", "") or "").strip(),
            "evidence": _design_evidence_snapshot(),
        }
        return design_memory.report(
            session_key=session_key,
            observation=observation,
            success=bool(success),
            source=source,
            note=note,
        )

    def _active_robot_profile() -> Optional[Dict[str, Any]]:
        state = profiles.list()
        active_id = str(state.get("active_profile_id") or "").strip()
        if not active_id:
            return None
        return next(
            (
                p
                for p in list(state.get("profiles") or [])
                if isinstance(p, dict)
                and str(p.get("profile_id", "")).strip() == active_id
            ),
            None,
        )

    def _burst_threshold_defaults(
        active_profile: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        # Nano compatibility lane: trigger-early defaults so brief runaway events are captured.
        out = {
            "freq_hz": 25.0,
            "trigger_enabled": True,
            "prebuffer_lines": 40,
            "trigger_angle_deg": 4.5,
            "trigger_out_frac": 0.55,
            "trigger_runaway": 0.18,
            "post_trigger_lines": 100,
            "profile_family": "arduino_avr",
        }
        if not isinstance(active_profile, dict):
            return out
        board = active_profile.get("board")
        if not isinstance(board, dict):
            return out
        profile_fqbn = str(board.get("fqbn", "")).strip()
        fam = _family_for_fqbn(profile_fqbn, firmware.list_targets()) or "arduino_avr"
        out["profile_family"] = fam
        if fam in {"esp32", "rp2040", "teensy"}:
            out.update(
                {
                    "freq_hz": 40.0,
                    "prebuffer_lines": 36,
                    "trigger_angle_deg": 5.0,
                    "trigger_out_frac": 0.85,
                    "trigger_runaway": 0.45,
                    "post_trigger_lines": 36,
                }
            )
        firmware_node = active_profile.get("firmware")
        if isinstance(firmware_node, dict):
            tm = str(firmware_node.get("telemetry_mode", "")).strip().lower()
            if tm == "binary_highrate" and fam == "arduino_avr":
                # Guard against impossible profile claims on Nano-class boards.
                out["profile_family"] = "arduino_avr/compat"
            if tm == "binary_highrate" and fam in {"esp32", "rp2040", "teensy"}:
                out.update(
                    {"freq_hz": 50.0, "prebuffer_lines": 40, "post_trigger_lines": 40}
                )
        return out

    def burst_status() -> Dict[str, Any]:
        lines = gateway.recent_lines(800)
        burst_events = [ln for ln in lines if ln.startswith("BURSTCSV")]
        csv_recent = sum(1 for ln in lines if ln.startswith("CSV,"))
        host = host_capture.status()
        state = "idle"
        if burst_events:
            last = burst_events[-1]
            if "DONE" in last:
                state = "done"
            elif "CANCELED" in last:
                state = "canceled"
            elif "STABLE" in last:
                state = "stable"
            elif "ARMED" in last:
                state = "armed"
        else:
            hs = str(host.get("state", "idle"))
            if hs in {"armed", "capturing", "done", "failed"}:
                state = hs
        return {
            "state": state,
            "last_event": burst_events[-1] if burst_events else None,
            "events_recent": burst_events[-12:],
            "csv_recent": csv_recent,
            "host_capture": host,
        }

    def tooling_trace_candidates() -> list[str]:
        paths: list[pathlib.Path] = []
        for pat in (
            "app/bridge/tests/fixtures/trace_replay_*.csv",
            "tests/results/run_*.csv",
            "tests/results/host_run_*.csv",
            "tests/results/*.csv",
        ):
            paths.extend(repo_root.glob(pat))
        uniq = sorted({str(p.relative_to(repo_root)) for p in paths if p.exists()})
        return uniq[-80:]

    def history_with_reply(
        history: list[Dict[str, Any]], reply: str
    ) -> list[Dict[str, Any]]:
        out = list(history)
        for i in range(len(out) - 1, -1, -1):
            node = out[i]
            if str(node.get("role", "")) == "assistant":
                repl = dict(node)
                repl["text"] = reply
                out[i] = repl
                break
        return out

    def sync_hardware_context(
        session_key: str, body: Dict[str, Any], ctx: Dict[str, Any]
    ) -> Dict[str, Any]:
        update_info: Dict[str, Any] = {
            "accepted": False,
            "changed": False,
            "initial": False,
        }
        if "hardware_context" in body:
            update_info = hw_context_store.upsert(
                session_key, body.get("hardware_context")
            )
        stored_ctx = hw_context_store.get(session_key)
        if isinstance(stored_ctx, dict):
            ctx["hardware_context"] = stored_ctx
        notice = _format_hardware_context_notice(stored_ctx, update_info)
        return {"update": update_info, "notice": notice}

    def _clean_tool_call(
        *,
        name: str,
        arguments: Dict[str, Any],
        ok: bool,
        data: Optional[Dict[str, Any]] = None,
        error: str = "",
        started_ms: int = 0,
    ) -> Dict[str, Any]:
        return clean_tool_call(
            name=name,
            arguments=arguments,
            ok=ok,
            data=data,
            error=error,
            started_ms=started_ms,
        )

    def _run_clean_auto_tools(
        *,
        message: str,
        model: str,
    ) -> list[Dict[str, Any]]:
        _ = model
        return run_clean_auto_tools(
            message=message,
            gateway=gateway,
            firmware=firmware,
            repo_root=repo_root,
            default_sketch_path_fn=_clean_default_sketch_path,
            default_fqbn_fn=_clean_default_fqbn,
            run_connect_probe_fn=run_connect_probe,
            run_compat_probe_fn=run_compat_probe,
        )

    def _build_clean_agent_context(
        *,
        mode: str,
        session_key: str,
        thread_id: Optional[str],
        attachments: Optional[list[Dict[str, Any]]] = None,
        clean_tool_calls: Optional[list[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        return build_clean_agent_context(
            mode=mode,
            session_key=session_key,
            thread_id=thread_id,
            attachments=attachments,
            clean_tool_calls=clean_tool_calls,
            gateway=gateway,
            firmware=firmware,
            setup_attempt_history=setup_attempt_history,
            ai=ai,
            extract_mission_facts_fn=_extract_mission_facts,
            mission_memory=mission_memory,
            knowledge=knowledge,
            config_history=config_history,
            control=control,
            assistant_capabilities_context_fn=_assistant_capabilities_context,
            best_known_design=design_memory.best(session_key=session_key),
        )

    def _clean_system_prompt(mode: str) -> str:
        return build_clean_system_prompt(
            mode=mode,
            agent_mode_system_prompt_fn=_agent_mode_system_prompt,
        )

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: Any) -> None:
            return

        def do_OPTIONS(self) -> None:
            _json(self, 200, {"ok": True})

        def do_GET(self) -> None:
            try:
                u = urlparse(self.path)
                if u.path == "/health":
                    code, payload = handle_health(
                        gateway=gateway,
                        control=control,
                        prearm_safety=prearm_safety,
                        telemetry_port=telemetry_port,
                        telemetry_enabled=websockets is not None,
                    )
                    return _json(self, code, payload)
                if u.path == "/status":
                    code, payload = handle_status(
                        gateway=gateway,
                        control=control,
                        prearm_safety=prearm_safety,
                        normalize_status_fn=_normalize_status_for_hud,
                        resolve_action_gates_fn=_resolve_action_gates,
                    )
                    return _json(self, code, payload)
                if u.path == "/telemetry/adapter-map":
                    st_raw = dict(gateway.health().get("last_status", {}))
                    normalized = _normalize_status_for_hud(st_raw)
                    return _json(
                        self,
                        200,
                        build_telemetry_adapters_payload(
                            adapter=normalized.get("adapter", {}),
                            adapters=RUNTIME_TELEMETRY_ADAPTERS,
                            canonical_fields=list(HUD_CANONICAL_FIELDS),
                        ),
                    )
                if u.path == "/diag/serial":
                    return _json(
                        self,
                        200,
                        build_diag_serial_payload(
                            serial=gateway.health(),
                            control=control.snapshot(),
                        ),
                    )
                if u.path == "/lines":
                    q = parse_qs(u.query)
                    n = int(q.get("n", ["100"])[0])
                    return _json(
                        self,
                        200,
                        build_lines_payload(lines=gateway.recent_lines(n)),
                    )
                if u.path == "/burst/status":
                    return _json(
                        self,
                        200,
                        build_burst_status_payload(burst=burst_status()),
                    )
                if u.path == "/commissioning/status":
                    return _json(
                        self,
                        200,
                        build_commissioning_status_payload(
                            commissioning=commissioning.status()
                        ),
                    )
                if u.path == "/commissioning/artifacts":
                    return _json(
                        self,
                        200,
                        build_commissioning_artifacts_payload(
                            artifacts=commissioning.artifacts()
                        ),
                    )
                if u.path == "/firmware/status":
                    code, payload = handle_firmware_status_get(firmware=firmware)
                    return _json(self, code, payload)
                if u.path == "/firmware/artifacts":
                    q = parse_qs(u.query)
                    code, payload = handle_firmware_artifacts_get(
                        firmware=firmware, query=q
                    )
                    return _json(self, code, payload)
                if u.path == "/design-memory":
                    q = parse_qs(u.query)
                    n_raw = str((q.get("limit") or ["30"])[0]).strip()
                    session_key = str((q.get("session_key") or [""])[0]).strip()
                    profile_id = str((q.get("profile_id") or [""])[0]).strip()
                    try:
                        n = int(n_raw)
                    except Exception:
                        n = 30
                    rows = design_memory.list_recent(limit=n)
                    if session_key:
                        rows = [
                            r
                            for r in rows
                            if str(r.get("last_session_key", "")).strip() == session_key
                        ]
                    if profile_id:
                        rows = [
                            r
                            for r in rows
                            if str(r.get("profile_id", "")).strip() == profile_id
                        ]
                    return _json(
                        self,
                        200,
                        build_design_memory_payload(design_memory=rows),
                    )
                if u.path == "/design-memory/best":
                    q = parse_qs(u.query)
                    session_key = str((q.get("session_key") or [""])[0]).strip()
                    profile_id = str((q.get("profile_id") or [""])[0]).strip()
                    return _json(
                        self,
                        200,
                        build_design_memory_best_payload(
                            best_design=design_memory.best(
                                session_key=session_key,
                                profile_id=profile_id,
                            )
                        ),
                    )
                if u.path == "/firmware/unified-schema":
                    code, payload = handle_firmware_unified_schema_get(firmware=firmware)
                    return _json(self, code, payload)
                if u.path == "/ai/status":
                    tok = _extract_auth_token(self)
                    me = auth.me(tok)
                    if not me:
                        return _json(
                            self,
                            200,
                            build_ai_status_payload(
                                ai_status=ai.status(
                                    configured=False,
                                    model="gpt-5-codex",
                                    session_key="anon",
                                ),
                                history=[],
                                threads=[],
                            ),
                        )
                    model = str(me.get("openai_model") or "gpt-5-codex")
                    configured = bool(me.get("openai_configured"))
                    skey = f"user:{me['id']}"
                    st = ai.status(configured=configured, model=model, session_key=skey)
                    tid = st.get("active_thread_id")
                    return _json(
                        self,
                        200,
                        build_ai_status_payload(
                            ai_status=st,
                            history=ai.history(skey, tid)[-80:],
                            threads=ai.list_threads(skey),
                        ),
                    )
                if u.path == "/agent/status":
                    tok = _extract_auth_token(self)
                    me = auth.me(tok) if tok else None
                    user_creds = (
                        auth.get_openai_key(int(me["id"]))
                        if me and isinstance(me.get("id"), int)
                        else None
                    )
                    mode_state = agent_mission.status()
                    resolved = provider_router.resolve_agent_runtime(
                        mode=str(mode_state.get("mode", "robot_dev")),
                        requested_api_key=None,
                        requested_model=None,
                        user_creds=user_creds,
                        env_api_key=ai.default_api_key,
                        env_model=os.environ.get("OPENAI_MODEL", ""),
                    )
                    codex_login = _codex_cli_login_status()
                    use_codex_cli = bool(codex_login.get("logged_in", False))
                    has_api_key = bool(str(resolved.get("api_key", "")).strip())
                    runtime_exec = _agent_choose_executor(
                        mode=str(mode_state.get("mode", "robot_dev")),
                        enable_tools=True,
                        has_api_key=has_api_key,
                        codex_logged_in=use_codex_cli,
                        codex_agent_available=bool(codex_agent is not None),
                    )
                    runtime_model = _agent_resolve_model(
                        str(mode_state.get("mode", "robot_dev")),
                        str(resolved.get("model", "")),
                        prefer_codex=use_codex_cli,
                    )
                    runtime_model_allowed = (
                        True if use_codex_cli else _agent_model_allowed(runtime_model)
                    )
                    runtime_configured = has_api_key or bool(use_codex_cli)
                    serial_h = gateway.health()
                    payload = build_agent_status_payload(
                        mode_state=mode_state,
                        resolved=resolved,
                        codex_login=codex_login,
                        runtime_exec=runtime_exec,
                        runtime_model=runtime_model,
                        runtime_model_allowed=runtime_model_allowed,
                        runtime_configured=runtime_configured,
                        serial_health=serial_h,
                        control_snapshot=control.snapshot(),
                        knowledge_context=knowledge.context(),
                        lines=gateway.recent_lines(80),
                    )
                    return _json(self, 200, payload)
                if u.path == "/agent/clean/status":
                    mode = (
                        str(
                            (parse_qs(u.query).get("mode", ["app_dev"]) or ["app_dev"])[
                                0
                            ]
                            or "app_dev"
                        ).strip()
                        or "app_dev"
                    )
                    codex_login = _codex_cli_login_status()
                    serial_h = gateway.health()
                    control_state = control.snapshot()
                    model = (
                        str(
                            os.environ.get("UPRIGHT_CLEAN_MODEL", "gpt-5-codex")
                        ).strip()
                        or "gpt-5-codex"
                    )
                    payload = build_clean_status_payload(
                        mode=mode,
                        codex_login=codex_login,
                        serial_health=serial_h,
                        control_snapshot=control_state,
                        model=model,
                        lines=gateway.recent_lines(80),
                    )
                    return _json(self, 200, payload)
                if u.path == "/agent/clean/threads":
                    q = parse_qs(u.query)
                    mode = (
                        str((q.get("mode", ["app_dev"]) or ["app_dev"])[0]).strip()
                        or "app_dev"
                    )
                    payload = handle_clean_threads_get(
                        mode=mode,
                        ai=ai,
                        codex_logged_in=bool(
                            _codex_cli_login_status().get("logged_in", False)
                        ),
                        model=str(os.environ.get("UPRIGHT_CLEAN_MODEL", "gpt-5-codex")),
                    )
                    return _json(self, 200, payload)
                if u.path == "/agent/threads":
                    guard = _legacy_execution_guard(u.path)
                    if guard is not None:
                        return _json(self, 403, guard)
                    q = parse_qs(u.query)
                    mode_state = agent_mission.status()
                    mode = str((q.get("mode", [""]) or [""])[0] or "").strip() or str(
                        mode_state.get("mode", "robot_dev")
                    )
                    tok = _extract_auth_token(self)
                    me = auth.me(tok) if tok else None
                    user_creds = (
                        auth.get_openai_key(int(me["id"]))
                        if me and isinstance(me.get("id"), int)
                        else None
                    )
                    session_key = (
                        f"user:{me['id']}:agent:{mode}"
                        if me and isinstance(me.get("id"), int)
                        else f"local:{mode}"
                    )
                    resolved = provider_router.resolve_agent_runtime(
                        mode=mode,
                        requested_api_key=None,
                        requested_model=None,
                        user_creds=user_creds,
                        env_api_key=ai.default_api_key,
                        env_model=os.environ.get("OPENAI_MODEL", ""),
                    )
                    codex_login = _codex_cli_login_status()
                    use_codex_cli = bool(codex_login.get("logged_in", False))
                    runtime_model = _agent_resolve_model(
                        mode,
                        str(resolved.get("model", "")),
                        prefer_codex=use_codex_cli,
                    )
                    runtime_configured = bool(resolved.get("api_key")) or bool(
                        use_codex_cli
                    )
                    return _json(
                        self,
                        200,
                        build_agent_status_payload(
                            agent=mode_state,
                            threads=ai.list_threads(session_key),
                            ai=ai.status(
                                configured=runtime_configured,
                                model=runtime_model or "(unset)",
                                session_key=session_key,
                            ),
                        ),
                    )
                if u.path == "/ai/threads":
                    tok = _extract_auth_token(self)
                    me = auth.me(tok)
                    if not me:
                        return _json(
                            self, 401, {"ok": False, "error": "unauthenticated"}
                        )
                    skey = f"user:{me['id']}"
                    return _json(
                        self,
                        200,
                        build_ai_threads_status_payload(
                            threads=ai.list_threads(skey),
                            ai=ai.status(
                                configured=bool(me.get("openai_configured")),
                                model=str(me.get("openai_model") or "gpt-5-codex"),
                                session_key=skey,
                            ),
                        ),
                    )
                if u.path == "/ai/profiles":
                    tok = _extract_auth_token(self)
                    me = auth.me(tok)
                    if not me:
                        return _json(
                            self, 401, {"ok": False, "error": "unauthenticated"}
                        )
                    return _json(
                        self,
                        200,
                        build_ai_profiles_payload(profiles=ai_profiles.list()),
                    )
                if u.path == "/ai/knowledge":
                    tok = _extract_auth_token(self)
                    me = auth.me(tok)
                    if not me:
                        return _json(
                            self, 401, {"ok": False, "error": "unauthenticated"}
                        )
                    return _json(
                        self,
                        200,
                        build_ai_knowledge_payload(knowledge=knowledge.context()),
                    )
                if u.path == "/auth/me":
                    tok = _extract_auth_token(self)
                    me = auth.me(tok)
                    if not me:
                        return _json(
                            self, 401, {"ok": False, "error": "unauthenticated"}
                        )
                    return _json(self, 200, build_auth_user_payload(user=me))
                if u.path == "/auth/openai-key/status":
                    tok = _extract_auth_token(self)
                    me = auth.me(tok)
                    if not me:
                        return _json(
                            self, 401, {"ok": False, "error": "unauthenticated"}
                        )
                    user_creds = auth.get_openai_key(int(me["id"]))
                    runtime_key = str(
                        (user_creds or {}).get("api_key")
                        or os.environ.get("OPENAI_API_KEY")
                        or ""
                    ).strip()
                    runtime_source = (
                        "user"
                        if user_creds and user_creds.get("api_key")
                        else ("env" if os.environ.get("OPENAI_API_KEY") else None)
                    )
                    return _json(
                        self,
                        200,
                        build_openai_config_payload(
                            configured=bool(me.get("openai_configured")),
                            model=me.get("openai_model"),
                            runtime_has_key=bool(runtime_key),
                            runtime_key_source=runtime_source,
                        ),
                    )
                if u.path == "/firmware/sketch":
                    q = parse_qs(u.query)
                    code, payload = handle_firmware_sketch_get(
                        firmware=firmware, query=q
                    )
                    return _json(self, code, payload)
                if u.path == "/firmware/boards":
                    code, payload = handle_firmware_boards_get(firmware=firmware)
                    return _json(self, code, payload)
                if u.path == "/firmware/targets":
                    code, payload = handle_firmware_targets_get(firmware=firmware)
                    return _json(self, code, payload)
                if u.path == "/firmware/runtime-manifest/validate":
                    q = parse_qs(u.query)
                    code, payload = handle_firmware_runtime_manifest_validate_get(
                        firmware=firmware, query=q
                    )
                    return _json(self, code, payload)
                if u.path == "/firmware/runtime-manifest/compat":
                    q = parse_qs(u.query)
                    code, payload = handle_firmware_runtime_manifest_compat_get(
                        firmware=firmware,
                        profiles=profiles,
                        query=q,
                        compatibility_fn=_runtime_manifest_profile_compatibility,
                    )
                    return _json(self, code, payload)
                if u.path == "/firmware/sketch-folders":
                    code, payload = handle_firmware_sketch_folders_get(firmware=firmware)
                    return _json(self, code, payload)
                if u.path == "/probe/compat":
                    q = parse_qs(u.query)
                    requested_profile = str(
                        (q.get("profile", [""]) or [""])[0] or ""
                    ).strip()
                    cache_key = (
                        f"compat:{requested_profile}" if requested_profile else "compat"
                    )
                    cached = cached_probe(cache_key)
                    if cached is not None:
                        return _json(
                            self, 200, build_compat_probe_payload(compat=cached)
                        )
                    # Throttle probe pressure when queue is already busy.
                    if int(gateway.health().get("queue_depth", 0) or 0) > 2:
                        fallback = {
                            "ok": False,
                            "profile": "unknown",
                            "firmware_id": None,
                            "required_fields": [],
                            "missing_fields": [],
                            "supported_commands": [],
                            "missing_commands": [],
                            "warnings": ["compat_probe_throttled_queue_busy"],
                        }
                        return _json(
                            self, 200, build_compat_probe_payload(compat=fallback)
                        )
                    out = run_compat_probe(
                        gateway, profile_override=requested_profile or None
                    )
                    store_probe(cache_key, out)
                    return _json(self, 200, build_compat_probe_payload(compat=out))
                if u.path == "/probe/connect":
                    cached = cached_probe("connect")
                    if cached is not None:
                        return _json(self, 200, build_probe_payload(probe=cached))
                    if int(gateway.health().get("queue_depth", 0) or 0) > 2:
                        fallback = {
                            "ok": False,
                            "connected": bool(gateway.health().get("connected", False)),
                            "port": str(gateway.health().get("port", "")),
                            "baud": int(gateway.health().get("baud", 0) or 0),
                            "port_meta": _get_port_meta(
                                str(gateway.health().get("port", ""))
                            ),
                            "mcu_guess": "unknown",
                            "firmware_profile": "unknown",
                            "confidence_pct": 0,
                            "status_schema_ok": False,
                            "status_error": None,
                            "components": {
                                "imu": False,
                                "motor_driver": False,
                                "encoder_feedback": False,
                                "voltage_telemetry": False,
                                "wheel_model": False,
                                "persistent_calibration": False,
                            },
                            "commands": [],
                            "missing_commands": [],
                            "warnings": ["connect_probe_throttled_queue_busy"],
                            "next_questions": [],
                            "compat": None,
                            "tuning_capabilities": _detect_tuning_capabilities(
                                {}, [], []
                            ),
                        }
                        return _json(self, 200, build_probe_payload(probe=fallback))
                    out = run_connect_probe(gateway)
                    store_probe("connect", out)
                    return _json(self, 200, build_probe_payload(probe=out))
                if u.path == "/tooling/tuning/capabilities":
                    cached_connect = cached_probe("connect")
                    if isinstance(cached_connect, dict) and isinstance(
                        cached_connect.get("tuning_capabilities"), dict
                    ):
                        return _json(
                            self,
                            200,
                            build_capabilities_payload(
                                capabilities=cached_connect.get("tuning_capabilities"),
                                source="connect_probe_cache",
                            ),
                        )
                    cached_compat = cached_probe("compat")
                    if isinstance(cached_compat, dict) and isinstance(
                        cached_compat.get("tuning_capabilities"), dict
                    ):
                        return _json(
                            self,
                            200,
                            build_capabilities_payload(
                                capabilities=cached_compat.get("tuning_capabilities"),
                                source="compat_probe_cache",
                            ),
                        )

                    status = dict(gateway.health().get("last_status", {}))
                    if not status:
                        try:
                            status = gateway.get_status()
                        except Exception:
                            status = {}
                    caps = _detect_tuning_capabilities(status, [], [])
                    return _json(
                        self,
                        200,
                        build_capabilities_payload(
                            capabilities=caps, source="status_only"
                        ),
                    )
                if u.path == "/overwatch/status":
                    q = parse_qs(u.query)
                    force_refresh = str(
                        (q.get("refresh", ["0"]) or ["0"])[0]
                    ).strip().lower() in {"1", "true", "yes"}
                    if not force_refresh:
                        cached = cached_probe("overwatch")
                        if cached is not None:
                            return _json(
                                self, 200, build_overwatch_payload(overwatch=cached)
                            )

                    compat = cached_probe("compat")
                    if compat is None:
                        if int(gateway.health().get("queue_depth", 0) or 0) <= 2:
                            try:
                                compat = run_compat_probe(gateway)
                                store_probe("compat", compat)
                            except Exception:
                                compat = {
                                    "ok": False,
                                    "missing_commands": [],
                                    "missing_fields": [],
                                }
                        else:
                            compat = {
                                "ok": False,
                                "missing_commands": [],
                                "missing_fields": [],
                            }

                    connect = cached_probe("connect")
                    if connect is None:
                        if int(gateway.health().get("queue_depth", 0) or 0) <= 2:
                            try:
                                connect = run_connect_probe(gateway)
                                store_probe("connect", connect)
                            except Exception:
                                connect = {"ok": False, "confidence_pct": 0}
                        else:
                            connect = {"ok": False, "confidence_pct": 0}

                    report = build_overwatch_report(
                        gateway=gateway,
                        firmware=firmware,
                        compat=compat if isinstance(compat, dict) else None,
                        connect=connect if isinstance(connect, dict) else None,
                    )
                    store_probe("overwatch", report)
                    return _json(self, 200, build_overwatch_payload(overwatch=report))
                if u.path == "/v1/setup/attempt-history":
                    q = parse_qs(u.query)
                    limit = int((q.get("limit", ["40"]) or ["40"])[0] or 40)
                    cursor = str((q.get("cursor", [""]) or [""])[0] or "")
                    kind = str((q.get("kind", ["all"]) or ["all"])[0] or "all")
                    page = setup_attempt_history.list_recent_page(
                        limit=limit, cursor_attempt_id=cursor, kind=kind
                    )
                    return _json(
                        self,
                        200,
                        build_attempt_history_payload(
                            attempts=page.get("attempts", []),
                            next_cursor=page.get("next_cursor", ""),
                            has_more=bool(page.get("has_more", False)),
                        ),
                    )
                if u.path == "/profiles":
                    code, payload = handle_profiles_list(profiles=profiles)
                    return _json(self, code, payload)
                if u.path == "/profiles/hardware":
                    code, payload = handle_profiles_hardware(
                        firmware=firmware,
                        build_hardware_registry_fn=_build_hardware_registry,
                    )
                    return _json(self, code, payload)
                if u.path == "/tooling/traces":
                    return _json(
                        self,
                        200,
                        build_tooling_traces_payload(traces=tooling_trace_candidates()),
                    )
                if u.path == "/ai/metrics":
                    tok = _extract_auth_token(self)
                    me = auth.me(tok)
                    if not me:
                        return _json(
                            self, 401, {"ok": False, "error": "unauthenticated"}
                        )
                    q = parse_qs(u.query)
                    since_hours = float(
                        (q.get("since_hours", ["24"]) or ["24"])[0] or 24
                    )
                    since_ts = (
                        time.time() - (since_hours * 3600) if since_hours > 0 else None
                    )
                    tool_filter = str((q.get("tool", [""]) or [""])[0]).strip() or None
                    db = get_codex_db()
                    try:
                        tool_metrics = db.get_tool_metrics(
                            since_ts=since_ts, tool_filter=tool_filter
                        )
                        db_stats = db.get_stats()
                        return _json(
                            self,
                            200,
                            build_tool_metrics_payload(
                                since_hours=since_hours,
                                tool_metrics=tool_metrics,
                                db_stats=db_stats,
                                ts=time.time(),
                            ),
                        )
                    except Exception as exc:
                        logger.warning(f"Metrics fetch error: {exc}")
                        return _json(
                            self, 500, {"ok": False, "error": f"metrics_error: {exc}"}
                        )
                if u.path == "/ai/rag/stats":
                    tok = _extract_auth_token(self)
                    me = auth.me(tok)
                    if not me:
                        return _json(
                            self, 401, {"ok": False, "error": "unauthenticated"}
                        )
                    try:
                        if not get_codex_rag:
                            return _json(
                                self, 503, {"ok": False, "error": "rag_not_available"}
                            )
                        user_creds = auth.get_openai_key(int(me["id"]))
                        openai_key = str(
                            (user_creds or {}).get("api_key")
                            or os.environ.get("OPENAI_API_KEY")
                            or ""
                        ).strip()
                        rag = get_codex_rag(openai_key)
                        stats = rag.get_index_stats()
                        return _json(
                            self,
                            200,
                            build_stats_payload(stats=stats, ts=time.time()),
                        )
                    except Exception as exc:
                        logger.warning(f"RAG stats error: {exc}")
                        return _json(
                            self, 500, {"ok": False, "error": f"rag_stats_error: {exc}"}
                        )
                if u.path == "/config/snapshots":
                    q = parse_qs(u.query)
                    limit = int((q.get("limit", ["30"]) or ["30"])[0] or 30)
                    return _json(
                        self,
                        200,
                        build_snapshots_payload(
                            snapshots=config_history.list_snapshots(limit=limit)
                        ),
                    )
                return _json(self, 404, {"ok": False, "error": "not_found"})
            except Exception as exc:
                return _json(self, 500, {"ok": False, "error": str(exc)})

        def do_POST(self) -> None:
            try:
                u = urlparse(self.path)
                body = _read_json(self)

                if u.path == "/auth/register":
                    email = str(body.get("email", ""))
                    password = str(body.get("password", ""))
                    out = auth.register(email, password)
                    return _json(
                        self,
                        200,
                        build_auth_session_payload(
                            session_token=out["session_token"], user=out["user"]
                        ),
                    )

                if u.path == "/auth/login":
                    email = str(body.get("email", ""))
                    password = str(body.get("password", ""))
                    out = auth.login(email, password)
                    return _json(
                        self,
                        200,
                        build_auth_session_payload(
                            session_token=out["session_token"], user=out["user"]
                        ),
                    )

                if u.path == "/auth/password-reset/request":
                    email = str(body.get("email", ""))
                    out = auth.request_password_reset(email)
                    return _json(self, 200, build_reset_payload(reset=out))

                if u.path == "/auth/password-reset/confirm":
                    email = str(body.get("email", ""))
                    token = str(body.get("token", ""))
                    new_password = str(body.get("new_password", ""))
                    auth.reset_password(email, token, new_password)
                    return _json(
                        self, 200, build_result_payload(result="password_reset")
                    )

                if u.path == "/auth/logout":
                    tok = _extract_auth_token(self, body)
                    auth.logout(tok)
                    return _json(self, 200, {"ok": True})

                if u.path == "/ai/thread/new":
                    tok = _extract_auth_token(self, body)
                    me = auth.me(tok)
                    if not me:
                        return _json(
                            self, 401, {"ok": False, "error": "unauthenticated"}
                        )
                    skey = f"user:{me['id']}"
                    created = ai.create_thread(skey, title=body.get("title"))
                    st = ai.status(
                        configured=bool(me.get("openai_configured")),
                        model=str(me.get("openai_model") or "gpt-5-codex"),
                        session_key=skey,
                    )
                    return _json(
                        self,
                        200,
                        build_ai_thread_payload(
                            thread=created,
                            threads=ai.list_threads(skey),
                            ai_status=st,
                            history=ai.history(skey, st.get("active_thread_id"))[-80:],
                        ),
                    )

                if u.path == "/ai/thread/select":
                    tok = _extract_auth_token(self, body)
                    me = auth.me(tok)
                    if not me:
                        return _json(
                            self, 401, {"ok": False, "error": "unauthenticated"}
                        )
                    thread_id = str(body.get("thread_id", "")).strip()
                    if not thread_id:
                        return _json(
                            self, 400, {"ok": False, "error": "thread_id_required"}
                        )
                    skey = f"user:{me['id']}"
                    selected = ai.select_thread(skey, thread_id)
                    st = ai.status(
                        configured=bool(me.get("openai_configured")),
                        model=str(me.get("openai_model") or "gpt-5-codex"),
                        session_key=skey,
                    )
                    return _json(
                        self,
                        200,
                        build_ai_thread_payload(
                            thread=selected,
                            threads=ai.list_threads(skey),
                            ai_status=st,
                            history=ai.history(skey, thread_id)[-80:],
                        ),
                    )

                if u.path == "/ai/profile/save":
                    tok = _extract_auth_token(self, body)
                    me = auth.me(tok)
                    if not me:
                        return _json(
                            self, 401, {"ok": False, "error": "unauthenticated"}
                        )
                    return _json(
                        self,
                        403,
                        {
                            "ok": False,
                            "error": "ai_profile_edit_locked",
                            "hint": "Assistant profiles are managed via local repository edits only.",
                        },
                    )

                if u.path == "/ai/profile/activate":
                    tok = _extract_auth_token(self, body)
                    me = auth.me(tok)
                    if not me:
                        return _json(
                            self, 401, {"ok": False, "error": "unauthenticated"}
                        )
                    return _json(
                        self,
                        403,
                        {
                            "ok": False,
                            "error": "ai_profile_edit_locked",
                            "hint": "Assistant profiles are managed via local repository edits only.",
                        },
                    )

                if u.path == "/auth/openai-key":
                    tok = _extract_auth_token(self, body)
                    me = auth.me(tok)
                    if not me:
                        return _json(
                            self, 401, {"ok": False, "error": "unauthenticated"}
                        )
                    api_key = str(body.get("api_key", ""))
                    model = str(body.get("model", "gpt-5-codex"))
                    out = auth.set_openai_key(int(me["id"]), api_key, model)
                    return _json(
                        self, 200, build_auth_openai_status_payload(openai=out)
                    )

                if u.path == "/auth/openai-key/delete":
                    tok = _extract_auth_token(self, body)
                    me = auth.me(tok)
                    if not me:
                        return _json(
                            self, 401, {"ok": False, "error": "unauthenticated"}
                        )
                    out = auth.clear_openai_key(int(me["id"]))
                    return _json(
                        self, 200, build_auth_openai_status_payload(openai=out)
                    )

                if u.path == "/session/heartbeat":
                    return _json(
                        self,
                        200,
                        build_session_heartbeat_payload(control=control.heartbeat()),
                    )

                if u.path == "/design-memory/report-success":
                    session_key = (
                        str(body.get("session_key", "")).strip() or "local:app_dev"
                    )
                    source = (
                        str(body.get("source", "user_report")).strip() or "user_report"
                    )
                    note = str(body.get("note", "")).strip()
                    success = bool(body.get("success", True))
                    profile_id = str(body.get("profile_id", "")).strip()
                    profile_label = str(body.get("profile_label", "")).strip()
                    sketch_revision = str(body.get("sketch_revision", "")).strip()
                    sketch_hash = str(body.get("sketch_hash", "")).strip()
                    test_type = str(body.get("test_type", "")).strip()
                    observation = (
                        body.get("observation")
                        if isinstance(body.get("observation"), dict)
                        else {}
                    )
                    if not observation:
                        fw_status = firmware.status()
                        fw_defaults = (
                            fw_status.get("defaults", {})
                            if isinstance(fw_status, dict)
                            else {}
                        )
                        runtime = _current_runtime_identity()
                        observation = {
                            "runtime_version": runtime.get("runtime_version", ""),
                            "tune_version": runtime.get("tune_version", ""),
                            "ident": runtime.get("ident", ""),
                            "hash": runtime.get("hash", ""),
                            "profile_id": profile_id,
                            "profile_label": profile_label,
                            "sketch_revision": sketch_revision,
                            "sketch_hash": sketch_hash or _current_sketch_hash(),
                            "test_type": test_type,
                            "fqbn": str(fw_defaults.get("fqbn", "") or "").strip(),
                            "port": str(fw_defaults.get("port", "") or "").strip(),
                            "evidence": _design_evidence_snapshot(),
                        }
                    elif not isinstance(observation.get("evidence"), dict):
                        observation["evidence"] = _design_evidence_snapshot()
                    row = design_memory.report(
                        session_key=session_key,
                        observation=observation,
                        success=success,
                        source=source,
                        note=note,
                    )
                    return _json(self, 200, build_design_payload(design=row))

                if u.path == "/design-memory/rate":
                    session_key = (
                        str(body.get("session_key", "")).strip() or "local:app_dev"
                    )
                    design_id = str(body.get("design_id", "")).strip()
                    rating = str(body.get("rating", "")).strip().lower()
                    note = str(body.get("note", "")).strip()
                    try:
                        row = design_memory.rate(
                            design_id=design_id,
                            rating=rating,
                            note=note,
                            source="user_rating",
                            session_key=session_key,
                        )
                    except RuntimeError as exc:
                        err = str(exc)
                        if err == "design_not_found":
                            return _json(self, 404, {"ok": False, "error": err})
                        return _json(self, 400, {"ok": False, "error": err})
                    return _json(self, 200, build_design_payload(design=row))

                if u.path == "/commissioning/run":
                    code, payload = handle_commissioning_run(
                        body=body,
                        gateway=gateway,
                        commissioning=commissioning,
                    )
                    return _json(self, code, payload)

                if u.path == "/commissioning/step":
                    code, payload = handle_commissioning_step()
                    return _json(self, code, payload)

                if u.path == "/firmware/check":
                    code, payload = handle_firmware_check_post(firmware=firmware)
                    return _json(self, code, payload)

                if u.path == "/firmware/compile":
                    code, payload = handle_firmware_compile(
                        body=body, firmware=firmware
                    )
                    return _json(self, code, payload)

                if u.path == "/firmware/upload":
                    code, payload = handle_firmware_upload(
                        body=body, firmware=firmware, prearm_safety=prearm_safety
                    )
                    return _json(self, code, payload)

                if u.path == "/firmware/upload-guarded":
                    code, payload = handle_firmware_upload_guarded(
                        body=body,
                        firmware=firmware,
                        gateway=gateway,
                        prearm_safety=prearm_safety,
                    )
                    return _json(self, code, payload)

                if u.path == "/firmware/install-cli":
                    code, payload = handle_firmware_install_cli(firmware=firmware)
                    return _json(self, code, payload)

                if u.path == "/firmware/sketch":
                    code, payload = handle_firmware_sketch_write(
                        body=body, firmware=firmware
                    )
                    return _json(self, code, payload)

                if u.path == "/firmware/sketch-folder/pick":
                    code, payload = handle_firmware_sketch_folder_pick(
                        firmware=firmware
                    )
                    return _json(self, code, payload)

                if u.path == "/firmware/generate-unified":
                    code, payload = handle_firmware_generate_unified(
                        body=body, firmware=firmware
                    )
                    return _json(self, code, payload)

                if u.path == "/firmware/generate-docs-pack":
                    code, payload = handle_firmware_generate_docs_pack(
                        body=body, firmware=firmware
                    )
                    return _json(self, code, payload)

                if u.path == "/profiles/validate":
                    code, payload = handle_profiles_validate(
                        body=body, profiles=profiles, gateway=gateway
                    )
                    return _json(self, code, payload)

                if u.path == "/firmware/runtime-manifest/validate":
                    sketch = str(body.get("sketch", "")).strip() or None
                    inline_manifest = body.get("manifest")
                    manifest_obj = (
                        inline_manifest if isinstance(inline_manifest, dict) else None
                    )
                    check = firmware.validate_runtime_manifest(
                        sketch=sketch,
                        manifest=manifest_obj,
                        require_exists=manifest_obj is None,
                    )
                    return _json(
                        self,
                        200,
                        {
                            "ok": bool(check.get("ok", False)),
                            "validation": check,
                        },
                    )

                if u.path == "/v1/setup/compat-test":
                    sketch_revision = str(body.get("sketch_revision", "")).strip()
                    action_source = (
                        str(body.get("action_source", "setup_page")).strip()
                        or "setup_page"
                    )
                    session_key = (
                        str(body.get("session_key", "")).strip() or "local:setup"
                    )
                    profile_id = str(body.get("profile_id", "")).strip()
                    profile_label = str(body.get("profile_label", "")).strip()
                    out = run_setup_compat_test(gateway)
                    attempt = setup_attempt_history.append(
                        test_type="compat",
                        status=str(out.get("status", "unknown")),
                        sketch_revision=sketch_revision,
                        sketch_hash=_current_sketch_hash(),
                        action_source=action_source,
                        profile_id=profile_id,
                        profile_label=profile_label,
                        result=out,
                    )
                    try:
                        _report_design_observation(
                            session_key=session_key,
                            success=str(out.get("status", "")).strip().lower()
                            == "pass",
                            source="setup_compat_test",
                            note=str(out.get("failure_summary", "")).strip(),
                            profile_id=profile_id,
                            profile_label=profile_label,
                            sketch_revision=sketch_revision,
                            sketch_hash=str(attempt.get("sketch_hash", "")).strip(),
                            test_type="compat",
                        )
                    except Exception:
                        pass
                    return _json(
                        self,
                        200,
                        build_setup_check_payload(
                            check_key="compat_test", check_result=out, attempt=attempt
                        ),
                    )

                if u.path == "/v1/setup/smoke-check":
                    sketch_revision = str(body.get("sketch_revision", "")).strip()
                    action_source = (
                        str(body.get("action_source", "setup_page")).strip()
                        or "setup_page"
                    )
                    session_key = (
                        str(body.get("session_key", "")).strip() or "local:setup"
                    )
                    profile_id = str(body.get("profile_id", "")).strip()
                    profile_label = str(body.get("profile_label", "")).strip()
                    out = run_setup_smoke_check(gateway, control)
                    attempt = setup_attempt_history.append(
                        test_type="smoke",
                        status=str(out.get("status", "unknown")),
                        sketch_revision=sketch_revision,
                        sketch_hash=_current_sketch_hash(),
                        action_source=action_source,
                        profile_id=profile_id,
                        profile_label=profile_label,
                        result=out,
                    )
                    try:
                        _report_design_observation(
                            session_key=session_key,
                            success=str(out.get("status", "")).strip().lower()
                            == "pass",
                            source="setup_smoke_check",
                            note=str(out.get("failure_summary", "")).strip(),
                            profile_id=profile_id,
                            profile_label=profile_label,
                            sketch_revision=sketch_revision,
                            sketch_hash=str(attempt.get("sketch_hash", "")).strip(),
                            test_type="smoke",
                        )
                    except Exception:
                        pass
                    return _json(
                        self,
                        200,
                        build_setup_check_payload(
                            check_key="smoke_check", check_result=out, attempt=attempt
                        ),
                    )

                if u.path == "/v1/setup/overwatch-check":
                    sketch_revision = str(body.get("sketch_revision", "")).strip()
                    action_source = (
                        str(body.get("action_source", "setup_page")).strip()
                        or "setup_page"
                    )
                    session_key = (
                        str(body.get("session_key", "")).strip() or "local:setup"
                    )
                    profile_id = str(body.get("profile_id", "")).strip()
                    profile_label = str(body.get("profile_label", "")).strip()
                    out = run_setup_overwatch_check(gateway, firmware)
                    attempt = setup_attempt_history.append(
                        test_type="overwatch",
                        status=str(out.get("status", "unknown")),
                        sketch_revision=sketch_revision,
                        sketch_hash=_current_sketch_hash(),
                        action_source=action_source,
                        profile_id=profile_id,
                        profile_label=profile_label,
                        result=out,
                    )
                    try:
                        _report_design_observation(
                            session_key=session_key,
                            success=str(out.get("status", "")).strip().lower()
                            == "pass",
                            source="setup_overwatch_check",
                            note=str(out.get("failure_summary", "")).strip(),
                            profile_id=profile_id,
                            profile_label=profile_label,
                            sketch_revision=sketch_revision,
                            sketch_hash=str(attempt.get("sketch_hash", "")).strip(),
                            test_type="overwatch",
                        )
                    except Exception:
                        pass
                    return _json(
                        self,
                        200,
                        build_setup_check_payload(
                            check_key="overwatch_check",
                            check_result=out,
                            attempt=attempt,
                        ),
                    )

                if u.path == "/profiles/save":
                    code, payload = handle_profiles_save(body=body, profiles=profiles)
                    return _json(self, code, payload)

                if u.path == "/profiles/activate":
                    code, payload = handle_profiles_activate(
                        body=body, profiles=profiles
                    )
                    return _json(self, code, payload)

                if u.path == "/profiles/delete":
                    code, payload = handle_profiles_delete(body=body, profiles=profiles)
                    return _json(self, code, payload)

                if u.path == "/config/revert":
                    snapshot_id = str(body.get("snapshot_id", "")).strip() or None
                    out = _revert_snapshot(
                        gateway, config_history, snapshot_id=snapshot_id
                    )
                    return _json(
                        self,
                        200,
                        build_revert_control_payload(
                            revert=out, control=control.snapshot()
                        ),
                    )

                if u.path == "/agent/file/upload":
                    try:
                        attachment = _agent_upload_from_body(repo_root, body)
                    except RuntimeError as exc:
                        return _json(self, 400, {"ok": False, "error": str(exc)})
                    except Exception as exc:
                        return _json(self, 500, {"ok": False, "error": str(exc)})
                    return _json(
                        self, 200, build_attachment_payload(attachment=attachment)
                    )

                if u.path == "/agent/clean/file/upload":
                    try:
                        attachment = _agent_upload_from_body(repo_root, body)
                    except RuntimeError as exc:
                        return _json(self, 400, {"ok": False, "error": str(exc)})
                    except Exception as exc:
                        return _json(self, 500, {"ok": False, "error": str(exc)})
                    return _json(
                        self, 200, build_attachment_payload(attachment=attachment)
                    )

                if u.path == "/agent/clean/firmware/compile":
                    inputs = resolve_clean_upload_inputs(
                        body=body,
                        default_sketch=_clean_default_sketch_path(repo_root, firmware),
                        default_fqbn=_clean_default_fqbn(),
                    )
                    code, payload = handle_clean_firmware_compile(
                        firmware=firmware,
                        sketch=str(inputs.get("sketch") or ""),
                        fqbn=str(inputs.get("fqbn") or ""),
                        idempotency_key=inputs.get("idempotency_key"),
                        tool_call_builder=_clean_tool_call,
                    )
                    return _json(self, code, payload)

                if u.path == "/agent/clean/firmware/upload":
                    inputs = resolve_clean_upload_inputs(
                        body=body,
                        default_sketch=_clean_default_sketch_path(repo_root, firmware),
                        default_fqbn=_clean_default_fqbn(),
                    )
                    code, payload = handle_clean_firmware_upload(
                        firmware=firmware,
                        gateway=gateway,
                        prearm_safety=prearm_safety,
                        sketch=str(inputs.get("sketch") or ""),
                        fqbn=str(inputs.get("fqbn") or ""),
                        port=inputs.get("port"),
                        idempotency_key=inputs.get("idempotency_key"),
                        tool_call_builder=_clean_tool_call,
                    )
                    return _json(self, code, payload)

                if u.path == "/agent/clean/firmware/upload/precheck":
                    requested_port = str(body.get("port", "")).strip()
                    requested_fqbn = (
                        str(body.get("fqbn", "")).strip() or _clean_default_fqbn()
                    )
                    requested_sketch = str(
                        body.get("sketch", "")
                    ).strip() or _clean_default_sketch_path(repo_root, firmware)
                    code, payload = handle_clean_upload_precheck(
                        precheck_builder=lambda **kwargs: _clean_upload_precheck_payload(
                            gateway=gateway, firmware=firmware, **kwargs
                        ),
                        requested_port=requested_port,
                        requested_fqbn=requested_fqbn,
                        requested_sketch=requested_sketch,
                    )
                    return _json(self, code, payload)

                if u.path == "/agent/clean/firmware/release-serial":
                    try:
                        confirm = str(body.get("confirm", "")).strip()
                        if confirm != "I_UNDERSTAND_STOP_BRIDGE":
                            return _json(
                                self,
                                400,
                                {
                                    "ok": False,
                                    "error": "release_serial_confirm_required",
                                    "hint": "send confirm=I_UNDERSTAND_STOP_BRIDGE to proceed",
                                },
                            )
                        stop_script = repo_root / "tools" / "stop_bridge.sh"
                        if not stop_script.exists():
                            return _json(
                                self,
                                404,
                                {
                                    "ok": False,
                                    "error": "stop_bridge_script_missing",
                                    "path": str(stop_script),
                                },
                            )
                        subprocess.Popen(
                            [
                                "/bin/bash",
                                "-lc",
                                f"sleep 0.25; '{str(stop_script)}' >/dev/null 2>&1",
                            ],
                            cwd=str(repo_root),
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            start_new_session=True,
                            close_fds=True,
                        )
                        return _json(
                            self,
                            200,
                            build_port_released_payload(
                                released=True,
                                note="bridge stopping in background; use IDE upload now",
                            ),
                        )
                    except Exception as exc:
                        return _json(
                            self,
                            500,
                            {"ok": False, "error": f"release_serial_failed:{exc}"},
                        )

                if u.path == "/agent/clean/recovery/known-good":
                    requested_port = str(body.get("port", "")).strip()
                    requested_fqbn = (
                        str(body.get("fqbn", "")).strip() or _clean_default_fqbn()
                    )
                    requested_sketch = str(
                        body.get("sketch", "")
                    ).strip() or _clean_default_sketch_path(repo_root, firmware)
                    code, payload = handle_clean_known_good_recovery(
                        gateway=gateway,
                        firmware=firmware,
                        control=control,
                        prearm_safety=prearm_safety,
                        requested_port=requested_port,
                        requested_fqbn=requested_fqbn,
                        requested_sketch=requested_sketch,
                        precheck_builder=lambda **kwargs: _clean_upload_precheck_payload(
                            gateway=gateway, firmware=firmware, **kwargs
                        ),
                        normalize_status=_normalize_status_for_hud,
                        resolve_action_gates=_resolve_action_gates,
                        tool_call_builder=_clean_tool_call,
                    )
                    return _json(self, code, payload)

                if u.path == "/agent/clean/thread/new":
                    mode = str(body.get("mode", "")).strip() or "app_dev"
                    title = str(body.get("title", "")).strip() or None
                    payload = handle_clean_thread_new(
                        mode=mode,
                        title=title,
                        ai=ai,
                    )
                    return _json(self, 200, payload)

                if u.path == "/agent/clean/thread/select":
                    mode = str(body.get("mode", "")).strip() or "app_dev"
                    thread_id = str(body.get("thread_id", "")).strip()
                    code, payload = handle_clean_thread_select(
                        mode=mode,
                        thread_id=thread_id,
                        ai=ai,
                    )
                    return _json(self, code, payload)

                if u.path == "/agent/clean/chat":
                    codex_login = _codex_cli_login_status()
                    err, req = parse_clean_chat_request(
                        body=body,
                        codex_login=codex_login,
                        env_model=str(
                            os.environ.get("UPRIGHT_CLEAN_MODEL", "gpt-5-codex")
                        ),
                        env_timeout=str(
                            os.environ.get("UPRIGHT_CLEAN_CODEX_EXEC_TIMEOUT_S", "120")
                        ),
                        sanitize_attachments_fn=_sanitize_agent_attachments,
                    )
                    if err is not None:
                        code, payload = err
                        return _json(self, code, payload)
                    assert req is not None
                    code, payload = run_clean_chat(
                        msg=str(req["msg"]),
                        mode=str(req["mode"]),
                        model=str(req["model"]),
                        clean_timeout_s=int(req["clean_timeout_s"]),
                        session_key=str(req["session_key"]),
                        thread_id=req.get("thread_id"),
                        attachments=list(req.get("attachments") or []),
                        auto_tools=bool(req.get("auto_tools", False)),
                        ai=ai,
                        run_auto_tools=_run_clean_auto_tools,
                        build_context=_build_clean_agent_context,
                        system_prompt_for_mode=_clean_system_prompt,
                        normalize_reply_for_prompt=_normalize_reply_for_prompt,
                    )
                    return _json(self, code, payload)

                if u.path == "/agent/clean/chat/stream":
                    codex_login = _codex_cli_login_status()
                    err, req = parse_clean_chat_request(
                        body=body,
                        codex_login=codex_login,
                        env_model=str(
                            os.environ.get("UPRIGHT_CLEAN_MODEL", "gpt-5-codex")
                        ),
                        env_timeout=str(
                            os.environ.get("UPRIGHT_CLEAN_CODEX_EXEC_TIMEOUT_S", "120")
                        ),
                        sanitize_attachments_fn=_sanitize_agent_attachments,
                    )
                    if err is not None:
                        code, payload = err
                        return _json(self, code, payload)
                    assert req is not None

                    apply_sse_headers(
                        send_response=self.send_response,
                        send_header=self.send_header,
                        end_headers=self.end_headers,
                    )

                    disconnected = threading.Event()
                    cancelled = threading.Event()

                    send_evt = make_sse_emitter(
                        wfile=self.wfile,
                        is_disconnected=lambda: disconnected.is_set(),
                        on_write_error=lambda: (disconnected.set(), cancelled.set()),
                    )

                    send_evt("start", {"ok": True})
                    run_clean_chat_stream(
                        msg=str(req["msg"]),
                        mode=str(req["mode"]),
                        model=str(req["model"]),
                        clean_timeout_s=int(req["clean_timeout_s"]),
                        session_key=str(req["session_key"]),
                        thread_id=req.get("thread_id"),
                        attachments=list(req.get("attachments") or []),
                        auto_tools=bool(req.get("auto_tools", False)),
                        ai=ai,
                        run_auto_tools=_run_clean_auto_tools,
                        build_context=_build_clean_agent_context,
                        system_prompt_for_mode=_clean_system_prompt,
                        normalize_reply_for_prompt=_normalize_reply_for_prompt,
                        emit=send_evt,
                        is_disconnected=lambda: disconnected.is_set(),
                        cancel_event=cancelled,
                    )
                    return

                if u.path == "/agent/clean/preflight":
                    codex_login = _codex_cli_login_status()
                    err, req = parse_clean_preflight_request(
                        body=body,
                        codex_login=codex_login,
                        env_model=str(
                            os.environ.get("UPRIGHT_CLEAN_MODEL", "gpt-5-codex")
                        ),
                        env_timeout=str(
                            os.environ.get("UPRIGHT_CLEAN_CODEX_EXEC_TIMEOUT_S", "120")
                        ),
                        default_sketch=_clean_default_sketch_path(repo_root, firmware),
                    )
                    if err is not None:
                        code, payload = err
                        return _json(self, code, payload)
                    assert req is not None
                    manifest_gate, compat_gate, active_profile_id = (
                        resolve_manifest_gates(
                            firmware=firmware,
                            profiles=profiles,
                            compatibility_fn=_runtime_manifest_profile_compatibility,
                            sketch=str(req["sketch"]),
                        )
                    )
                    payload = run_clean_preflight(
                        mode=str(req["mode"]),
                        max_ms=int(req["max_ms"]),
                        max_ms_tools=int(req["max_ms_tools"]),
                        gate_only=bool(req["gate_only"]),
                        with_compile=bool(req["with_compile"]),
                        model=str(req["model"]),
                        clean_timeout_s=int(req["clean_timeout_s"]),
                        manifest_gate=manifest_gate,
                        compat_gate=compat_gate,
                        active_profile_id=active_profile_id,
                        ai=ai,
                        run_auto_tools=_run_clean_auto_tools,
                        build_context=_build_clean_agent_context,
                        system_prompt_for_mode=_clean_system_prompt,
                        normalize_reply_for_prompt=_normalize_reply_for_prompt,
                        validate_preflight_payload=validate_clean_preflight_response,
                    )
                    return _json(self, 200, payload)

                if u.path == "/agent/clean/preflight/stream":
                    codex_login = _codex_cli_login_status()
                    err, req = parse_clean_preflight_request(
                        body=body,
                        codex_login=codex_login,
                        env_model=str(
                            os.environ.get("UPRIGHT_CLEAN_MODEL", "gpt-5-codex")
                        ),
                        env_timeout=str(
                            os.environ.get("UPRIGHT_CLEAN_CODEX_EXEC_TIMEOUT_S", "120")
                        ),
                        default_sketch=_clean_default_sketch_path(repo_root, firmware),
                    )
                    if err is not None:
                        code, payload = err
                        return _json(self, code, payload)
                    assert req is not None
                    manifest_gate, compat_gate, active_profile_id = (
                        resolve_manifest_gates(
                            firmware=firmware,
                            profiles=profiles,
                            compatibility_fn=_runtime_manifest_profile_compatibility,
                            sketch=str(req["sketch"]),
                        )
                    )

                    apply_sse_headers(
                        send_response=self.send_response,
                        send_header=self.send_header,
                        end_headers=self.end_headers,
                    )
                    send_evt = make_sse_emitter(wfile=self.wfile)

                    send_evt("start", {"ok": True, "mode": str(req["mode"])})
                    run_clean_preflight(
                        mode=str(req["mode"]),
                        max_ms=int(req["max_ms"]),
                        max_ms_tools=int(req["max_ms_tools"]),
                        gate_only=bool(req["gate_only"]),
                        with_compile=bool(req["with_compile"]),
                        model=str(req["model"]),
                        clean_timeout_s=int(req["clean_timeout_s"]),
                        manifest_gate=manifest_gate,
                        compat_gate=compat_gate,
                        active_profile_id=active_profile_id,
                        ai=ai,
                        run_auto_tools=_run_clean_auto_tools,
                        build_context=_build_clean_agent_context,
                        system_prompt_for_mode=_clean_system_prompt,
                        normalize_reply_for_prompt=_normalize_reply_for_prompt,
                        validate_preflight_payload=validate_clean_preflight_response,
                        emit=send_evt,
                    )
                    return

                if u.path == "/agent/mode":
                    mode = str(body.get("mode", "")).strip()
                    if not mode:
                        return _json(self, 400, {"ok": False, "error": "mode_required"})
                    try:
                        state = agent_mission.set_mode(mode)
                    except RuntimeError as exc:
                        if str(exc) == "invalid_mode":
                            return _json(
                                self,
                                400,
                                {
                                    "ok": False,
                                    "error": "invalid_mode",
                                    "allowed_modes": agent_mission.status().get(
                                        "allowed_modes", []
                                    ),
                                },
                            )
                        raise
                    return _json(self, 200, build_agent_state_payload(agent=state))

                if u.path == "/agent/thread/new":
                    guard = _legacy_execution_guard(u.path)
                    if guard is not None:
                        return _json(self, 403, guard)
                    mode_state = agent_mission.status()
                    mode = str(body.get("mode", "")).strip() or str(
                        mode_state.get("mode", "robot_dev")
                    )
                    tok = _extract_auth_token(self, body)
                    me = auth.me(tok) if tok else None
                    session_key = (
                        f"user:{me['id']}:agent:{mode}"
                        if me and isinstance(me.get("id"), int)
                        else f"local:{mode}"
                    )
                    title = str(body.get("title", "")).strip() or None
                    thread = ai.create_thread(session_key, title)
                    return _json(
                        self,
                        200,
                        build_agent_thread_state_payload(
                            agent=mode_state,
                            thread=thread,
                            threads=ai.list_threads(session_key),
                            history=ai.history(session_key, str(thread.get("id")))[
                                -80:
                            ],
                        ),
                    )

                if u.path == "/agent/thread/select":
                    guard = _legacy_execution_guard(u.path)
                    if guard is not None:
                        return _json(self, 403, guard)
                    mode_state = agent_mission.status()
                    mode = str(body.get("mode", "")).strip() or str(
                        mode_state.get("mode", "robot_dev")
                    )
                    thread_id = str(body.get("thread_id", "")).strip()
                    if not thread_id:
                        return _json(
                            self, 400, {"ok": False, "error": "thread_id_required"}
                        )
                    tok = _extract_auth_token(self, body)
                    me = auth.me(tok) if tok else None
                    session_key = (
                        f"user:{me['id']}:agent:{mode}"
                        if me and isinstance(me.get("id"), int)
                        else f"local:{mode}"
                    )
                    try:
                        thread = ai.select_thread(session_key, thread_id)
                    except RuntimeError as exc:
                        if str(exc) == "thread_not_found":
                            return _json(
                                self, 404, {"ok": False, "error": "thread_not_found"}
                            )
                        raise
                    return _json(
                        self,
                        200,
                        build_agent_thread_state_payload(
                            agent=mode_state,
                            thread=thread,
                            threads=ai.list_threads(session_key),
                            history=ai.history(session_key, thread_id)[-80:],
                        ),
                    )

                if u.path == "/agent/chat":
                    guard = _legacy_execution_guard(u.path)
                    if guard is not None:
                        return _json(self, 403, guard)
                    msg = str(body.get("message", "")).strip()
                    if not msg:
                        return _json(
                            self, 400, {"ok": False, "error": "missing_message"}
                        )
                    mode_state = agent_mission.status()
                    mode = str(body.get("mode", "")).strip() or str(
                        mode_state.get("mode", "robot_dev")
                    )
                    if mode != mode_state.get("mode"):
                        try:
                            mode_state = agent_mission.set_mode(mode)
                        except RuntimeError:
                            mode = str(mode_state.get("mode", "robot_dev"))
                    tok = _extract_auth_token(self, body)
                    me = auth.me(tok) if tok else None
                    user_creds = (
                        auth.get_openai_key(int(me["id"]))
                        if me and isinstance(me.get("id"), int)
                        else None
                    )
                    resolved = provider_router.resolve_agent_runtime(
                        mode=mode,
                        requested_api_key=str(body.get("api_key", "")).strip() or None,
                        requested_model=str(body.get("model", "")).strip() or None,
                        user_creds=user_creds,
                        env_api_key=ai.default_api_key,
                        env_model=os.environ.get("OPENAI_MODEL", ""),
                    )
                    codex_login = _codex_cli_login_status()
                    api_key = str(resolved.get("api_key", "")).strip()
                    use_codex_cli = bool(codex_login.get("logged_in", False))
                    enable_tools = bool(body.get("enable_tools", True))
                    runtime_exec = _agent_choose_executor(
                        mode=mode,
                        enable_tools=enable_tools,
                        has_api_key=bool(api_key),
                        codex_logged_in=use_codex_cli,
                        codex_agent_available=bool(codex_agent is not None),
                    )
                    executor = str(runtime_exec.get("executor", "blocked"))
                    model = _agent_resolve_model(
                        mode,
                        str(resolved.get("model", "")),
                        prefer_codex=use_codex_cli,
                    )
                    if executor == "blocked":
                        return _json(
                            self,
                            403,
                            {
                                "ok": False,
                                "error": str(
                                    runtime_exec.get(
                                        "degraded_reason", "runtime_blocked"
                                    )
                                ),
                                "executor": executor,
                                "can_execute": False,
                            },
                        )
                    if not model:
                        return _json(
                            self,
                            409,
                            {
                                "ok": False,
                                "error": "openai_model_missing",
                                "required": "codex_model",
                                "model_source": str(resolved.get("model_source", "")),
                            },
                        )
                    if (not use_codex_cli) and (not _agent_model_allowed(model)):
                        return _json(
                            self,
                            409,
                            {
                                "ok": False,
                                "error": "agent_model_not_allowed",
                                "required_substring": ",".join(
                                    resolved.get("allowed_model_substrings", [])
                                ),
                                "resolved_model": model,
                            },
                        )
                    serial_h = gateway.health()
                    cached_status = dict(serial_h.get("last_status", {}))
                    attachments = _sanitize_agent_attachments(body.get("attachments"))
                    ctx = {
                        "mission_mode": mode,
                        "status": cached_status,
                        "status_source": "gateway.health.last_status_cached",
                        "serial_health": serial_h,
                        "control": control.snapshot(),
                        "firmware": firmware.status(),
                        "commissioning": _commissioning_ai_context(commissioning),
                        "host_capture": _host_capture_ai_context(host_capture),
                        "burst": burst_status(),
                        "config_snapshots": config_history.list_snapshots(limit=8),
                        "assistant_knowledge": knowledge.context(),
                        "assistant_capabilities": _assistant_capabilities_context(
                            allow_apply=False
                        ),
                    }
                    if attachments:
                        ctx["attachments"] = attachments
                    thread_id = str(body.get("thread_id", "")).strip() or None
                    session_key = (
                        f"user:{me['id']}:agent:{mode}"
                        if me and isinstance(me.get("id"), int)
                        else f"local:{mode}"
                    )
                    prior_history = (
                        ai.history(session_key, thread_id) if thread_id else []
                    )
                    try:
                        if executor == "openai_tools":
                            fw_status = firmware.status()
                            fw_defaults = (
                                fw_status.get("defaults", {})
                                if isinstance(fw_status, dict)
                                else {}
                            )
                            active_sketch = str(
                                body.get("sketch_path")
                                or fw_status.get("sketch_path", "")
                                or fw_defaults.get("sketch", "")
                            )
                            board_fqbn = str(
                                body.get("board")
                                or fw_status.get("board", "")
                                or fw_defaults.get("fqbn", "arduino:avr:nano")
                            )
                            port = str(
                                body.get("port")
                                or fw_status.get("port", "")
                                or fw_defaults.get("port", "")
                            )
                            tool_out = codex_agent.chat_with_tools(
                                message=msg,
                                context=ctx,
                                api_key=api_key,
                                model=model,
                                system_prompt=_agent_mode_system_prompt(mode),
                                enable_tools=True,
                                active_sketch_path=active_sketch or None,
                                active_robot_id=str(body.get("robot_id", "default")),
                                board_fqbn=board_fqbn,
                                port=port,
                                conversation_history=prior_history,
                            )
                            answer = (
                                str(tool_out.get("answer", "")).strip() or "(no output)"
                            )
                            tid = ai._append(
                                session_key, "user", msg, thread_id=thread_id
                            )
                            ai._append(session_key, "assistant", answer, thread_id=tid)
                            hist = ai.history(session_key, tid)[-80:]
                            return _json(
                                self,
                                200,
                                build_agent_chat_reply_payload(
                                    agent=mode_state,
                                    reply=_normalize_reply_for_prompt(msg, answer),
                                    thread_id=tid,
                                    history=hist,
                                    threads=ai.list_threads(session_key),
                                    tool_calls=tool_out.get("tool_calls", []),
                                    iterations=int(tool_out.get("iterations", 1) or 1),
                                    provider="openai_tools",
                                    executor=executor,
                                ),
                            )
                        if executor == "codex_cli_exec":
                            out = ai.chat_codex_cli(
                                message=msg,
                                context=ctx,
                                session_key=session_key,
                                model=model,
                                thread_id=thread_id,
                                system_prompt=_agent_mode_system_prompt(mode),
                            )
                            tid = str(out.get("thread_id", "")).strip() or None
                            hist = ai.history(session_key, tid)[-80:] if tid else []
                            return _json(
                                self,
                                200,
                                build_agent_chat_reply_payload(
                                    agent=mode_state,
                                    reply=_normalize_reply_for_prompt(
                                        msg, out["answer"]
                                    ),
                                    thread_id=tid,
                                    history=hist,
                                    threads=ai.list_threads(session_key),
                                    tool_calls=[],
                                    iterations=1,
                                    provider="codex_cli",
                                    executor=executor,
                                ),
                            )
                        out = ai.chat(
                            message=msg,
                            context=ctx,
                            session_key=session_key,
                            api_key=api_key,
                            model=model,
                            thread_id=thread_id,
                            system_prompt=_agent_mode_system_prompt(mode),
                        )
                    except RuntimeError as exc:
                        return _json(self, 500, {"ok": False, "error": str(exc)})
                    tid = str(out.get("thread_id", "")).strip() or None
                    hist = ai.history(session_key, tid)[-80:] if tid else []
                    return _json(
                        self,
                        200,
                        build_agent_chat_reply_payload(
                            agent=mode_state,
                            reply=_normalize_reply_for_prompt(msg, out["answer"]),
                            thread_id=tid,
                            history=hist,
                            threads=ai.list_threads(session_key),
                            tool_calls=[],
                            iterations=1,
                            provider="openai",
                            executor="openai_chat",
                        ),
                    )

                if u.path == "/agent/chat/stream":
                    guard = _legacy_execution_guard(u.path)
                    if guard is not None:
                        return _json(self, 403, guard)
                    msg = str(body.get("message", "")).strip()
                    if not msg:
                        return _json(
                            self, 400, {"ok": False, "error": "missing_message"}
                        )
                    mode_state = agent_mission.status()
                    mode = str(body.get("mode", "")).strip() or str(
                        mode_state.get("mode", "robot_dev")
                    )
                    if mode != mode_state.get("mode"):
                        try:
                            mode_state = agent_mission.set_mode(mode)
                        except RuntimeError:
                            mode = str(mode_state.get("mode", "robot_dev"))
                    tok = _extract_auth_token(self, body)
                    me = auth.me(tok) if tok else None
                    user_creds = (
                        auth.get_openai_key(int(me["id"]))
                        if me and isinstance(me.get("id"), int)
                        else None
                    )
                    resolved = provider_router.resolve_agent_runtime(
                        mode=mode,
                        requested_api_key=str(body.get("api_key", "")).strip() or None,
                        requested_model=str(body.get("model", "")).strip() or None,
                        user_creds=user_creds,
                        env_api_key=ai.default_api_key,
                        env_model=os.environ.get("OPENAI_MODEL", ""),
                    )
                    codex_login = _codex_cli_login_status()
                    api_key = str(resolved.get("api_key", "")).strip()
                    use_codex_cli = bool(codex_login.get("logged_in", False))
                    enable_tools = bool(body.get("enable_tools", True))
                    runtime_exec = _agent_choose_executor(
                        mode=mode,
                        enable_tools=enable_tools,
                        has_api_key=bool(api_key),
                        codex_logged_in=use_codex_cli,
                        codex_agent_available=bool(codex_agent is not None),
                    )
                    executor = str(runtime_exec.get("executor", "blocked"))
                    model = _agent_resolve_model(
                        mode,
                        str(resolved.get("model", "")),
                        prefer_codex=use_codex_cli,
                    )
                    if executor == "blocked":
                        return _json(
                            self,
                            403,
                            {
                                "ok": False,
                                "error": str(
                                    runtime_exec.get(
                                        "degraded_reason", "runtime_blocked"
                                    )
                                ),
                                "executor": executor,
                                "can_execute": False,
                            },
                        )
                    if (not use_codex_cli) and (not _agent_model_allowed(model)):
                        return _json(
                            self,
                            409,
                            {
                                "ok": False,
                                "error": "agent_model_not_allowed",
                                "required_substring": ",".join(
                                    resolved.get("allowed_model_substrings", [])
                                ),
                                "resolved_model": model,
                            },
                        )

                    serial_h = gateway.health()
                    cached_status = dict(serial_h.get("last_status", {}))
                    attachments = _sanitize_agent_attachments(body.get("attachments"))
                    ctx = {
                        "mission_mode": mode,
                        "status": cached_status,
                        "status_source": "gateway.health.last_status_cached",
                        "serial_health": serial_h,
                        "control": control.snapshot(),
                        "firmware": firmware.status(),
                        "commissioning": _commissioning_ai_context(commissioning),
                        "host_capture": _host_capture_ai_context(host_capture),
                        "burst": burst_status(),
                        "config_snapshots": config_history.list_snapshots(limit=8),
                        "assistant_knowledge": knowledge.context(),
                        "assistant_capabilities": _assistant_capabilities_context(
                            allow_apply=False
                        ),
                    }
                    if attachments:
                        ctx["attachments"] = attachments
                    thread_id = str(body.get("thread_id", "")).strip() or None
                    session_key = (
                        f"user:{me['id']}:agent:{mode}"
                        if me and isinstance(me.get("id"), int)
                        else f"local:{mode}"
                    )

                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Cache-Control", "no-cache")
                    self.send_header("Connection", "keep-alive")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.send_header(
                        "Access-Control-Allow-Headers",
                        "Content-Type, Authorization, X-Session-Token",
                    )
                    self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
                    self.end_headers()

                    def send_evt(name: str, payload_obj: Dict[str, Any]) -> None:
                        blob = (
                            f"event: {name}\ndata: {json.dumps(payload_obj, ensure_ascii=True)}\n\n"
                        ).encode("utf-8")
                        self.wfile.write(blob)
                        self.wfile.flush()

                    send_evt("start", {"ok": True})
                    try:
                        if executor == "openai_tools":
                            fw_status = firmware.status()
                            fw_defaults = (
                                fw_status.get("defaults", {})
                                if isinstance(fw_status, dict)
                                else {}
                            )
                            active_sketch = str(
                                body.get("sketch_path")
                                or fw_status.get("sketch_path", "")
                                or fw_defaults.get("sketch", "")
                            )
                            board_fqbn = str(
                                body.get("board")
                                or fw_status.get("board", "")
                                or fw_defaults.get("fqbn", "arduino:avr:nano")
                            )
                            port = str(
                                body.get("port")
                                or fw_status.get("port", "")
                                or fw_defaults.get("port", "")
                            )
                            prior_history = (
                                ai.history(session_key, thread_id) if thread_id else []
                            )
                            tool_out = codex_agent.chat_with_tools(
                                message=msg,
                                context=ctx,
                                api_key=api_key,
                                model=model,
                                system_prompt=_agent_mode_system_prompt(mode),
                                enable_tools=True,
                                active_sketch_path=active_sketch or None,
                                active_robot_id=str(body.get("robot_id", "default")),
                                board_fqbn=board_fqbn,
                                port=port,
                                conversation_history=prior_history,
                            )
                            answer = (
                                str(tool_out.get("answer", "")).strip() or "(no output)"
                            )
                            send_evt("delta", {"text": answer})
                            tid = ai._append(
                                session_key, "user", msg, thread_id=thread_id
                            )
                            ai._append(session_key, "assistant", answer, thread_id=tid)
                            hist = ai.history(session_key, tid)[-80:]
                            send_evt(
                                "done",
                                build_agent_chat_reply_payload(
                                    agent=mode_state,
                                    reply=_normalize_reply_for_prompt(msg, answer),
                                    thread_id=tid,
                                    history=hist,
                                    threads=ai.list_threads(session_key),
                                    tool_calls=tool_out.get("tool_calls", []),
                                    iterations=int(tool_out.get("iterations", 1) or 1),
                                    provider="openai_tools",
                                    executor=executor,
                                ),
                            )
                            return
                        if executor == "codex_cli_exec":
                            out = ai.chat_codex_cli(
                                message=msg,
                                context=ctx,
                                session_key=session_key,
                                model=model,
                                thread_id=thread_id,
                                system_prompt=_agent_mode_system_prompt(mode),
                            )
                            answer = str(out.get("answer", "")).strip() or "(no output)"
                            send_evt("delta", {"text": answer})
                            tid = str(out.get("thread_id", "")).strip() or None
                            hist = ai.history(session_key, tid)[-80:] if tid else []
                            send_evt(
                                "done",
                                build_agent_chat_reply_payload(
                                    agent=mode_state,
                                    reply=_normalize_reply_for_prompt(msg, answer),
                                    thread_id=tid,
                                    history=hist,
                                    threads=ai.list_threads(session_key),
                                    tool_calls=[],
                                    iterations=1,
                                    provider="codex_cli",
                                    executor=executor,
                                ),
                            )
                            return

                        out = ai.chat_stream(
                            message=msg,
                            context=ctx,
                            session_key=session_key,
                            api_key=api_key,
                            model=model,
                            on_delta=lambda txt: send_evt("delta", {"text": txt}),
                            thread_id=thread_id,
                            system_prompt=_agent_mode_system_prompt(mode),
                        )
                        tid = str(out.get("thread_id", "")).strip() or None
                        hist = ai.history(session_key, tid)[-80:] if tid else []
                        send_evt(
                            "done",
                            build_agent_chat_reply_payload(
                                agent=mode_state,
                                reply=_normalize_reply_for_prompt(
                                    msg,
                                    str(out.get("answer", "")).strip() or "(no output)",
                                ),
                                thread_id=tid,
                                history=hist,
                                threads=ai.list_threads(session_key),
                                tool_calls=[],
                                iterations=1,
                                provider="openai",
                                executor="openai_chat",
                            ),
                        )
                    except Exception as exc:
                        send_evt("error", {"ok": False, "error": str(exc)})
                    return

                if u.path == "/ai/chat":
                    tok = _extract_auth_token(self, body)
                    me = auth.me(tok)
                    if not me:
                        return _json(
                            self, 401, {"ok": False, "error": "unauthenticated"}
                        )
                    creds = auth.get_openai_key(int(me["id"]))
                    if not creds:
                        return _json(
                            self,
                            403,
                            {"ok": False, "error": "openai_key_not_configured"},
                        )
                    msg = str(body.get("message", "")).strip()
                    if not msg:
                        return _json(
                            self, 400, {"ok": False, "error": "missing message"}
                        )
                    active_profile = ai_profiles.get_active()
                    policy = (
                        active_profile.get("policy", {})
                        if isinstance(active_profile, dict)
                        else {}
                    )
                    profile_allow_apply = (
                        bool(policy.get("allow_auto_apply", True))
                        if isinstance(policy, dict)
                        else True
                    )
                    requested_allow_apply = bool(body.get("allow_apply", True))
                    allow_apply = bool(requested_allow_apply and profile_allow_apply)
                    prompt = _resolve_system_prompt(
                        active_profile,
                        allow_apply=allow_apply,
                        repo_root=firmware.repo_root,
                    )
                    serial_h = gateway.health()
                    cached_status = dict(serial_h.get("last_status", {}))
                    ctx = {
                        "status": cached_status,
                        "status_source": "gateway.health.last_status_cached",
                        "serial_health": serial_h,
                        "control": control.snapshot(),
                        "firmware": firmware.status(),
                        "commissioning": _commissioning_ai_context(commissioning),
                        "host_capture": _host_capture_ai_context(host_capture),
                        "burst": burst_status(),
                        "config_snapshots": config_history.list_snapshots(limit=8),
                        "assistant_capabilities": _assistant_capabilities_context(
                            allow_apply=allow_apply
                        ),
                        "assistant_profile": active_profile,
                        "assistant_knowledge": knowledge.context(),
                    }
                    skey = f"user:{me['id']}"
                    hardware_sync = sync_hardware_context(skey, body, ctx)
                    hardware_notice = str(hardware_sync.get("notice", "")).strip()
                    thread_id = str(body.get("thread_id", "")).strip() or None
                    if thread_id:
                        try:
                            ai.history(skey, thread_id)
                        except RuntimeError as exc:
                            if str(exc) == "thread_not_found":
                                return _json(
                                    self,
                                    404,
                                    {"ok": False, "error": "thread_not_found"},
                                )
                            raise
                    full_history = ai.history(skey, thread_id) if thread_id else []
                    extracted_facts = _extract_mission_facts(full_history)
                    if extracted_facts:
                        mission_memory.upsert(
                            skey, extracted_facts, source="thread_history"
                        )
                    mission_facts = mission_memory.get(skey)
                    if mission_facts:
                        ctx["mission_facts"] = mission_facts
                    if _needs_ide_disambiguation(msg, mission_facts):
                        mission_memory.upsert(
                            skey,
                            {"ide_disambiguation_asked": "true"},
                            source="bridge_disambiguation_gate",
                        )
                        reply = _ide_disambiguation_reply()
                        tid = ai._append(skey, "user", msg, thread_id=thread_id)
                        ai._append(skey, "assistant", reply, thread_id=tid)
                        return _json(
                            self,
                            200,
                            build_ai_chat_response_payload(
                                reply=reply,
                                ai=ai.status(
                                    configured=True,
                                    model=str(creds["model"] or "gpt-5-codex"),
                                    session_key=skey,
                                ),
                                history=ai.history(skey, tid)[-80:],
                                threads=ai.list_threads(skey),
                                thread_id=tid,
                                apply=None,
                            ),
                        )
                    out = ai.chat(
                        message=msg,
                        context=ctx,
                        session_key=skey,
                        api_key=creds["api_key"],
                        model=str(creds["model"] or "gpt-5-codex"),
                        thread_id=thread_id,
                        system_prompt=prompt,
                    )
                    reply = _strip_apply_json_block(out["answer"])
                    if hardware_notice:
                        reply = f"{hardware_notice}\n\n{reply}".strip()
                    reply = _normalize_reply_for_prompt(msg, reply)
                    apply_result: Optional[Dict[str, Any]] = None
                    apply_src = _extract_apply_json(out["answer"])
                    plan = (
                        _sanitize_apply_plan(apply_src)
                        if isinstance(apply_src, dict)
                        else {}
                    )
                    if allow_apply and plan:
                        try:
                            apply_result = _apply_assistant_plan(
                                gateway,
                                config_history,
                                firmware,
                                plan,
                                source="ai/chat",
                            )
                        except Exception as exc:
                            apply_result = {"ok": False, "error": str(exc)}
                    if apply_result:
                        note = _format_apply_note(apply_result)
                        reply = f"{reply}\n\n{note}".strip()
                    hist = ai.history(skey, out.get("thread_id"))[-80:]
                    if reply != out["answer"]:
                        hist = history_with_reply(hist, reply)
                    return _json(
                        self,
                        200,
                        build_ai_chat_response_payload(
                            reply=reply,
                            ai=ai.status(
                                configured=True,
                                model=str(creds["model"] or "gpt-5-codex"),
                                session_key=skey,
                            ),
                            history=hist,
                            threads=ai.list_threads(skey),
                            thread_id=out.get("thread_id"),
                            apply=apply_result,
                        ),
                    )

                if u.path == "/ai/chat/tools":
                    # Tool-enabled chat endpoint using CodexAgent
                    if codex_agent is None:
                        return _json(
                            self,
                            501,
                            {"ok": False, "error": "tool_support_not_available"},
                        )
                    tok = _extract_auth_token(self, body)
                    me = auth.me(tok)
                    if not me:
                        return _json(
                            self, 401, {"ok": False, "error": "unauthenticated"}
                        )
                    creds = auth.get_openai_key(int(me["id"]))
                    if not creds:
                        return _json(
                            self,
                            403,
                            {"ok": False, "error": "openai_key_not_configured"},
                        )
                    msg = str(body.get("message", "")).strip()
                    if not msg:
                        return _json(
                            self, 400, {"ok": False, "error": "missing message"}
                        )
                    active_profile = ai_profiles.get_active()
                    policy = (
                        active_profile.get("policy", {})
                        if isinstance(active_profile, dict)
                        else {}
                    )
                    enable_tools = bool(body.get("enable_tools", True))
                    prompt = _resolve_system_prompt(
                        active_profile, allow_apply=True, repo_root=firmware.repo_root
                    )
                    serial_h = gateway.health()
                    cached_status = dict(serial_h.get("last_status", {}))
                    ctx = {
                        "status": cached_status,
                        "status_source": "gateway.health.last_status_cached",
                        "serial_health": serial_h,
                        "control": control.snapshot(),
                        "firmware": firmware.status(),
                        "commissioning": _commissioning_ai_context(commissioning),
                        "host_capture": _host_capture_ai_context(host_capture),
                        "burst": burst_status(),
                        "config_snapshots": config_history.list_snapshots(limit=8),
                        "assistant_profile": active_profile,
                        "assistant_knowledge": knowledge.context(),
                    }
                    # Extract sketch/robot context from request or firmware status
                    fw_status = firmware.status()
                    fw_defaults = (
                        fw_status.get("defaults", {})
                        if isinstance(fw_status, dict)
                        else {}
                    )
                    active_sketch = str(
                        body.get("sketch_path")
                        or fw_status.get("sketch_path", "")
                        or fw_defaults.get("sketch", "")
                    )
                    robot_id = str(body.get("robot_id", "default"))
                    board_fqbn = str(
                        body.get("board")
                        or fw_status.get("board", "")
                        or fw_defaults.get("fqbn", "arduino:avr:nano")
                    )
                    port = str(
                        body.get("port")
                        or fw_status.get("port", "")
                        or fw_defaults.get("port", "")
                    )
                    try:
                        skey = f"user:{me['id']}"
                        hardware_sync = sync_hardware_context(skey, body, ctx)
                        hardware_notice = str(hardware_sync.get("notice", "")).strip()
                        thread_id = str(body.get("thread_id", "")).strip() or None
                        if thread_id:
                            try:
                                ai.history(skey, thread_id)
                            except RuntimeError as exc:
                                if str(exc) == "thread_not_found":
                                    return _json(
                                        self,
                                        404,
                                        {"ok": False, "error": "thread_not_found"},
                                    )
                                raise
                        full_history = ai.history(skey, thread_id) if thread_id else []
                        prior_history = full_history[-20:]
                        extracted_facts = _extract_mission_facts(full_history)
                        if extracted_facts:
                            mission_memory.upsert(
                                skey, extracted_facts, source="thread_history"
                            )
                        mission_facts = mission_memory.get(skey)
                        if mission_facts:
                            ctx["mission_facts"] = mission_facts
                        if _needs_ide_disambiguation(msg, mission_facts):
                            mission_memory.upsert(
                                skey,
                                {"ide_disambiguation_asked": "true"},
                                source="bridge_disambiguation_gate",
                            )
                            reply = _ide_disambiguation_reply()
                            tid = ai._append(skey, "user", msg, thread_id=thread_id)
                            ai._append(skey, "assistant", reply, thread_id=tid)
                            return _json(
                                self,
                                200,
                                build_disambiguation_reply_payload(
                                    reply=reply,
                                    ai=ai.status(
                                        configured=True,
                                        model=str(creds["model"] or "gpt-4"),
                                        session_key=skey,
                                    ),
                                    history=ai.history(skey, tid)[-80:],
                                    threads=ai.list_threads(skey),
                                    thread_id=tid,
                                ),
                            )
                        result = codex_agent.chat_with_tools(
                            message=msg,
                            context=ctx,
                            api_key=creds["api_key"],
                            model=str(creds["model"] or "gpt-4"),
                            system_prompt=prompt,
                            enable_tools=enable_tools,
                            active_sketch_path=active_sketch,
                            active_robot_id=robot_id,
                            board_fqbn=board_fqbn,
                            port=port,
                            conversation_history=prior_history,
                        )
                        base_reply = str(result["answer"])
                        if hardware_notice:
                            base_reply = f"{hardware_notice}\n\n{base_reply}".strip()
                        normalized_reply = _normalize_reply_for_prompt(msg, base_reply)
                        tool_failure_summary = _summarize_tool_failures(
                            result.get("tool_calls")
                        )
                        if tool_failure_summary:
                            low_reply = normalized_reply.lower()
                            if "failed:" not in low_reply and "error" not in low_reply:
                                normalized_reply = (
                                    f"{normalized_reply}\n\nDiagnostics:\n{tool_failure_summary}"
                                ).strip()
                        sketch_artifact_issues = _summarize_sketch_artifact_issues(
                            result.get("tool_calls")
                        )
                        if sketch_artifact_issues:
                            normalized_reply = (
                                f"{normalized_reply}\n\nSketch Artifact Checks:\n{sketch_artifact_issues}"
                            ).strip()
                        tid = ai._append(skey, "user", msg, thread_id=thread_id)
                        ai._append(skey, "assistant", normalized_reply, thread_id=tid)
                        return _json(
                            self,
                            200,
                            build_chat_with_tools_payload(
                                reply=normalized_reply,
                                tool_calls=result.get("tool_calls", []),
                                iterations=result.get("iterations", 1),
                                ai=ai.status(
                                    configured=True,
                                    model=str(creds["model"] or "gpt-4"),
                                    session_key=skey,
                                ),
                                history=ai.history(skey, tid)[-80:],
                                threads=ai.list_threads(skey),
                                thread_id=tid,
                            ),
                        )
                    except Exception as exc:
                        return _json(self, 500, {"ok": False, "error": str(exc)})

                if u.path == "/ai/upload/confirm":
                    # Upload confirmation endpoint - validates token and executes upload
                    tok = _extract_auth_token(self, body)
                    me = auth.me(tok)
                    if not me:
                        return _json(
                            self, 401, {"ok": False, "error": "unauthenticated"}
                        )
                    confirm_token = str(body.get("token", "")).strip()
                    action = str(body.get("action", "")).strip()
                    if not confirm_token:
                        return _json(self, 400, {"ok": False, "error": "missing token"})
                    if action not in ("approve", "reject"):
                        return _json(
                            self,
                            400,
                            {
                                "ok": False,
                                "error": "invalid action, must be 'approve' or 'reject'",
                            },
                        )
                    if action == "reject":
                        # Clear pending upload if codex_agent available
                        if codex_agent and hasattr(codex_agent, "tool_executor"):
                            codex_agent.tool_executor._pending_uploads.pop(
                                confirm_token, None
                            )
                        return _json(self, 200, build_action_payload(action="rejected"))
                    # Approve action - execute the upload
                    if codex_agent is None:
                        return _json(
                            self,
                            501,
                            {
                                "ok": False,
                                "error": "tool_support_not_available",
                                "action": "invalid",
                            },
                        )
                    if not hasattr(codex_agent, "tool_executor"):
                        return _json(
                            self,
                            501,
                            {
                                "ok": False,
                                "error": "tool_executor_not_available",
                                "action": "invalid",
                            },
                        )
                    executor = codex_agent.tool_executor
                    # Check if token exists
                    if confirm_token not in executor._pending_uploads:
                        return _json(
                            self,
                            400,
                            {
                                "ok": False,
                                "error": "Invalid or expired confirmation token",
                                "action": "invalid",
                            },
                        )
                    # Execute upload with token
                    result = executor._tool_upload_firmware(
                        {"confirmation_token": confirm_token}
                    )
                    if result.ok:
                        return _json(
                            self,
                            200,
                            build_upload_confirm_success_payload(
                                sketch=result.data.get("sketch"),
                                board=result.data.get("board"),
                                port=result.data.get("port"),
                                output=result.data.get("output", ""),
                            ),
                        )
                    else:
                        # Check for specific error types
                        error_msg = result.error or "Upload failed"
                        action_type = (
                            "invalid" if "expired" in error_msg.lower() else "approved"
                        )
                        if "expired" in error_msg.lower():
                            action_type = "expired"
                        return _json(
                            self,
                            200,
                            {
                                "ok": False,
                                "action": action_type,
                                "error": error_msg,
                                "upload_result": {
                                    "ok": False,
                                    "error": error_msg,
                                    "output": result.data.get("output", ""),
                                },
                            },
                        )

                if u.path == "/ai/metrics":
                    # Metrics endpoint - returns safe aggregate counters for observability
                    tok = _extract_auth_token(self, body)
                    me = auth.me(tok)
                    if not me:
                        return _json(
                            self, 401, {"ok": False, "error": "unauthenticated"}
                        )

                    # Parse optional filters
                    since_hours = float(body.get("since_hours", 24))
                    since_ts = (
                        time.time() - (since_hours * 3600) if since_hours > 0 else None
                    )
                    tool_filter = str(body.get("tool", "")).strip() or None

                    # Get metrics from codex_db
                    db = get_codex_db()

                    try:
                        tool_metrics = db.get_tool_metrics(
                            since_ts=since_ts, tool_filter=tool_filter
                        )
                        db_stats = db.get_stats()

                        return _json(
                            self,
                            200,
                            build_tool_metrics_payload(
                                since_hours=since_hours,
                                tool_metrics=tool_metrics,
                                db_stats=db_stats,
                                ts=time.time(),
                            ),
                        )
                    except Exception as exc:
                        logger.warning(f"Metrics fetch error: {exc}")
                        return _json(
                            self, 500, {"ok": False, "error": f"metrics_error: {exc}"}
                        )

                if u.path == "/ai/rag/index":
                    tok = _extract_auth_token(self, body)
                    me = auth.me(tok)
                    if not me:
                        return _json(
                            self, 401, {"ok": False, "error": "unauthenticated"}
                        )
                    try:
                        if not get_codex_rag:
                            return _json(
                                self, 503, {"ok": False, "error": "rag_not_available"}
                            )
                        user_creds = auth.get_openai_key(int(me["id"]))
                        openai_key = str(
                            (user_creds or {}).get("api_key")
                            or os.environ.get("OPENAI_API_KEY")
                            or ""
                        ).strip()
                        if not openai_key:
                            return _json(
                                self,
                                400,
                                {
                                    "ok": False,
                                    "error": "no_openai_key",
                                    "hint": "Set OpenAI API key to enable RAG indexing",
                                },
                            )
                        rag = get_codex_rag(openai_key)
                        paths = body.get("paths")  # Optional: list of paths to index
                        force_reindex = bool(body.get("force_reindex", False))
                        start_ts = time.time()
                        doc_stats = rag.index_docs(
                            doc_paths=paths, force_reindex=force_reindex
                        )
                        sketch_stats = rag.index_sketches(force_reindex=force_reindex)
                        elapsed_ms = (time.time() - start_ts) * 1000
                        return _json(
                            self,
                            200,
                            build_rag_index_payload(
                                docs=doc_stats,
                                sketches=sketch_stats,
                                elapsed_ms=round(elapsed_ms, 2),
                                ts=time.time(),
                            ),
                        )
                    except Exception as exc:
                        logger.warning(f"RAG index error: {exc}")
                        return _json(
                            self, 500, {"ok": False, "error": f"rag_index_error: {exc}"}
                        )

                if u.path == "/ai/chat/stream":
                    tok = _extract_auth_token(self, body)
                    me = auth.me(tok)
                    if not me:
                        return _json(
                            self, 401, {"ok": False, "error": "unauthenticated"}
                        )
                    creds = auth.get_openai_key(int(me["id"]))
                    if not creds:
                        return _json(
                            self,
                            403,
                            {"ok": False, "error": "openai_key_not_configured"},
                        )
                    msg = str(body.get("message", "")).strip()
                    if not msg:
                        return _json(
                            self, 400, {"ok": False, "error": "missing message"}
                        )
                    active_profile = ai_profiles.get_active()
                    policy = (
                        active_profile.get("policy", {})
                        if isinstance(active_profile, dict)
                        else {}
                    )
                    profile_allow_apply = (
                        bool(policy.get("allow_auto_apply", True))
                        if isinstance(policy, dict)
                        else True
                    )
                    requested_allow_apply = bool(body.get("allow_apply", True))
                    allow_apply = bool(requested_allow_apply and profile_allow_apply)
                    prompt = _resolve_system_prompt(
                        active_profile,
                        allow_apply=allow_apply,
                        repo_root=firmware.repo_root,
                    )
                    serial_h = gateway.health()
                    cached_status = dict(serial_h.get("last_status", {}))

                    ctx = {
                        "status": cached_status,
                        "status_source": "gateway.health.last_status_cached",
                        "serial_health": serial_h,
                        "control": control.snapshot(),
                        "firmware": firmware.status(),
                        "commissioning": _commissioning_ai_context(commissioning),
                        "host_capture": _host_capture_ai_context(host_capture),
                        "burst": burst_status(),
                        "config_snapshots": config_history.list_snapshots(limit=8),
                        "assistant_capabilities": _assistant_capabilities_context(
                            allow_apply=allow_apply
                        ),
                        "assistant_profile": active_profile,
                        "assistant_knowledge": knowledge.context(),
                    }
                    skey = f"user:{me['id']}"
                    hardware_sync = sync_hardware_context(skey, body, ctx)
                    hardware_notice = str(hardware_sync.get("notice", "")).strip()
                    thread_id = str(body.get("thread_id", "")).strip() or None
                    if thread_id:
                        try:
                            ai.history(skey, thread_id)
                        except RuntimeError as exc:
                            if str(exc) == "thread_not_found":
                                return _json(
                                    self,
                                    404,
                                    {"ok": False, "error": "thread_not_found"},
                                )
                            raise

                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Cache-Control", "no-cache")
                    self.send_header("Connection", "keep-alive")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.send_header(
                        "Access-Control-Allow-Headers",
                        "Content-Type, Authorization, X-Session-Token",
                    )
                    self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
                    self.end_headers()

                    def send_evt(name: str, payload_obj: Dict[str, Any]) -> None:
                        blob = f"event: {name}\ndata: {json.dumps(payload_obj, ensure_ascii=True)}\n\n".encode(
                            "utf-8"
                        )
                        self.wfile.write(blob)
                        self.wfile.flush()

                    send_evt("start", {"ok": True})
                    try:
                        if hardware_notice:
                            send_evt("delta", {"text": f"{hardware_notice}\n\n"})
                        delta_marker = "UPRIGHT_APPLY_JSON:"
                        delta_state: Dict[str, Any] = {
                            "carry": "",
                            "suppress": False,
                        }

                        def on_stream_delta(txt: str) -> None:
                            if not txt:
                                return
                            if bool(delta_state["suppress"]):
                                return
                            combined = str(delta_state["carry"]) + txt
                            idx = combined.find(delta_marker)
                            if idx >= 0:
                                emit = combined[:idx]
                                delta_state["carry"] = ""
                                delta_state["suppress"] = True
                                if emit:
                                    send_evt("delta", {"text": emit})
                                return
                            keep = max(0, len(delta_marker) - 1)
                            safe_len = max(0, len(combined) - keep)
                            if safe_len > 0:
                                emit = combined[:safe_len]
                                delta_state["carry"] = combined[safe_len:]
                                send_evt("delta", {"text": emit})
                            else:
                                delta_state["carry"] = combined

                        out = ai.chat_stream(
                            message=msg,
                            context=ctx,
                            session_key=skey,
                            api_key=creds["api_key"],
                            model=str(creds["model"] or "gpt-5-codex"),
                            on_delta=on_stream_delta,
                            thread_id=thread_id,
                            system_prompt=prompt,
                        )
                        if (not bool(delta_state["suppress"])) and str(
                            delta_state["carry"]
                        ):
                            send_evt("delta", {"text": str(delta_state["carry"])})
                        reply = _strip_apply_json_block(out["answer"])
                        if hardware_notice:
                            reply = f"{hardware_notice}\n\n{reply}".strip()
                        reply = _normalize_reply_for_prompt(msg, reply)
                        apply_result: Optional[Dict[str, Any]] = None
                        apply_src = _extract_apply_json(out["answer"])
                        plan = (
                            _sanitize_apply_plan(apply_src)
                            if isinstance(apply_src, dict)
                            else {}
                        )
                        if allow_apply and plan:
                            try:
                                apply_result = _apply_assistant_plan(
                                    gateway,
                                    config_history,
                                    firmware,
                                    plan,
                                    source="ai/chat/stream",
                                )
                            except Exception as exc:
                                apply_result = {"ok": False, "error": str(exc)}
                        if apply_result:
                            note = _format_apply_note(apply_result)
                            reply = f"{reply}\n\n{note}".strip()
                            reply = _normalize_reply_for_prompt(msg, reply)
                            reply = _normalize_reply_for_prompt(msg, reply)
                        hist = ai.history(skey, out.get("thread_id"))[-80:]
                        if reply != out["answer"]:
                            hist = history_with_reply(hist, reply)
                        send_evt(
                            "done",
                            {
                                "ok": True,
                                "reply": reply,
                                "ai": ai.status(
                                    configured=True,
                                    model=str(creds["model"] or "gpt-5-codex"),
                                    session_key=skey,
                                ),
                                "history": hist,
                                "threads": ai.list_threads(skey),
                                "thread_id": out.get("thread_id"),
                                "apply": apply_result,
                            },
                        )
                    except Exception as exc:
                        send_evt("error", {"ok": False, "error": str(exc)})
                    return

                if u.path == "/tooling/trace-replay":
                    code, payload = handle_trace_replay(
                        body=body,
                        repo_root=repo_root,
                        replay_file=replay_file,
                    )
                    return _json(self, code, payload)

                if u.path == "/tooling/param-sweep":
                    code, payload = handle_param_sweep(
                        body=body,
                        gateway=gateway,
                        ParameterSweepRunner=ParameterSweepRunner,
                        parse_range_spec=parse_range_spec,
                        SweepConfig=SweepConfig,
                    )
                    return _json(self, code, payload)

                if u.path == "/tooling/surrogate/simulate":
                    code, payload = handle_surrogate_simulate(
                        body=body,
                        repo_root=repo_root,
                        simulate_from_logs=simulate_from_logs,
                    )
                    return _json(self, code, payload)

                if u.path == "/tooling/tuning/recommend":
                    code, payload = handle_tuning_recommend(
                        body=body,
                        repo_root=repo_root,
                        evaluate_tuning_plan=evaluate_tuning_plan,
                        replay_file=replay_file,
                        simulate_from_logs=simulate_from_logs,
                        validate_contract_fn=_validate_tuning_recommendation_contract,
                        evaluate_quality_fn=_evaluate_tuning_recommendation_quality,
                    )
                    return _json(self, code, payload)

                if u.path == "/tooling/tuning/preflight":
                    code, payload = handle_tuning_preflight(
                        body=body,
                        repo_root=repo_root,
                        status_now=gateway.get_status(),
                        evaluate_tuning_plan=evaluate_tuning_plan,
                        replay_file=replay_file,
                        simulate_from_logs=simulate_from_logs,
                        validate_contract_fn=_validate_tuning_recommendation_contract,
                        evaluate_quality_fn=_evaluate_tuning_recommendation_quality,
                        build_signature_fn=_build_tuning_apply_signature,
                        preflight_issue_fn=tuning_preflight.issue,
                        status_float_fn=_status_float,
                    )
                    return _json(self, code, payload)

                if u.path == "/command":
                    code, payload = handle_command(
                        body=body,
                        gateway=gateway,
                        control=control,
                        blocked_while_latched_fn=_blocked_while_latched,
                    )
                    return _json(self, code, payload)

                if u.path == "/burst/arm":
                    _require_action_allowed(
                        "burst_arm", gateway, control, prearm_gate=prearm_safety
                    )
                    active_profile = _active_robot_profile()
                    defaults = _burst_threshold_defaults(active_profile)
                    code, payload = handle_burst_arm(
                        body=body,
                        gateway=gateway,
                        host_capture=host_capture,
                        burst_status_fn=burst_status,
                        active_profile=active_profile,
                        defaults=defaults,
                    )
                    return _json(self, code, payload)

                if u.path == "/burst/label":
                    code, payload = handle_burst_label(
                        body=body,
                        host_capture=host_capture,
                        burst_status_fn=burst_status,
                    )
                    return _json(self, code, payload)

                if u.path == "/arm/prepare":
                    _require_action_allowed(
                        "arm_prepare", gateway, control, prearm_gate=prearm_safety
                    )
                    code, payload = handle_arm_prepare(control=control)
                    return _json(self, code, payload)

                if u.path == "/arm/precheck":
                    report = _run_prearm_hardware_check(gateway, control, body)
                    if bool(report.get("ok", False)):
                        prearm = prearm_safety.mark_pass(report)
                    else:
                        prearm = prearm_safety.require("prearm_failed")
                    try:
                        _report_design_observation(
                            session_key=(
                                str(body.get("session_key", "")).strip()
                                or "local:prearm"
                            ),
                            success=bool(report.get("ok", False)),
                            source="prearm_check",
                            note=(
                                str(report.get("summary", "")).strip()
                                or str(report.get("error", "")).strip()
                            ),
                            profile_id=str(body.get("profile_id", "")).strip(),
                            profile_label=str(body.get("profile_label", "")).strip(),
                            sketch_revision=str(
                                body.get("sketch_revision", "")
                            ).strip(),
                            test_type="prearm",
                        )
                    except Exception:
                        pass
                    payload = build_arm_precheck_payload(
                        report=report,
                        prearm_safety=prearm,
                        action_gates=_resolve_action_gates(
                            gateway, control, prearm_gate=prearm_safety
                        ),
                    )
                    validate_prearm_precheck_response(payload)
                    return _json(
                        self,
                        200 if bool(report.get("ok", False)) else 409,
                        payload,
                    )

                if u.path == "/arm/confirm":
                    _require_action_allowed(
                        "arm_confirm", gateway, control, prearm_gate=prearm_safety
                    )
                    code, payload = handle_arm_confirm(gateway=gateway, control=control)
                    return _json(self, code, payload)

                if u.path == "/arm":
                    _require_action_allowed(
                        "arm", gateway, control, prearm_gate=prearm_safety
                    )
                    code, payload = handle_arm(gateway=gateway, control=control)
                    return _json(self, code, payload)

                if u.path == "/disarm":
                    _require_action_allowed(
                        "disarm", gateway, control, prearm_gate=prearm_safety
                    )
                    code, payload = handle_disarm(gateway=gateway, control=control)
                    return _json(self, code, payload)

                if u.path == "/estop/latch":
                    code, payload = handle_estop_latch(gateway=gateway, control=control)
                    return _json(self, code, payload)

                if u.path == "/estop/reset":
                    code, payload = handle_estop_reset(gateway=gateway, control=control)
                    return _json(self, code, payload)

                if u.path == "/cal_zero":
                    _require_action_allowed("cal_zero", gateway, control)
                    code, payload = handle_cal_zero(gateway=gateway, control=control)
                    return _json(self, code, payload)

                if u.path == "/imu/calibrate":
                    _require_action_allowed("cal_zero", gateway, control)
                    code, payload = handle_imu_calibrate(
                        gateway=gateway,
                        control=control,
                        classify_imu_fn=lambda res, cmd: _classify_imu_command_result(
                            res, cmd_name=cmd
                        ),
                    )
                    return _json(self, code, payload)

                if u.path == "/imu/load":
                    code, payload = handle_imu_load(
                        gateway=gateway,
                        control=control,
                        classify_imu_fn=lambda res, cmd: _classify_imu_command_result(
                            res, cmd_name=cmd
                        ),
                    )
                    return _json(self, code, payload)

                if u.path == "/imu/save":
                    code, payload = handle_imu_save(
                        gateway=gateway,
                        control=control,
                        classify_imu_fn=lambda res, cmd: _classify_imu_command_result(
                            res, cmd_name=cmd
                        ),
                    )
                    return _json(self, code, payload)

                if u.path == "/imu/info":
                    code, payload = handle_imu_info(
                        gateway=gateway,
                        control=control,
                        classify_imu_fn=lambda res, cmd: _classify_imu_command_result(
                            res, cmd_name=cmd
                        ),
                    )
                    return _json(self, code, payload)

                if u.path == "/savecfg":
                    code, payload = handle_savecfg(gateway=gateway, control=control)
                    return _json(self, code, payload)

                if u.path == "/loadcfg":
                    code, payload = handle_loadcfg(gateway=gateway, control=control)
                    return _json(self, code, payload)

                if u.path == "/defaultcfg":
                    code, payload = handle_defaultcfg(gateway=gateway, control=control)
                    return _json(self, code, payload)

                if u.path == "/pid":
                    kp = float(body["kp"])
                    ki = float(body["ki"])
                    kd = float(body["kd"])
                    status_before = gateway.get_status()
                    _require_action_allowed(
                        "pid", gateway, control, status_override=status_before
                    )
                    current = {
                        "kp": _status_float(status_before, "kp", default=31.0),
                        "ki": _status_float(status_before, "ki", default=0.05),
                        "kd": _status_float(status_before, "kd", default=1.05),
                    }
                    target = {"kp": kp, "ki": ki, "kd": kd}
                    _guard_pid_apply(status_before, kp, ki, kd)
                    preflight_used = _enforce_preflight_if_needed(
                        preflight_store=tuning_preflight,
                        body=body,
                        family="pid",
                        status_before=status_before,
                        current=current,
                        target=target,
                    )
                    snap = config_history.save_snapshot(
                        source="/pid", status_before=status_before
                    )
                    res = gateway.command(
                        f"PID {kp} {ki} {kd}", expect_contains="OK PID", timeout=2.0
                    )
                    return _json(
                        self,
                        200,
                        build_tuning_result_payload(
                            result=res,
                            snapshot=snap,
                            status=gateway.get_status(),
                            control=control.snapshot(),
                            preflight_id=preflight_used,
                        ),
                    )

                if u.path == "/motion":
                    kv = float(body["kv"])
                    kx = float(body["kx"])
                    status_before = gateway.get_status()
                    _require_action_allowed(
                        "motion", gateway, control, status_override=status_before
                    )
                    current = {
                        "kv": _status_float(status_before, "kv", default=0.0),
                        "kx": _status_float(status_before, "kx", default=0.0),
                    }
                    target = {"kv": kv, "kx": kx}
                    _guard_motion_apply(status_before, kv, kx)
                    preflight_used = _enforce_preflight_if_needed(
                        preflight_store=tuning_preflight,
                        body=body,
                        family="motion",
                        status_before=status_before,
                        current=current,
                        target=target,
                    )
                    snap = config_history.save_snapshot(
                        source="/motion", status_before=status_before
                    )
                    res = gateway.command(
                        f"MOTION {kv} {kx}", expect_contains="OK MOTION", timeout=2.0
                    )
                    return _json(
                        self,
                        200,
                        build_tuning_result_payload(
                            result=res,
                            snapshot=snap,
                            status=gateway.get_status(),
                            control=control.snapshot(),
                            preflight_id=preflight_used,
                        ),
                    )

                if u.path == "/setpoint":
                    deg = float(body["deg"])
                    status_before = gateway.get_status()
                    _require_action_allowed(
                        "setpoint", gateway, control, status_override=status_before
                    )
                    current = {"deg": _status_float(status_before, "set", default=0.0)}
                    target = {"deg": deg}
                    _guard_setpoint_apply(status_before, deg)
                    preflight_used = _enforce_preflight_if_needed(
                        preflight_store=tuning_preflight,
                        body=body,
                        family="setpoint",
                        status_before=status_before,
                        current=current,
                        target=target,
                    )
                    snap = config_history.save_snapshot(
                        source="/setpoint", status_before=status_before
                    )
                    res = gateway.command(
                        f"SETPOINT {deg}", expect_contains="OK SETPOINT", timeout=2.0
                    )
                    return _json(
                        self,
                        200,
                        build_tuning_result_payload(
                            result=res,
                            snapshot=snap,
                            status=gateway.get_status(),
                            control=control.snapshot(),
                            preflight_id=preflight_used,
                        ),
                    )

                if u.path == "/limits":
                    out_max = float(body["out_max"])
                    tip_deg = float(body["tip_deg"])
                    i_max = float(body["i_max"])
                    status_before = gateway.get_status()
                    _require_action_allowed(
                        "limits", gateway, control, status_override=status_before
                    )
                    current = {
                        "out_max": _status_float(
                            status_before, "outMax", "out_max", default=180.0
                        ),
                        "tip_deg": _status_float(
                            status_before, "tipDeg", "tip_deg", default=35.0
                        ),
                        "i_max": _status_float(
                            status_before, "iMax", "i_max", default=70.0
                        ),
                    }
                    target = {"out_max": out_max, "tip_deg": tip_deg, "i_max": i_max}
                    _guard_limits_apply(status_before, out_max, tip_deg, i_max)
                    preflight_used = _enforce_preflight_if_needed(
                        preflight_store=tuning_preflight,
                        body=body,
                        family="limits",
                        status_before=status_before,
                        current=current,
                        target=target,
                    )
                    snap = config_history.save_snapshot(
                        source="/limits", status_before=status_before
                    )
                    res = gateway.command(
                        f"LIMITS {out_max} {tip_deg} {i_max}",
                        expect_contains="OK LIMITS",
                        timeout=2.0,
                    )
                    return _json(
                        self,
                        200,
                        build_tuning_result_payload(
                            result=res,
                            snapshot=snap,
                            status=gateway.get_status(),
                            control=control.snapshot(),
                            preflight_id=preflight_used,
                        ),
                    )

                return _json(self, 404, {"ok": False, "error": "not_found"})
            except KeyError as exc:
                return _json(self, 400, {"ok": False, "error": f"missing field: {exc}"})
            except RuntimeError as exc:
                msg = str(exc)
                if msg in {
                    "invalid_email",
                    "weak_password",
                    "email_exists",
                    "invalid_credentials",
                    "invalid_openai_key",
                    "empty_message",
                    "sketch_content_empty",
                }:
                    return _json(self, 400, {"ok": False, "error": msg})
                if msg.startswith("openai_key_verification_failed:"):
                    return _json(self, 503, {"ok": False, "error": msg})
                if msg in {"profile_label_required", "profile_id_required"}:
                    return _json(self, 400, {"ok": False, "error": msg})
                if msg.startswith("invalid_unified_profile:"):
                    return _json(self, 400, {"ok": False, "error": msg})
                if msg in {"ai_profile_label_required", "ai_profile_id_required"}:
                    return _json(self, 400, {"ok": False, "error": msg})
                if msg in {"profile_not_found"}:
                    return _json(self, 404, {"ok": False, "error": msg})
                if msg in {"ai_profile_not_found"}:
                    return _json(self, 404, {"ok": False, "error": msg})
                if msg in {"snapshot_not_found"}:
                    return _json(self, 404, {"ok": False, "error": msg})
                if msg in {"unauthenticated", "openai_api_key_missing"}:
                    return _json(self, 401, {"ok": False, "error": msg})
                if msg == "tuning_delta_too_large_while_balancing":
                    return _json(
                        self,
                        409,
                        {"ok": False, "error": msg, "control": control.snapshot()},
                    )
                if msg.startswith("invalid_tuning_value:"):
                    return _json(self, 400, {"ok": False, "error": msg})
                if msg in {
                    "preflight_required",
                    "preflight_invalid",
                    "preflight_mismatch",
                }:
                    return _json(
                        self,
                        428,
                        {"ok": False, "error": msg, "control": control.snapshot()},
                    )
                if msg in {"estop_latched", "session_stale"}:
                    return _json(
                        self,
                        423,
                        {"ok": False, "error": msg, "control": control.snapshot()},
                    )
                if msg.startswith("action_blocked:"):
                    parts = msg.split(":", 2)
                    action = parts[1] if len(parts) > 1 else "unknown"
                    reasons_raw = parts[2] if len(parts) > 2 else ""
                    reasons = [r for r in reasons_raw.split(",") if r]
                    return _json(
                        self,
                        423,
                        {
                            "ok": False,
                            "error": "action_blocked",
                            "action": action,
                            "reasons": reasons,
                            "action_gates": _resolve_action_gates(
                                gateway, control, prearm_gate=prearm_safety
                            ),
                            "control": control.snapshot(),
                        },
                    )
                if msg == "arm_not_prepared":
                    return _json(
                        self,
                        409,
                        {"ok": False, "error": msg, "control": control.snapshot()},
                    )
                if msg == "commissioning_running":
                    return _json(
                        self,
                        409,
                        {
                            "ok": False,
                            "error": msg,
                            "commissioning": commissioning.status(),
                        },
                    )
                if msg in {"firmware_running", "operation_in_progress"}:
                    return _json(
                        self,
                        409,
                        {"ok": False, "error": msg, "firmware": firmware.status()},
                    )
                return _json(self, 500, {"ok": False, "error": msg})
            except Exception as exc:
                return _json(self, 500, {"ok": False, "error": str(exc)})

    return Handler


def watchdog_loop(
    gateway: NanoSerialGateway, control: BridgeControlState, stop_evt: threading.Event
) -> None:
    while not stop_evt.wait(0.1):
        try:
            if not control.check_and_trip_watchdog():
                continue
            status = gateway.get_status()
            mode = str(status.get("mode", "UNKNOWN"))
            if mode in {"BALANCING", "ARMED"}:
                gateway.command("DISARM", timeout=1.0)
                control.record_watchdog_disarm(f"heartbeat_timeout:{mode}")
        except Exception:
            continue


def serial_reconnect_loop(
    gateway: NanoSerialGateway, firmware: FirmwareManager, stop_evt: threading.Event
) -> None:
    while not stop_evt.wait(2.0):
        try:
            # Avoid racing avrdude by reconnecting the bridge while a flash is active.
            if bool(firmware.status().get("running", False)):
                continue
            if gateway.health().get("connected", False):
                continue
            gateway.connect()
            ready = gateway.wait_ready(timeout=5.0)
            print(f"serial reconnected: mode={ready.get('mode', 'UNKNOWN')}")
        except Exception:
            try:
                gateway.close()
            except Exception:
                pass
            continue


def _startup_rag_indexing(openai_key: Optional[str]) -> None:
    """
    Background RAG indexing on server startup.
    Non-blocking - runs in daemon thread. Fails gracefully if RAG unavailable.
    """
    if not openai_key:
        logger.info("Startup RAG indexing skipped: no OpenAI key available")
        return
    if not get_codex_rag:
        logger.info("Startup RAG indexing skipped: RAG module not available")
        return
    try:
        rag = get_codex_rag(openai_key)
        logger.info("Starting background RAG indexing...")
        start_ts = time.time()
        doc_stats = rag.index_docs(force_reindex=False)
        sketch_stats = rag.index_sketches(force_reindex=False)
        elapsed_s = time.time() - start_ts
        logger.info(
            f"Background RAG indexing complete in {elapsed_s:.1f}s: "
            f"docs={doc_stats['files_processed']} processed/{doc_stats['files_skipped']} skipped, "
            f"sketches={sketch_stats['files_processed']} processed/{sketch_stats['files_skipped']} skipped"
        )
    except Exception as exc:
        logger.warning(f"Background RAG indexing failed (non-fatal): {exc}")


def main() -> int:
    _install_runtime_diagnostics()
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--port", default=os.environ.get("NANO_PORT", "/dev/tty.usbserial-2210")
    )
    ap.add_argument(
        "--baud", type=int, default=int(os.environ.get("NANO_BAUD", "115200"))
    )
    ap.add_argument("--host", default=os.environ.get("APP_BRIDGE_HOST", "127.0.0.1"))
    ap.add_argument(
        "--http-port", type=int, default=int(os.environ.get("APP_BRIDGE_PORT", "8797"))
    )
    ap.add_argument(
        "--telemetry-port",
        type=int,
        default=int(os.environ.get("APP_TELEMETRY_PORT", "8798")),
    )
    ap.add_argument(
        "--instance",
        default=os.environ.get("APP_BRIDGE_INSTANCE", "upright-lean-v1"),
        help="Instance label for process isolation/observability",
    )
    ap.add_argument(
        "--watchdog-timeout",
        type=float,
        default=float(os.environ.get("APP_WATCHDOG_TIMEOUT_S", "2.0")),
    )
    ap.add_argument(
        "--supervised",
        action="store_true",
        help="Suppress direct-run warning (set by supervisor)",
    )
    args = ap.parse_args()

    if not args.supervised:
        print("\n⚠️  Running bridge directly (no supervisor).")
        print("   For auto-restart on failure, use: ./tools/start_bridge.sh\n")
    print(f"bridge instance: {args.instance}")

    repo_root = pathlib.Path(__file__).resolve().parents[2]
    gw = NanoSerialGateway(args.port, args.baud)
    startup_serial_error: Optional[str] = None
    try:
        gw.connect()
    except Exception as exc:
        startup_serial_error = str(exc)
        try:
            gw.close()
        except Exception:
            pass
    control = BridgeControlState(watchdog_timeout_s=max(0.5, args.watchdog_timeout))
    commissioning = CommissioningManager(repo_root, args.port, args.baud)
    host_capture = HostCaptureManager(repo_root)
    firmware = FirmwareManager(repo_root, args.port)
    ai = AIManager(repo_root)
    ai_profiles = AIProfileManager(repo_root)
    knowledge = AssistantKnowledgeManager(repo_root)
    agent_mission = AgentMissionManager(repo_root)
    provider_router = ProviderRouter(repo_root)

    # Initialize CodexAgent for tool-enabled chat (optional - gracefully degrades if unavailable)
    codex_agent: Optional[Any] = None
    if create_codex_agent is not None:
        try:
            codex_agent = create_codex_agent(
                gateway=gw,
                firmware_module=firmware,
                probe_funcs={
                    "run_compat_probe": run_compat_probe,
                    "run_connect_probe": run_connect_probe,
                },
                repo_root=str(repo_root),
                host_capture=host_capture,
            )
            print("codex agent initialized with tool support")
            # Kick off background RAG indexing (non-blocking)
            startup_openai_key = os.environ.get("OPENAI_API_KEY")
            if startup_openai_key:
                rag_thread = threading.Thread(
                    target=_startup_rag_indexing,
                    args=(startup_openai_key,),
                    daemon=True,
                    name="startup-rag-indexing",
                )
                rag_thread.start()
                print("background RAG indexing started")
        except Exception as exc:
            print(f"codex agent init failed (tool support disabled): {exc}")
    auth = AuthManager(repo_root)
    mission_memory = MissionMemoryStore(repo_root)
    hardware_context = HardwareContextStore(repo_root)
    setup_attempt_history = SetupAttemptHistoryStore(repo_root)
    profiles = RobotProfilesManager(repo_root)
    config_history = ConfigHistoryManager(repo_root)
    prearm_safety = PreArmSafetyGate(required=True)
    telemetry = TelemetryHub(gw, control, host_capture, args.host, args.telemetry_port)
    telemetry.start()

    if startup_serial_error:
        print(
            f"bridge started without serial target: {args.port} @ {args.baud} ({startup_serial_error})"
        )
    else:
        print(f"bridge serial opened: {args.port} @ {args.baud}")
    print(
        f"telemetry websocket: ws://{args.host}:{args.telemetry_port}/telemetry enabled={websockets is not None}"
    )

    stop_evt = threading.Event()
    wd = threading.Thread(
        target=watchdog_loop, args=(gw, control, stop_evt), daemon=True
    )
    wd.start()
    reconn = threading.Thread(
        target=serial_reconnect_loop, args=(gw, firmware, stop_evt), daemon=True
    )
    reconn.start()

    server = ThreadingHTTPServer(
        (args.host, args.http_port),
        build_handler(
            gw,
            control,
            commissioning,
            host_capture,
            firmware,
            ai,
            ai_profiles,
            knowledge,
            agent_mission,
            provider_router,
            auth,
            mission_memory,
            profiles,
            config_history,
            args.telemetry_port,
            codex_agent,
            hardware_context,
            setup_attempt_history,
            prearm_safety,
        ),
    )
    print(f"bridge listening on http://{args.host}:{args.http_port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop_evt.set()
        telemetry.stop()
        server.server_close()
        gw.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
