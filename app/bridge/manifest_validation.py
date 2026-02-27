"""Manifest validation utilities extracted from server.py."""

from typing import Any, Dict, Optional

__all__ = [
    "_pin_range_for_family",
    "_family_capabilities",
    "_protocol_schema",
    "_has_valid_pin",
    "_validate_protocol_pins",
    "_validate_runtime_manifest_v1",
    "_manifest_required_field_present",
    "_family_for_fqbn",
    "_board_id_for_fqbn",
    "_runtime_manifest_profile_compatibility",
]


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
