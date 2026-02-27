"""Agent/AI helper utilities extracted from server.py."""

import faulthandler
import logging
import os
import pathlib
import re
import signal
import sys
import threading
import traceback
from typing import Any, Dict, List, Optional

try:
    from app.bridge.clean_auth_helpers import codex_cli_login_status
except ImportError:
    from clean_auth_helpers import codex_cli_login_status  # type: ignore

try:
    from app.bridge.clean_legacy_gate import (
        legacy_execution_enabled,
        legacy_execution_block_payload,
    )
except ImportError:
    from clean_legacy_gate import (  # type: ignore
        legacy_execution_enabled,
        legacy_execution_block_payload,
    )

logger = logging.getLogger(__name__)

__all__ = [
    "_codexrules_cache",
    "_load_codexrules",
    "_resolve_system_prompt",
    "_agent_mode_system_prompt",
    "_agent_model_allowed",
    "_agent_mode_default_model",
    "_agent_resolve_model",
    "_agent_choose_executor",
    "_install_runtime_diagnostics",
    "_codex_cli_login_status",
    "_legacy_execution_guard",
    "_extract_mission_facts",
    "_first_sentence",
    "_truncate_words",
    "_is_high_risk_user_request",
    "_strip_repetitive_caution_lines",
    "_soften_forced_reply_exact",
    "_normalize_reply_for_prompt",
]


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
