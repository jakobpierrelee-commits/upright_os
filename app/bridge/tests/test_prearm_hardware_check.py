import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from server import BridgeControlState, _run_prearm_hardware_check  # noqa: E402


class _GatewayStub:
    def __init__(self) -> None:
        self._estop = "0"
        self._fault = "0"
        self.support_motor_test = True
        self.support_prearm_rpc = False
        self.rpc_ok = True
        self.left_delta = 3
        self.right_delta = 4
        self.left_deltas: list[int] | None = None
        self.right_deltas: list[int] | None = None
        self.commands: list[str] = []

    def command(self, cmd: str, timeout: float = 1.0, **_: object):  # noqa: ARG002
        up = str(cmd).strip().upper()
        self.commands.append(up)
        if up == "HELP":
            help_line = "OK HELP GET ARM DISARM ESTOP PID SETPOINT LIMITS MOTOR_TEST"
            if not self.support_motor_test:
                help_line = "OK HELP GET ARM DISARM ESTOP PID SETPOINT LIMITS"
            return {"matched": help_line, "lines": [help_line]}
        if up == "PREARM_CHECK":
            if not self.support_prearm_rpc:
                raise RuntimeError("ERR PREARM_CHECK unsupported")
            line = (
                "OK PREARM_CHECK "
                f"ok={1 if self.rpc_ok else 0} stand=1 wheel_l={1 if self.rpc_ok else 0} wheel_r={1 if self.rpc_ok else 0} "
                "estop_latch=1 estop_unlatch=1 dL=2 dR=2 detail=rpc"
            )
            return {"matched": line, "lines": [line]}
        if up.startswith("MOTOR_TEST L "):
            if self._estop != "1" or self._fault != "0":
                raise RuntimeError("ERR MOTOR_TEST unsafe_state")
            if self.left_deltas is not None and self.left_deltas:
                self.left_delta = int(self.left_deltas.pop(0))
            moved = 1 if abs(self.left_delta) >= 1 else 0
            line = f"OK MOTOR_TEST wheel=L pwm=110 ms=160 dL={self.left_delta} dR=0 moved={moved}"
            return {"matched": line, "lines": [line]}
        if up.startswith("MOTOR_TEST R "):
            if self._estop != "1" or self._fault != "0":
                raise RuntimeError("ERR MOTOR_TEST unsafe_state")
            if self.right_deltas is not None and self.right_deltas:
                self.right_delta = int(self.right_deltas.pop(0))
            moved = 1 if abs(self.right_delta) >= 1 else 0
            line = f"OK MOTOR_TEST wheel=R pwm=110 ms=160 dL=0 dR={self.right_delta} moved={moved}"
            return {"matched": line, "lines": [line]}
        if up == "ESTOP 1":
            self._estop = "1"
            if self._fault == "0":
                self._fault = "32"
        elif up == "ESTOP 0":
            if self._fault == "32":
                self._fault = "0"
            self._estop = "0"
        elif up == "FAULTCLR":
            self._fault = "0"
        return "OK"

    def get_status(self):
        return {"mode": "SAFE_IDLE", "estop": self._estop, "fault": self._fault}


def test_prearm_check_fails_when_bot_not_on_stand() -> None:
    gw = _GatewayStub()
    control = BridgeControlState()
    out = _run_prearm_hardware_check(
        gw,
        control,
        {
            "bot_on_stand_ok": False,
            "left_wheel_pulse_ok": True,
            "right_wheel_pulse_ok": True,
            "auto_estop_probe": True,
        },
    )
    assert out["ok"] is False
    checks = {c["id"]: c for c in out["checks"]}
    assert checks["bot_on_stand"]["status"] == "fail"


def test_prearm_check_passes_when_stand_and_checks_ok() -> None:
    gw = _GatewayStub()
    control = BridgeControlState()
    out = _run_prearm_hardware_check(
        gw,
        control,
        {
            "bot_on_stand_ok": True,
            "left_wheel_pulse_ok": True,
            "right_wheel_pulse_ok": True,
            "auto_estop_probe": True,
        },
    )
    assert out["ok"] is True
    checks = {c["id"]: c for c in out["checks"]}
    assert checks["bot_on_stand"]["status"] == "pass"
    assert checks["estop_latch"]["status"] == "pass"
    assert checks["estop_unlatch"]["status"] == "pass"


