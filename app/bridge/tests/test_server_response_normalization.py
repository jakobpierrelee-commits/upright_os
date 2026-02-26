import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from server import _normalize_reply_for_prompt  # noqa: E402


def test_normalize_reply_only_stored() -> None:
    out = _normalize_reply_for_prompt(
        "Store this extra fact. Reply only: STORED.", "Stored! Done."
    )
    assert out == "STORED."


def test_normalize_yes_no_mode() -> None:
    out = _normalize_reply_for_prompt(
        "Answer only with YES or NO: bypass safety?", "No, never bypass safety."
    )
    assert out == "NO"


def test_normalize_one_sentence_mode() -> None:
    out = _normalize_reply_for_prompt(
        "In one sentence, what is your role?",
        "I help with robotics. I can also tune PID and run tools.",
    )
    assert out == "I help with robotics."
