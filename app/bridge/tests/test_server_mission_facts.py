import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from server import _extract_mission_facts  # noqa: E402


def test_extract_mission_facts_from_seed_messages():
    history = [
        {"role": "user", "text": "Store these mission facts exactly: branch=recover/uiux-restore-2026-02-19, target=embedded vectoring reliability, guardrail=no monkey patches, priority=safety over speed."},
        {"role": "assistant", "text": "STORED"},
        {"role": "user", "text": "Store this extra fact: preferred robot board is Arduino Nano + MPU6050."},
    ]
    facts = _extract_mission_facts(history)
    assert facts["branch"] == "recover/uiux-restore-2026-02-19"
    assert facts["target"] == "embedded vectoring reliability"
    assert facts["guardrail"] == "no monkey patches"
    assert facts["priority"] == "safety over speed."
    assert "Arduino Nano + MPU6050" in facts["board_imu"]


def test_extract_mission_facts_ignores_non_user_messages():
    history = [
        {"role": "assistant", "text": "Store these mission facts exactly: branch=bad"},
        {"role": "system", "text": "Store this extra fact: bad"},
    ]
    assert _extract_mission_facts(history) == {}
