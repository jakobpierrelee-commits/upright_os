import sys
import json
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from server import FirmwareManager  # noqa: E402


def _mk_unified_template(repo_root: Path) -> None:
    tdir = repo_root / "app" / "bridge" / "firmware_templates" / "unified_v1"
    tdir.mkdir(parents=True, exist_ok=True)
    (tdir / "main.ino.tmpl").write_text(
        "void setup(){}\nvoid loop(){}\n",
        encoding="utf-8",
    )


def _manifest_profile() -> dict:
    return {
        "board": {"fqbn": "arduino:avr:nano"},
        "hardware": {"imu_protocol": "i2c", "encoder_protocol": "quadrature"},
        "pins": {
            "motor_l_pwm": 5,
            "motor_l_dir": 4,
            "motor_r_pwm": 6,
            "motor_r_dir": 7,
            "imu_sda": 18,
            "imu_scl": 19,
            "enc_l_a": 2,
            "enc_l_b": 3,
            "enc_r_a": 10,
            "enc_r_b": 11,
        },
    }


def test_write_sketch_autogenerates_runtime_manifest(tmp_path: Path) -> None:
    repo_root = tmp_path
    fm = FirmwareManager(repo_root=repo_root, default_port="/dev/null")
    sketch_dir = repo_root / "generated_firmware" / "unit_sketch"
    sketch_dir.mkdir(parents=True, exist_ok=True)
    ino = sketch_dir / "unit_sketch.ino"
    out = fm.write_sketch(
        content="void setup(){}\nvoid loop(){}\n",
        path=str(ino),
        profile=_manifest_profile(),
    )
    assert out["bytes"] > 0
    manifest = sketch_dir / "runtime_manifest_v1.json"
    assert manifest.exists()
    raw = manifest.read_text(encoding="utf-8")
    node = json.loads(raw)
    release = node.get("release") or {}
    assert release.get("runtime_version")
    assert release.get("tune_version")
    assert "runtime" in list(node.get("telemetry_fields") or [])
    assert "tune" in list(node.get("telemetry_fields") or [])
    check = fm.validate_runtime_manifest(sketch=str(sketch_dir), require_exists=True)
    assert check["ok"] is True


def test_write_sketch_requires_profile_when_manifest_missing(tmp_path: Path) -> None:
    repo_root = tmp_path
    fm = FirmwareManager(repo_root=repo_root, default_port="/dev/null")
    sketch_dir = repo_root / "generated_firmware" / "unit_sketch_missing_profile"
    sketch_dir.mkdir(parents=True, exist_ok=True)
    ino = sketch_dir / "unit_sketch_missing_profile.ino"
    with pytest.raises(RuntimeError, match="profile_required_for_manifest"):
        fm.write_sketch(content="void setup(){}\nvoid loop(){}\n", path=str(ino))


def test_generate_unified_writes_runtime_manifest(tmp_path: Path) -> None:
    repo_root = tmp_path
    _mk_unified_template(repo_root)
    fm = FirmwareManager(repo_root=repo_root, default_port="/dev/null")
    profile = {
        "label": "unit_unified",
        "board": {"fqbn": "arduino:avr:nano:cpu=atmega328old", "port": "/dev/null"},
        "hardware": {"imu_type": "mpu6050", "motor_driver": "tb6612"},
        "pins": {
            "motor_l_pwm": 5,
            "motor_l_dir": 4,
            "motor_r_pwm": 6,
            "motor_r_dir": 7,
            "imu_sda": 18,
            "imu_scl": 19,
            "gate_enable": 8,
            "led": 13,
            "enc_l_a": 2,
            "enc_l_b": 3,
            "enc_r_a": 10,
            "enc_r_b": 11,
        },
    }
    out = fm.generate_unified(profile=profile, sketch_name="unit_unified")
    sketch_folder = Path(str(out["sketch_folder"]))
    manifest = sketch_folder / "runtime_manifest_v1.json"
    assert manifest.exists()
    check = fm.validate_runtime_manifest(sketch=str(sketch_folder), require_exists=True)
    assert check["ok"] is True


