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
    from app.bridge.domains.session_traceability.mission_memory import MissionMemoryStore
except ImportError:
    from domains.session_traceability.mission_memory import MissionMemoryStore  # type: ignore
try:
    from app.bridge.domains.session_traceability.design_memory import DesignMemoryStore
except ImportError:
    from domains.session_traceability.design_memory import DesignMemoryStore  # type: ignore
try:
    from app.bridge.domains.hardware_profile.hardware_context import HardwareContextStore
except ImportError:
    from domains.hardware_profile.hardware_context import HardwareContextStore  # type: ignore
try:
    from app.bridge.domains.session_traceability.setup_attempt_history import SetupAttemptHistoryStore
except ImportError:
    from domains.session_traceability.setup_attempt_history import SetupAttemptHistoryStore  # type: ignore
try:
    from app.bridge.domains.session_traceability.config_history_manager import ConfigHistoryManager
except ImportError:
    from domains.session_traceability.config_history_manager import ConfigHistoryManager  # type: ignore
try:
    from app.bridge.domains.session_traceability.ai_profile_manager import AIProfileManager
except ImportError:
    from domains.session_traceability.ai_profile_manager import AIProfileManager  # type: ignore
try:
    from app.bridge.domains.session_traceability.assistant_knowledge import AssistantKnowledgeManager
except ImportError:
    from domains.session_traceability.assistant_knowledge import AssistantKnowledgeManager  # type: ignore
try:
    from app.bridge.domains.session_traceability.agent_mission_manager import AgentMissionManager
except ImportError:
    from domains.session_traceability.agent_mission_manager import AgentMissionManager  # type: ignore
try:
    from app.bridge.domains.control_runtime.bridge_control_state import BridgeControlState
except ImportError:
    from domains.control_runtime.bridge_control_state import BridgeControlState  # type: ignore
try:
    from app.bridge.domains.control_runtime.telemetry_hub import TelemetryHub
except ImportError:
    from domains.control_runtime.telemetry_hub import TelemetryHub  # type: ignore
try:
    from app.bridge.domains.tuning_intelligence.commissioning_manager import CommissioningManager
except ImportError:
    from domains.tuning_intelligence.commissioning_manager import CommissioningManager  # type: ignore
try:
    from app.bridge.domains.hardware_profile.robot_profiles_manager import RobotProfilesManager
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
    from app.bridge.arm_safety import PreArmSafetyGate, run_prearm_hardware_check as _run_prearm_hardware_check_impl
except ImportError:
    from arm_safety import PreArmSafetyGate, run_prearm_hardware_check as _run_prearm_hardware_check_impl  # type: ignore
try:
    from app.bridge.clean_firmware_ops import handle_clean_firmware_compile, handle_clean_firmware_upload, handle_clean_known_good_recovery, handle_clean_upload_precheck, resolve_clean_upload_inputs, build_upload_target_runbook, build_upload_precheck_payload, summarize_sketch_artifact_issues, summarize_tool_failures, clean_upload_target_meta, clean_default_sketch_path, clean_default_fqbn
except ImportError:
    from clean_firmware_ops import handle_clean_firmware_compile, handle_clean_firmware_upload, handle_clean_known_good_recovery, handle_clean_upload_precheck, resolve_clean_upload_inputs, build_upload_target_runbook, build_upload_precheck_payload, summarize_sketch_artifact_issues, summarize_tool_failures, clean_upload_target_meta, clean_default_sketch_path, clean_default_fqbn  # type: ignore
try:
    from app.bridge.clean_contracts import validate_clean_preflight_response, validate_prearm_precheck_response
except ImportError:
    from clean_contracts import validate_clean_preflight_response, validate_prearm_precheck_response  # type: ignore
try:
    from app.bridge.clean_preflight import resolve_manifest_gates, run_clean_preflight
except ImportError:
    from clean_preflight import resolve_manifest_gates, run_clean_preflight  # type: ignore
try:
    from app.bridge.clean_codex_chat import run_clean_chat, run_clean_chat_stream
except ImportError:
    from clean_codex_chat import run_clean_chat, run_clean_chat_stream  # type: ignore
try:
    from app.bridge.clean_route_helpers import build_clean_agent_context, build_clean_system_prompt, clean_tool_call, run_clean_auto_tools
except ImportError:
    from clean_route_helpers import build_clean_agent_context, build_clean_system_prompt, clean_tool_call, run_clean_auto_tools  # type: ignore
try:
    from app.bridge.clean_auth_helpers import codex_cli_login_status, sanitize_agent_attachments
except ImportError:
    from clean_auth_helpers import codex_cli_login_status, sanitize_agent_attachments  # type: ignore
try:
    from app.bridge.clean_legacy_gate import legacy_execution_block_payload, legacy_execution_enabled
except ImportError:
    from clean_legacy_gate import legacy_execution_block_payload, legacy_execution_enabled  # type: ignore
try:
    from app.bridge.clean_threads import handle_clean_thread_new, handle_clean_thread_select, handle_clean_threads_get
except ImportError:
    from clean_threads import handle_clean_thread_new, handle_clean_thread_select, handle_clean_threads_get  # type: ignore
try:
    from app.bridge.clean_status import build_agent_status_payload, build_clean_status_payload
except ImportError:
    from clean_status import build_agent_status_payload, build_clean_status_payload  # type: ignore
# clean_profiles imports removed - all were unused
# clean_firmware imports removed - all were unused
try:
    from app.bridge.clean_safety import (
        build_arm_precheck_payload,
    )
except ImportError:
    pass
try:
    from app.bridge.clean_tuning import build_burst_status_payload, build_commissioning_artifacts_payload, build_commissioning_status_payload, build_lines_payload, build_tuning_result_payload
except ImportError:
    from clean_tuning import build_burst_status_payload, build_commissioning_artifacts_payload, build_commissioning_status_payload, build_lines_payload, build_tuning_result_payload  # type: ignore
try:
    from app.bridge.clean_probe import build_compat_probe_payload, build_design_memory_best_payload, build_design_memory_payload, build_probe_payload, build_tooling_traces_payload
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
        apply_tuning_plan,
        sanitize_apply_plan,
        revert_snapshot,
        format_apply_note,
        extract_apply_json,
        strip_apply_json_block,
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
        apply_tuning_plan,
        sanitize_apply_plan,
        revert_snapshot,
        format_apply_note,
        extract_apply_json,
        strip_apply_json_block,
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
    from app.bridge.hardware_registry import build_hardware_registry
except ImportError:
    from hardware_registry import build_hardware_registry  # type: ignore
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
        handle_burst_status_get,
        handle_commissioning_status_get,
        handle_commissioning_artifacts_get,
        read_csv_tail,
        commissioning_ai_context,
        host_capture_ai_context,
        json_response,
        read_json_body,
        extract_auth_token,
    )
