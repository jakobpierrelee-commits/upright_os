import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent))

from server import SetupAttemptHistoryStore, run_setup_overwatch_check  # noqa: E402


def test_setup_attempt_history_store_append_and_list(tmp_path: Path) -> None:
    store = SetupAttemptHistoryStore(tmp_path, max_entries=3)
    a1 = store.append(
        test_type="compat",
        status="pass",
        sketch_revision="r1",
        sketch_hash="abcd1234",
        action_source="setup_page",
        profile_id="p1",
        profile_label="Test Bot A",
        result={"status": "pass"},
    )
    a2 = store.append(
        test_type="smoke",
        status="warn",
        sketch_revision="r2",
        sketch_hash="efgh5678",
        action_source="setup_page",
        profile_id="p2",
        profile_label="Test Bot B",
        result={"status": "warn"},
    )
    rows = store.list_recent(limit=10)
    assert len(rows) == 2
    assert rows[0]["attempt_id"] == a2["attempt_id"]
    assert rows[1]["attempt_id"] == a1["attempt_id"]


def test_setup_attempt_history_store_respects_max_entries(tmp_path: Path) -> None:
    store = SetupAttemptHistoryStore(tmp_path, max_entries=30)
    for idx in range(31):
        store.append(
            test_type="compat",
            status="pass",
            sketch_revision=f"r{idx}",
            sketch_hash=f"h{idx}",
            action_source="setup_page",
            profile_id=f"p{idx}",
            profile_label=f"Bot {idx}",
            result={},
        )
    rows = store.list_recent(limit=10)
    assert len(store.list_recent(limit=999)) == 30
    assert rows[0]["sketch_revision"] == "r30"
    assert rows[-1]["sketch_revision"] == "r21"


def test_run_setup_overwatch_check_maps_status(monkeypatch) -> None:
    def fake_report(*, gateway, firmware, compat=None, connect=None):
        return {"overall": "warn", "score_pct": 66}

    monkeypatch.setattr("server.build_overwatch_report", fake_report)
    out = run_setup_overwatch_check(SimpleNamespace(), SimpleNamespace())
    assert out["status"] == "warn"
    assert out["overwatch"]["score_pct"] == 66


def test_setup_attempt_history_paging_with_kind_and_cursor(tmp_path: Path) -> None:
    store = SetupAttemptHistoryStore(tmp_path, max_entries=30)
    for idx in range(8):
        kind = "compat" if (idx % 2 == 0) else "smoke"
        store.append(
            test_type=kind,
            status="pass",
            sketch_revision=f"r{idx}",
            sketch_hash=f"h{idx}",
            action_source="setup_page",
            profile_id=f"p{idx}",
            profile_label=f"Bot {idx}",
            result={},
        )
    page1 = store.list_recent_page(limit=2, kind="compat")
    assert len(page1["attempts"]) == 2
    assert page1["has_more"] is True
    cursor = page1["next_cursor"]
    assert cursor
    page2 = store.list_recent_page(limit=2, kind="compat", cursor_attempt_id=cursor)
    assert len(page2["attempts"]) == 2
    assert page2["attempts"][0]["attempt_id"] != page1["attempts"][0]["attempt_id"]
