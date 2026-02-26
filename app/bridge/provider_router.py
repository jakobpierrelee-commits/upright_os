from __future__ import annotations

import json
import pathlib
import threading
from typing import Any, Dict, Optional


class ProviderRouter:
    def __init__(self, repo_root: pathlib.Path) -> None:
        self.repo_root = repo_root
        self.policy_path = repo_root / "docs" / "contracts" / "provider_routing_v1.json"
        self._lock = threading.Lock()
        self._cache: Dict[str, Any] = {"mtime": 0.0, "policy": None}

    def _default_policy(self) -> Dict[str, Any]:
        return {
            "version": "1.0",
            "default_provider": "openai",
            "allowed_model_substrings": ["codex"],
            "mission_mode_defaults": {
                "app_dev": "gpt-5-codex",
                "robot_dev": "gpt-5-codex",
                "ops_debug": "gpt-5-codex",
            },
            "fallback_order": ["request", "user_saved", "env", "mode_default"],
        }

    def _load_policy_unlocked(self) -> Dict[str, Any]:
        if not self.policy_path.exists():
            return self._default_policy()
        try:
            mtime = self.policy_path.stat().st_mtime
            if self._cache["policy"] is not None and self._cache["mtime"] == mtime:
                return dict(self._cache["policy"])
            raw = json.loads(self.policy_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return self._default_policy()
            merged = self._default_policy()
            merged.update(raw)
            self._cache = {"mtime": mtime, "policy": merged}
            return dict(merged)
        except Exception:
            return self._default_policy()

    def policy(self) -> Dict[str, Any]:
        with self._lock:
            return self._load_policy_unlocked()

    @staticmethod
    def _str(value: Any) -> str:
        return str(value or "").strip()

    def resolve_agent_runtime(
        self,
        *,
        mode: str,
        requested_api_key: Optional[str],
        requested_model: Optional[str],
        user_creds: Optional[Dict[str, Any]],
        env_api_key: str,
        env_model: str,
    ) -> Dict[str, Any]:
        policy = self.policy()
        mode_defaults = (
            policy.get("mission_mode_defaults", {})
            if isinstance(policy.get("mission_mode_defaults"), dict)
            else {}
        )
        fallback_order = (
            policy.get("fallback_order", [])
            if isinstance(policy.get("fallback_order"), list)
            else []
        )
        allowed_substrings = [
            str(x).strip().lower()
            for x in (policy.get("allowed_model_substrings", []) or [])
            if str(x).strip()
        ]

        request_key = self._str(requested_api_key)
        user_key = self._str((user_creds or {}).get("api_key"))
        env_key = self._str(env_api_key)

        request_model = self._str(requested_model)
        user_model = self._str((user_creds or {}).get("model"))
        env_model_val = self._str(env_model)
        mode_default = self._str(mode_defaults.get(mode, ""))

        key_by_source = {
            "request": request_key,
            "user_saved": user_key,
            "env": env_key,
            "mode_default": "",
        }
        model_by_source = {
            "request": request_model,
            "user_saved": user_model,
            "env": env_model_val,
            "mode_default": mode_default,
        }

        resolved_key = ""
        resolved_key_source = ""
        resolved_model = ""
        resolved_model_source = ""
        for source in fallback_order:
            candidate_key = key_by_source.get(source, "")
            if not resolved_key and candidate_key:
                resolved_key = candidate_key
                resolved_key_source = source
            candidate_model = model_by_source.get(source, "")
            if not resolved_model and candidate_model:
                resolved_model = candidate_model
                resolved_model_source = source
            if resolved_key and resolved_model:
                break

        model_allowed = False
        if resolved_model and allowed_substrings:
            lower_model = resolved_model.lower()
            model_allowed = any(sub in lower_model for sub in allowed_substrings)
            if not model_allowed:
                forced_model = mode_default
                forced_allowed = (
                    any(sub in forced_model.lower() for sub in allowed_substrings)
                    if forced_model
                    else False
                )
                if forced_allowed:
                    resolved_model = forced_model
                    resolved_model_source = "mode_default_forced"
                    model_allowed = True

        return {
            "provider": str(policy.get("default_provider", "openai")),
            "policy_version": str(policy.get("version", "1.0")),
            "api_key": resolved_key,
            "api_key_source": resolved_key_source,
            "model": resolved_model,
            "model_source": resolved_model_source,
            "model_allowed": model_allowed,
            "allowed_model_substrings": allowed_substrings,
        }