except ImportError:
    from routes_health import (  # type: ignore
        handle_health,
        handle_status,
        handle_telemetry_adapter_map_get,
        handle_diag_serial_get,
        handle_lines_get,
        handle_burst_status_get,
        handle_commissioning_status_get,
        handle_commissioning_artifacts_get,
        read_csv_tail,
        commissioning_ai_context,
        host_capture_ai_context,
        json_response,
        read_json_body,
        extract_auth_token,
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
        apply_assistant_plan,
        agent_upload_from_body,
        assistant_capabilities_context,
        hardware_context_board_label,
        format_hardware_context_notice,
        attachment_kind,
        startup_rag_indexing,
        needs_ide_disambiguation,
        ide_disambiguation_reply,
        safe_float,
        first_float,
        safe_upload_filename,
        sanitize_agent_attachments_wrapper,
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
        apply_assistant_plan,
        agent_upload_from_body,
        assistant_capabilities_context,
        hardware_context_board_label,
        format_hardware_context_notice,
        attachment_kind,
        startup_rag_indexing,
        needs_ide_disambiguation,
        ide_disambiguation_reply,
        safe_float,
        first_float,
        safe_upload_filename,
        sanitize_agent_attachments_wrapper,
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
    from app.bridge.routes_dispatch import (
        dispatch_simple_post,
        build_simple_post_routes,
        build_control_post_routes,
    )
except ImportError:
    from routes_dispatch import (  # type: ignore
        dispatch_simple_post,
        build_simple_post_routes,
        build_control_post_routes,
    )
try:
    from app.bridge.routes_streaming import (
        build_agent_chat_stream_context,
        resolve_agent_stream_runtime,
        make_inline_sse_emitter,
        apply_sse_response_headers,
        run_agent_chat_stream_executor,
    )
except ImportError:
    from routes_streaming import (  # type: ignore
        build_agent_chat_stream_context,
        resolve_agent_stream_runtime,
        make_inline_sse_emitter,
        apply_sse_response_headers,
        run_agent_chat_stream_executor,
    )
try:
    from app.bridge.routes_probe import (
        handle_probe_compat_get,
        handle_probe_connect_get,
        handle_setup_compat_test,
        handle_setup_smoke_check,
        handle_setup_overwatch_check,
        classify_imu_command_result,
        normalize_cmd,
        blocked_while_latched,
    )
except ImportError:
    from routes_probe import (  # type: ignore
        handle_probe_compat_get,
        handle_probe_connect_get,
        handle_setup_compat_test,
        handle_setup_smoke_check,
        handle_setup_overwatch_check,
        classify_imu_command_result,
        normalize_cmd,
        blocked_while_latched,
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
        validate_protocol_pins,
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
        validate_protocol_pins,
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
# _safe_float, _first_float, _safe_upload_filename moved to routes_ai.py
# _extract_apply_json, _strip_apply_json_block moved to routes_tuning.py
# _sanitize_apply_plan moved to routes_tuning.py as sanitize_apply_plan
# _format_apply_note moved to routes_tuning.py as format_apply_note
# _attachment_kind moved to routes_ai.py as attachment_kind
# _agent_upload_from_body moved to routes_ai.py as agent_upload_from_body
# _sanitize_agent_attachments moved to routes_ai.py as sanitize_agent_attachments_wrapper

# ConfigHistoryManager moved to domain module
# _apply_tuning_plan moved to routes_tuning.py as apply_tuning_plan
# _apply_assistant_plan moved to routes_ai.py as apply_assistant_plan
# _revert_snapshot moved to routes_tuning.py as revert_snapshot


# _read_csv_tail moved to routes_health.py as read_csv_tail
# HostCaptureManager moved to domains/tuning_intelligence/host_capture_manager.py


# _commissioning_ai_context, _host_capture_ai_context moved to routes_health.py
# assistant_capabilities_context moved to routes_ai.py

# AIProfileManager moved to domain module
# AssistantKnowledgeManager moved to domain module
# AgentMissionManager moved to domain module

# _clean_default_sketch_path, _clean_default_fqbn moved to clean_firmware_ops.py
# _clean_upload_target_meta moved to clean_firmware_ops.py as clean_upload_target_meta
# _clean_upload_target_runbook moved to clean_firmware_ops.py as build_upload_target_runbook
# _clean_upload_precheck_payload moved to clean_firmware_ops.py as build_upload_precheck_payload


# _summarize_tool_failures moved to clean_firmware_ops.py as summarize_tool_failures
# _summarize_sketch_artifact_issues moved to clean_firmware_ops.py as summarize_sketch_artifact_issues


# _needs_ide_disambiguation, _ide_disambiguation_reply moved to routes_ai.py
# _hardware_context_board_label, _format_hardware_context_notice moved to routes_ai.py
# _pin_range_for_family already imported from manifest_validation.py
# _family_capabilities, _protocol_schema, _has_valid_pin, _validate_protocol_pins
# all moved to manifest_validation.py (already imported)

# _validate_runtime_manifest_v1, _manifest_required_field_present,
# _family_for_fqbn, _board_id_for_fqbn moved to manifest_validation.py

# _runtime_manifest_profile_compatibility moved to manifest_validation.py

# _build_hardware_registry moved to hardware_registry.py


# RobotProfilesManager moved to domain module
# TelemetryHub moved to domain module
# _json, _read_json, _extract_auth_token moved to routes_health.py
# AuthManager moved to domain module
# _normalize_cmd, _blocked_while_latched moved to routes_probe.py
# _classify_imu_command_result moved to routes_probe.py as classify_imu_command_result


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
    setup_attempt_history = setup_attempt_history_store or SetupAttemptHistoryStore(repo_root)
    design_memory, prearm_safety = DesignMemoryStore(repo_root), prearm_safety_gate or PreArmSafetyGate(required=True)
    tuning_preflight = TuningPreflightStore(ttl_s=900.0, max_entries=256)
    probe_cache_lock = threading.Lock()
    probe_cache: Dict[str, Dict[str, Any]] = {"compat": {"ts": 0.0, "report": None}, "connect": {"ts": 0.0, "report": None}, "overwatch": {"ts": 0.0, "report": None}}

    def cached_probe(kind: str) -> Optional[Dict[str, Any]]:
        with probe_cache_lock:
            node, ts, report = probe_cache.get(kind, {}), float(probe_cache.get(kind, {}).get("ts", 0.0) or 0.0), probe_cache.get(kind, {}).get("report")
        return report if report is not None and (time.monotonic() - ts) <= (4.0 if kind == "compat" else 2.0) else None

    def store_probe(kind: str, report: Dict[str, Any]) -> None:
        with probe_cache_lock:
            probe_cache[kind] = {"ts": time.monotonic(), "report": report}

    def _current_sketch_hash() -> str:
        sketch_path = pathlib.Path(str((firmware.status().get("defaults", {}) or {}).get("sketch", "")))
        if sketch_path.exists() and sketch_path.is_dir():
            preferred = sketch_path / f"{sketch_path.name}.ino"
            sketch_path = preferred if preferred.exists() and preferred.is_file() else (sorted(sketch_path.glob("*.ino")) or [sketch_path])[0]
        if not sketch_path.exists() or not sketch_path.is_file():
            return ""
        try:
            return hashlib.sha256(sketch_path.read_bytes()).hexdigest()[:16]
        except Exception:
            return ""

    def _current_runtime_identity() -> Dict[str, str]:
        st = dict(gateway.health().get("last_status", {}))
        return {"runtime_version": str(st.get("runtime", st.get("runtime_version", "")) or "").strip(), "tune_version": str(st.get("tune", st.get("tune_version", "")) or "").strip(), "ident": str(st.get("ident", "") or "").strip(), "hash": str(st.get("hash", "") or "").strip(), "mode": str(st.get("mode", "") or "").strip(), "estop": str(st.get("estop", "") or "").strip(), "fault": str(st.get("fault", "") or "").strip()}

    def _design_evidence_snapshot() -> Dict[str, Any]:
        fw_status = firmware.status()
        fw_state = str((fw_status.get("state", "") if isinstance(fw_status, dict) else "") or "").strip().lower()
        fw_phase = str((fw_status.get("phase", "") if isinstance(fw_status, dict) else "") or "").strip().lower()
        fw_rc = fw_status.get("returncode", None) if isinstance(fw_status, dict) else None
        fw_tail = list(fw_status.get("log_tail", [])[-20:]) if isinstance(fw_status, dict) else []
        health = gateway.health()
        status = dict(health.get("last_status", {}))
        prearm = prearm_safety.snapshot()
        recent_attempts = setup_attempt_history.list_recent(limit=8)
        preflight_ok = any(isinstance(row, dict) and str(row.get("test_type", "")).strip().lower() == "preflight" and str(row.get("status", "")).strip().lower() == "pass" for row in recent_attempts)
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
        checks = {"upload_ok": bool(fw_rc == 0 or "upload_guarded_pass" in fw_state or "upload" in fw_phase), "reconnect_ok": any("bridge reconnected" in str(line).lower() for line in fw_tail) or bool(health.get("connected", False)), "preflight_ok": bool(preflight_ok), "prearm_ok": bool(prearm.get("passed", False)), "telemetry_feed_ok": bool(status), "no_fault": fault in {"", "0"}, "safe_mode_ok": mode in {"SAFE_IDLE", "IDLE", "BALANCING", "BALANCE"}}
        return {"checks": checks, "sources": {"firmware": {"state": fw_state, "phase": fw_phase, "returncode": fw_rc}, "bridge_connected": bool(health.get("connected", False)), "status_snapshot": dict(status), "status_mode": mode, "status_fault": fault, "prearm_passed": bool(prearm.get("passed", False)), "recent_preflight_ok": bool(preflight_ok), "overwatch_score_pct": latest_overwatch_score_pct}}

    def _report_design_observation(*, session_key: str, success: bool, source: str, note: str, profile_id: str = "", profile_label: str = "", sketch_revision: str = "", sketch_hash: str = "", test_type: str = "") -> Dict[str, Any]:
        fw_status, runtime = firmware.status(), _current_runtime_identity()
        fw_defaults = (fw_status.get("defaults", {}) or {}) if isinstance(fw_status, dict) else {}
        observation = {"runtime_version": runtime.get("runtime_version", ""), "tune_version": runtime.get("tune_version", ""), "ident": runtime.get("ident", ""), "hash": runtime.get("hash", ""), "profile_id": str(profile_id or "").strip(), "profile_label": str(profile_label or "").strip(), "sketch_revision": str(sketch_revision or "").strip(), "sketch_hash": str(sketch_hash or "").strip() or _current_sketch_hash(), "test_type": str(test_type or "").strip(), "fqbn": str(fw_defaults.get("fqbn", "") or "").strip(), "port": str(fw_defaults.get("port", "") or "").strip(), "evidence": _design_evidence_snapshot()}
        return design_memory.report(session_key=session_key, observation=observation, success=bool(success), source=source, note=note)

    def _active_robot_profile() -> Optional[Dict[str, Any]]:
        state, active_id = profiles.list(), str(profiles.list().get("active_profile_id") or "").strip()
        if not active_id:
            return None
        return next((p for p in list(state.get("profiles") or []) if isinstance(p, dict) and str(p.get("profile_id", "")).strip() == active_id), None)

    def _burst_threshold_defaults(active_profile: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        out = {"freq_hz": 25.0, "trigger_enabled": True, "prebuffer_lines": 40, "trigger_angle_deg": 4.5, "trigger_out_frac": 0.55, "trigger_runaway": 0.18, "post_trigger_lines": 100, "profile_family": "arduino_avr"}
        if not isinstance(active_profile, dict):
            return out
        board = active_profile.get("board")
        if not isinstance(board, dict):
            return out
        profile_fqbn = str(board.get("fqbn", "")).strip()
        fam = _family_for_fqbn(profile_fqbn, firmware.list_targets()) or "arduino_avr"
        out["profile_family"] = fam
        if fam in {"esp32", "rp2040", "teensy"}:
            out.update({"freq_hz": 40.0, "prebuffer_lines": 36, "trigger_angle_deg": 5.0, "trigger_out_frac": 0.85, "trigger_runaway": 0.45, "post_trigger_lines": 36})
        firmware_node = active_profile.get("firmware")
        if isinstance(firmware_node, dict):
            tm = str(firmware_node.get("telemetry_mode", "")).strip().lower()
            if tm == "binary_highrate" and fam == "arduino_avr":
                out["profile_family"] = "arduino_avr/compat"
            if tm == "binary_highrate" and fam in {"esp32", "rp2040", "teensy"}:
                out.update({"freq_hz": 50.0, "prebuffer_lines": 40, "post_trigger_lines": 40})
        return out

    def burst_status() -> Dict[str, Any]:
        lines, host = gateway.recent_lines(800), host_capture.status()
        burst_events = [ln for ln in lines if ln.startswith("BURSTCSV")]
        csv_recent = sum(1 for ln in lines if ln.startswith("CSV,"))
        state = "idle"
        if burst_events:
            last = burst_events[-1]
            state = "done" if "DONE" in last else "canceled" if "CANCELED" in last else "stable" if "STABLE" in last else "armed" if "ARMED" in last else "idle"
        else:
            hs = str(host.get("state", "idle"))
            if hs in {"armed", "capturing", "done", "failed"}:
                state = hs
        return {"state": state, "last_event": burst_events[-1] if burst_events else None, "events_recent": burst_events[-12:], "csv_recent": csv_recent, "host_capture": host}

    def tooling_trace_candidates() -> list[str]:
        paths: list[pathlib.Path] = []
        for pat in ("app/bridge/tests/fixtures/trace_replay_*.csv", "tests/results/run_*.csv", "tests/results/host_run_*.csv", "tests/results/*.csv"):
            paths.extend(repo_root.glob(pat))
        return sorted({str(p.relative_to(repo_root)) for p in paths if p.exists()})[-80:]

    def history_with_reply(history: list[Dict[str, Any]], reply: str) -> list[Dict[str, Any]]:
        out = list(history)
        for i in range(len(out) - 1, -1, -1):
            if str(out[i].get("role", "")) == "assistant":
                out[i] = {**out[i], "text": reply}
                break
        return out

    def sync_hardware_context(session_key: str, body: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
        update_info: Dict[str, Any] = {"accepted": False, "changed": False, "initial": False}
        if "hardware_context" in body:
            update_info = hw_context_store.upsert(session_key, body.get("hardware_context"))
        stored_ctx = hw_context_store.get(session_key)
        if isinstance(stored_ctx, dict):
            ctx["hardware_context"] = stored_ctx
        return {"update": update_info, "notice": _format_hardware_context_notice(stored_ctx, update_info)}

    def _clean_tool_call(*, name: str, arguments: Dict[str, Any], ok: bool, data: Optional[Dict[str, Any]] = None, error: str = "", started_ms: int = 0) -> Dict[str, Any]:
        return clean_tool_call(name=name, arguments=arguments, ok=ok, data=data, error=error, started_ms=started_ms)

    def _run_clean_auto_tools(*, message: str, model: str) -> list[Dict[str, Any]]:
        _ = model
        return run_clean_auto_tools(message=message, gateway=gateway, firmware=firmware, repo_root=repo_root, default_sketch_path_fn=_clean_default_sketch_path, default_fqbn_fn=_clean_default_fqbn, run_connect_probe_fn=run_connect_probe, run_compat_probe_fn=run_compat_probe)

    def _build_clean_agent_context(*, mode: str, session_key: str, thread_id: Optional[str], attachments: Optional[list[Dict[str, Any]]] = None, clean_tool_calls: Optional[list[Dict[str, Any]]] = None) -> Dict[str, Any]:
        return build_clean_agent_context(mode=mode, session_key=session_key, thread_id=thread_id, attachments=attachments, clean_tool_calls=clean_tool_calls, gateway=gateway, firmware=firmware, setup_attempt_history=setup_attempt_history, ai=ai, extract_mission_facts_fn=_extract_mission_facts, mission_memory=mission_memory, knowledge=knowledge, config_history=config_history, control=control, assistant_capabilities_context_fn=assistant_capabilities_context, best_known_design=design_memory.best(session_key=session_key))

    def _clean_system_prompt(mode: str) -> str:
        return build_clean_system_prompt(mode=mode, agent_mode_system_prompt_fn=_agent_mode_system_prompt)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: Any) -> None:
            return

        def do_OPTIONS(self) -> None:
            _json(self, 200, {"ok": True})

        def do_GET(self) -> None:
            try:
                u = urlparse(self.path)
                # Core GET routes dispatch
                _core_get = {
                    "/health": lambda: handle_health(gateway=gateway, control=control, prearm_safety=prearm_safety, telemetry_port=telemetry_port, telemetry_enabled=websockets is not None),
                    "/status": lambda: handle_status(gateway=gateway, control=control, prearm_safety=prearm_safety, normalize_status_fn=_normalize_status_for_hud, resolve_action_gates_fn=_resolve_action_gates),
                    "/telemetry/adapter-map": lambda: handle_telemetry_adapter_map_get(gateway=gateway, normalize_status_fn=_normalize_status_for_hud, build_telemetry_adapters_payload_fn=build_telemetry_adapters_payload, runtime_telemetry_adapters=RUNTIME_TELEMETRY_ADAPTERS, hud_canonical_fields=list(HUD_CANONICAL_FIELDS)),
                    "/diag/serial": lambda: handle_diag_serial_get(gateway=gateway, control=control, build_diag_serial_payload_fn=build_diag_serial_payload),
                    "/burst/status": lambda: handle_burst_status_get(burst_status_fn=burst_status, build_burst_status_payload_fn=build_burst_status_payload),
                    "/commissioning/status": lambda: handle_commissioning_status_get(commissioning=commissioning, build_commissioning_status_payload_fn=build_commissioning_status_payload),
                    "/commissioning/artifacts": lambda: handle_commissioning_artifacts_get(commissioning=commissioning, build_commissioning_artifacts_payload_fn=build_commissioning_artifacts_payload),
                }
                if u.path in _core_get:
                    return _json(self, *_core_get[u.path]())
                if u.path == "/lines":
                    q = parse_qs(u.query)
                    return _json(self, *handle_lines_get(gateway=gateway, n=int(q.get("n", ["100"])[0]), build_lines_payload_fn=build_lines_payload))
                # Firmware GET routes dispatch
                if u.path == "/firmware/status":
                    return _json(self, *handle_firmware_status_get(firmware=firmware))
                if u.path == "/firmware/artifacts":
                    return _json(self, *handle_firmware_artifacts_get(firmware=firmware, query=parse_qs(u.query)))
                # Design-memory and firmware schema routes
                if u.path in {"/design-memory", "/design-memory/best"}:
                    q = parse_qs(u.query)
                    if u.path == "/design-memory":
                        return _json(self, *handle_design_memory_list_get(query=q, design_memory=design_memory))
                    return _json(self, *handle_design_memory_best_get(query=q, design_memory=design_memory))
                if u.path == "/firmware/unified-schema":
                    return _json(self, *handle_firmware_unified_schema_get(firmware=firmware))
                if u.path == "/agent/status":
                    tok = _extract_auth_token(self)
                    return _json(self, *handle_agent_status_get(me=auth.me(tok) if tok else None, auth=auth, agent_mission=agent_mission, provider_router=provider_router, ai=ai, gateway=gateway, control=control, knowledge=knowledge, codex_agent_available=bool(codex_agent is not None), env_model=os.environ.get("OPENAI_MODEL", ""), codex_cli_login_status_fn=_codex_cli_login_status, agent_choose_executor_fn=_agent_choose_executor, agent_resolve_model_fn=_agent_resolve_model, agent_model_allowed_fn=_agent_model_allowed, build_agent_status_payload_fn=build_agent_status_payload))
                # Agent clean routes
                if u.path == "/agent/clean/status":
                    return _json(self, *handle_agent_clean_status_get(query=parse_qs(u.query), gateway=gateway, control=control, codex_cli_login_status_fn=_codex_cli_login_status, env_model=os.environ.get("UPRIGHT_CLEAN_MODEL", "gpt-5-codex"), build_clean_status_payload_fn=build_clean_status_payload))
                if u.path == "/agent/clean/threads":
                    q, mode = parse_qs(u.query), str((parse_qs(u.query).get("mode", ["app_dev"]) or ["app_dev"])[0]).strip() or "app_dev"
                    return _json(self, 200, handle_clean_threads_get(mode=mode, ai=ai, codex_logged_in=bool(_codex_cli_login_status().get("logged_in", False)), model=str(os.environ.get("UPRIGHT_CLEAN_MODEL", "gpt-5-codex"))))
                if u.path == "/agent/threads":
                    if (guard := _legacy_execution_guard(u.path)) is not None:
                        return _json(self, 403, guard)
                    tok, q = _extract_auth_token(self), parse_qs(u.query)
                    return _json(self, *handle_agent_threads_get(query=q, me=auth.me(tok) if tok else None, auth=auth, agent_mission=agent_mission, provider_router=provider_router, ai=ai, env_model=os.environ.get("OPENAI_MODEL", ""), codex_cli_login_status_fn=_codex_cli_login_status, agent_resolve_model_fn=_agent_resolve_model, build_agent_status_payload_fn=build_agent_status_payload))
                if u.path == "/auth/openai-key/status":
                    tok, me = _extract_auth_token(self), auth.me(_extract_auth_token(self))
                    if not me:
                        return _json(self, 401, {"ok": False, "error": "unauthenticated"})
                    return _json(self, *handle_auth_openai_key_status_get(me=me, auth=auth, env_api_key=os.environ.get("OPENAI_API_KEY", ""), build_openai_config_payload_fn=build_openai_config_payload))
                # More firmware GET routes
                if u.path == "/firmware/sketch":
                    return _json(self, *handle_firmware_sketch_get(firmware=firmware, query=parse_qs(u.query)))
                if u.path == "/firmware/boards":
                    return _json(self, *handle_firmware_boards_get(firmware=firmware))
                if u.path == "/firmware/targets":
                    return _json(self, *handle_firmware_targets_get(firmware=firmware))
                # Firmware manifest/folders routes
                if u.path == "/firmware/runtime-manifest/validate":
                    return _json(self, *handle_firmware_runtime_manifest_validate_get(firmware=firmware, query=parse_qs(u.query)))
                if u.path == "/firmware/runtime-manifest/compat":
                    return _json(self, *handle_firmware_runtime_manifest_compat_get(firmware=firmware, profiles=profiles, query=parse_qs(u.query), compatibility_fn=_runtime_manifest_profile_compatibility))
                if u.path == "/firmware/sketch-folders":
                    return _json(self, *handle_firmware_sketch_folders_get(firmware=firmware))
                # Probe and diagnostics routes
                _probe_deps = dict(gateway=gateway, cached_probe_fn=cached_probe, store_probe_fn=store_probe)
                if u.path == "/probe/compat":
                    return _json(self, *handle_probe_compat_get(query=parse_qs(u.query), run_compat_probe_fn=run_compat_probe, **_probe_deps))
                if u.path == "/probe/connect":
                    return _json(self, *handle_probe_connect_get(run_connect_probe_fn=run_connect_probe, get_port_meta_fn=_get_port_meta, detect_tuning_capabilities_fn=_detect_tuning_capabilities, **_probe_deps))
                if u.path == "/tooling/tuning/capabilities":
                    return _json(self, *handle_tuning_capabilities_get(gateway=gateway, cached_probe_fn=cached_probe, detect_tuning_capabilities_fn=_detect_tuning_capabilities))
                if u.path == "/overwatch/status":
                    return _json(self, *handle_overwatch_status_get(query=parse_qs(u.query), firmware=firmware, run_compat_probe_fn=run_compat_probe, run_connect_probe_fn=run_connect_probe, build_overwatch_report_fn=build_overwatch_report, **_probe_deps))
                # Simple list routes
                _list_routes = {
                    "/v1/setup/attempt-history": lambda q: handle_setup_attempt_history_get(query=q, setup_attempt_history=setup_attempt_history, build_attempt_history_payload_fn=build_attempt_history_payload),
                    "/profiles": lambda q: handle_profiles_list(profiles=profiles),
                    "/profiles/hardware": lambda q: handle_profiles_hardware(firmware=firmware, build_hardware_registry_fn=build_hardware_registry),
                    "/tooling/traces": lambda q: handle_tooling_traces_get(tooling_trace_candidates_fn=tooling_trace_candidates),
                    "/config/snapshots": lambda q: handle_config_snapshots_get(query=q, config_history=config_history),
                }
                if u.path in _list_routes:
                    return _json(self, *_list_routes[u.path](parse_qs(u.query)))
                return _json(self, 404, {"ok": False, "error": "not_found"})
            except Exception as exc:
                return _json(self, 500, {"ok": False, "error": str(exc)})

        def do_POST(self) -> None:
            try:
                u = urlparse(self.path)
                body = _read_json(self)


                # Auth routes requiring authentication
                if u.path in {"/auth/openai-key", "/auth/openai-key/delete"}:
                    tok = _extract_auth_token(self, body)
                    me = auth.me(tok)
                    if not me:
                        return _json(self, 401, {"ok": False, "error": "unauthenticated"})
                    if u.path == "/auth/openai-key":
                        return _json(self, *handle_auth_openai_key_set(body=body, me=me, auth=auth))
                    return _json(self, *handle_auth_openai_key_delete(me=me, auth=auth))

                # Simple POST routes dispatch
                _simple_routes = {
                    "/session/heartbeat": lambda: handle_session_heartbeat(control=control, build_session_heartbeat_payload_fn=build_session_heartbeat_payload),
                    "/design-memory/report-success": lambda: handle_design_memory_report_success(body=body, firmware=firmware, design_memory=design_memory, current_runtime_identity_fn=_current_runtime_identity, current_sketch_hash_fn=_current_sketch_hash, design_evidence_snapshot_fn=_design_evidence_snapshot),
                    "/design-memory/rate": lambda: handle_design_memory_rate(body=body, design_memory=design_memory),
                    "/commissioning/run": lambda: handle_commissioning_run(body=body, gateway=gateway, commissioning=commissioning),
                    "/commissioning/step": lambda: handle_commissioning_step(),
                }
                if u.path in _simple_routes:
                    code, payload = _simple_routes[u.path]()
                    return _json(self, code, payload)

                # Firmware routes dispatch
                _fw_routes = {
                    "/firmware/check": lambda: handle_firmware_check_post(firmware=firmware),
                    "/firmware/compile": lambda: handle_firmware_compile(body=body, firmware=firmware),
                    "/firmware/upload": lambda: handle_firmware_upload(body=body, firmware=firmware, prearm_safety=prearm_safety),
                    "/firmware/upload-guarded": lambda: handle_firmware_upload_guarded(body=body, firmware=firmware, gateway=gateway, prearm_safety=prearm_safety),
                    "/firmware/install-cli": lambda: handle_firmware_install_cli(firmware=firmware),
                    "/firmware/sketch": lambda: handle_firmware_sketch_write(body=body, firmware=firmware),
                    "/firmware/sketch-folder/pick": lambda: handle_firmware_sketch_folder_pick(firmware=firmware),
                    "/firmware/generate-unified": lambda: handle_firmware_generate_unified(body=body, firmware=firmware),
                    "/firmware/generate-docs-pack": lambda: handle_firmware_generate_docs_pack(body=body, firmware=firmware),
                    "/profiles/validate": lambda: handle_profiles_validate(body=body, profiles=profiles, gateway=gateway),
                }
                if u.path in _fw_routes:
                    code, payload = _fw_routes[u.path]()
                    return _json(self, code, payload)

                if u.path == "/firmware/runtime-manifest/validate":
                    sketch, inline_manifest = str(body.get("sketch", "")).strip() or None, body.get("manifest")
                    manifest_obj = inline_manifest if isinstance(inline_manifest, dict) else None
                    check = firmware.validate_runtime_manifest(sketch=sketch, manifest=manifest_obj, require_exists=manifest_obj is None)
                    return _json(self, 200, {"ok": bool(check.get("ok", False)), "validation": check})

                # Setup check routes dispatch
                _setup_deps = dict(body=body, gateway=gateway, setup_attempt_history=setup_attempt_history, current_sketch_hash_fn=_current_sketch_hash, report_design_observation_fn=_report_design_observation, build_setup_check_payload_fn=build_setup_check_payload)
                _setup_routes = {
                    "/v1/setup/compat-test": lambda: handle_setup_compat_test(**_setup_deps, run_setup_compat_test_fn=run_setup_compat_test),
                    "/v1/setup/smoke-check": lambda: handle_setup_smoke_check(**_setup_deps, control=control, run_setup_smoke_check_fn=run_setup_smoke_check),
                    "/v1/setup/overwatch-check": lambda: handle_setup_overwatch_check(**_setup_deps, firmware=firmware, run_setup_overwatch_check_fn=run_setup_overwatch_check),
                }
                if u.path in _setup_routes:
                    code, payload = _setup_routes[u.path]()
                    return _json(self, code, payload)

                # Profile routes dispatch
                _profile_routes = {
                    "/profiles/save": lambda: handle_profiles_save(body=body, profiles=profiles),
                    "/profiles/activate": lambda: handle_profiles_activate(body=body, profiles=profiles),
                    "/profiles/delete": lambda: handle_profiles_delete(body=body, profiles=profiles),
                }
                if u.path in _profile_routes:
                    code, payload = _profile_routes[u.path]()
                    return _json(self, code, payload)

                if u.path == "/config/revert":
                    return _json(self, *handle_config_revert(body=body, revert_snapshot_fn=lambda snapshot_id: revert_snapshot(gateway, config_history, snapshot_id=snapshot_id), control_snapshot=control.snapshot(), build_revert_control_payload_fn=build_revert_control_payload))

                # File upload routes (identical handlers)
                if u.path in {"/agent/file/upload", "/agent/clean/file/upload"}:
                    _upload_fn = lambda repo, body: agent_upload_from_body(repo, body, safe_filename_fn=_safe_upload_filename, attachment_kind_fn=_attachment_kind)
                    return _json(self, *handle_agent_file_upload(body=body, repo_root=repo_root, agent_upload_from_body_fn=_upload_fn, build_attachment_payload_fn=build_attachment_payload))

                # Clean firmware compile/upload routes
                if u.path in {"/agent/clean/firmware/compile", "/agent/clean/firmware/upload"}:
                    inputs = resolve_clean_upload_inputs(body=body, default_sketch=_clean_default_sketch_path(repo_root, firmware), default_fqbn=_clean_default_fqbn())
                    _sketch, _fqbn, _idem = str(inputs.get("sketch") or ""), str(inputs.get("fqbn") or ""), inputs.get("idempotency_key")
                    if u.path == "/agent/clean/firmware/compile":
                        return _json(self, *handle_clean_firmware_compile(firmware=firmware, sketch=_sketch, fqbn=_fqbn, idempotency_key=_idem, tool_call_builder=_clean_tool_call))
                    return _json(self, *handle_clean_firmware_upload(firmware=firmware, gateway=gateway, prearm_safety=prearm_safety, sketch=_sketch, fqbn=_fqbn, port=inputs.get("port"), idempotency_key=_idem, tool_call_builder=_clean_tool_call))

                if u.path == "/agent/clean/firmware/upload/precheck":
                    _port, _fqbn = str(body.get("port", "")).strip(), str(body.get("fqbn", "")).strip() or _clean_default_fqbn()
                    _sketch = str(body.get("sketch", "")).strip() or _clean_default_sketch_path(repo_root, firmware)
                    _precheck = lambda **kwargs: build_upload_precheck_payload(gateway=gateway, firmware=firmware, target_meta_fn=lambda fqbn, fw: clean_upload_target_meta(fqbn=fqbn, firmware=fw, board_id_fn=_board_id_for_fqbn, family_fn=_family_for_fqbn), **kwargs)
                    return _json(self, *handle_clean_upload_precheck(precheck_builder=_precheck, requested_port=_port, requested_fqbn=_fqbn, requested_sketch=_sketch))

                if u.path == "/agent/clean/firmware/release-serial":
                    return _json(self, *handle_release_serial_post(body=body, repo_root=repo_root, build_port_released_payload_fn=build_port_released_payload))

                if u.path == "/agent/clean/recovery/known-good":
                    _port, _fqbn = str(body.get("port", "")).strip(), str(body.get("fqbn", "")).strip() or _clean_default_fqbn()
                    _sketch = str(body.get("sketch", "")).strip() or _clean_default_sketch_path(repo_root, firmware)
                    _precheck = lambda **kwargs: build_upload_precheck_payload(gateway=gateway, firmware=firmware, target_meta_fn=lambda fqbn, fw: clean_upload_target_meta(fqbn=fqbn, firmware=fw, board_id_fn=_board_id_for_fqbn, family_fn=_family_for_fqbn), **kwargs)
                    return _json(self, *handle_clean_known_good_recovery(gateway=gateway, firmware=firmware, control=control, prearm_safety=prearm_safety, requested_port=_port, requested_fqbn=_fqbn, requested_sketch=_sketch, precheck_builder=_precheck, normalize_status=_normalize_status_for_hud, resolve_action_gates=_resolve_action_gates, tool_call_builder=_clean_tool_call))

                # Clean thread routes
                if u.path in {"/agent/clean/thread/new", "/agent/clean/thread/select"}:
                    mode = str(body.get("mode", "")).strip() or "app_dev"
                    if u.path == "/agent/clean/thread/new":
                        return _json(self, 200, handle_clean_thread_new(mode=mode, title=str(body.get("title", "")).strip() or None, ai=ai))
                    return _json(self, *handle_clean_thread_select(mode=mode, thread_id=str(body.get("thread_id", "")).strip(), ai=ai))

                if u.path == "/agent/clean/chat":
                    return _json(self, *handle_clean_chat_post(body=body, ai=ai, codex_cli_login_status_fn=_codex_cli_login_status, parse_clean_chat_request_fn=parse_clean_chat_request, sanitize_agent_attachments_fn=_sanitize_agent_attachments, run_clean_chat_fn=run_clean_chat, run_clean_auto_tools_fn=_run_clean_auto_tools, build_clean_agent_context_fn=_build_clean_agent_context, clean_system_prompt_fn=_clean_system_prompt, normalize_reply_for_prompt_fn=_normalize_reply_for_prompt, env_clean_model=str(os.environ.get("UPRIGHT_CLEAN_MODEL", "gpt-5-codex")), env_clean_timeout=str(os.environ.get("UPRIGHT_CLEAN_CODEX_EXEC_TIMEOUT_S", "120"))))

                if u.path == "/agent/clean/chat/stream":
                    err, req = parse_clean_chat_request(body=body, codex_login=_codex_cli_login_status(), env_model=str(os.environ.get("UPRIGHT_CLEAN_MODEL", "gpt-5-codex")), env_timeout=str(os.environ.get("UPRIGHT_CLEAN_CODEX_EXEC_TIMEOUT_S", "120")), sanitize_attachments_fn=_sanitize_agent_attachments)
                    if err is not None:
                        return _json(self, err[0], err[1])
                    assert req is not None
                    apply_sse_headers(send_response=self.send_response, send_header=self.send_header, end_headers=self.end_headers)
                    disconnected, cancelled = threading.Event(), threading.Event()
                    send_evt = make_sse_emitter(wfile=self.wfile, is_disconnected=lambda: disconnected.is_set(), on_write_error=lambda: (disconnected.set(), cancelled.set()))
                    send_evt("start", {"ok": True})
                    run_clean_chat_stream(msg=str(req["msg"]), mode=str(req["mode"]), model=str(req["model"]), clean_timeout_s=int(req["clean_timeout_s"]), session_key=str(req["session_key"]), thread_id=req.get("thread_id"), attachments=list(req.get("attachments") or []), auto_tools=bool(req.get("auto_tools", False)), ai=ai, run_auto_tools=_run_clean_auto_tools, build_context=_build_clean_agent_context, system_prompt_for_mode=_clean_system_prompt, normalize_reply_for_prompt=_normalize_reply_for_prompt, emit=send_evt, is_disconnected=lambda: disconnected.is_set(), cancel_event=cancelled)
                    return

                if u.path == "/agent/clean/preflight":
                    return _json(self, *handle_clean_preflight_post(body=body, ai=ai, firmware=firmware, profiles=profiles, repo_root=repo_root, codex_cli_login_status_fn=_codex_cli_login_status, parse_clean_preflight_request_fn=parse_clean_preflight_request, clean_default_sketch_path_fn=_clean_default_sketch_path, resolve_manifest_gates_fn=resolve_manifest_gates, runtime_manifest_profile_compatibility_fn=_runtime_manifest_profile_compatibility, run_clean_preflight_fn=run_clean_preflight, run_clean_auto_tools_fn=_run_clean_auto_tools, build_clean_agent_context_fn=_build_clean_agent_context, clean_system_prompt_fn=_clean_system_prompt, normalize_reply_for_prompt_fn=_normalize_reply_for_prompt, validate_clean_preflight_response_fn=validate_clean_preflight_response, env_clean_model=str(os.environ.get("UPRIGHT_CLEAN_MODEL", "gpt-5-codex")), env_clean_timeout=str(os.environ.get("UPRIGHT_CLEAN_CODEX_EXEC_TIMEOUT_S", "120"))))

                if u.path == "/agent/clean/preflight/stream":
                    codex_login = _codex_cli_login_status()
                    err, req = parse_clean_preflight_request(body=body, codex_login=codex_login, env_model=str(os.environ.get("UPRIGHT_CLEAN_MODEL", "gpt-5-codex")), env_timeout=str(os.environ.get("UPRIGHT_CLEAN_CODEX_EXEC_TIMEOUT_S", "120")), default_sketch=_clean_default_sketch_path(repo_root, firmware))
                    if err is not None:
                        return _json(self, err[0], err[1])
                    assert req is not None
                    manifest_gate, compat_gate, active_profile_id = resolve_manifest_gates(firmware=firmware, profiles=profiles, compatibility_fn=_runtime_manifest_profile_compatibility, sketch=str(req["sketch"]))
                    apply_sse_headers(send_response=self.send_response, send_header=self.send_header, end_headers=self.end_headers)
                    send_evt = make_sse_emitter(wfile=self.wfile)

                    send_evt("start", {"ok": True, "mode": str(req["mode"])})
                    run_clean_preflight(mode=str(req["mode"]), max_ms=int(req["max_ms"]), max_ms_tools=int(req["max_ms_tools"]), gate_only=bool(req["gate_only"]), with_compile=bool(req["with_compile"]), model=str(req["model"]), clean_timeout_s=int(req["clean_timeout_s"]), manifest_gate=manifest_gate, compat_gate=compat_gate, active_profile_id=active_profile_id, ai=ai, run_auto_tools=_run_clean_auto_tools, build_context=_build_clean_agent_context, system_prompt_for_mode=_clean_system_prompt, normalize_reply_for_prompt=_normalize_reply_for_prompt, validate_preflight_payload=validate_clean_preflight_response, emit=send_evt)
                    return

                # Agent mode/thread routes
                if u.path == "/agent/mode":
                    return _json(self, *handle_agent_mode_set(body=body, agent_mission=agent_mission, build_agent_state_payload_fn=build_agent_state_payload))
                if u.path == "/agent/thread/new":
                    guard = _legacy_execution_guard(u.path)
                    if guard is not None:
                        return _json(self, 403, guard)
                    tok = _extract_auth_token(self, body)
                    me = auth.me(tok) if tok else None
                    return _json(self, *handle_agent_thread_new(body=body, me=me, agent_mission=agent_mission, ai=ai, build_agent_thread_state_payload_fn=build_agent_thread_state_payload))

                if u.path == "/agent/chat":
                    return _json(self, *handle_agent_chat_post(body=body, gateway=gateway, control=control, firmware=firmware, commissioning=commissioning, host_capture=host_capture, config_history=config_history, knowledge=knowledge, ai=ai, auth=auth, agent_mission=agent_mission, provider_router=provider_router, codex_agent=codex_agent, burst_status_fn=burst_status, legacy_execution_guard_fn=_legacy_execution_guard, extract_auth_token_fn=_extract_auth_token, codex_cli_login_status_fn=_codex_cli_login_status, agent_choose_executor_fn=_agent_choose_executor, agent_resolve_model_fn=_agent_resolve_model, agent_model_allowed_fn=_agent_model_allowed, agent_mode_system_prompt_fn=_agent_mode_system_prompt, sanitize_agent_attachments_fn=_sanitize_agent_attachments, commissioning_ai_context_fn=lambda c: commissioning_ai_context(c, read_csv_tail_fn=read_csv_tail), host_capture_ai_context_fn=lambda h: host_capture_ai_context(h, read_csv_tail_fn=read_csv_tail), assistant_capabilities_context_fn=assistant_capabilities_context, normalize_reply_for_prompt_fn=_normalize_reply_for_prompt, build_agent_chat_reply_payload_fn=build_agent_chat_reply_payload, handler_self=self, env_openai_model=os.environ.get("OPENAI_MODEL", "")))

                if u.path == "/agent/chat/stream":
                    guard = _legacy_execution_guard(u.path)
                    if guard is not None:
                        return _json(self, 403, guard)
                    msg = str(body.get("message", "")).strip()
                    if not msg:
                        return _json(self, 400, {"ok": False, "error": "missing_message"})
                    mode_state = agent_mission.status()
                    mode = str(body.get("mode", "")).strip() or str(mode_state.get("mode", "robot_dev"))
                    if mode != mode_state.get("mode"):
                        try:
                            mode_state = agent_mission.set_mode(mode)
                        except RuntimeError:
                            mode = str(mode_state.get("mode", "robot_dev"))
                    tok = _extract_auth_token(self, body)
                    me = auth.me(tok) if tok else None
                    err_resp, runtime = resolve_agent_stream_runtime(body=body, mode=mode, auth=auth, me=me, ai=ai, provider_router=provider_router, codex_agent=codex_agent, codex_cli_login_status_fn=_codex_cli_login_status, agent_choose_executor_fn=_agent_choose_executor, agent_resolve_model_fn=_agent_resolve_model, agent_model_allowed_fn=_agent_model_allowed, env_model=os.environ.get("OPENAI_MODEL", ""))
                    if err_resp is not None:
                        return _json(self, err_resp[0], err_resp[1])
                    api_key, model, executor = runtime["api_key"], runtime["model"], runtime["executor"]
                    ctx = build_agent_chat_stream_context(body=body, mode=mode, gateway=gateway, control=control, firmware=firmware, commissioning=commissioning, host_capture=host_capture, config_history=config_history, knowledge=knowledge, burst_status_fn=burst_status, commissioning_ai_context_fn=lambda c: commissioning_ai_context(c, read_csv_tail_fn=read_csv_tail), host_capture_ai_context_fn=lambda h: host_capture_ai_context(h, read_csv_tail_fn=read_csv_tail), assistant_capabilities_context_fn=assistant_capabilities_context, sanitize_attachments_fn=_sanitize_agent_attachments)
                    thread_id, session_key = str(body.get("thread_id", "")).strip() or None, f"user:{me['id']}:agent:{mode}" if me and isinstance(me.get("id"), int) else f"local:{mode}"
                    apply_sse_response_headers(self)
                    send_evt = make_inline_sse_emitter(self.wfile)
                    send_evt("start", {"ok": True})
                    try:
                        run_agent_chat_stream_executor(executor=executor, msg=msg, mode=mode, model=model, api_key=api_key, ctx=ctx, session_key=session_key, thread_id=thread_id, body=body, ai=ai, codex_agent=codex_agent, firmware=firmware, mode_state=mode_state, agent_mode_system_prompt_fn=_agent_mode_system_prompt, normalize_reply_for_prompt_fn=_normalize_reply_for_prompt, build_agent_chat_reply_payload_fn=build_agent_chat_reply_payload, send_evt=send_evt)
                    except Exception as exc:
                        send_evt("error", {"ok": False, "error": str(exc)})
                    return


                # Tooling routes dispatch
                _tooling_routes = {
                    "/tooling/trace-replay": lambda: handle_trace_replay(body=body, repo_root=repo_root, replay_file=replay_file),
                    "/tooling/param-sweep": lambda: handle_param_sweep(body=body, gateway=gateway, ParameterSweepRunner=ParameterSweepRunner, parse_range_spec=parse_range_spec, SweepConfig=SweepConfig),
                    "/tooling/surrogate/simulate": lambda: handle_surrogate_simulate(body=body, repo_root=repo_root, simulate_from_logs=simulate_from_logs),
                    "/tooling/tuning/recommend": lambda: handle_tuning_recommend(body=body, repo_root=repo_root, evaluate_tuning_plan=evaluate_tuning_plan, replay_file=replay_file, simulate_from_logs=simulate_from_logs, validate_contract_fn=_validate_tuning_recommendation_contract, evaluate_quality_fn=_evaluate_tuning_recommendation_quality),
                    "/tooling/tuning/preflight": lambda: handle_tuning_preflight(body=body, repo_root=repo_root, status_now=gateway.get_status(), evaluate_tuning_plan=evaluate_tuning_plan, replay_file=replay_file, simulate_from_logs=simulate_from_logs, validate_contract_fn=_validate_tuning_recommendation_contract, evaluate_quality_fn=_evaluate_tuning_recommendation_quality, build_signature_fn=_build_tuning_apply_signature, preflight_issue_fn=tuning_preflight.issue, status_float_fn=_status_float),
                }
                if u.path in _tooling_routes:
                    code, payload = _tooling_routes[u.path]()
                    return _json(self, code, payload)

                if u.path == "/command":
                    return _json(self, *handle_command(body=body, gateway=gateway, control=control, blocked_while_latched_fn=_blocked_while_latched))
                if u.path == "/burst/arm":
                    _require_action_allowed("burst_arm", gateway, control, prearm_gate=prearm_safety)
                    active_profile, defaults = _active_robot_profile(), _burst_threshold_defaults(_active_robot_profile())
                    return _json(self, *handle_burst_arm(body=body, gateway=gateway, host_capture=host_capture, burst_status_fn=burst_status, active_profile=active_profile, defaults=defaults))
                if u.path == "/burst/label":
                    return _json(self, *handle_burst_label(body=body, host_capture=host_capture, burst_status_fn=burst_status))

                _arm_routes = {"/arm/prepare": ("arm_prepare", lambda: handle_arm_prepare(control=control)), "/arm/confirm": ("arm_confirm", lambda: handle_arm_confirm(gateway=gateway, control=control)), "/arm": ("arm", lambda: handle_arm(gateway=gateway, control=control)), "/disarm": ("disarm", lambda: handle_disarm(gateway=gateway, control=control))}
                if u.path in _arm_routes:
                    action, handler = _arm_routes[u.path]
                    _require_action_allowed(action, gateway, control, prearm_gate=prearm_safety)
                    return _json(self, *handler())
                if u.path == "/arm/precheck":
                    return _json(self, *handle_arm_precheck(body=body, gateway=gateway, control=control, prearm_safety=prearm_safety, run_prearm_hardware_check_fn=_run_prearm_hardware_check, report_design_observation_fn=_report_design_observation, resolve_action_gates_fn=_resolve_action_gates))
                _estop_routes = {"/estop/latch": lambda: handle_estop_latch(gateway=gateway, control=control), "/estop/reset": lambda: handle_estop_reset(gateway=gateway, control=control)}
                if u.path in _estop_routes:
                    return _json(self, *_estop_routes[u.path]())

                _imu_fn = lambda res, cmd: classify_imu_command_result(res, cmd_name=cmd)
                _imu_routes = {"/cal_zero": lambda: handle_cal_zero(gateway=gateway, control=control), "/imu/calibrate": lambda: handle_imu_calibrate(gateway=gateway, control=control, classify_imu_fn=_imu_fn), "/imu/load": lambda: handle_imu_load(gateway=gateway, control=control, classify_imu_fn=_imu_fn), "/imu/save": lambda: handle_imu_save(gateway=gateway, control=control, classify_imu_fn=_imu_fn), "/imu/info": lambda: handle_imu_info(gateway=gateway, control=control, classify_imu_fn=_imu_fn)}
                if u.path in _imu_routes:
                    if u.path in {"/cal_zero", "/imu/calibrate"}:
                        _require_action_allowed("cal_zero", gateway, control)
                    return _json(self, *_imu_routes[u.path]())
                _cfg_routes = {"/savecfg": lambda: handle_savecfg(gateway=gateway, control=control), "/loadcfg": lambda: handle_loadcfg(gateway=gateway, control=control), "/defaultcfg": lambda: handle_defaultcfg(gateway=gateway, control=control)}
                if u.path in _cfg_routes:
                    return _json(self, *_cfg_routes[u.path]())

                _tuning_deps = dict(body=body, gateway=gateway, control=control, config_history=config_history, tuning_preflight=tuning_preflight, require_action_allowed_fn=_require_action_allowed, status_float_fn=_status_float, enforce_preflight_if_needed_fn=_enforce_preflight_if_needed, build_tuning_result_payload_fn=build_tuning_result_payload)
                _tuning_routes = {"/pid": lambda: handle_pid_post(**_tuning_deps, guard_pid_apply_fn=_guard_pid_apply), "/motion": lambda: handle_motion_post(**_tuning_deps, guard_motion_apply_fn=_guard_motion_apply), "/setpoint": lambda: handle_setpoint_post(**_tuning_deps, guard_setpoint_apply_fn=_guard_setpoint_apply), "/limits": lambda: handle_limits_post(**_tuning_deps, guard_limits_apply_fn=_guard_limits_apply)}
                if u.path in _tuning_routes:
                    return _json(self, *_tuning_routes[u.path]())

                return _json(self, 404, {"ok": False, "error": "not_found"})
            except KeyError as exc:
                return _json(self, 400, {"ok": False, "error": f"missing field: {exc}"})
            except RuntimeError as exc:
                msg = str(exc)
                _400_errs, _404_errs, _401_errs = {"invalid_email", "weak_password", "email_exists", "invalid_credentials", "invalid_openai_key", "empty_message", "sketch_content_empty", "profile_label_required", "profile_id_required", "ai_profile_label_required", "ai_profile_id_required"}, {"profile_not_found", "ai_profile_not_found", "snapshot_not_found"}, {"unauthenticated", "openai_api_key_missing"}
                _409_ctrl, _428_errs, _423_errs, _409_fw = {"tuning_delta_too_large_while_balancing", "arm_not_prepared"}, {"preflight_required", "preflight_invalid", "preflight_mismatch"}, {"estop_latched", "session_stale"}, {"firmware_running", "operation_in_progress"}
                if msg in _400_errs or msg.startswith("invalid_unified_profile:") or msg.startswith("invalid_tuning_value:"):
                    return _json(self, 400, {"ok": False, "error": msg})
                if msg.startswith("openai_key_verification_failed:"):
                    return _json(self, 503, {"ok": False, "error": msg})
                if msg in _404_errs:
                    return _json(self, 404, {"ok": False, "error": msg})
                if msg in _401_errs:
                    return _json(self, 401, {"ok": False, "error": msg})
                if msg in _409_ctrl:
                    return _json(self, 409, {"ok": False, "error": msg, "control": control.snapshot()})
                if msg in _428_errs:
                    return _json(self, 428, {"ok": False, "error": msg, "control": control.snapshot()})
                if msg in _423_errs:
                    return _json(self, 423, {"ok": False, "error": msg, "control": control.snapshot()})
                if msg.startswith("action_blocked:"):
                    parts = msg.split(":", 2)
                    return _json(self, 423, {"ok": False, "error": "action_blocked", "action": parts[1] if len(parts) > 1 else "unknown", "reasons": [r for r in (parts[2] if len(parts) > 2 else "").split(",") if r], "action_gates": _resolve_action_gates(gateway, control, prearm_gate=prearm_safety), "control": control.snapshot()})
                if msg == "commissioning_running":
                    return _json(self, 409, {"ok": False, "error": msg, "commissioning": commissioning.status()})
                if msg in _409_fw:
                    return _json(self, 409, {"ok": False, "error": msg, "firmware": firmware.status()})
                return _json(self, 500, {"ok": False, "error": msg})
            except Exception as exc:
                return _json(self, 500, {"ok": False, "error": str(exc)})

    return Handler


def watchdog_loop(gateway: NanoSerialGateway, control: BridgeControlState, stop_evt: threading.Event) -> None:
    while not stop_evt.wait(0.1):
        try:
            if not control.check_and_trip_watchdog():
                continue
            mode = str(gateway.get_status().get("mode", "UNKNOWN"))
            if mode in {"BALANCING", "ARMED"}:
                gateway.command("DISARM", timeout=1.0)
                control.record_watchdog_disarm(f"heartbeat_timeout:{mode}")
        except Exception:
            continue


def serial_reconnect_loop(gateway: NanoSerialGateway, firmware: FirmwareManager, stop_evt: threading.Event) -> None:
    while not stop_evt.wait(2.0):
        try:
            if bool(firmware.status().get("running", False)) or gateway.health().get("connected", False):
                continue
            gateway.connect()
            print(f"serial reconnected: mode={gateway.wait_ready(timeout=5.0).get('mode', 'UNKNOWN')}")
        except Exception:
            try:
                gateway.close()
            except Exception:
                pass
            continue


# _startup_rag_indexing moved to routes_ai.py as startup_rag_indexing


def main() -> int:
    _install_runtime_diagnostics()
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default=os.environ.get("NANO_PORT", "/dev/tty.usbserial-2210"))
    ap.add_argument("--baud", type=int, default=int(os.environ.get("NANO_BAUD", "115200")))
    ap.add_argument("--host", default=os.environ.get("APP_BRIDGE_HOST", "127.0.0.1"))
    ap.add_argument("--http-port", type=int, default=int(os.environ.get("APP_BRIDGE_PORT", "8797")))
    ap.add_argument("--telemetry-port", type=int, default=int(os.environ.get("APP_TELEMETRY_PORT", "8798")))
    ap.add_argument("--instance", default=os.environ.get("APP_BRIDGE_INSTANCE", "upright-lean-v1"), help="Instance label")
    ap.add_argument("--watchdog-timeout", type=float, default=float(os.environ.get("APP_WATCHDOG_TIMEOUT_S", "2.0")))
    ap.add_argument("--supervised", action="store_true", help="Suppress direct-run warning")
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
    commissioning, host_capture = CommissioningManager(repo_root, args.port, args.baud), HostCaptureManager(repo_root)
    firmware, ai = FirmwareManager(repo_root, args.port), AIManager(repo_root)
    ai_profiles, knowledge = AIProfileManager(repo_root), AssistantKnowledgeManager(repo_root)
    agent_mission, provider_router = AgentMissionManager(repo_root), ProviderRouter(repo_root)

    codex_agent: Optional[Any] = None
    if create_codex_agent is not None:
        try:
            codex_agent = create_codex_agent(gateway=gw, firmware_module=firmware, probe_funcs={"run_compat_probe": run_compat_probe, "run_connect_probe": run_connect_probe}, repo_root=str(repo_root), host_capture=host_capture)
            print("codex agent initialized with tool support")
            startup_openai_key = os.environ.get("OPENAI_API_KEY")
            if startup_openai_key:
                threading.Thread(target=_startup_rag_indexing, args=(startup_openai_key,), daemon=True, name="startup-rag-indexing").start()
                print("background RAG indexing started")
        except Exception as exc:
            print(f"codex agent init failed (tool support disabled): {exc}")
    auth, mission_memory = AuthManager(repo_root), MissionMemoryStore(repo_root)
    hardware_context, setup_attempt_history = HardwareContextStore(repo_root), SetupAttemptHistoryStore(repo_root)
    profiles, config_history = RobotProfilesManager(repo_root), ConfigHistoryManager(repo_root)
    prearm_safety, telemetry = PreArmSafetyGate(required=True), TelemetryHub()

    print(f"bridge started without serial target: {args.port} @ {args.baud} ({startup_serial_error})" if startup_serial_error else f"bridge serial opened: {args.port} @ {args.baud}")
    print(f"telemetry websocket: ws://{args.host}:{args.telemetry_port}/telemetry enabled={websockets is not None}")

    stop_evt = threading.Event()
    threading.Thread(target=watchdog_loop, args=(gw, control, stop_evt), daemon=True).start()
    threading.Thread(target=serial_reconnect_loop, args=(gw, firmware, stop_evt), daemon=True).start()

    server = ThreadingHTTPServer((args.host, args.http_port), build_handler(gw, control, commissioning, host_capture, firmware, ai, ai_profiles, knowledge, agent_mission, provider_router, auth, mission_memory, profiles, config_history, args.telemetry_port, codex_agent, hardware_context, setup_attempt_history, prearm_safety))
    print(f"bridge listening on http://{args.host}:{args.http_port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop_evt.set()
        server.server_close()
        gw.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