def test_prearm_check_uses_auto_motor_test_when_supported() -> None:
    gw = _GatewayStub()
    control = BridgeControlState()
    out = _run_prearm_hardware_check(
        gw,
        control,
        {
            "bot_on_stand_ok": True,
            "auto_wheel_probe": True,
            "auto_estop_probe": True,
        },
    )
    assert out["ok"] is True
    assert out["wheel_probe_mode"] == "auto_firmware"
    checks = {c["id"]: c for c in out["checks"]}
    assert checks["wheel_left_pulse"]["status"] == "pass"
    assert checks["wheel_right_pulse"]["status"] == "pass"


def test_prearm_check_fails_when_auto_motor_test_reports_no_motion() -> None:
    gw = _GatewayStub()
    gw.left_delta = 0
    control = BridgeControlState()
    out = _run_prearm_hardware_check(
        gw,
        control,
        {
            "bot_on_stand_ok": True,
            "auto_wheel_probe": True,
            "auto_estop_probe": True,
        },
    )
    assert out["ok"] is False
    checks = {c["id"]: c for c in out["checks"]}
    assert checks["wheel_left_pulse"]["status"] == "fail"


def test_prearm_check_retries_wheel_probe_until_motion_detected() -> None:
    gw = _GatewayStub()
    gw.left_deltas = [0, 0, 2]
    gw.right_deltas = [0, 3]
    control = BridgeControlState()
    out = _run_prearm_hardware_check(
        gw,
        control,
        {
            "bot_on_stand_ok": True,
            "auto_wheel_probe": True,
            "wheel_probe_retries": 3,
            "auto_estop_probe": True,
        },
    )
    assert out["ok"] is True
    checks = {c["id"]: c for c in out["checks"]}
    assert checks["wheel_left_pulse"]["status"] == "pass"
    assert checks["wheel_right_pulse"]["status"] == "pass"
    assert "ESTOP 1" in gw.commands


def test_prearm_check_auto_probe_clears_fault_before_motor_test() -> None:
    gw = _GatewayStub()
    gw._fault = "32"
    control = BridgeControlState()
    out = _run_prearm_hardware_check(
        gw,
        control,
        {
            "bot_on_stand_ok": True,
            "auto_wheel_probe": True,
            "auto_estop_probe": True,
        },
    )
    checks = {c["id"]: c for c in out["checks"]}
    assert checks["wheel_probe_prepare"]["status"] == "pass"
    assert checks["wheel_left_pulse"]["status"] == "pass"
    assert checks["wheel_right_pulse"]["status"] == "pass"
    assert "FAULTCLR" in gw.commands


def test_prearm_check_accepts_estop_latched_fault_code_for_motor_test() -> None:
    gw = _GatewayStub()
    # Simulate runtime starting faulted; precheck should clear to estop=1,fault=0.
    gw._fault = "32"
    control = BridgeControlState()
    out = _run_prearm_hardware_check(
        gw,
        control,
        {
            "bot_on_stand_ok": True,
            "auto_wheel_probe": True,
            "auto_estop_probe": True,
        },
    )
    checks = {c["id"]: c for c in out["checks"]}
    assert checks["wheel_probe_prepare"]["status"] == "pass"
    assert gw.get_status().get("fault") == "0"


def test_prearm_check_uses_firmware_rpc_when_supported() -> None:
    gw = _GatewayStub()
    gw.support_prearm_rpc = True
    control = BridgeControlState()
    out = _run_prearm_hardware_check(
        gw,
        control,
        {"bot_on_stand_ok": True, "auto_wheel_probe": True, "auto_estop_probe": True},
    )
    assert out["ok"] is True
    assert out.get("rpc_used") is True
    assert out.get("phase") == "prearm_hardware_safety_rpc_v1"
