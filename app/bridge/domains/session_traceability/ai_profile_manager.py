"""
AI Profile Manager - Assistant profile configuration and management.

Extracted from server.py to domains/session_traceability/
"""

from __future__ import annotations

import json
import pathlib
import secrets
import threading
import time
from typing import Any, Dict


class AIProfileManager:
    def __init__(self, repo_root: pathlib.Path) -> None:
        self.path = repo_root / "app" / "bridge" / "ai_profiles.json"
        self._lock = threading.Lock()

    def _default_profile(self) -> Dict[str, Any]:
        now = time.time()
        return {
            "profile_id": "default",
            "label": "Default Copilot",
            "description": "Operator-first debug copilot with strict truth and UI-capability guardrails.",
            "instructions": (
                "Execution mode: operate like a full Codex agent with proactive tool use and execution-first behavior. "
                "Keep operator-facing responses short and actionable, but do not force rigid one-line formats. "
                "For non-high-risk requests, execute directly instead of repeatedly asking for permission. "
                "In troubleshooting, ask clarifying questions only when required to unblock execution. "
                "Never claim compile/upload/flash/calibration/reconnect success without tool-confirmed evidence. "
                "Align guidance to actual UI capabilities; never instruct UI actions that do not exist. "
                "Firmware generation policy: treat existing/example sketches as references only, not canonical architecture. "
                "When user asks for a specialized sketch (for example raw pin-data reader), generate purpose-built code from requirements, not a near-copy of template logic. "
                "Sketch write policy: when editing/generating a sketch, write full file content, then verify non-empty read-back and report path + byte count. "
                "Baud policy: baud is read-only in UI and treated as a session invariant; "
                "if mismatch is suspected, direct user to bridge restart/startup with explicit baud. "
                "Include safety cautions only when action is high-risk or user requests a checklist."
            ),
            "policy": {
                "allow_auto_apply": True,
            },
            "created_at": now,
            "updated_at": now,
        }

    def _read_unlocked(self) -> Dict[str, Any]:
        if not self.path.exists():
            d = self._default_profile()
            return {"active_profile_id": d["profile_id"], "profiles": [d]}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            d = self._default_profile()
            return {"active_profile_id": d["profile_id"], "profiles": [d]}
        if not isinstance(raw, dict):
            d = self._default_profile()
            return {"active_profile_id": d["profile_id"], "profiles": [d]}
        profiles = raw.get("profiles")
        if not isinstance(profiles, list) or not profiles:
            d = self._default_profile()
            profiles = [d]
        active_profile_id = raw.get("active_profile_id")
        if not isinstance(active_profile_id, str) or not any(
            str(p.get("profile_id", "")) == active_profile_id for p in profiles
        ):
            active_profile_id = str(profiles[0].get("profile_id", "default"))
        return {"active_profile_id": active_profile_id, "profiles": profiles}

    def _write_unlocked(self, data: Dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(data, indent=2, sort_keys=True), encoding="utf-8"
        )

    def list(self) -> Dict[str, Any]:
        with self._lock:
            data = self._read_unlocked()
            profiles = list(data.get("profiles", []))
            profiles.sort(
                key=lambda p: float(p.get("updated_at", 0.0) or 0.0), reverse=True
            )
            return {
                "active_profile_id": data.get("active_profile_id"),
                "profiles": profiles,
            }

    def get_active(self) -> Dict[str, Any]:
        with self._lock:
            data = self._read_unlocked()
            active = str(data.get("active_profile_id", ""))
            for p in data.get("profiles", []):
                if str(p.get("profile_id", "")) == active:
                    return p
            return data.get("profiles", [self._default_profile()])[0]

    def save(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        label = str(profile.get("label", "")).strip()
        if not label:
            raise RuntimeError("ai_profile_label_required")
        description = str(profile.get("description", "")).strip()
        instructions = str(profile.get("instructions", "")).strip()
        policy_in = profile.get("policy")
        policy = policy_in if isinstance(policy_in, dict) else {}
        allow_auto_apply = bool(policy.get("allow_auto_apply", True))
        with self._lock:
            data = self._read_unlocked()
            profiles = list(data.get("profiles", []))
            now = time.time()
            pid = str(profile.get("profile_id", "")).strip() or secrets.token_urlsafe(8)
            next_profile = {
                "profile_id": pid,
                "label": label,
                "description": description,
                "instructions": instructions,
                "policy": {"allow_auto_apply": allow_auto_apply},
                "created_at": now,
                "updated_at": now,
            }
            replaced = False
            for i, p in enumerate(profiles):
                if str(p.get("profile_id", "")) == pid:
                    next_profile["created_at"] = float(p.get("created_at", now) or now)
                    profiles[i] = next_profile
                    replaced = True
                    break
            if not replaced:
                profiles.append(next_profile)
            active_profile_id = str(data.get("active_profile_id") or pid)
            out = {"active_profile_id": active_profile_id, "profiles": profiles}
            self._write_unlocked(out)
            return {"active_profile_id": active_profile_id, "profile": next_profile}

    def activate(self, profile_id: str) -> Dict[str, Any]:
        pid = str(profile_id).strip()
        if not pid:
            raise RuntimeError("ai_profile_id_required")
        with self._lock:
            data = self._read_unlocked()
            profiles = list(data.get("profiles", []))
            if not any(str(p.get("profile_id", "")) == pid for p in profiles):
                raise RuntimeError("ai_profile_not_found")
            out = {"active_profile_id": pid, "profiles": profiles}
            self._write_unlocked(out)
            return {"active_profile_id": pid}
