from __future__ import annotations

import math
import time
from typing import Any, Callable, Dict, Optional, Tuple
import concurrent.futures


EmitEvent = Callable[[str, Dict[str, Any]], None]


def build_clean_preflight_questions(with_compile: bool) -> list[str]:
    questions = [
        "one line only: preflight q1 ok",
        "run connect probe [tool:connect_probe] and summarize in one line",
        "run compat probe [tool:compat_probe] and summarize in one line",
    ]
    if with_compile:
        questions.append(
            "compile profiled runtime [tool:compile_profiled_runtime_v1] and report one-line result"
        )
    questions.extend(
        [
            "one line: confirm clean lane is codex-cli runtime",
            "one line only: preflight complete",
        ]
    )
    return questions


def _local_preflight_reply(prompt: str, *, model: str) -> Optional[str]:
    text = str(prompt or "").strip().lower()
    if text == "one line only: preflight q1 ok":
        return "preflight q1 ok"
    if text == "one line: confirm clean lane is codex-cli runtime":
        return f"clean lane codex-cli runtime confirmed ({model})"
    if text == "one line only: preflight complete":
        return "preflight complete"
    return None


def _question_timeout_s(*, limit_ms: int, clean_timeout_s: int) -> int:
    # Keep question execution bounded so Verify cannot appear stuck for minutes.
    # Allow small overhead beyond policy limit, but never exceed configured cap.
    limit_s = max(1, int(math.ceil(float(limit_ms) / 1000.0)))
    return max(10, min(int(clean_timeout_s), limit_s + 5))


def _tool_summary_for_prompt(
    prompt: str, tool_calls: list[Dict[str, Any]]
) -> Optional[str]:
    text = str(prompt or "").lower()
    if not tool_calls:
        return None
    first = tool_calls[0] if isinstance(tool_calls[0], dict) else {}
    name = str(first.get("name", "")).strip().lower()
    result = first.get("result") if isinstance(first.get("result"), dict) else {}
    ok = bool(result.get("ok", False))
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    err = str(result.get("error", "")).strip()

    if "[tool:connect_probe]" in text and name == "connect_probe":
        conf = int(data.get("confidence_pct", 0) or 0)
        return (
            f"connect probe {'ok' if ok else 'failed'}; confidence={conf}%"
            if ok
            else f"connect probe failed: {err or 'unknown_error'}"
        )
    if "[tool:compat_probe]" in text and name == "compat_probe":
        missing_fields = list(data.get("missing_fields", [])[:3])
        missing_commands = list(data.get("missing_commands", [])[:3])
        if ok:
            if not missing_fields and not missing_commands:
                return "compat probe ok; no missing required fields/commands"
            return (
                "compat probe ok; "
                f"missing_fields={','.join(map(str, missing_fields)) or 'none'}; "
                f"missing_commands={','.join(map(str, missing_commands)) or 'none'}"
            )
        return f"compat probe failed: {err or 'unknown_error'}"
    if "[tool:compile_profiled_runtime_v1]" in text and name == "firmware_compile":
        rc = data.get("returncode")
        phase = str(data.get("phase", "")).strip() or "compile"
        return (
            f"{phase} {'pass' if ok and int(rc or 1) == 0 else 'fail'}"
            if ok
            else f"compile failed: {err or 'unknown_error'}"
        )
    return None


def _run_auto_tools_with_timeout(
    *,
    run_auto_tools: Callable[..., list[Dict[str, Any]]],
    message: str,
    model: str,
    timeout_s: int,
) -> list[Dict[str, Any]]:
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(run_auto_tools, message=message, model=model)
        return fut.result(timeout=max(1, int(timeout_s)))


