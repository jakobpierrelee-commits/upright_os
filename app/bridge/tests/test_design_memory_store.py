import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from server import DesignMemoryStore  # noqa: E402


def test_design_memory_report_persists_and_scores(tmp_path: Path) -> None:
    store = DesignMemoryStore(tmp_path)
    row = store.report(
        session_key="local:app_dev",
        observation={
            "runtime_version": "v1",
            "tune_version": "t1",
            "ident": "upright-nano",
            "hash": "abc123",
            "profile_id": "nano_balance",
        },
        success=True,
        source="setup_compat_test",
        note="compat passed",
    )
    assert str(row.get("design_id", "")).startswith("design_")
    assert int(row.get("success_count", 0)) == 1
    assert float(row.get("score", 0.0)) >= 3.0

    reloaded = DesignMemoryStore(tmp_path)
    recent = reloaded.list_recent(limit=5)
    assert len(recent) >= 1
    assert str(recent[0].get("design_id", "")).startswith("design_")


def test_design_memory_rate_updates_best_selection(tmp_path: Path) -> None:
    store = DesignMemoryStore(tmp_path)
    first = store.report(
        session_key="local:app_dev",
        observation={
            "runtime_version": "v1",
            "ident": "a",
            "hash": "111",
            "profile_id": "p1",
        },
        success=True,
        source="auto",
        note="first pass",
    )
    second = store.report(
        session_key="local:app_dev",
        observation={
            "runtime_version": "v2",
            "ident": "b",
            "hash": "222",
            "profile_id": "p1",
        },
        success=True,
        source="auto",
        note="second pass",
    )
    store.rate(
        design_id=str(second["design_id"]),
        rating="positive",
        note="felt better",
        session_key="local:app_dev",
    )
    store.rate(
        design_id=str(first["design_id"]),
        rating="negative",
        note="unstable",
        session_key="local:app_dev",
    )
    best = store.best(session_key="local:app_dev", profile_id="p1")
    assert best is not None
    assert str(best.get("design_id")) == str(second["design_id"])

