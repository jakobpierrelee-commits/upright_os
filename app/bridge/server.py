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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger(__name__)

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
        validate_prearm_precheck_response,
    )
except ImportError:
    from clean_contracts import (  # type: ignore
        validate_clean_preflight_response,
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
        build_clean_status_payload,
    )
except ImportError:
    from clean_status import (  # type: ignore
        build_agent_status_payload,
        build_clean_status_payload,
    )
# clean_profiles imports removed - all were unused
# clean_firmware imports removed - all were unused
try:
    from app.bridge.clean_safety import (
        build_arm_precheck_payload,
    )
except ImportError:
    pass
try:
    from app.bridge.clean_tuning import (
        build_burst_status_payload,
        build_commissioning_artifacts_payload,
        build_commissioning_status_payload,
        build_lines_payload,
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
    )
except ImportError:
    pass
try:
    from app.bridge.routes_tuning import (
        handle_tuning_capabilities_get,
        handle_tuning_preflight,
        handle_tuning_recommend,
        handle_pid_post,
        handle_motion_post,
        handle_setpoint_post,
        handle_limits_post,
    )
except ImportError:
    from routes_tuning import (  # type: ignore
        handle_tuning_capabilities_get,
        handle_tuning_preflight,
        handle_tuning_recommend,
        handle_pid_post,
        handle_motion_post,
        handle_setpoint_post,
        handle_limits_post,
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
        handle_tooling_traces_get,
        handle_trace_replay,
    )
except ImportError:
    from routes_tooling import (  # type: ignore
        handle_param_sweep,
        handle_surrogate_simulate,
        handle_tooling_traces_get,
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
        handle_release_serial_post,
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
        handle_release_serial_post,
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
        handle_arm_precheck,
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
        handle_arm_precheck,
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
        handle_telemetry_adapter_map_get,
        handle_diag_serial_get,
        handle_lines_get,
    )
except ImportError:
    from routes_health import (  # type: ignore
        handle_health,
        handle_status,
        handle_telemetry_adapter_map_get,
        handle_diag_serial_get,
        handle_lines_get,
    )
try:
    from app.bridge.routes_ai import (
        handle_agent_clean_status_get,
        handle_agent_file_upload,
        handle_agent_mode_set,
        handle_agent_status_get,
        handle_agent_thread_new,
        handle_agent_thread_select,
        handle_agent_threads_get,
        handle_ai_knowledge_get,
        handle_ai_metrics_get,
        handle_ai_profile_activate,
        handle_ai_profile_save,
        handle_ai_profiles_get,
        handle_ai_rag_stats_get,
        handle_ai_status_get,
        handle_ai_thread_new,
        handle_ai_thread_select,
        handle_ai_threads_get,
        handle_session_heartbeat,
        handle_setup_attempt_history_get,
        handle_agent_chat_post,
        handle_clean_preflight_post,
        handle_clean_chat_post,
    )
except ImportError:
    from routes_ai import (  # type: ignore
        handle_agent_clean_status_get,
        handle_agent_file_upload,
        handle_agent_mode_set,
        handle_agent_status_get,
        handle_agent_thread_new,
        handle_agent_threads_get,
        handle_ai_knowledge_get,
        handle_ai_metrics_get,
        handle_ai_profile_activate,
        handle_ai_profile_save,
        handle_ai_profiles_get,
        handle_ai_rag_stats_get,
        handle_ai_status_get,
        handle_ai_thread_new,
        handle_ai_thread_select,
        handle_ai_threads_get,
        handle_session_heartbeat,
        handle_setup_attempt_history_get,
        handle_agent_chat_post,
        handle_clean_preflight_post,
        handle_clean_chat_post,
    )
try:
    from app.bridge.routes_auth import (
        handle_auth_login,
        handle_auth_logout,
        handle_auth_me_get,
        handle_auth_openai_key_delete,
        handle_auth_openai_key_set,
        handle_auth_openai_key_status_get,
        handle_auth_password_reset_confirm,
        handle_auth_password_reset_request,
        handle_auth_register,
    )