def resolve_manifest_gates(
    *,
    firmware: Any,
    profiles: Any,
    compatibility_fn: Callable[..., Dict[str, Any]],
    sketch: str,
) -> Tuple[Dict[str, Any], Dict[str, Any], str]:
    manifest_gate = firmware.validate_runtime_manifest(
        sketch=sketch, require_exists=True
    )
    profile_state = profiles.list()
    active_profile_id = str(profile_state.get("active_profile_id") or "").strip()
    active_profile = next(
        (
            p
            for p in list(profile_state.get("profiles") or [])
            if isinstance(p, dict)
            and str(p.get("profile_id", "")).strip() == active_profile_id
        ),
        None,
    )
    compat_gate = compatibility_fn(
        manifest_validation=manifest_gate,
        active_profile=active_profile if isinstance(active_profile, dict) else None,
        targets=firmware.list_targets(),
    )
    return manifest_gate, compat_gate, active_profile_id


def _gate_payload(
    *,
    ok: bool,
    mode: str,
    failures: int,
    max_ms: int,
    max_ms_tools: int,
    manifest_gate: Dict[str, Any],
    compat_gate: Dict[str, Any],
    active_profile_id: str,
    result: Dict[str, Any],
    gate_only: bool = False,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "ok": ok,
        "mode": mode,
        "failures": failures,
        "max_ms": max_ms,
        "max_ms_tools": max_ms_tools,
        "gate": {
            "runtime_manifest": manifest_gate,
            "manifest_profile_compat": compat_gate,
            "active_profile_id": active_profile_id or None,
            "fail_closed": True,
        },
        "results": [result],
    }
    if gate_only:
        payload["gate"]["gate_only"] = True
    return payload


