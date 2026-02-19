import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from server import AIManager


def test_ai_state_recovers_from_corrupt_primary_using_backup(tmp_path: Path) -> None:
    ai = AIManager(tmp_path)
    skey = "user:test"
    ai._append(skey, "user", "hello")
    ai._append(skey, "assistant", "world")
    ai._append(skey, "user", "again")

    # force one more save so a backup is produced
    ai._append(skey, "assistant", "done")

    state_path = tmp_path / "app" / "bridge" / "ai_threads.json"
    backups_dir = tmp_path / "app" / "bridge" / "ai_threads_backups"
    assert state_path.exists()
    assert backups_dir.exists()
    assert any(backups_dir.glob("ai_threads_*.json"))

    state_path.write_text("{not-json", encoding="utf-8")

    recovered = AIManager(tmp_path)
    hist = recovered.history(skey)
    assert len(hist) >= 2


def test_ai_state_backup_rotation_prunes_old_files(tmp_path: Path) -> None:
    ai = AIManager(tmp_path)
    ai.max_state_backups = 2
    skey = "user:rotation"

    for i in range(8):
        ai._append(skey, "user", f"m{i}")

    backups_dir = tmp_path / "app" / "bridge" / "ai_threads_backups"
    files = sorted(backups_dir.glob("ai_threads_*.json"))
    assert len(files) <= 2


def test_ai_state_atomic_write_has_single_primary_file(tmp_path: Path) -> None:
    ai = AIManager(tmp_path)
    skey = "user:atomic"
    ai._append(skey, "user", "one")
    ai._append(skey, "assistant", "two")

    state_path = tmp_path / "app" / "bridge" / "ai_threads.json"
    tmp_path_file = tmp_path / "app" / "bridge" / "ai_threads.tmp"

    assert state_path.exists()
    assert not tmp_path_file.exists()
