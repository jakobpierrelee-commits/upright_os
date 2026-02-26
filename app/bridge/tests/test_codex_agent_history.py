import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from codex_agent import CodexAgent  # noqa: E402


def test_chat_with_tools_includes_prior_history():
    agent = CodexAgent()
    captured = {}

    def fake_call_openai(*, messages, api_key, model, tools, timeout_s=60):
        captured["messages"] = messages
        return {"choices": [{"message": {"content": "ok", "tool_calls": None}}]}

    history = [
        {"role": "user", "text": "Remember branch recover/uiux-restore-2026-02-19"},
        {"role": "assistant", "text": "Stored."},
    ]

    with patch.object(agent, "_call_openai", side_effect=fake_call_openai):
        out = agent.chat_with_tools(
            message="What branch is active?",
            context={},
            api_key="k",
            model="gpt-5-mini",
            system_prompt="test",
            enable_tools=False,
            conversation_history=history,
        )

    assert out["answer"] == "ok"
    msgs = captured["messages"]
    roles = [m["role"] for m in msgs]
    assert roles.count("user") >= 2
    assert any(m["role"] == "assistant" and "Stored." in m["content"] for m in msgs)
    assert msgs[-1]["role"] == "user"
    assert msgs[-1]["content"] == "What branch is active?"


def test_chat_with_tools_ignores_invalid_history_entries():
    agent = CodexAgent()
    captured = {}

    def fake_call_openai(*, messages, api_key, model, tools, timeout_s=60):
        captured["messages"] = messages
        return {"choices": [{"message": {"content": "ok", "tool_calls": None}}]}

    history = [
        {"role": "system", "text": "ignore"},
        {"role": "user", "text": ""},
        {"role": "assistant", "text": "valid"},
    ]

    with patch.object(agent, "_call_openai", side_effect=fake_call_openai):
        agent.chat_with_tools(
            message="ping",
            context={},
            api_key="k",
            model="gpt-5-mini",
            system_prompt="test",
            enable_tools=False,
            conversation_history=history,
        )

    msgs = captured["messages"]
    hist_msgs = [m for m in msgs if m["role"] in {"user", "assistant"} and m["content"] != "ping"]
    assert len(hist_msgs) == 1
    assert hist_msgs[0]["role"] == "assistant"
    assert hist_msgs[0]["content"] == "valid"


def test_chat_with_tools_injects_mission_facts_system_message():
    agent = CodexAgent()
    captured = {}

    def fake_call_openai(*, messages, api_key, model, tools, timeout_s=60):
        captured["messages"] = messages
        return {"choices": [{"message": {"content": "ok", "tool_calls": None}}]}

    with patch.object(agent, "_call_openai", side_effect=fake_call_openai):
        agent.chat_with_tools(
            message="recall mission facts",
            context={"mission_facts": {"branch": "recover/uiux-restore-2026-02-19", "board_imu": "Arduino Nano + MPU6050"}},
            api_key="k",
            model="gpt-5-mini",
            system_prompt="test",
            enable_tools=False,
        )

    msgs = captured["messages"]
    sys_msgs = [m["content"] for m in msgs if m["role"] == "system"]
    assert any("mission_facts=" in s for s in sys_msgs)
