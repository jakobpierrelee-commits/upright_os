import pathlib
import sys

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from clean_probe import (
    build_compat_probe_payload,
    build_design_memory_best_payload,
    build_design_memory_payload,
    build_probe_payload,
    build_tooling_traces_payload,
    build_tuning_capabilities_payload,
)


def test_build_probe_payload_shape() -> None:
    payload = build_probe_payload(
        probe={"ok": True, "connected": True, "confidence_pct": 85}
    )
    assert payload["ok"] is True
    assert payload["probe"]["connected"] is True
    assert payload["probe"]["confidence_pct"] == 85


def test_build_compat_probe_payload_shape() -> None:
    payload = build_compat_probe_payload(
        compat={"ok": True, "profile": "balance_v1", "missing_fields": []}
    )
    assert payload["ok"] is True
    assert payload["compat"]["profile"] == "balance_v1"


def test_build_design_memory_payload_shape() -> None:
    payload = build_design_memory_payload(
        design_memory=[{"id": "d1", "success": True}, {"id": "d2", "success": False}]
    )
    assert payload["ok"] is True
    assert len(payload["design_memory"]) == 2


def test_build_design_memory_best_payload_shape() -> None:
    payload = build_design_memory_best_payload(
        best_design={"id": "d1", "success": True, "score": 0.95}
    )
    assert payload["ok"] is True
    assert payload["best_design"]["score"] == 0.95


def test_build_design_memory_best_payload_none() -> None:
    payload = build_design_memory_best_payload(best_design=None)
    assert payload["ok"] is True
    assert payload["best_design"] is None


def test_build_tooling_traces_payload_shape() -> None:
    payload = build_tooling_traces_payload(
        traces=[{"path": "/logs/a.jsonl"}, {"path": "/logs/b.jsonl"}]
    )
    assert payload["ok"] is True
    assert len(payload["traces"]) == 2


def test_build_tuning_capabilities_payload_shape() -> None:
    payload = build_tuning_capabilities_payload(
        capabilities={"pid_tuning": True, "kalman_tuning": False}
    )
    assert payload["ok"] is True
    assert payload["tuning_capabilities"]["pid_tuning"] is True