except ImportError:
    from routes_auth import (  # type: ignore
        handle_auth_login,
        handle_auth_logout,
        handle_auth_me_get,
        handle_auth_openai_key_delete,
        handle_auth_openai_key_set,
        handle_auth_openai_key_status_get,
        handle_auth_password_reset_confirm,
        handle_auth_password_reset_request,
        handle_auth_register,
    )
try:
    from app.bridge.routes_design import (
        handle_design_memory_best_get,
        handle_design_memory_list_get,
        handle_design_memory_rate,
        handle_design_memory_report_success,
    )
except ImportError:
    from routes_design import (  # type: ignore
        handle_design_memory_best_get,
        handle_design_memory_list_get,
        handle_design_memory_rate,
        handle_design_memory_report_success,
    )
try:
    from app.bridge.routes_config import (
        handle_config_revert,
        handle_config_snapshots_get,
    )
except ImportError:
    from routes_config import (  # type: ignore
        handle_config_revert,
        handle_config_snapshots_get,
    )
try:
    from app.bridge.routes_overwatch import handle_overwatch_status_get
except ImportError:
    from routes_overwatch import handle_overwatch_status_get  # type: ignore
try:
    from app.bridge.routes_probe import (
        handle_probe_compat_get,
        handle_probe_connect_get,
        handle_setup_compat_test,
        handle_setup_smoke_check,
        handle_setup_overwatch_check,
    )
except ImportError:
    from routes_probe import (  # type: ignore
        handle_probe_compat_get,
        handle_probe_connect_get,
        handle_setup_compat_test,
        handle_setup_smoke_check,
        handle_setup_overwatch_check,
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
        build_ai_threads_status_payload,
        build_chat_with_tools_payload,
        build_disambiguation_reply_payload,
        build_openai_config_payload,
        build_rag_index_payload,
        build_session_heartbeat_payload,
    )
try:
    from app.bridge.clean_serial import (
        build_diag_serial_payload,
        build_telemetry_adapters_payload,
    )
except ImportError:
    from clean_serial import (  # type: ignore
        build_diag_serial_payload,
        build_telemetry_adapters_payload,
    )
try:
    from app.bridge.clean_misc import (
        build_action_payload,
        build_agent_state_payload,
        build_attempt_history_payload,
        build_attachment_payload,
        build_capabilities_payload,
        build_design_payload,
        build_overwatch_payload,
        build_port_released_payload,
        build_reset_payload,
        build_result_payload,
        build_revert_control_payload,
        build_setup_check_payload,
        build_snapshots_payload,
        build_stats_payload,
        build_tool_metrics_payload,
        build_upload_confirm_success_payload,
    )
