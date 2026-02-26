import pathlib
import sys

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from clean_profiles import (
    build_profiles_hardware_payload,
    build_profiles_payload,
    build_runtime_manifest_compat_payload,
)


def test_build_profiles_payload_shape() -> None:
    payload = build_profiles_payload(
        profiles_state={
            "active_profile_id": "p1",
            "profiles": [{"profile_id": "p1", "label": "Primary"}],
        }
    )
    assert payload["ok"] is True
    assert payload["profiles"]["active_profile_id"] == "p1"
    assert payload["profiles"]["profiles"][0]["label"] == "Primary"


def test_build_profiles_hardware_payload_shape() -> None:
    payload = build_profiles_hardware_payload(
        registry={"boards": [{"id": "nano", "label": "Arduino Nano"}]}
    )
    assert payload["ok"] is True
    assert payload["registry"]["boards"][0]["id"] == "nano"


def test_build_runtime_manifest_compat_payload_selects_active_profile() -> None:
    seen = {}

    def compat_fn(*, manifest_validation, active_profile, targets):
        seen["manifest"] = manifest_validation
        seen["active_profile"] = active_profile
        seen["targets"] = targets
        return {"ok": True, "errors": [], "warnings": []}

    payload = build_runtime_manifest_compat_payload(
        manifest_check={"ok": True, "manifest": {"board": {"fqbn": "a:b:c"}}},
        profiles_state={
            "active_profile_id": "p2",
            "profiles": [
                {"profile_id": "p1", "label": "A"},
                {"profile_id": "p2", "label": "B"},
            ],
        },
        targets={"boards": []},
        compatibility_fn=compat_fn,
    )

    assert payload["ok"] is True
    assert payload["active_profile_id"] == "p2"
    assert payload["compatibility"]["ok"] is True
    assert seen["active_profile"]["profile_id"] == "p2"