def test_build_runtime_manifest_merges_probe_commands(tmp_path: Path) -> None:
    repo_root = tmp_path
    fm = FirmwareManager(repo_root=repo_root, default_port="/dev/null")
    profile = _manifest_profile()
    profile["probe"] = {"commands": ["GET", "arm", "MOTION", "MOTION"]}
    manifest = fm._build_runtime_manifest_from_profile(
        fqbn="arduino:avr:nano", profile=profile
    )
    assert "MOTION" in manifest["commands"]
    assert manifest["commands"].count("MOTION") == 1
    release = manifest.get("release") or {}
    assert release.get("runtime_version") == "runtime_v1.0.0"
    assert release.get("tune_version") == "tune_v1"


def test_build_runtime_manifest_supports_release_version_overrides(tmp_path: Path) -> None:
    repo_root = tmp_path
    fm = FirmwareManager(repo_root=repo_root, default_port="/dev/null")
    profile = _manifest_profile()
    profile["release"] = {
        "runtime_version": "profiled_runtime_v1.2.0",
        "tune_version": "tune_v5",
    }
    manifest = fm._build_runtime_manifest_from_profile(
        fqbn="arduino:avr:nano", profile=profile
    )
    release = manifest.get("release") or {}
    assert release.get("runtime_version") == "profiled_runtime_v1.2.0"
    assert release.get("tune_version") == "tune_v5"


def test_build_runtime_manifest_uses_release_json_defaults(tmp_path: Path) -> None:
    repo_root = tmp_path
    release_dir = (
        repo_root / "app" / "bridge" / "firmware_templates" / "profiled_runtime_v1"
    )
    release_dir.mkdir(parents=True, exist_ok=True)
    (release_dir / "release.json").write_text(
        json.dumps(
            {
                "runtime_version": "profiled_runtime_v9.9.9",
                "tune_version": "tune_v42",
                "version_policy": "runtime_only_for_structure",
            }
        ),
        encoding="utf-8",
    )
    fm = FirmwareManager(repo_root=repo_root, default_port="/dev/null")
    manifest = fm._build_runtime_manifest_from_profile(
        fqbn="arduino:avr:nano", profile=_manifest_profile()
    )
    release = manifest.get("release") or {}
    assert release.get("runtime_version") == "profiled_runtime_v9.9.9"
    assert release.get("tune_version") == "tune_v42"
    assert release.get("version_policy") == "runtime_only_for_structure"


def test_build_runtime_manifest_supports_teensy41_non_avr_profile(tmp_path: Path) -> None:
    repo_root = tmp_path
    fm = FirmwareManager(repo_root=repo_root, default_port="/dev/null")
    profile = {
        "board": {"fqbn": "teensy:avr:teensy41"},
        "hardware": {
            "imu_protocol": "i2c",
            "encoder_protocol": "spi",
            "actuator_protocol": "can",
            "motor_driver": "bldc_foc",
            "imu_type": "bno085",
        },
        "pins": {
            "imu_sda": 18,
            "imu_scl": 19,
            "enc_miso": 12,
            "enc_mosi": 11,
            "enc_sck": 13,
            "enc_cs": 10,
            "motor_can_tx": 22,
            "motor_can_rx": 23,
        },
        "probe": {"commands": ["GET", "ARM", "DISARM", "PID", "SETPOINT", "MOTION"]},
    }
    manifest = fm._build_runtime_manifest_from_profile(
        fqbn="teensy:avr:teensy41", profile=profile
    )
    assert manifest["board"]["id"] == "teensy41"
    assert manifest["board"]["family"] == "teensy"
    assert manifest["interfaces"]["encoders"]["protocol"] == "spi"
    assert manifest["interfaces"]["actuator"]["protocol"] == "can"
    check = fm.validate_runtime_manifest(manifest=manifest, require_exists=False)
    assert check["ok"] is True