except ImportError:
    from clean_misc import (  # type: ignore
        build_action_payload,
        build_agent_state_payload,
        build_attempt_history_payload,
        build_attachment_payload,
        build_design_payload,
        build_port_released_payload,
        build_revert_control_payload,
        build_setup_check_payload,
        build_stats_payload,
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

try:
    from app.bridge.manifest_validation import (
        _pin_range_for_family,
        _family_capabilities,
        _protocol_schema,
        _has_valid_pin,
        _validate_protocol_pins,
        _validate_runtime_manifest_v1,
        _manifest_required_field_present,
        _family_for_fqbn,
        _board_id_for_fqbn,
        _runtime_manifest_profile_compatibility,
    )
except ImportError:
    from manifest_validation import (  # type: ignore
        _pin_range_for_family,
        _family_capabilities,
        _protocol_schema,
        _has_valid_pin,
        _validate_protocol_pins,
        _validate_runtime_manifest_v1,
        _manifest_required_field_present,
        _family_for_fqbn,
        _board_id_for_fqbn,
        _runtime_manifest_profile_compatibility,
    )

try:
    from app.bridge.contract_readiness import (
        V1_REQUIRED_FIELDS,
        V1_GYRO_ALIASES,
        V2_READINESS_FIELDS,
        V2_FACTORY_FIELDS,
        V2_OPTIONAL_FIELDS,
        detect_contract_readiness,
        _compute_action_gates,
        _default_compat_policy,
        _load_compat_policy,
        _status_has_required_fields,
        _resolve_compat_profile,
        _resolve_action_gates,
        _require_action_allowed,
    )
except ImportError:
    from contract_readiness import (  # type: ignore
        V1_REQUIRED_FIELDS,
        V1_GYRO_ALIASES,
        V2_READINESS_FIELDS,
        V2_FACTORY_FIELDS,
        V2_OPTIONAL_FIELDS,
        detect_contract_readiness,
        _compute_action_gates,
        _default_compat_policy,
        _load_compat_policy,
        _status_has_required_fields,
        _resolve_compat_profile,
        _resolve_action_gates,
        _require_action_allowed,
    )

try:
    from app.bridge.probe_runners import (
        run_compat_probe,
        _get_port_meta,
        _guess_mcu,
        run_connect_probe,
        run_setup_compat_test,
        run_setup_smoke_check,
        run_setup_overwatch_check,
        _latest_docs_folder,
        _validate_docs_artifacts,
        build_overwatch_report,
    )
except ImportError:
    from probe_runners import (  # type: ignore
        run_compat_probe,
        _get_port_meta,
        _guess_mcu,
        run_connect_probe,
        run_setup_compat_test,
        run_setup_smoke_check,
        run_setup_overwatch_check,
        _latest_docs_folder,
        _validate_docs_artifacts,
        build_overwatch_report,
    )

try:
    from app.bridge.tuning_guards import (
        TUNING_BAL_BOUNDS,
        TUNING_PREFLIGHT_DELTA,
        _status_float,
        _require_tuning_range,
        _guard_pid_apply,
        _guard_motion_apply,
        _guard_setpoint_apply,
        _guard_limits_apply,
        _detect_tuning_capabilities,
        _validate_tuning_recommendation_contract,
        _evaluate_tuning_recommendation_quality,
        _build_tuning_apply_signature,
        _requires_preflight,
        _enforce_preflight_if_needed,
    )
except ImportError:
    from tuning_guards import (  # type: ignore
        TUNING_BAL_BOUNDS,
        TUNING_PREFLIGHT_DELTA,
        _status_float,
        _require_tuning_range,
        _guard_pid_apply,
        _guard_motion_apply,
        _guard_setpoint_apply,
        _guard_limits_apply,
        _detect_tuning_capabilities,
        _validate_tuning_recommendation_contract,
        _evaluate_tuning_recommendation_quality,
        _build_tuning_apply_signature,
        _requires_preflight,
        _enforce_preflight_if_needed,
    )

try:
    from app.bridge.agent_helpers import (
        _codexrules_cache,
        _load_codexrules,
        _resolve_system_prompt,
        _agent_mode_system_prompt,
        _agent_model_allowed,
        _agent_mode_default_model,
        _agent_resolve_model,
        _agent_choose_executor,
        _install_runtime_diagnostics,
        _codex_cli_login_status,
        _legacy_execution_guard,
        _extract_mission_facts,
        _first_sentence,
        _truncate_words,
        _is_high_risk_user_request,
        _strip_repetitive_caution_lines,
        _soften_forced_reply_exact,
        _normalize_reply_for_prompt,
    )
except ImportError:
    from agent_helpers import (  # type: ignore
        _codexrules_cache,
        _load_codexrules,
        _resolve_system_prompt,
        _agent_mode_system_prompt,
        _agent_model_allowed,
        _agent_mode_default_model,
        _agent_resolve_model,
        _agent_choose_executor,
        _install_runtime_diagnostics,
        _codex_cli_login_status,
        _legacy_execution_guard,
        _extract_mission_facts,
        _first_sentence,
        _truncate_words,
        _is_high_risk_user_request,
        _strip_repetitive_caution_lines,
        _soften_forced_reply_exact,
        _normalize_reply_for_prompt,
    )


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
        limits_cfg = plan["limits"]
        out_max = (
            _safe_float(limits_cfg.get("out_max"))
            if isinstance(limits_cfg, dict)
            else None
        )
        tip_deg = (
            _safe_float(limits_cfg.get("tip_deg"))
            if isinstance(limits_cfg, dict)
            else None
        )
        i_max = (
            _safe_float(limits_cfg.get("i_max"))
            if isinstance(limits_cfg, dict)
            else None
        )
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



def _run_prearm_hardware_check(
    gateway: NanoSerialGateway,
    control: BridgeControlState,
    body: Dict[str, Any],
) -> Dict[str, Any]:
    return _run_prearm_hardware_check_impl(gateway, control, body)




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
                    code, payload = handle_telemetry_adapter_map_get(
                        gateway=gateway,
                        normalize_status_fn=_normalize_status_for_hud,
                        build_telemetry_adapters_payload_fn=build_telemetry_adapters_payload,
                        runtime_telemetry_adapters=RUNTIME_TELEMETRY_ADAPTERS,
                        hud_canonical_fields=list(HUD_CANONICAL_FIELDS),
                    )
                    return _json(self, code, payload)
                if u.path == "/diag/serial":
                    code, payload = handle_diag_serial_get(
                        gateway=gateway,
                        control=control,
                        build_diag_serial_payload_fn=build_diag_serial_payload,
                    )
                    return _json(self, code, payload)
                if u.path == "/lines":
                    q = parse_qs(u.query)
                    n = int(q.get("n", ["100"])[0])
                    code, payload = handle_lines_get(
                        gateway=gateway,
                        n=n,
                        build_lines_payload_fn=build_lines_payload,
                    )
                    return _json(self, code, payload)
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
                    code, payload = handle_design_memory_list_get(
                        query=q,
                        design_memory=design_memory,
                    )
                    return _json(self, code, payload)
                if u.path == "/design-memory/best":
                    q = parse_qs(u.query)
                    code, payload = handle_design_memory_best_get(
                        query=q,
                        design_memory=design_memory,
                    )
                    return _json(self, code, payload)
                if u.path == "/firmware/unified-schema":
                    code, payload = handle_firmware_unified_schema_get(
                        firmware=firmware
                    )
                    return _json(self, code, payload)
                if u.path == "/agent/status":
                    tok = _extract_auth_token(self)
                    me = auth.me(tok) if tok else None
                    code, payload = handle_agent_status_get(
                        me=me,
                        auth=auth,
                        agent_mission=agent_mission,
                        provider_router=provider_router,
                        ai=ai,
                        gateway=gateway,
                        control=control,
                        knowledge=knowledge,
                        codex_agent_available=bool(codex_agent is not None),
                        env_model=os.environ.get("OPENAI_MODEL", ""),
                        codex_cli_login_status_fn=_codex_cli_login_status,
                        agent_choose_executor_fn=_agent_choose_executor,
                        agent_resolve_model_fn=_agent_resolve_model,
                        agent_model_allowed_fn=_agent_model_allowed,
                        build_agent_status_payload_fn=build_agent_status_payload,
                    )
                    return _json(self, code, payload)
                if u.path == "/agent/clean/status":
                    q = parse_qs(u.query)
                    code, payload = handle_agent_clean_status_get(
                        query=q,
                        gateway=gateway,
                        control=control,
                        codex_cli_login_status_fn=_codex_cli_login_status,
                        env_model=os.environ.get("UPRIGHT_CLEAN_MODEL", "gpt-5-codex"),
                        build_clean_status_payload_fn=build_clean_status_payload,
                    )
                    return _json(self, code, payload)
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
                    tok = _extract_auth_token(self)
                    me = auth.me(tok) if tok else None
                    code, payload = handle_agent_threads_get(
                        query=q,
                        me=me,
                        auth=auth,
                        agent_mission=agent_mission,
                        provider_router=provider_router,
                        ai=ai,
                        env_model=os.environ.get("OPENAI_MODEL", ""),
                        codex_cli_login_status_fn=_codex_cli_login_status,
                        agent_resolve_model_fn=_agent_resolve_model,
                        build_agent_status_payload_fn=build_agent_status_payload,
                    )
                    return _json(self, code, payload)
                if u.path == "/auth/openai-key/status":
                    tok = _extract_auth_token(self)
                    me = auth.me(tok)
                    if not me:
                        return _json(
                            self, 401, {"ok": False, "error": "unauthenticated"}
                        )
                    code, payload = handle_auth_openai_key_status_get(
                        me=me,
                        auth=auth,
                        env_api_key=os.environ.get("OPENAI_API_KEY", ""),
                        build_openai_config_payload_fn=build_openai_config_payload,
                    )
                    return _json(self, code, payload)
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
                    code, payload = handle_firmware_sketch_folders_get(
                        firmware=firmware
                    )
                    return _json(self, code, payload)
                if u.path == "/probe/compat":
                    q = parse_qs(u.query)
                    code, payload = handle_probe_compat_get(
                        query=q,
                        gateway=gateway,
                        cached_probe_fn=cached_probe,
                        store_probe_fn=store_probe,
                        run_compat_probe_fn=run_compat_probe,
                    )
                    return _json(self, code, payload)
                if u.path == "/probe/connect":
                    code, payload = handle_probe_connect_get(
                        gateway=gateway,
                        cached_probe_fn=cached_probe,
                        store_probe_fn=store_probe,
                        run_connect_probe_fn=run_connect_probe,
                        get_port_meta_fn=_get_port_meta,
                        detect_tuning_capabilities_fn=_detect_tuning_capabilities,
                    )
                    return _json(self, code, payload)
                if u.path == "/tooling/tuning/capabilities":
                    code, payload = handle_tuning_capabilities_get(
                        gateway=gateway,
                        cached_probe_fn=cached_probe,
                        detect_tuning_capabilities_fn=_detect_tuning_capabilities,
                    )
                    return _json(self, code, payload)
                if u.path == "/overwatch/status":
                    q = parse_qs(u.query)
                    code, payload = handle_overwatch_status_get(
                        query=q,
                        cached_probe_fn=cached_probe,
                        store_probe_fn=store_probe,
                        gateway=gateway,
                        firmware=firmware,
                        run_compat_probe_fn=run_compat_probe,
                        run_connect_probe_fn=run_connect_probe,
                        build_overwatch_report_fn=build_overwatch_report,
                    )
                    return _json(self, code, payload)
                if u.path == "/v1/setup/attempt-history":
                    q = parse_qs(u.query)
                    code, payload = handle_setup_attempt_history_get(
                        query=q,
                        setup_attempt_history=setup_attempt_history,
                        build_attempt_history_payload_fn=build_attempt_history_payload,
                    )
                    return _json(self, code, payload)
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
                    code, payload = handle_tooling_traces_get(
                        tooling_trace_candidates_fn=tooling_trace_candidates,
                    )
                    return _json(self, code, payload)
                if u.path == "/config/snapshots":
                    q = parse_qs(u.query)
                    code, payload = handle_config_snapshots_get(
                        query=q,
                        config_history=config_history,
                    )
                    return _json(self, code, payload)
                return _json(self, 404, {"ok": False, "error": "not_found"})
            except Exception as exc:
                return _json(self, 500, {"ok": False, "error": str(exc)})

        def do_POST(self) -> None:
            try:
                u = urlparse(self.path)
                body = _read_json(self)


                if u.path == "/auth/openai-key":
                    tok = _extract_auth_token(self, body)
                    me = auth.me(tok)
                    if not me:
                        return _json(
                            self, 401, {"ok": False, "error": "unauthenticated"}
                        )
                    code, payload = handle_auth_openai_key_set(
                        body=body, me=me, auth=auth
                    )
                    return _json(self, code, payload)

                if u.path == "/auth/openai-key/delete":
                    tok = _extract_auth_token(self, body)
                    me = auth.me(tok)
                    if not me:
                        return _json(
                            self, 401, {"ok": False, "error": "unauthenticated"}
                        )
                    code, payload = handle_auth_openai_key_delete(me=me, auth=auth)
                    return _json(self, code, payload)

                if u.path == "/session/heartbeat":
                    code, payload = handle_session_heartbeat(
                        control=control,
                        build_session_heartbeat_payload_fn=build_session_heartbeat_payload,
                    )
                    return _json(self, code, payload)

                if u.path == "/design-memory/report-success":
                    code, payload = handle_design_memory_report_success(
                        body=body,
                        firmware=firmware,
                        design_memory=design_memory,
                        current_runtime_identity_fn=_current_runtime_identity,
                        current_sketch_hash_fn=_current_sketch_hash,
                        design_evidence_snapshot_fn=_design_evidence_snapshot,
                    )
                    return _json(self, code, payload)

                if u.path == "/design-memory/rate":
                    code, payload = handle_design_memory_rate(
                        body=body,
                        design_memory=design_memory,
                    )
                    return _json(self, code, payload)

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
                    code, payload = handle_setup_compat_test(
                        body=body,
                        gateway=gateway,
                        setup_attempt_history=setup_attempt_history,
                        run_setup_compat_test_fn=run_setup_compat_test,
                        current_sketch_hash_fn=_current_sketch_hash,
                        report_design_observation_fn=_report_design_observation,
                        build_setup_check_payload_fn=build_setup_check_payload,
                    )
                    return _json(self, code, payload)

                if u.path == "/v1/setup/smoke-check":
                    code, payload = handle_setup_smoke_check(
                        body=body,
                        gateway=gateway,
                        control=control,
                        setup_attempt_history=setup_attempt_history,
                        run_setup_smoke_check_fn=run_setup_smoke_check,
                        current_sketch_hash_fn=_current_sketch_hash,
                        report_design_observation_fn=_report_design_observation,
                        build_setup_check_payload_fn=build_setup_check_payload,
                    )
                    return _json(self, code, payload)

                if u.path == "/v1/setup/overwatch-check":
                    code, payload = handle_setup_overwatch_check(
                        body=body,
                        gateway=gateway,
                        firmware=firmware,
                        setup_attempt_history=setup_attempt_history,
                        run_setup_overwatch_check_fn=run_setup_overwatch_check,
                        current_sketch_hash_fn=_current_sketch_hash,
                        report_design_observation_fn=_report_design_observation,
                        build_setup_check_payload_fn=build_setup_check_payload,
                    )
                    return _json(self, code, payload)

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
                    code, payload = handle_config_revert(
                        body=body,
                        revert_snapshot_fn=lambda snapshot_id: _revert_snapshot(
                            gateway, config_history, snapshot_id=snapshot_id
                        ),
                        control_snapshot=control.snapshot(),
                        build_revert_control_payload_fn=build_revert_control_payload,
                    )
                    return _json(self, code, payload)

                if u.path == "/agent/file/upload":
                    code, payload = handle_agent_file_upload(
                        body=body,
                        repo_root=repo_root,
                        agent_upload_from_body_fn=_agent_upload_from_body,
                        build_attachment_payload_fn=build_attachment_payload,
                    )
                    return _json(self, code, payload)

                if u.path == "/agent/clean/file/upload":
                    code, payload = handle_agent_file_upload(
                        body=body,
                        repo_root=repo_root,
                        agent_upload_from_body_fn=_agent_upload_from_body,
                        build_attachment_payload_fn=build_attachment_payload,
                    )
                    return _json(self, code, payload)

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
                    code, payload = handle_release_serial_post(
                        body=body,
                        repo_root=repo_root,
                        build_port_released_payload_fn=build_port_released_payload,
                    )
                    return _json(self, code, payload)

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
                    code, payload = handle_clean_chat_post(
                        body=body,
                        ai=ai,
                        codex_cli_login_status_fn=_codex_cli_login_status,
                        parse_clean_chat_request_fn=parse_clean_chat_request,
                        sanitize_agent_attachments_fn=_sanitize_agent_attachments,
                        run_clean_chat_fn=run_clean_chat,
                        run_clean_auto_tools_fn=_run_clean_auto_tools,
                        build_clean_agent_context_fn=_build_clean_agent_context,
                        clean_system_prompt_fn=_clean_system_prompt,
                        normalize_reply_for_prompt_fn=_normalize_reply_for_prompt,
                        env_clean_model=str(os.environ.get("UPRIGHT_CLEAN_MODEL", "gpt-5-codex")),
                        env_clean_timeout=str(os.environ.get("UPRIGHT_CLEAN_CODEX_EXEC_TIMEOUT_S", "120")),
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
                    code, payload = handle_clean_preflight_post(
                        body=body,
                        ai=ai,
                        firmware=firmware,
                        profiles=profiles,
                        repo_root=repo_root,
                        codex_cli_login_status_fn=_codex_cli_login_status,
                        parse_clean_preflight_request_fn=parse_clean_preflight_request,
                        clean_default_sketch_path_fn=_clean_default_sketch_path,
                        resolve_manifest_gates_fn=resolve_manifest_gates,
                        runtime_manifest_profile_compatibility_fn=_runtime_manifest_profile_compatibility,
                        run_clean_preflight_fn=run_clean_preflight,
                        run_clean_auto_tools_fn=_run_clean_auto_tools,
                        build_clean_agent_context_fn=_build_clean_agent_context,
                        clean_system_prompt_fn=_clean_system_prompt,
                        normalize_reply_for_prompt_fn=_normalize_reply_for_prompt,
                        validate_clean_preflight_response_fn=validate_clean_preflight_response,
                        env_clean_model=str(os.environ.get("UPRIGHT_CLEAN_MODEL", "gpt-5-codex")),
                        env_clean_timeout=str(os.environ.get("UPRIGHT_CLEAN_CODEX_EXEC_TIMEOUT_S", "120")),
                    )
                    return _json(self, code, payload)

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
                    code, payload = handle_agent_mode_set(
                        body=body,
                        agent_mission=agent_mission,
                        build_agent_state_payload_fn=build_agent_state_payload,
                    )
                    return _json(self, code, payload)

                if u.path == "/agent/thread/new":
                    guard = _legacy_execution_guard(u.path)
                    if guard is not None:
                        return _json(self, 403, guard)
                    tok = _extract_auth_token(self, body)
                    me = auth.me(tok) if tok else None
                    code, payload = handle_agent_thread_new(
                        body=body,
                        me=me,
                        agent_mission=agent_mission,
                        ai=ai,
                        build_agent_thread_state_payload_fn=build_agent_thread_state_payload,
                    )
                    return _json(self, code, payload)

                if u.path == "/agent/chat":
                    code, payload = handle_agent_chat_post(
                        body=body,
                        gateway=gateway,
                        control=control,
                        firmware=firmware,
                        commissioning=commissioning,
                        host_capture=host_capture,
                        config_history=config_history,
                        knowledge=knowledge,
                        ai=ai,
                        auth=auth,
                        agent_mission=agent_mission,
                        provider_router=provider_router,
                        codex_agent=codex_agent,
                        burst_status_fn=burst_status,
                        legacy_execution_guard_fn=_legacy_execution_guard,
                        extract_auth_token_fn=_extract_auth_token,
                        codex_cli_login_status_fn=_codex_cli_login_status,
                        agent_choose_executor_fn=_agent_choose_executor,
                        agent_resolve_model_fn=_agent_resolve_model,
                        agent_model_allowed_fn=_agent_model_allowed,
                        agent_mode_system_prompt_fn=_agent_mode_system_prompt,
                        sanitize_agent_attachments_fn=_sanitize_agent_attachments,
                        commissioning_ai_context_fn=_commissioning_ai_context,
                        host_capture_ai_context_fn=_host_capture_ai_context,
                        assistant_capabilities_context_fn=_assistant_capabilities_context,
                        normalize_reply_for_prompt_fn=_normalize_reply_for_prompt,
                        build_agent_chat_reply_payload_fn=build_agent_chat_reply_payload,
                        handler_self=self,
                        env_openai_model=os.environ.get("OPENAI_MODEL", ""),
                    )
                    return _json(self, code, payload)

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
                    code, payload = handle_arm_precheck(
                        body=body,
                        gateway=gateway,
                        control=control,
                        prearm_safety=prearm_safety,
                        run_prearm_hardware_check_fn=_run_prearm_hardware_check,
                        report_design_observation_fn=_report_design_observation,
                        resolve_action_gates_fn=_resolve_action_gates,
                    )
                    return _json(self, code, payload)

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
                    code, payload = handle_pid_post(
                        body=body,
                        gateway=gateway,
                        control=control,
                        config_history=config_history,
                        tuning_preflight=tuning_preflight,
                        require_action_allowed_fn=_require_action_allowed,
                        status_float_fn=_status_float,
                        guard_pid_apply_fn=_guard_pid_apply,
                        enforce_preflight_if_needed_fn=_enforce_preflight_if_needed,
                        build_tuning_result_payload_fn=build_tuning_result_payload,
                    )
                    return _json(self, code, payload)

                if u.path == "/motion":
                    code, payload = handle_motion_post(
                        body=body,
                        gateway=gateway,
                        control=control,
                        config_history=config_history,
                        tuning_preflight=tuning_preflight,
                        require_action_allowed_fn=_require_action_allowed,
                        status_float_fn=_status_float,
                        guard_motion_apply_fn=_guard_motion_apply,
                        enforce_preflight_if_needed_fn=_enforce_preflight_if_needed,
                        build_tuning_result_payload_fn=build_tuning_result_payload,
                    )
                    return _json(self, code, payload)

                if u.path == "/setpoint":
                    code, payload = handle_setpoint_post(
                        body=body,
                        gateway=gateway,
                        control=control,
                        config_history=config_history,
                        tuning_preflight=tuning_preflight,
                        require_action_allowed_fn=_require_action_allowed,
                        status_float_fn=_status_float,
                        guard_setpoint_apply_fn=_guard_setpoint_apply,
                        enforce_preflight_if_needed_fn=_enforce_preflight_if_needed,
                        build_tuning_result_payload_fn=build_tuning_result_payload,
                    )
                    return _json(self, code, payload)

                if u.path == "/limits":
                    code, payload = handle_limits_post(
                        body=body,
                        gateway=gateway,
                        control=control,
                        config_history=config_history,
                        tuning_preflight=tuning_preflight,
                        require_action_allowed_fn=_require_action_allowed,
                        status_float_fn=_status_float,
                        guard_limits_apply_fn=_guard_limits_apply,
                        enforce_preflight_if_needed_fn=_enforce_preflight_if_needed,
                        build_tuning_result_payload_fn=build_tuning_result_payload,
                    )
                    return _json(self, code, payload)

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
