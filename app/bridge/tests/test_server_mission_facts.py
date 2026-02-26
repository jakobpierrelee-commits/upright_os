import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from server import _extract_mission_facts  # noqa: E402


def test_extract_mission_facts_from_seed_messages():
    history = [
        {
            "role": "user",
            "text": "Store these mission facts exactly: branch=recover/uiux-restore-2026-02-19, target=embedded vectoring reliability, guardrail=no monkey patches, priority=safety over speed.",
        },
        {"role": "assistant", "text": "STORED"},
        {
            "role": "user",
            "text": "Store this extra fact: preferred robot board is Arduino Nano + MPU6050.",
        },
    ]
    facts = _extract_mission_facts(history)
    assert facts["branch"] == "recover/uiux-restore-2026-02-19"
    assert facts["target"] == "embedded vectoring reliability"
    assert facts["guardrail"] == "no monkey patches"
    assert facts["priority"] == "safety over speed."
    assert "Arduino Nano + MPU6050" in facts["preferred_board_imu"]


def test_extract_mission_facts_ignores_non_user_messages():
    history = [
        {"role": "assistant", "text": "Store these mission facts exactly: branch=bad"},
        {"role": "system", "text": "Store this extra fact: bad"},
    ]
    assert _extract_mission_facts(history) == {}


def test_extract_mission_facts_distinguishes_test_board_and_corrections():
    history = [
        {
            "role": "user",
            "text": "Store this extra fact: current board for testing is Arduino Nano + MPU6050.",
        },
        {
            "role": "user",
            "text": "Preferred board is not Arduino Nano; that's only for testing right now.",
        },
    ]
    facts = _extract_mission_facts(history)
    assert "Arduino Nano + MPU6050" in facts["current_test_board_imu"]
    assert facts["board_selection_policy"].startswith("current board may be test-only")
    assert facts["hardware_recommendation_mode"] == "proactive"


def test_extract_mission_facts_hardware_policy_preferences():
    history = [
        {
            "role": "user",
            "text": (
                "rank hardware on reliability>capability>control performance>safety>cost>devspeed, "
                "prefer parts in stock but recommend something better if needed, "
                "no major constraints right now, "
                "future features: latency, processing speed, memory, storage, wireless connectivity, on board logging, OTA updates, edge ai, steering, "
                "must at least ask for clarifications on parts before making new recommendations, "
                "ask at the beginning about better parts once, "
                "he is not merely a parts recommender."
            ),
        }
    ]
    facts = _extract_mission_facts(history)
    assert (
        facts["hardware_priority_order"]
        == "reliability>capability>control_performance>safety>cost>dev_speed"
    )
    assert facts["prefer_in_stock"] == "true"
    assert facts["allow_better_non_stock"] == "true"
    assert facts["constraints_mode"] == "exploratory"
    assert facts["require_parts_clarification_before_new_reco"] == "true"
    assert facts["hardware_upgrade_optin_once"] == "true"
    assert facts["assistant_role_scope"] == "full_stack_controls_mechatronics"
    assert "latency" in facts["future_feature_priorities"]
    assert "edge_ai" in facts["future_feature_priorities"]
