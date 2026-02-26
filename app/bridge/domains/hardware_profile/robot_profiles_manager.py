"""
Robot Profiles Manager - Hardware profile configuration and validation.

Extracted from server.py to domains/hardware_profile/

Note: The validate() method has a dependency on run_connect_probe from server.py.
This is injected at runtime to avoid circular imports.
"""

from __future__ import annotations

import json
import pathlib
import secrets
import threading
import time
from typing import Any, Callable, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from app.bridge.nano_serial_gateway import NanoSerialGateway


class RobotProfilesManager:
    def __init__(
        self,
        repo_root: pathlib.Path,
        run_connect_probe_fn: Optional[Callable[..., Dict[str, Any]]] = None,
    ) -> None:
        self.path = repo_root / "app" / "bridge" / "robot_profiles.json"
        self._lock = threading.Lock()
        self._run_connect_probe = run_connect_probe_fn

    def _read(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {"active_profile_id": None, "profiles": []}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {"active_profile_id": None, "profiles": []}
        if not isinstance(raw, dict):
            return {"active_profile_id": None, "profiles": []}
        profiles = raw.get("profiles")
        if not isinstance(profiles, list):
            profiles = []
        active_profile_id = raw.get("active_profile_id")
        if active_profile_id is not None and not isinstance(active_profile_id, str):
            active_profile_id = None
        return {"active_profile_id": active_profile_id, "profiles": profiles}

    def _write(self, data: Dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(data, indent=2, sort_keys=True), encoding="utf-8"
        )

    def list(self) -> Dict[str, Any]:
        with self._lock:
            data = self._read()
            profiles = list(data.get("profiles", []))
            profiles.sort(
                key=lambda p: float(p.get("updated_at", 0) or 0), reverse=True
            )
            return {
                "active_profile_id": data.get("active_profile_id"),
                "profiles": profiles,
            }

    def save(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        label = str(profile.get("label", "")).strip()
        if not label:
            raise RuntimeError("profile_label_required")
        chassis = str(profile.get("chassis", "custom")).strip() or "custom"
        with self._lock:
            data = self._read()
            profiles = list(data.get("profiles", []))
            now = time.time()
            pid = str(profile.get("profile_id", "")).strip() or secrets.token_urlsafe(8)
            next_profile = {
                "profile_id": pid,
                "label": label,
                "chassis": chassis,
                "board": profile.get("board", {})
                if isinstance(profile.get("board"), dict)
                else {},
                "parts": profile.get("parts", {})
                if isinstance(profile.get("parts"), dict)
                else {},
                "pinmap": profile.get("pinmap", {})
                if isinstance(profile.get("pinmap"), dict)
                else {},
                "firmware": profile.get("firmware", {})
                if isinstance(profile.get("firmware"), dict)
                else {},
                "limits": profile.get("limits", {})
                if isinstance(profile.get("limits"), dict)
                else {},
                "calibration": profile.get("calibration", {})
                if isinstance(profile.get("calibration"), dict)
                else {},
                "probe": profile.get("probe", {})
                if isinstance(profile.get("probe"), dict)
                else {},
                "validation": profile.get("validation", {})
                if isinstance(profile.get("validation"), dict)
                else {},
                "created_at": float(profile.get("created_at", now) or now),
                "updated_at": now,
            }
            replaced = False
            for i, p in enumerate(profiles):
                if str(p.get("profile_id", "")) == pid:
                    created_at = float(p.get("created_at", now) or now)
                    next_profile["created_at"] = created_at
                    profiles[i] = next_profile
                    replaced = True
                    break
            if not replaced:
                profiles.append(next_profile)
            active_profile_id = data.get("active_profile_id") or pid
            out = {"active_profile_id": active_profile_id, "profiles": profiles}
            self._write(out)
            return {"active_profile_id": active_profile_id, "profile": next_profile}

    def activate(self, profile_id: str) -> Dict[str, Any]:
        pid = str(profile_id).strip()
        if not pid:
            raise RuntimeError("profile_id_required")
        with self._lock:
            data = self._read()
            profiles = list(data.get("profiles", []))
            if not any(str(p.get("profile_id", "")) == pid for p in profiles):
                raise RuntimeError("profile_not_found")
            out = {"active_profile_id": pid, "profiles": profiles}
            self._write(out)
            return {"active_profile_id": pid}

    def delete(self, profile_id: str) -> Dict[str, Any]:
        pid = str(profile_id).strip()
        if not pid:
            raise RuntimeError("profile_id_required")
        with self._lock:
            data = self._read()
            profiles = [
                p
                for p in list(data.get("profiles", []))
                if str(p.get("profile_id", "")) != pid
            ]
            active = data.get("active_profile_id")
            if active == pid:
                active = str(profiles[0].get("profile_id")) if profiles else None
            out = {"active_profile_id": active, "profiles": profiles}
            self._write(out)
            return {"active_profile_id": active, "profiles": profiles}

    def validate(
        self,
        gateway: "NanoSerialGateway",
        *,
        duration_s: float = 12.0,
        sample_interval_s: float = 0.25,
    ) -> Dict[str, Any]:
        if self._run_connect_probe is None:
            raise RuntimeError("run_connect_probe not configured")

        duration_s = max(2.0, min(duration_s, 90.0))
        sample_interval_s = max(0.1, min(sample_interval_s, 1.0))

        connect = self._run_connect_probe(gateway)
        serial = gateway.health()
        compat = connect.get("compat", {}) if isinstance(connect, dict) else {}

        missing_fields = (
            list((compat.get("missing_fields") or []))
            if isinstance(compat, dict)
            else []
        )
        has_schema = (
            ("ang" not in missing_fields)
            and ("raw" not in missing_fields)
            and (not any("gyro" in str(f) for f in missing_fields))
        )

        required_cmds = (
            list((compat.get("required_commands") or []))
            if isinstance(compat, dict)
            else []
        )
        if not required_cmds:
            required_cmds = [
                "GET",
                "ARM",
                "DISARM",
                "PID",
                "SETPOINT",
                "LIMITS",
                "CAL ZERO",
                "SAVECFG",
            ]
        supported_cmds = (
            set((compat.get("supported_commands") or []))
            if isinstance(compat, dict)
            else set()
        )
        if not supported_cmds:
            supported_cmds = set(
                connect.get("commands", []) if isinstance(connect, dict) else []
            )
        blocking_missing = (
            list((compat.get("blocking_missing_commands") or []))
            if isinstance(compat, dict)
            else []
        )
        missing_cmds = (
            list(blocking_missing)
            if blocking_missing
            else [c for c in required_cmds if c not in supported_cmds]
        )

        samples = 0
        fresh_hits = 0
        q_ok_hits = 0
        timeout_start = int(
            ((serial.get("serial_metrics") or {}).get("timeouts", 0)) or 0
        )
        until = time.monotonic() + duration_s
        while time.monotonic() < until:
            h = gateway.health()
            samples += 1
            age_ms = h.get("last_status_age_ms")
            qd = int(h.get("queue_depth", 0) or 0)
            if isinstance(age_ms, (float, int)) and float(age_ms) < 500.0:
                fresh_hits += 1
            if qd <= 2:
                q_ok_hits += 1
            time.sleep(sample_interval_s)
        end = gateway.health()
        timeout_end = int(((end.get("serial_metrics") or {}).get("timeouts", 0)) or 0)
        timeout_delta = max(0, timeout_end - timeout_start)

        freshness_ratio = (fresh_hits / samples) if samples else 0.0
        queue_ratio = (q_ok_hits / samples) if samples else 0.0

        checks = [
            {
                "id": "compat_fields",
                "label": "Compatibility fields present (ang/raw/gyro)",
                "ok": bool(has_schema),
                "detail": "missing="
                + (",".join(missing_fields) if missing_fields else "none"),
            },
            {
                "id": "commands_supported",
                "label": "Required commands supported",
                "ok": len(missing_cmds) == 0,
                "detail": "missing="
                + (",".join(missing_cmds) if missing_cmds else "none"),
            },
            {
                "id": "telemetry_freshness",
                "label": "Telemetry freshness (<500ms for >=95% samples)",
                "ok": freshness_ratio >= 0.95,
                "detail": f"fresh_ratio={freshness_ratio:.3f} samples={samples}",
            },
            {
                "id": "queue_depth",
                "label": "Serial queue depth healthy (<=2 for >=95% samples)",
                "ok": queue_ratio >= 0.95,
                "detail": f"queue_ratio={queue_ratio:.3f} samples={samples}",
            },
            {
                "id": "timeouts",
                "label": "Serial timeouts <= 1 during validation window",
                "ok": timeout_delta <= 1,
                "detail": f"timeout_delta={timeout_delta}",
            },
        ]
        ok = all(bool(c["ok"]) for c in checks)
        score_pct = int(
            round(100.0 * (sum(1 for c in checks if c["ok"]) / max(1, len(checks))))
        )

        return {
            "ok": ok,
            "score_pct": score_pct,
            "checks": checks,
            "generated_at": time.time(),
            "duration_s": duration_s,
            "sample_interval_s": sample_interval_s,
            "connect": connect,
            "compat": compat,
            "serial": end,
        }
