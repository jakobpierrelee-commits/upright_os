#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TEMPLATE_DIR = ROOT / "app" / "bridge" / "firmware_templates" / "profiled_runtime_v1"


def _load_json(path: Path) -> dict[str, Any]:
    node = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(node, dict):
        raise RuntimeError(f"{path} must contain a JSON object")
    return node


def _sanitize_release(node: dict[str, Any]) -> dict[str, str]:
    runtime_version = str(node.get("runtime_version", "")).strip()
    tune_version = str(node.get("tune_version", "")).strip()
    version_policy = str(node.get("version_policy", "")).strip()
    if not runtime_version:
        raise RuntimeError("release.json missing runtime_version")
    if not tune_version:
        raise RuntimeError("release.json missing tune_version")
    if not version_policy:
        raise RuntimeError("release.json missing version_policy")
    return {
        "runtime_version": runtime_version,
        "tune_version": tune_version,
        "version_policy": version_policy,
    }


def _render_header(release: dict[str, str], *, source_rel: str) -> str:
    return (
        "#pragma once\n\n"
        "/*\n"
        "  Generated from release.json.\n"
        "  Source of truth:\n"
        f"  {source_rel}\n"
        "*/\n\n"
        "#ifndef UPRIGHT_RUNTIME_VERSION\n"
        f"#define UPRIGHT_RUNTIME_VERSION \"{release['runtime_version']}\"\n"
        "#endif\n\n"
        "#ifndef UPRIGHT_TUNE_VERSION\n"
        f"#define UPRIGHT_TUNE_VERSION \"{release['tune_version']}\"\n"
        "#endif\n"
    )


def _sync_manifest(manifest: dict[str, Any], release: dict[str, str]) -> dict[str, Any]:
    out = dict(manifest)
    out["release"] = {
        "runtime_version": release["runtime_version"],
        "tune_version": release["tune_version"],
        "version_policy": release["version_policy"],
    }
    telemetry = list(out.get("telemetry_fields") or [])
    for field in ("runtime", "tune"):
        if field not in telemetry:
            telemetry.append(field)
    out["telemetry_fields"] = telemetry
    return out


def _write_if_changed(path: Path, new_text: str) -> bool:
    old_text = path.read_text(encoding="utf-8") if path.exists() else ""
    if old_text == new_text:
        return False
    path.write_text(new_text, encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sync profiled runtime release metadata into header + manifest."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if generated files are out of sync with release.json.",
    )
    parser.add_argument(
        "--template-dir",
        default=str(DEFAULT_TEMPLATE_DIR),
        help="Firmware template directory containing release.json/release_version.h/runtime_manifest_v1.json",
    )
    args = parser.parse_args()

    template_dir = Path(args.template_dir).expanduser()
    if not template_dir.is_absolute():
        template_dir = (ROOT / template_dir).resolve()
    release_path = template_dir / "release.json"
    header_path = template_dir / "release_version.h"
    manifest_path = template_dir / "runtime_manifest_v1.json"

    if not release_path.exists():
        raise RuntimeError(f"missing release file: {release_path}")
    if not manifest_path.exists():
        raise RuntimeError(f"missing manifest file: {manifest_path}")

    source_rel = str(release_path.relative_to(ROOT)).replace("\\", "/")

    release = _sanitize_release(_load_json(release_path))
    expected_header = _render_header(release, source_rel=source_rel)
    header_current = header_path.read_text(encoding="utf-8") if header_path.exists() else ""
    header_diff = header_current != expected_header

    manifest_current = _load_json(manifest_path)
    manifest_expected = _sync_manifest(manifest_current, release)
    expected_manifest_text = json.dumps(manifest_expected, indent=2) + "\n"
    manifest_current_text = manifest_path.read_text(encoding="utf-8")
    manifest_diff = manifest_current_text != expected_manifest_text

    if args.check:
        if header_diff or manifest_diff:
            print("[sync_release_metadata] OUT OF SYNC")
            if header_diff:
                print(f"- header mismatch: {header_path}")
            if manifest_diff:
                print(f"- manifest mismatch: {manifest_path}")
            print("Run: python3 tools/lean/sync_release_metadata.py")
            return 1
        print("[sync_release_metadata] PASS (in sync)")
        return 0

    changed_header = _write_if_changed(header_path, expected_header)
    changed_manifest = _write_if_changed(manifest_path, expected_manifest_text)
    print("[sync_release_metadata] release source:", release_path)
    print(
        "[sync_release_metadata] updated:",
        f"header={'yes' if changed_header else 'no'}",
        f"manifest={'yes' if changed_manifest else 'no'}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
