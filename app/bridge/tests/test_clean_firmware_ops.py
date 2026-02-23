import pathlib
import sys

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from clean_firmware_ops import (
    handle_clean_firmware_compile,
    handle_clean_firmware_upload,
)


def _tool_call_builder(**kwargs):
    return {"name": kwargs.get("name"), "result": {"ok": kwargs.get("ok", False), "error": kwargs.get("error", "")}}


class _FirmwareOk:
    def compile(self, **kwargs):
        return {"state": "done", "phase": "compile", "returncode": 0}

    def upload_guarded(self, **kwargs):
        return {"state": "done", "phase": "upload", "returncode": 0}

    def status(self):
        return {"state": "running"}


class _FirmwareBusy(_FirmwareOk):
    def compile(self, **kwargs):
        raise RuntimeError("operation_in_progress")

    def upload_guarded(self, **kwargs):
        raise RuntimeError("operation_in_progress")


class _Prearm:
    def __init__(self):
        self.reason = ""

    def require(self, reason: str):
        self.reason = reason
        return {"required": True, "passed": False, "reason": reason}


def test_handle_clean_firmware_compile_ok() -> None:
    code, payload = handle_clean_firmware_compile(
        firmware=_FirmwareOk(),
        sketch="a.ino",
        fqbn="arduino:avr:nano",
        idempotency_key=None,
        tool_call_builder=_tool_call_builder,
    )
    assert code == 200
    assert payload["ok"] is True
    assert payload["firmware"]["returncode"] == 0


def test_handle_clean_firmware_compile_busy() -> None:
    code, payload = handle_clean_firmware_compile(
        firmware=_FirmwareBusy(),
        sketch="a.ino",
        fqbn="arduino:avr:nano",
        idempotency_key="k1",
        tool_call_builder=_tool_call_builder,
    )
    assert code == 409
    assert payload["ok"] is False
    assert payload["error"] == "operation_in_progress"


def test_handle_clean_firmware_upload_ok() -> None:
    prearm = _Prearm()
    code, payload = handle_clean_firmware_upload(
        firmware=_FirmwareOk(),
        gateway=object(),
        prearm_safety=prearm,
        sketch="a.ino",
        fqbn="arduino:avr:nano",
        port="/dev/null",
        idempotency_key=None,
        tool_call_builder=_tool_call_builder,
    )
    assert code == 200
    assert payload["ok"] is True
    assert prearm.reason == "firmware_upload_guarded"


def test_handle_clean_firmware_upload_busy() -> None:
    code, payload = handle_clean_firmware_upload(
        firmware=_FirmwareBusy(),
        gateway=object(),
        prearm_safety=_Prearm(),
        sketch="a.ino",
        fqbn="arduino:avr:nano",
        port=None,
        idempotency_key="k2",
        tool_call_builder=_tool_call_builder,
    )
    assert code == 409
    assert payload["ok"] is False
    assert payload["error"] == "operation_in_progress"
