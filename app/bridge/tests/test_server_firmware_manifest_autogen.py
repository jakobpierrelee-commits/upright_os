import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from server import FirmwareManager  # noqa: E402


def _mk_unified_template(repo_root: Path) -> None:
    tdir = repo_root / "app" / "bridge" / "firmware_templates" / "unified_v1"
    tdir.mkdir(parents=True, exist_ok=True)
    (tdir / "main.ino.tmpl").write_text(
        "void setup(){}\nvoid loop(){}\n",
        encoding="utf-8",
    )


def test_write_sketch_autogenerates_runtime_manifest(tmp_path: Path) -> None:
    repo_root = tmp_path
    fm = FirmwareManager(repo_root=repo_root, default_port="/dev/null")
    sketch_dir = repo_root / "generated_firmware" / "unit_sketch"
    sketch_dir.mkdir(parents=True, exist_ok=True)
    ino = sketch_dir / "unit_sketch.ino"
    out = fm.write_sketch(content="void setup(){}\nvoid loop(){}\n", path=str(ino))
    assert out["bytes"] > 0
    manifest = sketch_dir / "runtime_manifest_v1.json"
    assert manifest.exists()
    check = fm.validate_runtime_manifest(sketch=str(sketch_dir), require_exists=True)
    assert check["ok"] is True


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