def run_clean_preflight(
    *,
    mode: str,
    max_ms: int,
    max_ms_tools: int,
    gate_only: bool,
    with_compile: bool,
    model: str,
    clean_timeout_s: int,
    manifest_gate: Dict[str, Any],
    compat_gate: Dict[str, Any],
    active_profile_id: str,
    ai: Any,
    run_auto_tools: Callable[..., list[Dict[str, Any]]],
    build_context: Callable[..., Dict[str, Any]],
    system_prompt_for_mode: Callable[[str], str],
    normalize_reply_for_prompt: Callable[[str, str], str],
    validate_preflight_payload: Callable[[Dict[str, Any]], None],
    emit: Optional[EmitEvent] = None,
) -> Dict[str, Any]:
    if not bool(manifest_gate.get("ok", False)):
        reason = "runtime_manifest_invalid:" + ", ".join(
            list(manifest_gate.get("errors") or [])[:5]
        )
        result = {
            "id": "manifest_gate",
            "ok": False,
            "dt_ms": 0,
            "limit_ms": max_ms,
            "expect_tools": False,
            "tool_calls": [],
            "error": reason,
            "reply": "runtime manifest gate blocked preflight",
        }
        payload = _gate_payload(
            ok=False,
            mode=mode,
            failures=1,
            max_ms=max_ms,
            max_ms_tools=max_ms_tools,
            manifest_gate=manifest_gate,
            compat_gate=compat_gate,
            active_profile_id=active_profile_id,
            result=result,
        )
        validate_preflight_payload(payload)
        if emit:
            emit("check_done", {"index": 1, "total": 1, "result": result})
            emit("done", payload)
        return payload

    if not bool(compat_gate.get("ok", False)):
        reason = "runtime_manifest_profile_incompatible:" + ", ".join(
            list(compat_gate.get("errors") or [])[:5]
        )
        result = {
            "id": "manifest_profile_compat_gate",
            "ok": False,
            "dt_ms": 0,
            "limit_ms": max_ms,
            "expect_tools": False,
            "tool_calls": [],
            "error": reason,
            "reply": "runtime manifest/profile compatibility gate blocked preflight",
        }
        payload = _gate_payload(
            ok=False,
            mode=mode,
            failures=1,
            max_ms=max_ms,
            max_ms_tools=max_ms_tools,
            manifest_gate=manifest_gate,
            compat_gate=compat_gate,
            active_profile_id=active_profile_id,
            result=result,
        )
        validate_preflight_payload(payload)
        if emit:
            emit("check_done", {"index": 1, "total": 1, "result": result})
            emit("done", payload)
        return payload

    if gate_only:
        result = {
            "id": "manifest_gate",
            "ok": True,
            "dt_ms": 0,
            "limit_ms": max_ms,
            "expect_tools": False,
            "tool_calls": [],
            "error": "",
            "reply": "runtime manifest gates passed",
        }
        payload = _gate_payload(
            ok=True,
            mode=mode,
            failures=0,
            max_ms=max_ms,
            max_ms_tools=max_ms_tools,
            manifest_gate=manifest_gate,
            compat_gate=compat_gate,
            active_profile_id=active_profile_id,
            result=result,
            gate_only=True,
        )
        validate_preflight_payload(payload)
        if emit:
            emit("check_done", {"index": 1, "total": 1, "result": result})
            emit("done", payload)
        return payload

    questions = build_clean_preflight_questions(with_compile)
    session_key = f"local:clean:{mode}"
    thread = ai.create_thread(session_key, "Clean Preflight")
    thread_id = str(thread.get("id", "")).strip() or None
    results: list[Dict[str, Any]] = []
    failures = 0
    total = len(questions)

    for idx, prompt in enumerate(questions):
        expect_tools = "[tool:" in prompt.lower()
        if emit:
            emit(
                "check_start",
                {
                    "index": idx + 1,
                    "total": total,
                    "id": f"q{idx + 1}",
                    "expect_tools": expect_tools,
                    "prompt": prompt,
                },
            )
        limit_ms = max_ms_tools if expect_tools else max_ms
        ok = True
        error = ""
        tool_calls: list[Dict[str, Any]] = []
        tool_summary = None
        if expect_tools:
            try:
                tool_calls = _run_auto_tools_with_timeout(
                    run_auto_tools=run_auto_tools,
                    message=prompt,
                    model=model,
                    timeout_s=_question_timeout_s(
                        limit_ms=limit_ms, clean_timeout_s=clean_timeout_s
                    ),
                )
                tool_summary = _tool_summary_for_prompt(prompt, tool_calls)
            except Exception as exc:
                tool_calls = []
                tool_summary = None
                ok = False
                error = f"tool_timeout_or_error:{exc}"
        ctx = build_context(
            mode=mode,
            session_key=session_key,
            thread_id=thread_id,
            attachments=None,
            clean_tool_calls=tool_calls,
        )
        t0 = int(time.time() * 1000)
        reply = ""
        local_reply = _local_preflight_reply(prompt, model=model)
        if expect_tools:
            if tool_summary is not None:
                reply = tool_summary
            else:
                ok = False
                if not error:
                    error = "tool_calls_missing"
                reply = "tool-backed preflight check failed"
        elif local_reply is not None:
            reply = local_reply
        else:
            try:
                out = ai.chat_codex_cli(
                    message=prompt,
                    context=ctx,
                    session_key=session_key,
                    model=model,
                    thread_id=thread_id,
                    system_prompt=system_prompt_for_mode(mode),
                    timeout_s_override=_question_timeout_s(
                        limit_ms=limit_ms, clean_timeout_s=clean_timeout_s
                    ),
                )
                thread_id = str(out.get("thread_id", "")).strip() or thread_id
                reply = str(out.get("answer", "(no output)"))
            except Exception as exc:
                ok = False
                error = str(exc)
        dt_ms = int(time.time() * 1000) - t0
        if expect_tools and len(tool_calls) <= 0:
            ok = False
            error = error or "tool_calls_missing"
        if dt_ms > limit_ms:
            ok = False
            error = error or f"slow:{dt_ms}>{limit_ms}"
        if not reply.strip():
            ok = False
            error = error or "empty_reply"
        if not ok:
            failures += 1
        result = {
            "id": f"q{idx + 1}",
            "ok": ok,
            "dt_ms": dt_ms,
            "limit_ms": limit_ms,
            "expect_tools": expect_tools,
            "tool_calls": tool_calls,
            "error": error,
            "reply": normalize_reply_for_prompt(prompt, reply)[:240],
        }
        results.append(result)
        if emit:
            emit("check_done", {"index": idx + 1, "total": total, "result": result})

    payload = {
        "ok": failures == 0,
        "mode": mode,
        "failures": failures,
        "max_ms": max_ms,
        "max_ms_tools": max_ms_tools,
        "results": results,
    }
    validate_preflight_payload(payload)
    if emit:
        emit("done", payload)
    return payload
